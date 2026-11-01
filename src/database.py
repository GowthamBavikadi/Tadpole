# database.py — Unified SQLite Persistence for Tasks, Idea Boxes, Detail Views, Links & FTS5 Search
import os
import re
import json
import sqlite3
from datetime import datetime
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "brain.db")


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA temp_store=MEMORY")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS focus (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                topic TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                filename TEXT NOT NULL,
                source TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS created_reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS drops (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                summary TEXT,
                type TEXT NOT NULL,
                tags TEXT,
                source TEXT,
                raw_content TEXT,
                links TEXT DEFAULT '[]',
                due_date TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        drop_cols = [r["name"] for r in conn.execute("PRAGMA table_info(drops)").fetchall()]
        if "links" not in drop_cols:
            conn.execute("ALTER TABLE drops ADD COLUMN links TEXT DEFAULT '[]'")
        if "due_date" not in drop_cols:
            conn.execute("ALTER TABLE drops ADD COLUMN due_date TEXT")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                drop_id INTEGER REFERENCES drops(id) ON DELETE SET NULL,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                raw_text TEXT DEFAULT '',
                links TEXT DEFAULT '[]',
                status TEXT DEFAULT 'todo',
                due_date TEXT,
                tags TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            )
        """)
        task_cols = [r["name"] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()]
        if "description" not in task_cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN description TEXT DEFAULT ''")
        if "raw_text" not in task_cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN raw_text TEXT DEFAULT ''")
        if "links" not in task_cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN links TEXT DEFAULT '[]'")

        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
                drop_id UNINDEXED,
                title,
                tags,
                source UNINDEXED,
                chunk_text,
                tokenize='porter unicode61'
            )
        """)

        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status, created_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_drops_type ON drops(type, created_at DESC)")
        conn.commit()


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _parse_links(links_raw) -> list[str]:
    if not links_raw:
        return []
    if isinstance(links_raw, list):
        return [str(x) for x in links_raw if x]
    try:
        parsed = json.loads(links_raw)
        if isinstance(parsed, list):
            return [str(x) for x in parsed if x]
    except Exception:
        pass
    return [s.strip() for s in str(links_raw).split(",") if s.strip()]


def get_focus() -> str | None:
    with get_db() as conn:
        row = conn.execute("SELECT topic FROM focus WHERE id = 1").fetchone()
        return row["topic"] if row else None


def set_focus(topic: str | None):
    with get_db() as conn:
        if topic:
            conn.execute(
                "INSERT INTO focus (id, topic, updated_at) VALUES (1, ?, CURRENT_TIMESTAMP) "
                "ON CONFLICT(id) DO UPDATE SET topic=excluded.topic, updated_at=CURRENT_TIMESTAMP",
                (topic,)
            )
        else:
            conn.execute("DELETE FROM focus WHERE id = 1")


def index_knowledge_chunks(drop_id: int, title: str, tags: str, source: str, full_text: str):
    if not full_text or not full_text.strip():
        return
    clean = full_text.strip()
    chunk_size = 800
    overlap = 150
    chunks = []
    start = 0
    while start < len(clean) and len(chunks) < 40:
        end = min(len(clean), start + chunk_size)
        chunks.append(clean[start:end])
        if end >= len(clean):
            break
        start = end - overlap

    with get_db() as conn:
        conn.execute("DELETE FROM knowledge_fts WHERE drop_id = ?", (str(drop_id),))
        for ch in chunks:
            conn.execute(
                "INSERT INTO knowledge_fts (drop_id, title, tags, source, chunk_text) VALUES (?, ?, ?, ?, ?)",
                (str(drop_id), title, tags, source, ch)
            )


def search_knowledge_chunks(query: str, limit: int = 6) -> list[dict]:
    words = [w for w in re.findall(r"[A-Za-z0-9]{2,}", query.lower()) if w not in {
        "what", "when", "where", "which", "who", "whom", "whose", "why", "how",
        "the", "and", "for", "with", "from", "that", "this", "have", "has", "had",
        "are", "was", "were", "can", "could", "should", "would", "about", "into",
        "tell", "show", "give", "find", "summarise", "summarize", "my", "me", "in"
    }]

    results = []
    with get_db() as conn:
        if words:
            fts_query = " OR ".join(f'"{w}"*' for w in words[:8])
            try:
                rows = conn.execute(
                    "SELECT drop_id, title, tags, source, chunk_text, bm25(knowledge_fts) AS rank "
                    "FROM knowledge_fts WHERE knowledge_fts MATCH ? "
                    "ORDER BY rank LIMIT ?",
                    (fts_query, limit)
                ).fetchall()
                results = [dict(r) for r in rows]
            except Exception:
                results = []

        if not results:
            rows = conn.execute(
                "SELECT id AS drop_id, title, tags, source, "
                "COALESCE(summary || '\n' || SUBSTR(raw_content, 1, 600), summary) AS chunk_text "
                "FROM drops ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
            results = [dict(r) for r in rows]

    return results


# ─── DROPS / IDEA BOXES CRUD ───
def add_drop(title: str, summary: str = "", drop_type: str = "idea",
             tags: str = "", source: str = "", raw_content: str = "",
             links: list[str] | None = None, due_date: str | None = None) -> int:
    links_json = json.dumps(links or [])
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO drops (title, summary, type, tags, source, raw_content, links, due_date) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (title, summary, drop_type, tags, source, raw_content, links_json, due_date)
        )
        drop_id = cursor.lastrowid

    combined_text = f"{title}\n{summary}\n{raw_content}\n{' '.join(links or [])}".strip()
    index_knowledge_chunks(drop_id, title, tags, source, combined_text)
    return drop_id


def get_drop_by_id(drop_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM drops WHERE id = ?", (drop_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["links_list"] = _parse_links(d.get("links"))
        return d


def add_link_to_drop(drop_id: int, url: str) -> list[str]:
    url = url.strip()
    if not url:
        return []
    if not re.match(r"^[a-zA-Z]+://", url):
        url = "https://" + url

    with get_db() as conn:
        row = conn.execute(
            "SELECT id, title, summary, tags, source, raw_content, links FROM drops WHERE id = ?",
            (drop_id,)
        ).fetchone()
        if not row:
            return []
        current_links = _parse_links(row["links"])
        if url not in current_links:
            current_links.append(url)
        conn.execute(
            "UPDATE drops SET links = ? WHERE id = ?",
            (json.dumps(current_links), drop_id)
        )

    combined = f"{row['title']}\n{row['summary'] or ''}\n{row['raw_content'] or ''}\n{' '.join(current_links)}".strip()
    index_knowledge_chunks(drop_id, row["title"], row["tags"] or "", row["source"] or "", combined)
    return current_links


def remove_link_from_drop(drop_id: int, url: str) -> list[str]:
    with get_db() as conn:
        row = conn.execute("SELECT links FROM drops WHERE id = ?", (drop_id,)).fetchone()
        if not row:
            return []
        current_links = [u for u in _parse_links(row["links"]) if u != url]
        conn.execute("UPDATE drops SET links = ? WHERE id = ?", (json.dumps(current_links), drop_id))
        return current_links


def update_drop_due_date(drop_id: int, due_date: str | None):
    with get_db() as conn:
        conn.execute("UPDATE drops SET due_date = ? WHERE id = ?", (due_date, drop_id))


def delete_drop(drop_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM drops WHERE id = ?", (drop_id,))
        conn.execute("DELETE FROM knowledge_fts WHERE drop_id = ?", (str(drop_id),))


def get_recent_drops(limit: int = 15) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, title, summary, type, tags, source, raw_content, links, due_date, created_at "
            "FROM drops WHERE type != 'task' ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["links_list"] = _parse_links(d.get("links"))
            out.append(d)
        return out


def get_recent_ideas(limit: int = 15) -> list[dict]:
    return get_recent_drops(limit=limit)


# ─── TASKS CRUD (WITH FULL DETAIL PAGE FIELDS: DESCRIPTION, LINKS, DUE DATE, CREATED_AT, RAW_TEXT) ───
def add_task(title: str, due_date: str | None = None, tags: str = "",
             drop_id: int | None = None, description: str = "",
             raw_text: str = "", links: list[str] | None = None) -> int:
    links_json = json.dumps(links or [])
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO tasks (title, description, raw_text, links, due_date, tags, drop_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (title, description, raw_text or title, links_json, due_date, tags, drop_id)
        )
        return cursor.lastrowid


def get_task_by_id(task_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            return None
        t = dict(row)
        t["links_list"] = _parse_links(t.get("links"))
        return t


def add_link_to_task(task_id: int, url: str) -> list[str]:
    url = url.strip()
    if not url:
        return []
    if not re.match(r"^[a-zA-Z]+://", url):
        url = "https://" + url

    with get_db() as conn:
        row = conn.execute("SELECT links, drop_id FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            return []
        current_links = _parse_links(row["links"])
        if url not in current_links:
            current_links.append(url)
        conn.execute("UPDATE tasks SET links = ? WHERE id = ?", (json.dumps(current_links), task_id))
        if row["drop_id"]:
            add_link_to_drop(int(row["drop_id"]), url)
        return current_links


def remove_link_from_task(task_id: int, url: str) -> list[str]:
    with get_db() as conn:
        row = conn.execute("SELECT links, drop_id FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            return []
        current_links = [u for u in _parse_links(row["links"]) if u != url]
        conn.execute("UPDATE tasks SET links = ? WHERE id = ?", (json.dumps(current_links), task_id))
        if row["drop_id"]:
            remove_link_from_drop(int(row["drop_id"]), url)
        return current_links


def update_task_due_date(task_id: int, due_date: str | None):
    with get_db() as conn:
        conn.execute("UPDATE tasks SET due_date = ? WHERE id = ?", (due_date, task_id))


def get_pending_tasks(limit: int = 20) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, drop_id, title, description, raw_text, links, status, due_date, tags, created_at "
            "FROM tasks WHERE status = 'todo' "
            "ORDER BY CASE WHEN tags LIKE '%#urgent%' THEN 0 ELSE 1 END, "
            "CASE WHEN due_date IS NOT NULL AND due_date != '' THEN 0 ELSE 1 END, "
            "created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        out = []
        for r in rows:
            t = dict(r)
            t["links_list"] = _parse_links(t.get("links"))
            out.append(t)
        return out


def toggle_task_status(task_id: int) -> str:
    with get_db() as conn:
        row = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            return "todo"
        new_status = "done" if row["status"] == "todo" else "todo"
        completed_val = "CURRENT_TIMESTAMP" if new_status == "done" else "NULL"
        conn.execute(
            f"UPDATE tasks SET status = ?, completed_at = {completed_val} WHERE id = ?",
            (new_status, task_id)
        )
        return new_status


def delete_task(task_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))


def update_task(task_id: int, title: str, tags: str = "", due_date: str | None = None, description: str | None = None):
    with get_db() as conn:
        if description is not None:
            conn.execute(
                "UPDATE tasks SET title = ?, tags = ?, due_date = ?, description = ? WHERE id = ?",
                (title, tags, due_date, description, task_id)
            )
        else:
            conn.execute(
                "UPDATE tasks SET title = ?, tags = ?, due_date = ? WHERE id = ?",
                (title, tags, due_date, task_id)
            )


def clear_completed_tasks() -> int:
    with get_db() as conn:
        cur = conn.execute("DELETE FROM tasks WHERE status = 'done'")
        return cur.rowcount


init_db()
