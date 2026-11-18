import json
import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS clips (
    id INTEGER PRIMARY KEY, login TEXT, moment_start REAL, moment_end REAL, score REAL,
    title TEXT, path TEXT, status TEXT, published TEXT, timings TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS targets (
    id INTEGER PRIMARY KEY, kind TEXT, name TEXT, config TEXT, enabled INTEGER DEFAULT 0,
    mode TEXT DEFAULT 'auto', daily_limit INTEGER DEFAULT 50, min_score REAL DEFAULT 8,
    min_interval_min REAL DEFAULT 5, created_at REAL);
CREATE TABLE IF NOT EXISTS publications (
    id INTEGER PRIMARY KEY, clip_id INTEGER, target_id INTEGER, status TEXT, url TEXT, error TEXT,
    created_at REAL, done_at REAL, UNIQUE (clip_id, target_id));
CREATE INDEX IF NOT EXISTS pub_target ON publications (target_id, status, done_at);
CREATE TABLE IF NOT EXISTS streamers (
    login TEXT PRIMARY KEY, display_name TEXT, avatar TEXT, list TEXT DEFAULT 'white', layout TEXT DEFAULT '',
    facecam TEXT, sensitivity REAL DEFAULT 1.0, hashtags TEXT, created_at REAL, last_live_at REAL);
CREATE TABLE IF NOT EXISTS viewer_clips (
    slug TEXT PRIMARY KEY, login TEXT, title TEXT, created REAL, duration REAL, views INTEGER,
    curator TEXT, seen_at REAL, views_at REAL, clip_id INTEGER);
CREATE INDEX IF NOT EXISTS vc_login ON viewer_clips (login, created);
CREATE TABLE IF NOT EXISTS features (
    login TEXT, sec INTEGER, chat REAL, users INTEGER, z_chat REAL, z_audio REAL, loud REAL,
    laugh INTEGER, shock INTEGER, hype INTEGER, clipword INTEGER, viewers INTEGER, PRIMARY KEY (login, sec));
"""
COLUMNS = {
    "clips": {"meta": "TEXT", "transcript": "TEXT", "manual": "INTEGER DEFAULT 0", "error": "TEXT", "reasons": "TEXT",
              "subs": "TEXT", "edit": "TEXT", "src_path": "TEXT", "src_duration": "REAL", "duplicate_of": "INTEGER",
              "version": "INTEGER DEFAULT 1", "updated_at": "REAL", "stream_title": "TEXT",
              "source": "TEXT", "judge": "TEXT", "safety": "TEXT", "rank": "REAL", "label": "REAL"},
    "targets": {"quiet_from": "INTEGER", "quiet_to": "INTEGER", "caption": "TEXT", "checked_at": "REAL",
                "check_message": "TEXT", "check_ok": "INTEGER", "policy": "TEXT"},
    "publications": {"remote": "TEXT", "views": "INTEGER", "views_at": "REAL", "deleted": "INTEGER DEFAULT 0"},
}
JSON_FIELDS = {"judge", "safety", "policy", "published", "timings", "meta", "config", "reasons", "subs", "edit", "remote", "facecam", "hashtags"}


def _decode(row: dict) -> dict:
    for k in JSON_FIELDS & row.keys():
        if isinstance(row[k], str):
            try:
                row[k] = json.loads(row[k])
            except ValueError:
                pass
    return row


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        for table, cols in COLUMNS.items():
            have = {r["name"] for r in self.db.execute(f"PRAGMA table_info({table})")}
            for col, typ in cols.items():
                if col not in have:
                    self.db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
        self.db.commit()

    def rows(self, sql: str, *args) -> list[dict]:
        return [_decode(dict(r)) for r in self.db.execute(sql, args)]

    def row(self, sql: str, *args) -> dict | None:
        r = self.rows(sql, *args)
        return r[0] if r else None

    def _update(self, table: str, row_id, fields: dict, key: str = "id"):
        if not fields:
            return
        fields = {k: json.dumps(v, ensure_ascii=False) if k in JSON_FIELDS and v is not None else v
                  for k, v in fields.items()}
        cols = ", ".join(f"{k} = ?" for k in fields)
        self.db.execute(f"UPDATE {table} SET {cols} WHERE {key} = ?", (*fields.values(), row_id))
        self.db.commit()

    def execute(self, sql: str, *args):
        cur = self.db.execute(sql, args)
        self.db.commit()
        return cur

    # clips
    def add(self, login: str, start: float, end: float, score: float, manual: bool = False) -> int:
        cur = self.db.execute(
            "INSERT INTO clips (login, moment_start, moment_end, score, status, manual, created_at) VALUES (?,?,?,?,?,?,?)",
            (login, start, end, score, "detected", int(manual), time.time()),
        )
        self.db.commit()
        return cur.lastrowid

    def update(self, clip_id: int, **fields):
        self._update("clips", clip_id, fields)

    def clip(self, clip_id: int) -> dict | None:
        return self.row("SELECT * FROM clips WHERE id = ?", clip_id)

    def recent(self, limit: int = 20) -> list[dict]:
        return self.rows("SELECT * FROM clips ORDER BY id DESC LIMIT ?", limit)

    # settings
    def get_settings(self) -> dict:
        return {r["key"]: json.loads(r["value"]) for r in self.db.execute("SELECT key, value FROM settings")}

    def set_settings(self, values: dict):
        self.db.executemany(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            [(k, json.dumps(v, ensure_ascii=False)) for k, v in values.items()],
        )
        self.db.commit()

    # targets
    def targets(self, enabled_only: bool = False) -> list[dict]:
        return self.rows("SELECT * FROM targets" + (" WHERE enabled = 1" if enabled_only else "") + " ORDER BY id")

    def target(self, target_id: int) -> dict | None:
        return self.row("SELECT * FROM targets WHERE id = ?", target_id)

    def add_target(self, **fields) -> int:
        fields = {**fields, "config": json.dumps(fields.get("config") or {}, ensure_ascii=False), "created_at": time.time()}
        cur = self.db.execute(
            f"INSERT INTO targets ({', '.join(fields)}) VALUES ({', '.join('?' * len(fields))})", tuple(fields.values())
        )
        self.db.commit()
        return cur.lastrowid

    def update_target(self, target_id: int, **fields):
        self._update("targets", target_id, fields)

    def delete_target(self, target_id: int):
        self.db.execute("DELETE FROM publications WHERE target_id = ? AND status NOT IN ('done', 'publishing')", (target_id,))
        self.db.execute("DELETE FROM targets WHERE id = ?", (target_id,))
        self.db.commit()

    # publications
    def add_publication(self, clip_id: int, target_id: int) -> int | None:
        cur = self.db.execute(
            "INSERT OR IGNORE INTO publications (clip_id, target_id, status, created_at) VALUES (?,?,?,?)",
            (clip_id, target_id, "queued", time.time()),
        )
        self.db.commit()
        return cur.lastrowid if cur.rowcount else None

    def update_publication(self, pub_id: int, **fields):
        self._update("publications", pub_id, fields)

    def publications(self, clip_ids: list[int]) -> list[dict]:
        if not clip_ids:
            return []
        q = ",".join("?" * len(clip_ids))
        return self.rows(f"SELECT * FROM publications WHERE clip_id IN ({q})", *clip_ids)

    # streamers
    def streamers(self, list_name: str | None = None) -> list[dict]:
        if list_name:
            return self.rows("SELECT * FROM streamers WHERE list = ? ORDER BY login", list_name)
        return self.rows("SELECT * FROM streamers ORDER BY list DESC, login")

    def streamer(self, login: str) -> dict | None:
        return self.row("SELECT * FROM streamers WHERE login = ?", login)

    def upsert_streamer(self, login: str, **fields):
        login = login.lower()
        if not self.streamer(login):
            self.execute("INSERT INTO streamers (login, created_at) VALUES (?, ?)", login, time.time())
        if fields:
            self._update("streamers", login, fields, key="login")

    def delete_streamer(self, login: str):
        self.execute("DELETE FROM streamers WHERE login = ?", login)
