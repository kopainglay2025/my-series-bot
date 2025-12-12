import os
import re
from imdb import Cinemagoer
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors.exceptions.bad_request_400 import MediaEmpty, PhotoInvalidDimensions, WebpageMediaEmpty
from src import app  

imdb = Cinemagoer()

def list_to_str(lst):
    return ", ".join(str(item) for item in lst) if lst else "N/A"

async def get_poster(query, id=False):
    if not id:
        query = query.strip().lower()
        year = re.findall(r'[1-2]\d{3}$', query, re.IGNORECASE)
        title = query.replace(year[0], "").strip() if year else query

        movieid = imdb.search_movie(title.lower(), results=1)
        if not movieid:
            return None  

        movieid = movieid[0].movieID
    else:
        movieid = query

    movie = imdb.get_movie(movieid)
    date = movie.get("original air date") or movie.get("year") or "N/A"
    plot = movie.get('plot', ["N/A"])[0] if not os.getenv("LONG_IMDB_DESCRIPTION") else movie.get('plot outline')

    if plot and len(plot) > 800:
        plot = plot[:800] + "..."

    return {
        'title': movie.get('title'),
        'votes': movie.get('votes'),
        "imdb_id": f"tt{movie.get('imdbID')}",
        "genres": list_to_str(movie.get("genres")),
        "poster": movie.get('full-size cover url'),
        "plot": plot,
        "rating": str(movie.get("rating")),
        'release_date': date,
        "url": f'https://www.imdb.com/title/tt{movieid}'
    }

@app.on_message(filters.command(["imdb"]))
async def imdb_search(client, message):
    if ' ' not in message.text:
        return await message.reply('Please provide a movie/series name.')

    k = await message.reply('Searching IMDb...')
    _, title = message.text.split(None, 1)
    imdb_data = await get_poster(title)

    await k.delete()

    if not imdb_data:
        return await message.reply("Movie name not found. Check the name or report to @AsuraaSupports.")

    btn = [[InlineKeyboardButton(text="View on IMDb", url=imdb_data['url'])]]

    caption = f"""<b>
🎬 Title: <a href="{imdb_data['url']}">{imdb_data['title']}</a>
📌 Genres: {imdb_data['genres']}
⭐ Rating: <a href="{imdb_data['url']}/ratings">{imdb_data['rating']}</a> / 10 ({imdb_data['votes']} votes)
📅 Release Date: {imdb_data['release_date']}
</b>"""

    if imdb_data.get('poster'):
        try:
            await message.reply_photo(
                photo=imdb_data['poster'], 
                caption=caption, 
                reply_markup=InlineKeyboardMarkup(btn), 
                parse_mode=enums.ParseMode.HTML
            )
        except (MediaEmpty, PhotoInvalidDimensions, WebpageMediaEmpty):
            fallback_poster = imdb_data['poster'].replace('.jpg', "._V1_UX360.jpg")
            await message.reply_photo(
                photo=fallback_poster, 
                caption=caption, 
                reply_markup=InlineKeyboardMarkup(btn), 
                parse_mode=enums.ParseMode.HTML
            )
        except Exception:
            await message.reply(
                caption, 
                reply_markup=InlineKeyboardMarkup(btn), 
                disable_web_page_preview=False, 
                parse_mode=enums.ParseMode.HTML
            )
    else:
        await message.reply(
            caption, 
            reply_markup=InlineKeyboardMarkup(btn), 
            disable_web_page_preview=False, 
            parse_mode=enums.ParseMode.HTML
        )