# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ludovic Stumme
"""SQLite storage for tracks and folders metadata."""

from __future__ import annotations

import sqlite3
import time
import uuid
from pathlib import Path
from typing import Optional

_DB_PATH: Optional[Path] = None


def init(db_path: Path) -> None:
    global _DB_PATH
    _DB_PATH = db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS tracks (
                id          TEXT PRIMARY KEY,
                filename    TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'pending',
                bpm         REAL,
                duration    REAL,
                error       TEXT,
                created_at  REAL NOT NULL,
                folder_id   TEXT,
                note        TEXT,
                mix         TEXT,
                key         TEXT
            );
            CREATE TABLE IF NOT EXISTS folders (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                parent_id   TEXT,
                created_at  REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS attachments (
                id          TEXT PRIMARY KEY,
                track_id    TEXT NOT NULL,
                filename    TEXT NOT NULL,
                stored_name TEXT NOT NULL,
                size        INTEGER,
                created_at  REAL NOT NULL
            );
            """
        )
        # Migration for pre-folders databases.
        cols = [r[1] for r in c.execute("PRAGMA table_info(tracks)").fetchall()]
        if "folder_id" not in cols:
            c.execute("ALTER TABLE tracks ADD COLUMN folder_id TEXT")
        if "note" not in cols:
            c.execute("ALTER TABLE tracks ADD COLUMN note TEXT")
        if "mix" not in cols:
            c.execute("ALTER TABLE tracks ADD COLUMN mix TEXT")
        if "key" not in cols:
            c.execute("ALTER TABLE tracks ADD COLUMN key TEXT")


def _conn() -> sqlite3.Connection:
    assert _DB_PATH is not None, "db.init() must be called first"
    c = sqlite3.connect(_DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


# ---------------------------------------------------------------- tracks

def insert_track(filename: str, folder_id: Optional[str] = None) -> str:
    track_id = uuid.uuid4().hex[:12]
    with _conn() as c:
        c.execute(
            "INSERT INTO tracks (id, filename, created_at, folder_id) VALUES (?, ?, ?, ?)",
            (track_id, filename, time.time(), folder_id),
        )
    return track_id


def update_status(track_id: str, status: str, error: Optional[str] = None) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE tracks SET status = ?, error = ? WHERE id = ?",
            (status, error, track_id),
        )


def update_metadata(track_id: str, bpm: float, duration: float, key: Optional[str] = None) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE tracks SET bpm = ?, duration = ?, key = ? WHERE id = ?",
            (bpm, duration, key, track_id),
        )


def set_track_key(track_id: str, key: Optional[str]) -> None:
    with _conn() as c:
        c.execute("UPDATE tracks SET key = ? WHERE id = ?", (key, track_id))


def set_track_folder(track_id: str, folder_id: Optional[str]) -> None:
    with _conn() as c:
        c.execute("UPDATE tracks SET folder_id = ? WHERE id = ?", (folder_id, track_id))


def set_track_note(track_id: str, note: Optional[str]) -> None:
    with _conn() as c:
        c.execute("UPDATE tracks SET note = ? WHERE id = ?", (note, track_id))


def set_track_mix(track_id: str, mix: Optional[str]) -> None:
    with _conn() as c:
        c.execute("UPDATE tracks SET mix = ? WHERE id = ?", (mix, track_id))


def get_track(track_id: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute("SELECT * FROM tracks WHERE id = ?", (track_id,)).fetchone()
        return dict(row) if row else None


def list_tracks(folder_id: Optional[str] = None) -> list[dict]:
    sql = (
        "SELECT t.*, "
        "(SELECT COUNT(*) FROM attachments a WHERE a.track_id = t.id) AS attachment_count "
        "FROM tracks t WHERE "
    )
    with _conn() as c:
        if folder_id is None:
            rows = c.execute(sql + "t.folder_id IS NULL ORDER BY t.created_at DESC").fetchall()
        else:
            rows = c.execute(
                sql + "t.folder_id = ? ORDER BY t.created_at DESC", (folder_id,)
            ).fetchall()
        return [dict(r) for r in rows]


def delete_track(track_id: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM tracks WHERE id = ?", (track_id,))


# --------------------------------------------------------------- folders

def insert_folder(name: str, parent_id: Optional[str] = None) -> str:
    folder_id = uuid.uuid4().hex[:12]
    with _conn() as c:
        c.execute(
            "INSERT INTO folders (id, name, parent_id, created_at) VALUES (?, ?, ?, ?)",
            (folder_id, name, parent_id, time.time()),
        )
    return folder_id


def get_folder(folder_id: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute("SELECT * FROM folders WHERE id = ?", (folder_id,)).fetchone()
        return dict(row) if row else None


def list_folders() -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT * FROM folders ORDER BY name COLLATE NOCASE").fetchall()
        return [dict(r) for r in rows]


def rename_folder(folder_id: str, name: str) -> None:
    with _conn() as c:
        c.execute("UPDATE folders SET name = ? WHERE id = ?", (name, folder_id))


def move_folder(folder_id: str, parent_id: Optional[str]) -> None:
    with _conn() as c:
        c.execute("UPDATE folders SET parent_id = ? WHERE id = ?", (parent_id, folder_id))


def reparent_contents(folder_id: str, new_parent_id: Optional[str]) -> None:
    """Move the direct children (subfolders + tracks) of a folder to a new parent."""
    with _conn() as c:
        c.execute(
            "UPDATE folders SET parent_id = ? WHERE parent_id = ?",
            (new_parent_id, folder_id),
        )
        c.execute(
            "UPDATE tracks SET folder_id = ? WHERE folder_id = ?",
            (new_parent_id, folder_id),
        )


def delete_folder(folder_id: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM folders WHERE id = ?", (folder_id,))


# ----------------------------------------------------------- attachments

def insert_attachment(track_id: str, filename: str, stored_name: str, size: int) -> str:
    att_id = uuid.uuid4().hex[:12]
    with _conn() as c:
        c.execute(
            "INSERT INTO attachments (id, track_id, filename, stored_name, size, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (att_id, track_id, filename, stored_name, size, time.time()),
        )
    return att_id


def set_attachment_stored_name(att_id: str, stored_name: str) -> None:
    with _conn() as c:
        c.execute("UPDATE attachments SET stored_name = ? WHERE id = ?", (stored_name, att_id))


def get_attachment(att_id: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute("SELECT * FROM attachments WHERE id = ?", (att_id,)).fetchone()
        return dict(row) if row else None


def list_attachments(track_id: str) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM attachments WHERE track_id = ? ORDER BY created_at",
            (track_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def delete_attachment(att_id: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM attachments WHERE id = ?", (att_id,))


def delete_attachments_for_track(track_id: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM attachments WHERE track_id = ?", (track_id,))
