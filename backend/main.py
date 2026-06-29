# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ludovic Stumme
"""FastAPI entry point: upload, list, stream stems, delete tracks."""

from __future__ import annotations

import json
import mimetypes
import os
import shutil
from concurrent.futures import Future, ProcessPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__, db, tasks

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("MUSICAPP_DATA") or (ROOT / "data"))
TRACKS_DIR = DATA_DIR / "tracks"
STEMS_DIR = DATA_DIR / "stems"
ATTACH_DIR = DATA_DIR / "attachments"
DB_PATH = DATA_DIR / "music.db"
FRONTEND_BUILD = ROOT / "frontend" / "build"

ALLOWED_EXT = {".mp3", ".wav", ".flac", ".m4a", ".ogg"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    for d in (DATA_DIR, TRACKS_DIR, STEMS_DIR, ATTACH_DIR):
        d.mkdir(parents=True, exist_ok=True)
    db.init(DB_PATH)
    app.state.executor = ProcessPoolExecutor(
        max_workers=1, initializer=tasks.worker_init
    )
    try:
        yield
    finally:
        app.state.executor.shutdown(wait=False, cancel_futures=True)


app = FastAPI(title="PlayPart", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _on_job_done(track_id: str, fut: Future) -> None:
    try:
        result = fut.result()
        db.update_metadata(track_id, result["bpm"], result["duration"], result.get("key"))
        db.update_status(track_id, "done")
    except Exception as exc:
        db.update_status(track_id, "error", repr(exc))


class TrackPatch(BaseModel):
    folder_id: str | None = None
    note: str | None = None
    mix: dict | None = None
    key: str | None = None


def _track_out(track: dict) -> dict:
    """Parse the JSON-encoded mix column into an object for the client."""
    if track.get("mix"):
        try:
            track["mix"] = json.loads(track["mix"])
        except (ValueError, TypeError):
            track["mix"] = None
    return track


class FolderCreate(BaseModel):
    name: str
    parent_id: str | None = None


class FolderPatch(BaseModel):
    name: str | None = None
    parent_id: str | None = None


def _is_descendant(folder_id: str, candidate_ancestor: str) -> bool:
    """True if folder_id is, or is a descendant of, candidate_ancestor."""
    folders = {f["id"]: f for f in db.list_folders()}
    cur: str | None = folder_id
    while cur is not None:
        if cur == candidate_ancestor:
            return True
        cur = folders.get(cur, {}).get("parent_id")
    return False


@app.post("/api/tracks")
async def upload_track(
    file: UploadFile = File(...),
    folder_id: str | None = Form(None),
):
    if not file.filename:
        raise HTTPException(400, "Filename required")
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"Unsupported extension: {ext}")
    folder_id = folder_id or None
    if folder_id and not db.get_folder(folder_id):
        raise HTTPException(404, "Folder not found")

    track_id = db.insert_track(file.filename, folder_id)
    audio_path = TRACKS_DIR / f"{track_id}{ext}"
    audio_path.write_bytes(await file.read())
    stems_dir = STEMS_DIR / track_id

    fut = app.state.executor.submit(
        tasks.process_track, str(audio_path), str(stems_dir)
    )
    fut.add_done_callback(lambda f: _on_job_done(track_id, f))
    return _track_out(db.get_track(track_id))


@app.get("/api/tracks")
def list_tracks(folder_id: str | None = None):
    return [_track_out(t) for t in db.list_tracks(folder_id or None)]


@app.patch("/api/tracks/{track_id}")
def patch_track(track_id: str, patch: TrackPatch):
    if not db.get_track(track_id):
        raise HTTPException(404, "Track not found")
    if "folder_id" in patch.model_fields_set:
        if patch.folder_id and not db.get_folder(patch.folder_id):
            raise HTTPException(404, "Folder not found")
        db.set_track_folder(track_id, patch.folder_id)
    if "note" in patch.model_fields_set:
        db.set_track_note(track_id, patch.note)
    if "mix" in patch.model_fields_set:
        db.set_track_mix(track_id, json.dumps(patch.mix) if patch.mix is not None else None)
    if "key" in patch.model_fields_set:
        db.set_track_key(track_id, patch.key)
    return _track_out(db.get_track(track_id))


@app.post("/api/tracks/{track_id}/detect-key")
def detect_key(track_id: str):
    """Recompute the key for an existing track (e.g. one ingested before
    key detection existed). Runs librosa in the request thread; quick (~few s)."""
    if not db.get_track(track_id):
        raise HTTPException(404, "Track not found")
    audio = next(TRACKS_DIR.glob(f"{track_id}.*"), None)
    if not audio:
        raise HTTPException(404, "Audio file missing")
    key = tasks.detect_key_from_file(str(audio))
    db.set_track_key(track_id, key)
    return _track_out(db.get_track(track_id))


@app.get("/api/tracks/{track_id}")
def get_track(track_id: str):
    track = db.get_track(track_id)
    if not track:
        raise HTTPException(404, "Track not found")
    stems_dir = STEMS_DIR / track_id
    track["stems"] = (
        sorted(p.stem for p in stems_dir.glob("*.wav"))
        if stems_dir.is_dir()
        else []
    )
    return _track_out(track)


_PITCH_RANGE = 6


@app.get("/api/tracks/{track_id}/stems/{stem_name}")
def get_stem(track_id: str, stem_name: str, pitch: int = 0):
    base = STEMS_DIR / track_id
    original = base / f"{stem_name}.wav"
    if not original.is_file():
        raise HTTPException(404, "Stem not found")
    # Drums are never pitch-shifted; pitch out of range falls back to original.
    if pitch == 0 or stem_name == "drums" or abs(pitch) > _PITCH_RANGE:
        return FileResponse(original, media_type="audio/wav")
    sign = "+" if pitch > 0 else "-"
    pitched = base / f"p{sign}{abs(pitch)}" / f"{stem_name}.wav"
    if not pitched.is_file():
        tasks.render_pitch_shifted(str(original), pitched, pitch)
    return FileResponse(pitched, media_type="audio/wav")


@app.delete("/api/tracks/{track_id}")
def delete_track(track_id: str):
    track = db.get_track(track_id)
    if not track:
        raise HTTPException(404, "Track not found")
    stems_dir = STEMS_DIR / track_id
    if stems_dir.is_dir():
        shutil.rmtree(stems_dir)
    att_dir = ATTACH_DIR / track_id
    if att_dir.is_dir():
        shutil.rmtree(att_dir)
    for p in TRACKS_DIR.glob(f"{track_id}.*"):
        p.unlink(missing_ok=True)
    db.delete_attachments_for_track(track_id)
    db.delete_track(track_id)
    return {"deleted": track_id}


@app.post("/api/tracks/{track_id}/attachments")
async def upload_attachment(track_id: str, file: UploadFile = File(...)):
    if not db.get_track(track_id):
        raise HTTPException(404, "Track not found")
    if not file.filename:
        raise HTTPException(400, "Filename required")
    data = await file.read()
    ext = Path(file.filename).suffix.lower()
    att_dir = ATTACH_DIR / track_id
    att_dir.mkdir(parents=True, exist_ok=True)
    att_id = db.insert_attachment(track_id, file.filename, "", len(data))
    stored_name = f"{att_id}{ext}"
    (att_dir / stored_name).write_bytes(data)
    db.set_attachment_stored_name(att_id, stored_name)
    return db.get_attachment(att_id)


@app.get("/api/tracks/{track_id}/attachments")
def list_attachments(track_id: str):
    if not db.get_track(track_id):
        raise HTTPException(404, "Track not found")
    return db.list_attachments(track_id)


@app.get("/api/attachments/{att_id}")
def download_attachment(att_id: str):
    att = db.get_attachment(att_id)
    if not att:
        raise HTTPException(404, "Attachment not found")
    path = ATTACH_DIR / att["track_id"] / att["stored_name"]
    if not path.is_file():
        raise HTTPException(404, "File missing")
    media_type, _ = mimetypes.guess_type(att["filename"])
    # inline so browsers preview what they can (PDF, images); others download.
    disposition = f"inline; filename*=UTF-8''{quote(att['filename'])}"
    return FileResponse(
        path,
        media_type=media_type or "application/octet-stream",
        headers={"Content-Disposition": disposition},
    )


@app.delete("/api/attachments/{att_id}")
def delete_attachment(att_id: str):
    att = db.get_attachment(att_id)
    if not att:
        raise HTTPException(404, "Attachment not found")
    path = ATTACH_DIR / att["track_id"] / att["stored_name"]
    path.unlink(missing_ok=True)
    db.delete_attachment(att_id)
    return {"deleted": att_id}


@app.post("/api/folders")
def create_folder(payload: FolderCreate):
    if payload.parent_id and not db.get_folder(payload.parent_id):
        raise HTTPException(404, "Parent folder not found")
    folder_id = db.insert_folder(payload.name, payload.parent_id)
    return db.get_folder(folder_id)


@app.get("/api/folders")
def list_folders():
    return db.list_folders()


@app.patch("/api/folders/{folder_id}")
def patch_folder(folder_id: str, patch: FolderPatch):
    if not db.get_folder(folder_id):
        raise HTTPException(404, "Folder not found")
    if "name" in patch.model_fields_set and patch.name:
        db.rename_folder(folder_id, patch.name)
    if "parent_id" in patch.model_fields_set:
        new_parent = patch.parent_id
        if new_parent:
            if not db.get_folder(new_parent):
                raise HTTPException(404, "Target folder not found")
            if _is_descendant(new_parent, folder_id):
                raise HTTPException(400, "Cannot move a folder into itself or a descendant")
        db.move_folder(folder_id, new_parent)
    return db.get_folder(folder_id)


@app.delete("/api/folders/{folder_id}")
def delete_folder(folder_id: str):
    folder = db.get_folder(folder_id)
    if not folder:
        raise HTTPException(404, "Folder not found")
    # Non-destructive: contents move up to this folder's parent.
    db.reparent_contents(folder_id, folder["parent_id"])
    db.delete_folder(folder_id)
    return {"deleted": folder_id}


@app.get("/api/health")
def health():
    import torch

    cuda = torch.cuda.is_available()
    return {
        "status": "ok",
        "version": __version__,
        "device": "cuda" if cuda else "cpu",
        "gpu": torch.cuda.get_device_name(0) if cuda else None,
    }


# Frontend static serving (only when a build is present).
# Registered last so the SPA catch-all doesn't shadow API routes.
if FRONTEND_BUILD.is_dir():
    app.mount("/_app", StaticFiles(directory=FRONTEND_BUILD / "_app"), name="app_assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        candidate = FRONTEND_BUILD / path
        if path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_BUILD / "index.html")
