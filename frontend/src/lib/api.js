// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Ludovic Stumme
// API client. In dev, hits the FastAPI on :8765 (VITE_API_URL). In prod (built
// static, served by the same FastAPI) we use relative URLs.
const ORIGIN = import.meta.env.VITE_API_URL ?? '';
const BASE = `${ORIGIN}/api`;

async function json(r) {
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

// ---- health
export async function getHealth() {
  return json(await fetch(`${BASE}/health`));
}

// ---- tracks
export async function listTracks(folderId) {
  const q = folderId ? `?folder_id=${encodeURIComponent(folderId)}` : '';
  return json(await fetch(`${BASE}/tracks${q}`));
}

export async function getTrack(id) {
  return json(await fetch(`${BASE}/tracks/${id}`));
}

export async function uploadTrack(file, folderId) {
  const fd = new FormData();
  fd.append('file', file);
  if (folderId) fd.append('folder_id', folderId);
  return json(await fetch(`${BASE}/tracks`, { method: 'POST', body: fd }));
}

export async function patchTrack(id, patch) {
  return json(
    await fetch(`${BASE}/tracks/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    })
  );
}

export async function deleteTrack(id) {
  return json(await fetch(`${BASE}/tracks/${id}`, { method: 'DELETE' }));
}

export function stemUrl(trackId, stem, pitch = 0) {
  const q = pitch ? `?pitch=${pitch}` : '';
  return `${BASE}/tracks/${trackId}/stems/${stem}${q}`;
}

// ---- folders
export async function listFolders() {
  return json(await fetch(`${BASE}/folders`));
}

export async function createFolder(name, parentId) {
  return json(
    await fetch(`${BASE}/folders`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, parent_id: parentId ?? null }),
    })
  );
}

export async function patchFolder(id, patch) {
  return json(
    await fetch(`${BASE}/folders/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    })
  );
}

export async function deleteFolder(id) {
  return json(await fetch(`${BASE}/folders/${id}`, { method: 'DELETE' }));
}

// ---- attachments
export async function listAttachments(trackId) {
  return json(await fetch(`${BASE}/tracks/${trackId}/attachments`));
}

export async function uploadAttachment(trackId, file) {
  const fd = new FormData();
  fd.append('file', file);
  return json(await fetch(`${BASE}/tracks/${trackId}/attachments`, { method: 'POST', body: fd }));
}

export async function deleteAttachment(attId) {
  return json(await fetch(`${BASE}/attachments/${attId}`, { method: 'DELETE' }));
}

export function attachmentUrl(attId) {
  return `${BASE}/attachments/${attId}`;
}
