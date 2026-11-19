"""Database layer: SQLite with FTS5 full-text index."""
import json
import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get("SMARTIR_DB", os.path.join(os.path.dirname(__file__), "..", "data", "smartir.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('depositor','librarian','admin')),
    password_hash TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY,
    handle TEXT UNIQUE,
    title TEXT NOT NULL,
    creators TEXT NOT NULL,          -- JSON list
    advisor TEXT DEFAULT '',
    date_issued TEXT DEFAULT '',
    item_type TEXT DEFAULT '',
    subjects TEXT DEFAULT '[]',      -- JSON list
    abstract TEXT DEFAULT '',
    publisher TEXT DEFAULT '',
    language TEXT DEFAULT 'en',
    faculty TEXT DEFAULT '',
    department TEXT DEFAULT '',
    rights TEXT DEFAULT 'open',      -- open | embargo | restricted
    embargo_until TEXT DEFAULT '',
    source_url TEXT DEFAULT '',
    origin TEXT DEFAULT 'local',     -- unilag | local | demo
    batch TEXT DEFAULT '',           -- audit_sample | extension (UNILAG records only)
    status TEXT NOT NULL DEFAULT 'submitted'
        CHECK (status IN ('submitted','returned','published','withdrawn')),
    review_note TEXT DEFAULT '',
    submitted_by INTEGER REFERENCES users(id),
    reviewed_by INTEGER REFERENCES users(id),
    quality_score REAL DEFAULT 0,
    fulltext TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    stored_name TEXT DEFAULT '',
    size_bytes INTEGER DEFAULT 0,
    mime TEXT DEFAULT 'application/pdf'
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    item_id INTEGER REFERENCES items(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('view','download','search','harvest')),
    detail TEXT DEFAULT '',
    at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY,
    item_id INTEGER,
    user_id INTEGER,
    action TEXT NOT NULL,
    note TEXT DEFAULT '',
    at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
    title, creators, subjects, abstract, fulltext, faculty, item_type,
    content='items', content_rowid='id', tokenize='porter unicode61'
);
CREATE TRIGGER IF NOT EXISTS items_ai AFTER INSERT ON items BEGIN
  INSERT INTO items_fts(rowid,title,creators,subjects,abstract,fulltext,faculty,item_type)
  VALUES (new.id,new.title,new.creators,new.subjects,new.abstract,new.fulltext,new.faculty,new.item_type);
END;
CREATE TRIGGER IF NOT EXISTS items_ad AFTER DELETE ON items BEGIN
  INSERT INTO items_fts(items_fts,rowid,title,creators,subjects,abstract,fulltext,faculty,item_type)
  VALUES ('delete',old.id,old.title,old.creators,old.subjects,old.abstract,old.fulltext,old.faculty,old.item_type);
END;
CREATE TRIGGER IF NOT EXISTS items_au AFTER UPDATE ON items BEGIN
  INSERT INTO items_fts(items_fts,rowid,title,creators,subjects,abstract,fulltext,faculty,item_type)
  VALUES ('delete',old.id,old.title,old.creators,old.subjects,old.abstract,old.fulltext,old.faculty,old.item_type);
  INSERT INTO items_fts(rowid,title,creators,subjects,abstract,fulltext,faculty,item_type)
  VALUES (new.id,new.title,new.creators,new.subjects,new.abstract,new.fulltext,new.faculty,new.item_type);
END;
CREATE INDEX IF NOT EXISTS idx_items_status ON items(status);
CREATE INDEX IF NOT EXISTS idx_items_faculty ON items(faculty);
CREATE INDEX IF NOT EXISTS idx_events_item ON events(item_id, kind);
"""


def connect(path=None):
    target = path or DB_PATH
    if target != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    conn = sqlite3.connect(target, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


@contextmanager
def get_conn():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(path=None):
    conn = connect(path)
    conn.executescript(SCHEMA)
    if "batch" not in [r[1] for r in conn.execute("PRAGMA table_info(items)")]:
        conn.execute("ALTER TABLE items ADD COLUMN batch TEXT DEFAULT ''")  # databases created before this column
    conn.commit()
    conn.close()


def row_to_item(row):
    if row is None:
        return None
    d = dict(row)
    d["creators"] = json.loads(d.get("creators") or "[]")
    d["subjects"] = json.loads(d.get("subjects") or "[]")
    return d
