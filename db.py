# db.py
import sqlite3
import datetime
import shutil
from typing import Optional, List
import re

DB_NAME = "media_archive.db"

def get_connection(path: str = DB_NAME):
    conn = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(path: str = DB_NAME):
    with get_connection(path) as conn:
        cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS series (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT,
            poster_file_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        try: cur.execute("ALTER TABLE series ADD COLUMN poster_file_id TEXT")
        except: pass
        cur.execute("""CREATE TABLE IF NOT EXISTS seasons (
            id INTEGER PRIMARY KEY,
            series_id INTEGER NOT NULL,
            number INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(series_id, number),
            FOREIGN KEY(series_id) REFERENCES series(id) ON DELETE CASCADE
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY,
            season_id INTEGER NOT NULL,
            number INTEGER NOT NULL,
            title TEXT,
            file_id TEXT,
            file_unique_id TEXT,
            file_name TEXT,
            file_size INTEGER,
            uploaded_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(season_id, number),
            FOREIGN KEY(season_id) REFERENCES seasons(id) ON DELETE CASCADE
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS watched_episodes (
            user_id INTEGER NOT NULL,
            episode_id INTEGER NOT NULL,
            watched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, episode_id),
            FOREIGN KEY(episode_id) REFERENCES episodes(id) ON DELETE CASCADE
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS favorites (
            user_id INTEGER NOT NULL,
            item_type TEXT NOT NULL,
            item_id INTEGER NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, item_type, item_id)
        )""")
        conn.commit()

# --- CRUD SERIES ---
def add_series(title: str, description: str = None, path: str = DB_NAME) -> int:
    with get_connection(path) as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO series(title, description) VALUES(?, ?)", (title, description))
        conn.commit()
        return cur.lastrowid

def get_all_series(path: str = DB_NAME) -> List[sqlite3.Row]:
    with get_connection(path) as conn:
        return list(conn.cursor().execute("SELECT id, title, description, poster_file_id FROM series ORDER BY title").fetchall())

def get_series(series_id: int, path: str = DB_NAME) -> Optional[sqlite3.Row]:
    with get_connection(path) as conn:
        return conn.cursor().execute("SELECT * FROM series WHERE id=?", (series_id,)).fetchone()

def update_series(series_id: int, title: str = None, description: str = None, poster_file_id: str = None, path: str = DB_NAME):
    with get_connection(path) as conn:
        cur = conn.cursor()
        if title is not None:
            cur.execute("UPDATE series SET title=? WHERE id=?", (title, series_id))
        if description is not None:
            cur.execute("UPDATE series SET description=? WHERE id=?", (description, series_id))
        if poster_file_id is not None:
            cur.execute("UPDATE series SET poster_file_id=? WHERE id=?", (poster_file_id, series_id))
        conn.commit()

def update_series_poster(series_id: int, poster_file_id: str, path: str = DB_NAME):
    with get_connection(path) as conn:
        conn.cursor().execute("UPDATE series SET poster_file_id=? WHERE id=?", (poster_file_id, series_id))
        conn.commit()

def clear_series_poster(series_id: int, path: str = DB_NAME):
    with get_connection(path) as conn:
        conn.cursor().execute("UPDATE series SET poster_file_id=NULL WHERE id=?", (series_id,))
        conn.commit()

# --- WATCH META HELPERS ---
def get_last_watched_at_for_series(user_id: int, series_id: int, path: str = DB_NAME):
    with get_connection(path) as conn:
        row = conn.cursor().execute("""
            SELECT MAX(w.watched_at) as last_dt
            FROM watched_episodes w
            JOIN episodes e ON w.episode_id = e.id
            JOIN seasons s ON e.season_id = s.id
            WHERE w.user_id=? AND s.series_id=?
        """, (user_id, series_id)).fetchone()
        return row["last_dt"] if row and row["last_dt"] else None

def get_last_watched_at_for_season(user_id: int, season_id: int, path: str = DB_NAME):
    with get_connection(path) as conn:
        row = conn.cursor().execute("""
            SELECT MAX(w.watched_at) as last_dt
            FROM watched_episodes w
            JOIN episodes e ON w.episode_id = e.id
            WHERE w.user_id=? AND e.season_id=?
        """, (user_id, season_id)).fetchone()
        return row["last_dt"] if row and row["last_dt"] else None

def get_last_watched_at_for_episode(user_id: int, episode_id: int, path: str = DB_NAME):
    with get_connection(path) as conn:
        row = conn.cursor().execute("""
            SELECT watched_at FROM watched_episodes
            WHERE user_id=? AND episode_id=? LIMIT 1
        """, (user_id, episode_id)).fetchone()
        return row["watched_at"] if row else None

def delete_series(series_id: int, path: str = DB_NAME):
    with get_connection(path) as conn:
        conn.cursor().execute("DELETE FROM series WHERE id=?", (series_id,))
        conn.commit()

# --- CRUD SEASONS ---
def add_season(series_id: int, number: int, path: str = DB_NAME) -> int:
    with get_connection(path) as conn:
        cur = conn.cursor()
        cur.execute("INSERT OR IGNORE INTO seasons(series_id, number) VALUES(?, ?)", (series_id, number))
        conn.commit()
        cur.execute("SELECT id FROM seasons WHERE series_id=? AND number=?", (series_id, number))
        return cur.fetchone()["id"]

def get_seasons(series_id: int, path: str = DB_NAME) -> List[sqlite3.Row]:
    with get_connection(path) as conn:
        return list(conn.cursor().execute("SELECT id, number, series_id FROM seasons WHERE series_id=? ORDER BY number", (series_id,)).fetchall())

def get_season(season_id: int, path: str = DB_NAME) -> Optional[sqlite3.Row]:
    with get_connection(path) as conn:
        return conn.cursor().execute("SELECT * FROM seasons WHERE id=?", (season_id,)).fetchone()

def update_season(season_id: int, number: int = None, path: str = DB_NAME):
    with get_connection(path) as conn:
        if number is not None:
            conn.cursor().execute("UPDATE seasons SET number=? WHERE id=?", (number, season_id))
        conn.commit()

def delete_season(season_id: int, path: str = DB_NAME):
    with get_connection(path) as conn:
        conn.cursor().execute("DELETE FROM seasons WHERE id=?", (season_id,))
        conn.commit()

def get_next_season(series_id: int, current_season_number: int, path: str = DB_NAME) -> Optional[sqlite3.Row]:
    with get_connection(path) as conn:
        return conn.cursor().execute("""
        SELECT * FROM seasons WHERE series_id=? AND number > ? ORDER BY number ASC LIMIT 1
        """, (series_id, current_season_number)).fetchone()

# --- CRUD EPISODES ---
def add_episode(season_id: int, number: int, title: str = None,
                file_id: str = None, file_unique_id: str = None,
                file_name: str = None, file_size: int = None,
                uploaded_at: datetime.datetime = None,
                path: str = DB_NAME) -> int:
    with get_connection(path) as conn:
        cur = conn.cursor()
        cur.execute("""INSERT OR REPLACE INTO episodes(season_id, number, title, file_id, file_unique_id, file_name, file_size, uploaded_at)
                       VALUES(?, ?, ?, ?, ?, ?, ?, ?)""",
                    (season_id, number, title, file_id, file_unique_id, file_name, file_size, uploaded_at))
        conn.commit()
        cur.execute("SELECT id FROM episodes WHERE season_id=? AND number=?", (season_id, number))
        return cur.fetchone()["id"]

def get_episodes(season_id: int, path: str = DB_NAME) -> List[sqlite3.Row]:
    with get_connection(path) as conn:
        return list(conn.cursor().execute("SELECT id, number, title, file_id, season_id FROM episodes WHERE season_id=? ORDER BY number", (season_id,)).fetchall())

def get_episode(episode_id: int, path: str = DB_NAME) -> Optional[sqlite3.Row]:
    with get_connection(path) as conn:
        return conn.cursor().execute("SELECT * FROM episodes WHERE id=?", (episode_id,)).fetchone()

def update_episode(episode_id: int, number: int = None, title: str = None, path: str = DB_NAME):
    with get_connection(path) as conn:
        cur = conn.cursor()
        if number is not None: cur.execute("UPDATE episodes SET number=? WHERE id=?", (number, episode_id))
        if title is not None: cur.execute("UPDATE episodes SET title=? WHERE id=?", (title, episode_id))
        conn.commit()

def update_episode_file(episode_id: int, file_id: str, file_unique_id: str = None, file_name: str = None, file_size: int = None, uploaded_at: datetime.datetime = None, path: str = DB_NAME):
    with get_connection(path) as conn:
        conn.cursor().execute("""UPDATE episodes SET file_id=?, file_unique_id=?, file_name=?, file_size=?, uploaded_at=? WHERE id=?""",
                              (file_id, file_unique_id, file_name, file_size, uploaded_at, episode_id))
        conn.commit()

def delete_episode(episode_id: int, path: str = DB_NAME):
    with get_connection(path) as conn:
        conn.cursor().execute("DELETE FROM episodes WHERE id=?", (episode_id,))
        conn.commit()

def get_previous_episode(season_id: int, current_number: int, path: str = DB_NAME) -> Optional[sqlite3.Row]:
    with get_connection(path) as conn:
        return conn.cursor().execute("""
        SELECT id FROM episodes WHERE season_id=? AND number < ? ORDER BY number DESC LIMIT 1
        """, (season_id, current_number)).fetchone()

def get_next_episode(season_id: int, current_number: int, path: str = DB_NAME) -> Optional[sqlite3.Row]:
    with get_connection(path) as conn:
        return conn.cursor().execute("""
        SELECT id FROM episodes WHERE season_id=? AND number > ? ORDER BY number ASC LIMIT 1
        """, (season_id, current_number)).fetchone()

def get_max_episode_number(season_id: int, path: str = DB_NAME) -> int:
    with get_connection(path) as conn:
        result = conn.cursor().execute("SELECT MAX(number) FROM episodes WHERE season_id=?", (season_id,)).fetchone()
        return result[0] if result[0] else 0

# --- WATCH HISTORY ---
def mark_episode_watched(user_id: int, episode_id: int, path: str = DB_NAME):
    with get_connection(path) as conn:
        conn.cursor().execute("INSERT OR IGNORE INTO watched_episodes (user_id, episode_id) VALUES (?, ?)", (user_id, episode_id))
        conn.commit()

def is_episode_watched(user_id: int, episode_id: int, path: str = DB_NAME) -> bool:
    with get_connection(path) as conn:
        result = conn.cursor().execute("SELECT 1 FROM watched_episodes WHERE user_id=? AND episode_id=?", (user_id, episode_id)).fetchone()
        return bool(result)

def get_unwatched_episodes(user_id: int, limit: int = 3, path: str = DB_NAME) -> List[sqlite3.Row]:
    with get_connection(path) as conn:
        return list(conn.cursor().execute("""
        SELECT e.id, e.title, e.number, s.number as season_number, ser.title as series_title
        FROM episodes e
        JOIN seasons s ON e.season_id = s.id
        JOIN series ser ON s.series_id = ser.id
        LEFT JOIN watched_episodes w ON e.id = w.episode_id AND w.user_id = ?
        WHERE w.episode_id IS NULL
        ORDER BY e.created_at DESC LIMIT ?
        """, (user_id, limit)).fetchall())

def get_continue_watching_data(user_id: int, limit: int = 5, path: str = DB_NAME):
    with get_connection(path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT s.id as series_id, s.title as series_title, MAX(we.watched_at) as last_watched_at
            FROM watched_episodes we
            JOIN episodes e ON we.episode_id = e.id
            JOIN seasons se ON e.season_id = se.id
            JOIN series s ON se.series_id = s.id
            WHERE we.user_id = ?
            GROUP BY s.id
            ORDER BY last_watched_at DESC
            LIMIT ?
        """, (user_id, limit))
        
        series_to_check = cur.fetchall()
        results = []
        
        for s_row in series_to_check:
            series_id = s_row['series_id']
            series_title = s_row['series_title']
            last_watched_at = s_row['last_watched_at']
            
            cur.execute("""
                SELECT e.id as last_ep_id, e.number as last_ep_num, se.id as last_season_id, se.number as last_season_num
                FROM watched_episodes we
                JOIN episodes e ON we.episode_id = e.id
                JOIN seasons se ON e.season_id = se.id
                WHERE we.user_id = ? AND se.series_id = ?
                ORDER BY we.watched_at DESC
                LIMIT 1
            """, (user_id, series_id))
            last_watched_ep = cur.fetchone()

            if last_watched_ep:
                cur.execute("""
                    SELECT e.id, e.number, se.number as season_number
                    FROM episodes e
                    JOIN seasons se ON e.season_id = se.id
                    WHERE e.season_id = ? AND e.number = ?
                """, (last_watched_ep['last_season_id'], last_watched_ep['last_ep_num'] + 1))
                next_ep = cur.fetchone()
                
                next_ep_data = None
                if next_ep:
                    next_ep_data = {
                        'id': next_ep['id'],
                        'season_number': next_ep['season_number'],
                        'number': next_ep['number']
                    }
                else:
                    cur.execute("""
                        SELECT e.id, e.number, se.number as season_number
                        FROM episodes e
                        JOIN seasons se ON e.season_id = se.id
                        WHERE se.series_id = ? AND se.number = ?
                        ORDER BY e.number ASC
                        LIMIT 1
                    """, (series_id, last_watched_ep['last_season_num'] + 1))
                    next_ep_in_next_season = cur.fetchone()
                    if next_ep_in_next_season:
                        next_ep_data = {
                            'id': next_ep_in_next_season['id'],
                            'season_number': next_ep_in_next_season['season_number'],
                            'number': next_ep_in_next_season['number']
                        }
                        
                results.append({
                    'series_id': series_id,
                    'series_title': series_title,
                    'last_ep_id': last_watched_ep['last_ep_id'],
                    'last_ep_s': last_watched_ep['last_season_num'],
                    'last_ep_e': last_watched_ep['last_ep_num'],
                    'next_ep_data': next_ep_data,
                    'last_watched_at': last_watched_at
                })
        return results

# --- FAVORITES ---
def add_favorite(user_id: int, item_type: str, item_id: int, path: str = DB_NAME):
    with get_connection(path) as conn:
        conn.cursor().execute("INSERT OR IGNORE INTO favorites (user_id, item_type, item_id) VALUES (?, ?, ?)", (user_id, item_type, item_id))
        conn.commit()

def remove_favorite(user_id: int, item_type: str, item_id: int, path: str = DB_NAME):
    with get_connection(path) as conn:
        conn.cursor().execute("DELETE FROM favorites WHERE user_id=? AND item_type=? AND item_id=?", (user_id, item_type, item_id))
        conn.commit()

def is_favorite(user_id: int, item_type: str, item_id: int, path: str = DB_NAME) -> bool:
    with get_connection(path) as conn:
        result = conn.cursor().execute("SELECT 1 FROM favorites WHERE user_id=? AND item_type=? AND item_id=?", (user_id, item_type, item_id)).fetchone()
        return bool(result)

def get_favorites(user_id: int, path: str = DB_NAME) -> List[sqlite3.Row]:
    with get_connection(path) as conn:
        return list(conn.cursor().execute("""
        SELECT item_type, item_id FROM favorites WHERE user_id=? ORDER BY added_at DESC
        """, (user_id,)).fetchall())

# --- UTILS ---
def export_db(destination_path: str, path: str = DB_NAME):
    shutil.copy2(path, destination_path)

def dump_sample_data(path: str = DB_NAME):
    init_db(path)
    rid = add_series("Sample Series", "Desc", path)
    add_season(rid, 1, path)
    return True
 