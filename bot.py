# bot.py
import os
import datetime
from datetime import timezone
from collections import defaultdict
import threading
from dotenv import load_dotenv
import telebot
from telebot import types
import db
import handlers
import admin
import utils
from uuid import uuid4

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not found in .env")

db.init_db()
if not db.get_all_series():
    db.dump_sample_data()

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

album_storage = defaultdict(list)
album_timers = {}

def get_menu_button():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(types.KeyboardButton("Главное меню"))
    return markup

@bot.message_handler(commands=["start"])
def on_start(message):
    handlers.handle_start(message, bot)
    bot.send_message(message.chat.id, "Используйте кнопку ниже:", reply_markup=get_menu_button())

@bot.message_handler(commands=["add"])
def cmd_add(message):
    handlers.cmd_add_series(message, bot)

@bot.callback_query_handler(func=lambda call: True)
def on_callback(call):
    try:
        data = call.data or ""
        chat_id = call.message.chat.id
        
        # Навигация
        if data.startswith("list_series:"):
            handlers.callback_list_series(call, bot, int(data.split(":")[1]))
        elif data == "main_menu":
            handlers.send_main(chat_id, bot)
        elif data.startswith("series:"):
            handlers.callback_series(call, bot, int(data.split(":")[1]))
        elif data.startswith("season:"):
            handlers.callback_season(call, bot, int(data.split(":")[1]))
        elif data.startswith("episode:"):
            handlers.callback_episode(call, bot, int(data.split(":")[1]))
        
        # Админка
        elif data == "add_menu":
            bot.answer_callback_query(call.id, "Команды: /add")
            bot.send_message(chat_id, "Используйте /add для добавления сериала")
        elif data.startswith("add_season:"):
            handlers.cmd_add_season(call, bot, int(data.split(":")[1]))
        elif data.startswith("add_episode:"):
            handlers.cmd_add_episode(call, bot, int(data.split(":")[1]))
            
        # Редактирование
        elif data == "edit_menu":
            handlers.callback_edit_menu(call, bot)
        elif data.startswith("edit_series:"):
            handlers.callback_edit_series(call, bot, int(data.split(":")[1]))
        elif data.startswith("edit_season:"):
            handlers.callback_edit_season(call, bot, int(data.split(":")[1]))
        elif data.startswith("edit_episode:"):
            handlers.callback_edit_episode(call, bot, int(data.split(":")[1]))
        elif data.startswith("delete_series:"):
            handlers.callback_delete_series(call, bot, int(data.split(":")[1]))
        elif data.startswith("delete_season:"):
            handlers.callback_delete_season(call, bot, int(data.split(":")[1]))
        elif data.startswith("delete_episode:"):
            handlers.callback_delete_episode(call, bot, int(data.split(":")[1]))
        elif data.startswith("update_series_title:"):
            handlers.cmd_update_series_title(call, bot, int(data.split(":")[1]))
        elif data.startswith("update_season_number:"):
            handlers.cmd_update_season_number(call, bot, int(data.split(":")[1]))
        elif data.startswith("update_episode_number:"):
            handlers.cmd_update_episode_number(call, bot, int(data.split(":")[1]))
        elif data.startswith("update_episode_title:"):
            handlers.cmd_update_episode_title(call, bot, int(data.split(":")[1]))
        elif data.startswith("update_episode_file:"):
            handlers.cmd_update_episode_file(call, bot, int(data.split(":")[1]))

        # Просмотр и избранное
        elif data == "continue_watch":
            handlers.callback_continue_watch(call, bot)
        elif data == "favorites":
            handlers.callback_favorites(call, bot)
        elif data.startswith("favorite_add:"):
            parts = data.split(":")
            handlers.add_to_favorite(call, bot, parts[1], int(parts[2]))
        elif data.startswith("favorite_remove:"):
            parts = data.split(":")
            handlers.remove_from_favorite(call, bot, parts[1], int(parts[2]))

        # Smart add
        elif data.startswith("smart_add_to_series:"):
            parts = data.split(":")
            handlers.process_smart_add_episode(call, bot, int(parts[1]), parts[2] if len(parts) > 2 else None)

        else:
            bot.answer_callback_query(call.id, "Неизвестно")

    except Exception as e:
        utils.logger.exception("Callback Error")
        try: bot.answer_callback_query(call.id, "Ошибка")
        except: pass

@bot.message_handler(content_types=['text'])
def catch_all_text(message):
    text = message.text.strip()
    
    if text in ["Меню", "Главное меню"]:
        handlers.send_main(message.chat.id, bot)
        return

    # Обработка обновления файла
    pending = utils.get_pending(message.chat.id)
    if pending and pending.get("action") == "update_episode_file":
         bot.reply_to(message, "Пришлите файл, а не текст.")
         return

    if text.lower() == "/backup" and admin.is_admin(message.from_user.id):
        path = f"backup_{int(datetime.datetime.now().timestamp())}.db"
        db.export_db(path)
        with open(path, "rb") as f:
            bot.send_document(message.chat.id, f)
        os.remove(path)
        return

def auto_detect_series(file_name: str, parsed: Dict):
    if 'series_title' in parsed and parsed['series_title']:
        search_title = parsed['series_title'].lower()
        for series in db.get_all_series():
            s_title = series['title'].lower()
            if search_title == s_title or search_title in s_title or s_title in search_title:
                return series['id']
    # Fallback на старый метод
    clean = re.sub(r'[^a-zA-Zа-яА-Я0-9]', ' ', file_name)
    words = clean.lower().split()
    important = [w for w in words[:6] if len(w) > 3 and w not in ['1080p', '720p', 'web', 'dl', 'h264', 'x264', 'season', 'episode', 'mkv', 'mp4', 'avi', 'сезон', 'серия']]
    if not important: return None
    for series in db.get_all_series():
        s_words = re.sub(r'[^a-zA-Zа-яА-Я0-9]', ' ', series['title'].lower()).split()
        if any(w in s_words for w in important):
            return series['id']
    return None

def collect_album_file(message):
    media_group_id = message.media_group_id
    file_info = message.document or message.video
    if not file_info: return
    file_name = getattr(file_info, 'file_name', 'unknown.mkv')
    parsed = utils.parse_file_name(file_name)
    item = {
        "file_info": file_info,
        "file_name": file_name,
        "parsed": parsed,
        "chat_id": message.chat.id,
        "user_id": message.from_user.id
    }
    album_storage[media_group_id].append(item)
    if media_group_id in album_timers: album_timers[media_group_id].cancel()
    timer = threading.Timer(4.0, finalize_album, args=[media_group_id])
    album_timers[media_group_id] = timer
    timer.start()

def finalize_album(media_group_id):
    if media_group_id not in album_storage: return
    files = album_storage.pop(media_group_id)
    album_timers.pop(media_group_id, None)
    chat_id = files[0]["chat_id"]
    if not admin.is_admin(files[0]["user_id"]): return
    
    auto_added = 0
    for f in files:
        if not f["parsed"]: continue
        guessed = auto_detect_series(f["file_name", f["parsed"]])
        unique_key = str(uuid4())
        utils.set_pending(chat_id, {
            "action": "smart_add_episode",
            "parsed": f["parsed"],
            "file_id": f["file_info"].file_id,
            "file_unique_id": f["file_info"].file_unique_id,
            "file_name": f["file_name"],
            "file_size": f["file_info"].file_size,
            "uploaded_at": datetime.datetime.now(timezone.utc)
        }, key=unique_key)
        
        if guessed:
            handlers.process_smart_add_episode_direct(chat_id, bot, guessed, unique_key)
            auto_added += 1
        else:
            bot.send_message(chat_id, f"Файл: {f['file_name']}\nВыберите:", 
                             reply_markup=handlers.get_series_keyboard(unique_key))
    
    if auto_added > 0:
        bot.send_message(chat_id, f"Авто-добавлено: {auto_added}")

def process_single_file(message):
    if not admin.is_admin(message.from_user.id): return
    file_info = message.document or message.video
    if not file_info: return
    file_name = getattr(file_info, 'file_name', 'video.mp4')
    parsed = utils.parse_file_name(file_name)
    
    pending = utils.get_pending(message.chat.id)
    if pending and pending.get("action") == "update_episode_file":
        handlers.process_add_episode_file(message, bot) # Исправил вызов функции
        return
    
    if not parsed:
        bot.reply_to(message, "Не распознано.")
        return
        
    guessed = filauto_detect_series(file_name, parsed)
    unique_key = str(uuid4())
    utils.set_pending(message.chat.id, {
        "action": "smart_add_episode",
        "parsed": parsed,
        "file_id": file_info.file_id,
        "file_unique_id": file_info.file_unique_id,
        "file_name": file_name,
        "file_size": file_info.file_size,
        "uploaded_at": datetime.datetime.now(timezone.utc)
    }, key=unique_key)
    
    if guessed:
        handlers.process_smart_add_episode_direct(message.chat.id, bot, guessed, unique_key)
        bot.reply_to(message, "Добавлено!")
    else:
        bot.reply_to(message, f"Файл: {file_name}\nВыберите сериал:", 
                     reply_markup=handlers.get_series_keyboard(unique_key))

@bot.message_handler(content_types=['document', 'video'])
def handle_media(message):
    if message.media_group_id:
        collect_album_file(message)
    else:
        process_single_file(message)

if __name__ == "__main__":
    print("Bot started...")
    bot.infinity_polling()