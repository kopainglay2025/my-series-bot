# test_db.py
# tests/test_db.py
import os
import tempfile
import db
import datetime

def test_db_crud():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        db.init_db(path)
        sid = db.add_series("Test Series", "desc", path)
        assert sid > 0
        seasons = db.get_seasons(sid, path)
        assert seasons == []
        season_id = db.add_season(sid, 1, path)
        assert season_id > 0
        eid = db.add_episode(season_id, 1, "Ep1", file_id="file_123", file_unique_id="uniq_1", file_name="ep1.mkv", file_size=12345, uploaded_at=datetime.datetime.utcnow(), path=path)
        assert eid > 0
        ep = db.get_episode(eid, path)
        assert ep["file_id"] == "file_123"
        db.update_episode_file(eid, "file_456", file_unique_id="uniq_2", file_name="ep1_new.mkv", file_size=2222, uploaded_at=datetime.datetime.utcnow(), path=path)
        ep2 = db.get_episode(eid, path)
        assert ep2["file_id"] == "file_456"
        db.update_episode(eid, number=2, title="New Title", path=path)
        ep3 = db.get_episode(eid, path)
        assert ep3["number"] == 2
        assert ep3["title"] == "New Title"
        db.delete_episode(eid, path)
        assert db.get_episode(eid, path) is None
        db.update_season(season_id, number=2, path=path)
        season2 = db.get_season(season_id, path)
        assert season2["number"] == 2
        db.delete_season(season_id, path)
        assert db.get_season(season_id, path) is None
        db.update_series(sid, title="New Title", path=path)
        series2 = db.get_series(sid, path)
        assert series2["title"] == "New Title"
        db.delete_series(sid, path)
        assert db.get_series(sid, path) is None
        
        # Test watched
        user_id = 123
        eid2 = db.add_episode(season_id, 1, "Ep2", path=path)
        db.mark_episode_watched(user_id, eid2, path)
        assert db.is_episode_watched(user_id, eid2, path)
        unwatched = db.get_unwatched_episodes(user_id, path=path)
        assert len(unwatched) == 0  # Since we marked it watched
        
        # Test favorites
        db.add_favorite(user_id, 'series', sid, path)
        assert db.is_favorite(user_id, 'series', sid, path)
        db.remove_favorite(user_id, 'series', sid, path)
        assert not db.is_favorite(user_id, 'series', sid, path)
        
        # Test search
        db.add_series("Search Test", path=path)
        results = db.search_items("Search", path)
        assert len(results) > 0
    finally:
        os.remove(path)