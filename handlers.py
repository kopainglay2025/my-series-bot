import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import db
import admin
import utils
import datetime
import math

PAGE_SIZE = 8

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def clean_chat(chat_id: int, bot: telebot.TeleBot):
    """Удаляет старые сообщения бота (меню, навигацию), видео не трогаем"""
    last_msg_id = utils.get_last_bot_msg(chat_id)
    if last_msg_id:
        try: bot.delete_message(chat_id, last_msg_id)
        except: pass

def send_main(chat_id: int, bot: telebot.TeleBot, reply_markup=None):
    clean_chat(chat_id, bot)
    msg = bot.send_message(
        chat_id,
        "🏠 <b>Главное меню</b>\nВыберите раздел:",
        reply_markup=build_main_menu(),
        parse_mode="HTML"
    )
    utils.set_last_bot_msg(chat_id, msg.message_id)

def build_main_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    # Быстрые действия в первом ряду
    markup.row(
        InlineKeyboardButton("📂 Архив сериалов", callback_data="list_series:0"),
        InlineKeyboardButton("⏯ Продолжить", callback_data="continue_watch"),
    )
    # Второй ряд — избранное
    markup.row(InlineKeyboardButton("⭐ Избранное", callback_data="favorites"))
    # Третий ряд — админка
    markup.row(
        InlineKeyboardButton("➕ Добавить (админ)", callback_data="add_menu"), 
        InlineKeyboardButton("✏️ Редактировать (админ)", callback_data="edit_menu")
    )
    return markup

def handle_start(message, bot: telebot.TeleBot):
    send_main(message.chat.id, bot)

# --- СПИСКИ И ПРОСМОТР ---

def callback_list_series(call, bot: telebot.TeleBot, page: int = 0):
    chat_id = call.message.chat.id
    series = db.get_all_series()
    start = page * PAGE_SIZE
    page_items = series[start:start+PAGE_SIZE]
    markup = InlineKeyboardMarkup()
    
    # Полное название сериала, по 1 в строку
    for s in page_items:
        markup.add(InlineKeyboardButton(f"{s['title']}", callback_data=f"series:{s['id']}"))
    
    nav = []
    if start > 0:
        nav.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"list_series:{page-1}"))
    if start + PAGE_SIZE < len(series):
        nav.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"list_series:{page+1}"))
    if nav:
        markup.row(*nav)
    
    markup.row(InlineKeyboardButton("Главное меню", callback_data="main_menu"))
    
    try:
        bot.edit_message_text("📂 <b>Список сериалов</b>", chat_id, call.message.message_id, reply_markup=markup, parse_mode="HTML")
        utils.set_last_bot_msg(chat_id, call.message.message_id)
    except:
        send_main(chat_id, bot)

def callback_series(call, bot: telebot.TeleBot, series_id: int):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    series_info = db.get_series(series_id)
    seasons = db.get_seasons(series_id)
    markup = InlineKeyboardMarkup()
    
    if not seasons:
        markup.add(InlineKeyboardButton("➕ Добавить сезон (админ)", callback_data=f"add_season:{series_id}"))
    else:
        # Сезоны по 2 в ряд
        row = []
        for s in seasons:
            row.append(InlineKeyboardButton(f"Сезон {s['number']}", callback_data=f"season:{s['id']}"))
            if len(row) == 2:
                markup.row(*row)
                row = []
        if row:
            markup.row(*row)
    
    is_fav = db.is_favorite(user_id, 'series', series_id)
    fav_text = "❌ Удалить из избранного" if is_fav else "⭐ В избранное"
    markup.row(InlineKeyboardButton(fav_text, callback_data=f"favorite_{'remove' if is_fav else 'add'}:series:{series_id}"))
    
    if seasons:
        markup.row(InlineKeyboardButton("➕ Добавить сезон (админ)", callback_data=f"add_season:{series_id}"))
    
    markup.row(InlineKeyboardButton("⬅️ К списку", callback_data="list_series:0"), 
               InlineKeyboardButton("Главное меню", callback_data="main_menu"))
    
    title = series_info["title"] if series_info else "Сериал"
    poster_id = series_info["poster_file_id"] if series_info else None
    description = (series_info["description"] or "").strip() if series_info else ""
    if not description:
        fetched_desc = utils.fetch_tmdb_description(title)
        if fetched_desc:
            description = fetched_desc
            db.update_series(series_id, description=description)

    # Форматируем описание в свёрнутую цитату (spoiler)
    desc_for_caption = ""
    if description:
        # Обрезаем если слишком длинное
        desc_text = description[:800] + "..." if len(description) > 800 else description
        # Оборачиваем в spoiler для экономии места
        desc_for_caption = f"\n\n<b>Описание:</b>\n<tg-spoiler>{desc_text}</tg-spoiler>"

    # Если есть постер — отправляем одну карточку с клавиатурой
    if poster_id:
        try:
            try: bot.delete_message(chat_id, call.message.message_id)
            except: pass
            msg = bot.send_photo(
                chat_id,
                poster_id,
                caption=f"📺 <b>{title}</b>{desc_for_caption}\n\nВыберите сезон:",
                reply_markup=markup,
                parse_mode="HTML"
            )
            utils.set_last_bot_msg(chat_id, msg.message_id)
            return
        except Exception as e:
            utils.logger.warning(f"Poster send failed: {e}")

    # Фолбэк без постера — редактируем текст
    try:
        extra = desc_for_caption if desc_for_caption else ""
        bot.edit_message_text(f"📺 <b>{title}</b>{extra}\n\nВыберите сезон:", chat_id, call.message.message_id, reply_markup=markup, parse_mode="HTML")
        utils.set_last_bot_msg(chat_id, call.message.message_id)
    except:
        msg = bot.send_message(chat_id, f"📺 <b>{title}</b>{extra}\n\nВыберите сезон:", reply_markup=markup, parse_mode="HTML")
        utils.set_last_bot_msg(chat_id, msg.message_id)

def callback_season(call, bot: telebot.TeleBot, season_id: int):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    season = db.get_season(season_id)
    series_info = db.get_series(season['series_id']) if season else None
    episodes = db.get_episodes(season_id)
    markup = InlineKeyboardMarkup()
    
    if not episodes:
        markup.add(InlineKeyboardButton("➕ Добавить эпизод (админ)", callback_data=f"add_episode:{season_id}"))
    else:
         # Если серий больше 15 — показываем в несколько столбцов
        if len(episodes) > 15:
            # Определяем количество столбцов
            cols = 2
            if len(episodes) > 40:
                cols = 3
                
            # Сортируем по номеру (episodes уже должны быть отсортированы, но для надежности)
            episodes_sorted = sorted(episodes, key=lambda x: x['number'])
            
            # Вычисляем количество строк
            rows = math.ceil(len(episodes_sorted) / cols)
            
            grid = [[] for _ in range(rows)]
            
            for i, e in enumerate(episodes_sorted):
                # Заполняем по столбцам: сначала весь первый столбец, потом второй и т.д.
                # Индекс строки = i % rows
                row_idx = i % rows
                
                # Формируем текст кнопки (компактный)
                title = e['title']
                b_text = f"{e['number']}"
                if title:
                    # Обрезаем название, если длинное
                    trunc_len = 12 if cols == 3 else 18
                    if len(title) > trunc_len:
                        title = title[:trunc_len] + "..."
                    b_text += f". {title}"
                
                btn = InlineKeyboardButton(b_text, callback_data=f"episode:{e['id']}")
                grid[row_idx].append(btn)
                
            for row_buttons in grid:
                markup.row(*row_buttons)
        else:
            # Стандартный список (1 столбец)
            for e in episodes:
                title = e['title'] if e['title'] else ""
                button_text = f"Серия {e['number']} - {title}".strip(" - ")
                markup.add(InlineKeyboardButton(button_text, callback_data=f"episode:{e['id']}"))
            
    is_fav = db.is_favorite(user_id, 'season', season_id)
    fav_text = "❌ Удалить из избранного" if is_fav else "⭐ В избранное"
    markup.row(InlineKeyboardButton(fav_text, callback_data=f"favorite_{'remove' if is_fav else 'add'}:season:{season_id}"))
    
    if episodes:
        markup.row(InlineKeyboardButton("➕ Добавить эпизод (админ)", callback_data=f"add_episode:{season_id}"))
        
    markup.row(InlineKeyboardButton("⬅️ К сериалу", callback_data=f"series:{season['series_id']}"), 
               InlineKeyboardButton("Главное меню", callback_data="main_menu"))
    
    try:
        series_title = series_info["title"] if series_info else "Сериал"
        bot.edit_message_text(f"🎞️ <b>{series_title}</b>\nСезон {season['number']} — выберите эпизод:", chat_id, call.message.message_id, reply_markup=markup, parse_mode="HTML")
        utils.set_last_bot_msg(chat_id, call.message.message_id)
    except:
        msg = bot.send_message(chat_id, f"🎞️ <b>{series_title}</b>\nСезон {season['number']} — выберите эпизод:", reply_markup=markup, parse_mode="HTML")
        utils.set_last_bot_msg(chat_id, msg.message_id)

def callback_episode(call, bot: telebot.TeleBot, episode_id: int):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    episode = db.get_episode(episode_id)
    
    if not episode:
        bot.answer_callback_query(call.id, "⚠️ Эпизод не найден")
        return

    season = db.get_season(episode['season_id'])
    series = db.get_series(season['series_id'])
    ep_title = episode['title'] or "Без названия"
    
    # Красивая полная подпись
    caption = f"🎬 <b>{series['title']}</b>\nСезон {season['number']} • Серия {episode['number']} — {ep_title}"

    # Удаляем меню списка серий, чтобы не копились
    try:
        bot.delete_message(chat_id, call.message.message_id)
    except: pass

    if episode["file_id"]:
        try:
            sent = bot.send_video(
                chat_id,
                episode["file_id"],
                caption=caption,
                parse_mode="HTML",
                supports_streaming=True,
                timeout=120
            )
            utils.set_last_video_msg(chat_id, sent.message_id)
            db.mark_episode_watched(user_id, episode_id)
        except Exception as e:
            bot.send_message(chat_id, f"⚠️ Ошибка видео: {e}")
    else:
        bot.send_message(chat_id, "⚠️ Файл отсутствует")

    markup = InlineKeyboardMarkup()
    prev_ep = db.get_previous_episode(season['id'], episode['number'])
    next_ep = db.get_next_episode(season['id'], episode['number'])
    
    nav = []
    if prev_ep:
        nav.append(InlineKeyboardButton("⬅️ Предыдущая", callback_data=f"episode:{prev_ep['id']}"))
    
    if next_ep:
        nav.append(InlineKeyboardButton("Следующая ➡️", callback_data=f"episode:{next_ep['id']}"))
    else:
        next_season = db.get_next_season(series['id'], season['number'])
        if next_season:
            first_ep_next = db.get_episodes(next_season['id'])
            if first_ep_next:
                nav.append(InlineKeyboardButton("След. сезон ➡️", callback_data=f"episode:{first_ep_next[0]['id']}"))

    if nav:
        markup.row(*nav)

    is_fav = db.is_favorite(user_id, 'episode', episode_id)
    fav_text = "❌ Избранное" if is_fav else "⭐ Избранное"
    markup.row(InlineKeyboardButton(fav_text, callback_data=f"favorite_{'remove' if is_fav else 'add'}:episode:{episode_id}"))
    
    markup.row(InlineKeyboardButton("⬅️ К сезону", callback_data=f"season:{season['id']}"),
               InlineKeyboardButton("Главное меню", callback_data="main_menu"))
    
    nav_msg = bot.send_message(chat_id, "<b>Навигация по эпизоду</b>:", reply_markup=markup, parse_mode="HTML")
    utils.set_last_bot_msg(chat_id, nav_msg.message_id)

def callback_episode_range(call, bot: telebot.TeleBot, season_id: int, start: int, end: int):
    chat_id = call.message.chat.id
    episodes = [e for e in db.get_episodes(season_id) if start <= e['number'] <= end]
    markup = InlineKeyboardMarkup()
    for e in episodes:
        title = e['title'] if e['title'] else ""
        button_text = f"Серия {e['number']} - {title}".strip(" - ")
        markup.add(InlineKeyboardButton(button_text, callback_data=f"episode:{e['id']}"))

    markup.row(InlineKeyboardButton("⬅️ К сезонам", callback_data=f"season:{season_id}"),
               InlineKeyboardButton("Главное меню", callback_data="main_menu"))

    try:
        bot.edit_message_text(f"Серии {start}–{end}:", chat_id, call.message.message_id, reply_markup=markup)
        utils.set_last_bot_msg(chat_id, call.message.message_id)
    except:
        msg = bot.send_message(chat_id, f"Серии {start}–{end}:", reply_markup=markup)
        utils.set_last_bot_msg(chat_id, msg.message_id)

# --- ПРОСМОТР И ИЗБРАННОЕ ---

def callback_continue_watch(call, bot: telebot.TeleBot):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    
    # Получаем историю
    watch_data = db.get_continue_watching_data(user_id, limit=5)
    
    markup = InlineKeyboardMarkup()
    text = "📜 <b>История просмотра</b>\n"
    
    if not watch_data:
        unwatched = db.get_unwatched_episodes(user_id, limit=3)
        if unwatched:
            text = "<b>Вы ещё ничего не смотрели.</b>\nВот новинки:"
            for u in unwatched:
                # Полный текст для новинок
                text_button = f"🆕 {u['series_title']} — Сезон {u['season_number']} Серия {u['number']}"
                markup.add(InlineKeyboardButton(text_button, callback_data=f"episode:{u['id']}"))
        else:
            text = "Список просмотра пуст."
    else:
        for data in watch_data:
            # 1. Заголовок - Название сериала (переход к сезонам этого сериала)
            series_id = data['series_id']
            series_title = data['series_title']
            markup.row(InlineKeyboardButton(f"📺 {series_title}", callback_data=f"series:{series_id}"))
            
            # 2. Две кнопки в одной строке: Закончили тут | Следующий
            row_buttons = []
            
            # Кнопка остановки
            last_text = f"✅ S{data['last_ep_s']}E{data['last_ep_e']} (Закончили тут)"
            row_buttons.append(InlineKeyboardButton(last_text, callback_data=f"episode:{data['last_ep_id']}"))

            # Кнопка следующего
            if data['next_ep_data']:
                next_d = data['next_ep_data']
                next_text = f"➡️ S{next_d['season_number']}E{next_d['number']} (След.)"
                row_buttons.append(InlineKeyboardButton(next_text, callback_data=f"episode:{next_d['id']}"))
            
            markup.row(*row_buttons)
            
            if not data['next_ep_data']:
                markup.row(InlineKeyboardButton("✨ Полностью досмотрен", callback_data="continue_watch"))

            # Метаданные с форматированием даты
            if data.get("last_watched_at"):
                formatted_date = utils.format_watch_date(str(data['last_watched_at']))
                text += f"• <b>{series_title}</b> — <b>Дата и время:</b> {formatted_date}\n"

    markup.row(InlineKeyboardButton("Главное меню", callback_data="main_menu"))
    
    try:
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup, parse_mode="HTML")
        utils.set_last_bot_msg(chat_id, call.message.message_id)
    except:
        utils.clean_chat(chat_id, bot)
        msg = bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")
        utils.set_last_bot_msg(chat_id, msg.message_id)

def add_to_favorite(call, bot: telebot.TeleBot, item_type: str, item_id: int):
    db.add_favorite(call.from_user.id, item_type, item_id)
    bot.answer_callback_query(call.id, "✅ Добавлено")
    if item_type == 'series': callback_series(call, bot, item_id)
    elif item_type == 'season': callback_season(call, bot, item_id)
    elif item_type == 'episode': callback_episode(call, bot, item_id)

def remove_from_favorite(call, bot: telebot.TeleBot, item_type: str, item_id: int):
    db.remove_favorite(call.from_user.id, item_type, item_id)
    bot.answer_callback_query(call.id, "🗑️ Удалено")
    if item_type == 'series': callback_series(call, bot, item_id)
    elif item_type == 'season': callback_season(call, bot, item_id)
    elif item_type == 'episode': callback_episode(call, bot, item_id)

def callback_favorites(call, bot: telebot.TeleBot):
    user_id = call.from_user.id
    favorites = db.get_favorites(user_id)
    markup = InlineKeyboardMarkup()
    if not favorites:
        markup.add(InlineKeyboardButton("Список пуст", callback_data="main_menu"))
    else:
        for f in favorites:
            meta_text = ""
            if f['item_type'] == 'series':
                s = db.get_series(f['item_id'])
                if s:
                    last_dt = db.get_last_watched_at_for_series(user_id, f['item_id'])
                    if last_dt: meta_text = f" • последнее: {last_dt}"
                    markup.add(InlineKeyboardButton(f"📺 {s['title']}{meta_text}", callback_data=f"series:{f['item_id']}"))
            elif f['item_type'] == 'season':
                s = db.get_season(f['item_id'])
                if s:
                    ser = db.get_series(s['series_id'])
                    last_dt = db.get_last_watched_at_for_season(user_id, f['item_id'])
                    if last_dt: meta_text = f" • последнее: {last_dt}"
                    markup.add(InlineKeyboardButton(f"💿 {ser['title']} — Сезон {s['number']}{meta_text}", callback_data=f"season:{f['item_id']}"))
            elif f['item_type'] == 'episode':
                e = db.get_episode(f['item_id'])
                if e:
                    s = db.get_season(e['season_id'])
                    ser = db.get_series(s['series_id'])
                    last_dt = db.get_last_watched_at_for_episode(user_id, f['item_id'])
                    if last_dt: meta_text = f" • просмотрено: {last_dt}"
                    else:
                        watched = db.is_episode_watched(user_id, f['item_id'])
                        meta_text = " • не смотрели" if not watched else ""
                    markup.add(InlineKeyboardButton(f"🎬 {ser['title']} — Сезон {s['number']} Серия {e['number']}{meta_text}", callback_data=f"episode:{f['item_id']}"))
    markup.row(InlineKeyboardButton("Главное меню", callback_data="main_menu"))
    bot.edit_message_text("⭐ <b>Избранное</b>\n— — —", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="HTML")
    utils.set_last_bot_msg(call.message.chat.id, call.message.message_id)

# --- АДМИНКА ---
def cmd_add_series(message, bot: telebot.TeleBot):
    if not admin.is_admin(message.from_user.id): return
    msg = bot.reply_to(message, "Введите название сериала:")
    bot.register_next_step_handler(msg, lambda m: process_add_series(m, bot))

def process_add_series(message, bot: telebot.TeleBot):
    title = message.text.strip()
    if not title: return
    db.add_series(title)
    send_main(message.chat.id, bot)

def cmd_add_season(call, bot: telebot.TeleBot, series_id: int):
    if not admin.is_admin(call.from_user.id): return
    try: bot.delete_message(call.message.chat.id, call.message.message_id)
    except: pass
    msg = bot.send_message(call.message.chat.id, "Номер сезона:")
    bot.register_next_step_handler(msg, lambda m: process_add_season(m, bot, series_id))

def process_add_season(message, bot, series_id):
    try: number = int(message.text.strip())
    except: return
    db.add_season(series_id, number)
    send_main(message.chat.id, bot)

def cmd_add_episode(call, bot: telebot.TeleBot, season_id: int):
    if not admin.is_admin(call.from_user.id): return
    utils.set_pending(call.message.chat.id, {"action": "add_episode", "season_id": season_id})
    try: bot.delete_message(call.message.chat.id, call.message.message_id)
    except: pass
    bot.send_message(call.message.chat.id, "Отправьте файл:")

def callback_edit_menu(call, bot: telebot.TeleBot):
    chat_id = call.message.chat.id
    series = db.get_all_series()
    markup = InlineKeyboardMarkup()
    for s in series:
        markup.add(InlineKeyboardButton(f"{s['title']}", callback_data=f"edit_series:{s['id']}"))
    markup.row(InlineKeyboardButton("Главное меню", callback_data="main_menu"))
    bot.edit_message_text("Редактирование:", chat_id, call.message.message_id, reply_markup=markup)

def callback_edit_series(call, bot: telebot.TeleBot, series_id: int):
    chat_id = call.message.chat.id
    seasons = db.get_seasons(series_id)
    markup = InlineKeyboardMarkup()
    for s in seasons:
        markup.add(InlineKeyboardButton(f"Сезон {s['number']}", callback_data=f"edit_season:{s['id']}"))
    markup.row(InlineKeyboardButton("✏️ Название", callback_data=f"update_series_title:{series_id}"),
               InlineKeyboardButton("📝 Описание", callback_data=f"update_series_description:{series_id}"))
    markup.row(InlineKeyboardButton("🖼 Постер", callback_data=f"update_series_poster:{series_id}"),
               InlineKeyboardButton("🗑 Постер", callback_data=f"delete_series_poster:{series_id}"))
    markup.row(InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_series:{series_id}"))
    markup.row(InlineKeyboardButton("Назад", callback_data="edit_menu"))
    bot.edit_message_text("Ред. сериала:", chat_id, call.message.message_id, reply_markup=markup)

def callback_edit_season(call, bot: telebot.TeleBot, season_id: int):
    chat_id = call.message.chat.id
    episodes = db.get_episodes(season_id)
    markup = InlineKeyboardMarkup()
    for e in episodes:
        # ИЗМЕНЕНО: Добавляем название эпизода, если оно есть.
        title_text = e['title'] if e['title'] else ""
        button_text = f"Серия {e['number']}"
        if title_text:
            button_text += f" — {title_text}"
        markup.add(InlineKeyboardButton(button_text, callback_data=f"edit_episode:{e['id']}")) 
    markup.row(InlineKeyboardButton("✏️ № Сезона", callback_data=f"update_season_num:{season_id}"),
               InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_season:{season_id}"))
    markup.row(InlineKeyboardButton("Назад", callback_data=f"edit_series:{db.get_season(season_id)['series_id']}"))
    bot.edit_message_text("Ред. сезона:", chat_id, call.message.message_id, reply_markup=markup)

def callback_edit_episode(call, bot: telebot.TeleBot, episode_id: int):
    chat_id = call.message.chat.id
    episode = db.get_episode(episode_id)
    if not episode: return
    
    markup = InlineKeyboardMarkup()
    # ИЗМЕНЕНО: Используем 'update_ep_num' и 'update_ep_title'
    markup.row(InlineKeyboardButton("✏️ Номер", callback_data=f"update_ep_num:{episode_id}"),
               InlineKeyboardButton("✏️ Название", callback_data=f"update_ep_title:{episode_id}"))
    
    # ... (Остальные кнопки без изменений)
    markup.row(InlineKeyboardButton("📁 Файл", callback_data=f"update_episode_file:{episode_id}"),
               InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_episode:{episode_id}"))
    markup.row(InlineKeyboardButton("Назад", callback_data=f"edit_season:{episode['season_id']}"))
    
    title_text = episode['title'] or "Без названия"
    text = f"Ред. Серия {episode['number']}: <b>{title_text}</b>"
    
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup, parse_mode="HTML")

def callback_delete_series(call, bot: telebot.TeleBot, series_id: int):
    db.delete_series(series_id)
    bot.answer_callback_query(call.id, "Удалено")
    callback_edit_menu(call, bot)

def callback_delete_season(call, bot: telebot.TeleBot, season_id: int):
    s = db.get_season(season_id)
    db.delete_season(season_id)
    bot.answer_callback_query(call.id, "Удалено")
    callback_edit_series(call, bot, s["series_id"])

def callback_delete_episode(call, bot: telebot.TeleBot, episode_id: int):
    e = db.get_episode(episode_id)
    db.delete_episode(episode_id)
    bot.answer_callback_query(call.id, "Удалено")
    callback_edit_season(call, bot, e["season_id"])

def cmd_update_series_title(call, bot, sid):
    msg = bot.send_message(call.message.chat.id, "Новое название:")
    bot.register_next_step_handler(msg, lambda m: _do_update(m, bot, db.update_series, sid, title=m.text))

def start_update_series_description(call, bot: telebot.TeleBot, series_id: int):
    chat_id = call.message.chat.id
    utils.set_pending(chat_id, {"action": "update_series_description", "series_id": series_id})
    bot.edit_message_text("Введите новое описание сериала:", chat_id, call.message.message_id, reply_markup=None)

def cmd_update_season_number(call, bot, sid):
    msg = bot.send_message(call.message.chat.id, "Новый номер сезона:")
    bot.register_next_step_handler(msg, lambda m: _do_update(m, bot, db.update_season, sid, number=int(m.text) if m.text.isdigit() else None))

def cmd_update_episode_number(call, bot, eid):
    msg = bot.send_message(call.message.chat.id, "Новый номер серии:")
    bot.register_next_step_handler(msg, lambda m: _do_update(m, bot, db.update_episode, eid, number=int(m.text) if m.text.isdigit() else None))

def cmd_update_episode_title(call, bot, eid):
    msg = bot.send_message(call.message.chat.id, "Новое название серии:")
    bot.register_next_step_handler(msg, lambda m: _do_update(m, bot, db.update_episode, eid, title=m.text))

def _do_update(m, bot, func, item_id, **kwargs):
    func(item_id, **kwargs)
    send_main(m.chat.id, bot)

def cmd_update_episode_file(call, bot, eid):
    utils.set_pending(call.message.chat.id, {"action": "update_episode_file", "episode_id": eid})
    bot.send_message(call.message.chat.id, "Пришлите новый файл:")

# --- SMART ADD ---
def get_series_keyboard(pending_key: str):
    series = db.get_all_series()
    markup = InlineKeyboardMarkup()
    for s in series:
        markup.add(InlineKeyboardButton(s['title'], callback_data=f"smart_add_to_series:{s['id']}:{pending_key}"))
    markup.row(InlineKeyboardButton("Отмена", callback_data="main_menu"))
    return markup

def process_smart_add_episode_direct(chat_id, bot, series_id, pending_key):
    _finalize_smart_add(chat_id, None, bot, series_id, pending_key)

def process_smart_add_episode(call, bot: telebot.TeleBot, series_id: int, pending_key: str = None):
    try: bot.delete_message(call.message.chat.id, call.message.message_id)
    except: pass
    _finalize_smart_add(call.message.chat.id, call.id, bot, series_id, pending_key)

def _finalize_smart_add(chat_id, callback_id, bot, series_id, pending_key):
    if pending_key:
        pending = utils.pop_pending(chat_id, pending_key)
        if pending.get("temp_message_id"):
            try: bot.delete_message(chat_id, pending["temp_message_id"])
            except: pass
    else:
        pending = utils.pop_pending(chat_id)

    if not pending or pending.get("action") != "smart_add_episode": return

    parsed = pending["parsed"]
    series = db.get_series(series_id)
    
    # Проверка перемещена вверх: если не спарсилось, уведомляем и выходим БЕЗ добавления
    if not parsed:
        bot.send_message(chat_id, f"Не удалось распарсить файл: {pending['file_name']}. Добавьте вручную.")
        return

    season_num = parsed.get("season", 1)
    season_id = db.add_season(series_id, season_num)
    
    max_ep = db.get_max_episode_number(season_id)
    ep_num = parsed.get("episode", max_ep + 1)
    ep_title = parsed.get("title")

    # Всегда пробуем получить корректное русское название с TMDB; если не вышло — оставляем распаршенное
    tmdb_title = utils.fetch_tmdb_ru_title(series["title"], season_num, ep_num)
    if tmdb_title:
        ep_title = tmdb_title
    
    db.add_episode(season_id, ep_num, ep_title,
                   file_id=pending["file_id"], file_unique_id=pending["file_unique_id"],
                   file_name=pending["file_name"], file_size=pending["file_size"],
                   uploaded_at=pending["uploaded_at"])

    msg_text = f"Добавлено: Сезон {season_num} Серия {ep_num}"
    if callback_id: bot.answer_callback_query(callback_id, msg_text)
    else: bot.send_message(chat_id, msg_text)

    remaining = any(v.get("action") == "smart_add_episode" for v in utils.pending_actions.get(chat_id, {}).values())
    if not remaining: send_main(chat_id, bot)

def start_update_ep_title(call, bot: telebot.TeleBot, episode_id: int):
    chat_id = call.message.chat.id
    utils.set_pending(chat_id, {"action": "update_ep_title", "episode_id": episode_id})
    bot.edit_message_text("Введите новое название эпизода:", chat_id, call.message.message_id, reply_markup=None)

def start_update_ep_num(call, bot: telebot.TeleBot, episode_id: int):
    chat_id = call.message.chat.id
    utils.set_pending(chat_id, {"action": "update_ep_num", "episode_id": episode_id})
    bot.edit_message_text("Введите новый номер эпизода:", chat_id, call.message.message_id, reply_markup=None)

def start_update_season_num(call, bot: telebot.TeleBot, season_id: int):
    chat_id = call.message.chat.id
    utils.set_pending(chat_id, {"action": "update_season_num", "season_id": season_id})
    bot.edit_message_text("Введите новый номер сезона:", chat_id, call.message.message_id, reply_markup=None)

def start_update_series_poster(call, bot: telebot.TeleBot, series_id: int):
    chat_id = call.message.chat.id
    utils.set_pending(chat_id, {"action": "update_series_poster", "series_id": series_id})
    bot.edit_message_text("Пришлите фото для постера сериала:", chat_id, call.message.message_id, reply_markup=None)

def delete_series_poster(call, bot: telebot.TeleBot, series_id: int):
    db.clear_series_poster(series_id)
    bot.answer_callback_query(call.id, "🗑 Постер удалён")
    callback_edit_series(call, bot, series_id)

# --- ОБРАБОТЧИКИ ТЕКСТА (Message Handlers) ---

def process_update_ep_title(message, bot: telebot.TeleBot):
    chat_id = message.chat.id
    pending = utils.pop_pending(chat_id)
    new_title = message.text.strip()
    episode_id = pending.get("episode_id")
    
    if not episode_id: return send_main(chat_id, bot)
    
    db.update_episode(episode_id, title=new_title)
    
    bot.reply_to(message, f"Название эпизода обновлено на: <b>{new_title}</b>", parse_mode="HTML")
    # Возвращаемся в меню редактирования эпизода
    # Для этого нужна имитация call-объекта, или просто отправка в главное меню
    send_main(chat_id, bot) # Простой возврат в главное меню

def process_update_series_description(message, bot: telebot.TeleBot):
    chat_id = message.chat.id
    pending = utils.pop_pending(chat_id)
    new_description = message.text.strip()
    series_id = pending.get("series_id")
    
    if not series_id: return send_main(chat_id, bot)
    
    db.update_series(series_id, description=new_description)
    
    bot.reply_to(message, f"✅ Описание сериала обновлено", parse_mode="HTML")
    send_main(chat_id, bot)

def process_update_ep_num(message, bot: telebot.TeleBot):
    chat_id = message.chat.id
    pending = utils.pop_pending(chat_id)
    new_num = message.text.strip()
    episode_id = pending.get("episode_id")
    
    if not episode_id: return send_main(chat_id, bot)
    if not new_num.isdigit():
        bot.reply_to(message, "Ошибка: номер должен быть числом. Попробуйте снова.")
        utils.set_pending(chat_id, pending) # Возвращаем ожидание
        return

    db.update_episode(episode_id, number=int(new_num))
    
    bot.reply_to(message, f"Номер эпизода обновлен на: <b>{new_num}</b>", parse_mode="HTML")
    send_main(chat_id, bot)

def process_update_season_num(message, bot: telebot.TeleBot):
    chat_id = message.chat.id
    pending = utils.pop_pending(chat_id)
    new_num = message.text.strip()
    season_id = pending.get("season_id")
    
    if not season_id: return send_main(chat_id, bot)
    if not new_num.isdigit():
        bot.reply_to(message, "Ошибка: номер должен быть числом. Попробуйте снова.")
        utils.set_pending(chat_id, pending) # Возвращаем ожидание
        return

    db.update_season(season_id, number=int(new_num))
    
    bot.reply_to(message, f"Номер сезона обновлен на: <b>{new_num}</b>", parse_mode="HTML")
    send_main(chat_id, bot)

def process_update_series_poster(message, bot: telebot.TeleBot):
    chat_id = message.chat.id
    pending = utils.pop_pending(chat_id)
    series_id = pending.get("series_id")
    if not series_id:
        return send_main(chat_id, bot)
    photos = message.photo or []
    if not photos:
        bot.reply_to(message, "⚠️ Пришлите фото для постера.")
        utils.set_pending(chat_id, pending)
        return
    best = photos[-1]
    db.update_series_poster(series_id, best.file_id)
    bot.reply_to(message, "🖼 Постер обновлён.", parse_mode="HTML")
    send_main(chat_id, bot)
 