<!-- SPDX-License-Identifier: MIT
Copyright (c) 2026 Ludovic Stumme
-->
<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import * as api from '$lib/api.js';
  import { t } from '$lib/i18n.svelte.js';

  let folders = $state([]);
  let tracks = $state([]);
  let error = $state(null);
  let uploading = $state(false);
  let newFolderName = $state('');
  let pollTimer = null;

  let currentFolderId = $derived($page.url.searchParams.get('folder') || null);

  let byId = $derived(new Map(folders.map((f) => [f.id, f])));

  let crumbs = $derived.by(() => {
    const chain = [];
    let cur = currentFolderId;
    while (cur) {
      const f = byId.get(cur);
      if (!f) break;
      chain.unshift(f);
      cur = f.parent_id;
    }
    return chain;
  });

  let subfolders = $derived(
    folders.filter((f) => (f.parent_id || null) === currentFolderId)
  );

  function pathLabel(id) {
    const parts = [];
    let cur = id;
    while (cur) {
      const f = byId.get(cur);
      if (!f) break;
      parts.unshift(f.name);
      cur = f.parent_id;
    }
    return parts.join(' / ');
  }

  function descendantIds(rootId) {
    const childrenOf = new Map();
    for (const f of folders) {
      const p = f.parent_id || null;
      (childrenOf.get(p) ?? childrenOf.set(p, []).get(p)).push(f.id);
    }
    const out = new Set([rootId]);
    const stack = [rootId];
    while (stack.length) {
      for (const c of childrenOf.get(stack.pop()) ?? []) {
        out.add(c);
        stack.push(c);
      }
    }
    return out;
  }

  async function loadFolders() {
    folders = await api.listFolders();
  }

  async function loadTracks() {
    tracks = await api.listTracks(currentFolderId);
    const pending = tracks.some((t) => t.status === 'pending');
    if (pending && !pollTimer) pollTimer = setInterval(loadTracks, 3000);
    else if (!pending && pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  // Refetch tracks whenever the current folder changes.
  $effect(() => {
    currentFolderId;
    loadTracks().catch((e) => (error = String(e)));
  });

  onMount(() => {
    loadFolders().catch((e) => (error = String(e)));
    return () => pollTimer && clearInterval(pollTimer);
  });

  function navigate(id) {
    goto(id ? `/?folder=${id}` : '/');
  }

  async function createFolder() {
    const name = newFolderName.trim();
    if (!name) return;
    try {
      await api.createFolder(name, currentFolderId);
      newFolderName = '';
      await loadFolders();
    } catch (e) {
      error = String(e);
    }
  }

  async function renameFolder(f, ev) {
    ev.stopPropagation();
    const name = prompt(t('home.prompt_rename_folder'), f.name);
    if (!name || name === f.name) return;
    await api.patchFolder(f.id, { name });
    await loadFolders();
  }

  async function deleteFolder(f, ev) {
    ev.stopPropagation();
    if (!confirm(t('home.confirm_delete_folder', { name: f.name }))) return;
    await api.deleteFolder(f.id);
    await Promise.all([loadFolders(), loadTracks()]);
  }

  async function onFile(ev) {
    const file = ev.target.files?.[0];
    if (!file) return;
    uploading = true;
    error = null;
    try {
      await api.uploadTrack(file, currentFolderId);
      ev.target.value = '';
      await loadTracks();
    } catch (e) {
      error = String(e);
    } finally {
      uploading = false;
    }
  }

  async function removeTrack(id, ev) {
    ev.stopPropagation();
    if (!confirm(t('home.confirm_delete_track'))) return;
    await api.deleteTrack(id);
    await loadTracks();
  }

  async function moveTrack(id, dest) {
    await api.patchTrack(id, { folder_id: dest || null });
    await loadTracks();
  }

  async function moveFolder(id, dest) {
    try {
      await api.patchFolder(id, { parent_id: dest || null });
      await loadFolders();
    } catch (e) {
      error = String(e);
    }
  }

  function fmtDuration(s) {
    if (!s) return '';
    const m = Math.floor(s / 60);
    return `${m}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
  }

  function statusLabel(s) {
    return {
      pending: t('status.processing'),
      done: t('status.ready'),
      error: t('status.error'),
    }[s] ?? s;
  }
</script>

<!-- Breadcrumb -->
<nav class="crumbs">
  <button class="crumb" onclick={() => navigate(null)}>{t('nav.root')}</button>
  {#each crumbs as c (c.id)}
    <span class="sep">/</span>
    <button class="crumb" onclick={() => navigate(c.id)}>{c.name}</button>
  {/each}
</nav>

<!-- Toolbar: new folder + upload -->
<section class="toolbar">
  <div class="newfolder">
    <input
      type="text"
      placeholder={t('home.new_folder_placeholder')}
      bind:value={newFolderName}
      onkeydown={(e) => e.key === 'Enter' && createFolder()}
    />
    <button onclick={createFolder}>{t('home.new_folder_button')}</button>
  </div>
  <label class="upload-btn">
    <input type="file" accept="audio/*" onchange={onFile} disabled={uploading} />
    <span>{uploading ? t('home.uploading') : t('home.upload_button')}</span>
  </label>
</section>

{#if error}<p class="err">{error}</p>{/if}

<!-- Subfolders -->
{#if subfolders.length}
  <ul class="list">
    {#each subfolders as f (f.id)}
      <li class="row folder" onclick={() => navigate(f.id)} role="button" tabindex="0"
          onkeydown={(e) => e.key === 'Enter' && navigate(f.id)}>
        <span class="icon">📁</span>
        <span class="name">{f.name}</span>
        <select
          class="move"
          onclick={(e) => e.stopPropagation()}
          onchange={(e) => { moveFolder(f.id, e.target.value); e.target.selectedIndex = 0; }}
        >
          <option value="" disabled selected>{t('action.move_to')}</option>
          {#if (f.parent_id || null) !== null}<option value="">{t('nav.root')}</option>{/if}
          {#each folders.filter((o) => !descendantIds(f.id).has(o.id) && o.id !== (f.parent_id || '')) as o (o.id)}
            <option value={o.id}>{pathLabel(o.id)}</option>
          {/each}
        </select>
        <button class="act" onclick={(e) => renameFolder(f, e)} aria-label={t('aria.rename')}>✎</button>
        <button class="act" onclick={(e) => deleteFolder(f, e)} aria-label={t('aria.delete')}>×</button>
      </li>
    {/each}
  </ul>
{/if}

<!-- Tracks -->
{#if tracks.length}
  <ul class="list">
    {#each tracks as track (track.id)}
      <li class="row track" class:done={track.status === 'done'}
          onclick={() => track.status === 'done' && goto(`/tracks/${track.id}`)}
          role="button" tabindex="0"
          onkeydown={(e) => e.key === 'Enter' && track.status === 'done' && goto(`/tracks/${track.id}`)}>
        <span class="icon">🎵</span>
        <div class="info">
          <div class="name">{track.filename}</div>
          <div class="meta">
            <span class="status status-{track.status}">{statusLabel(track.status)}</span>
            {#if track.bpm}<span>{Math.round(track.bpm)} BPM</span>{/if}
            {#if track.key}<span>{track.key}</span>{/if}
            {#if track.duration}<span>{fmtDuration(track.duration)}</span>{/if}
            {#if track.note}<span title={t('track.notes_indicator')}>📝</span>{/if}
            {#if track.attachment_count}<span title={t('track.attachments_indicator')}>📎</span>{/if}
          </div>
          {#if track.error}<div class="err small">{track.error}</div>{/if}
        </div>
        <select
          class="move"
          onclick={(e) => e.stopPropagation()}
          onchange={(e) => { moveTrack(track.id, e.target.value); e.target.selectedIndex = 0; }}
        >
          <option value="" disabled selected>{t('action.move_to')}</option>
          {#if currentFolderId !== null}<option value="">{t('nav.root')}</option>{/if}
          {#each folders.filter((o) => o.id !== currentFolderId) as o (o.id)}
            <option value={o.id}>{pathLabel(o.id)}</option>
          {/each}
        </select>
        <button class="act" onclick={(e) => removeTrack(track.id, e)} aria-label={t('aria.delete')}>×</button>
      </li>
    {/each}
  </ul>
{/if}

{#if !subfolders.length && !tracks.length}
  <p class="empty">{t('home.empty_folder')}</p>
{/if}

<style>
  .crumbs {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 4px;
    margin-bottom: 16px;
    font-size: 14px;
  }
  .crumb {
    background: transparent;
    border: none;
    color: var(--fg-dim);
    padding: 4px 6px;
    border-radius: 6px;
  }
  .crumb:hover { background: var(--bg-3); color: var(--fg); }
  .crumbs .crumb:last-of-type { color: var(--fg); font-weight: 500; }
  .sep { color: var(--fg-dim); }

  .toolbar {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    margin-bottom: 16px;
  }
  .newfolder { display: flex; gap: 6px; flex: 1; min-width: 220px; }
  .newfolder input {
    flex: 1;
    background: var(--bg-2);
    border: 1px solid var(--border);
    color: var(--fg);
    border-radius: 8px;
    padding: 10px 12px;
  }
  .upload-btn {
    display: inline-flex;
    align-items: center;
    background: var(--accent);
    color: white;
    border-radius: 8px;
    padding: 10px 16px;
    cursor: pointer;
    white-space: nowrap;
  }
  .upload-btn input { display: none; }

  .list { list-style: none; padding: 0; margin: 0 0 10px; display: flex; flex-direction: column; gap: 8px; }
  .row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 14px;
    background: var(--bg-2);
    border: 1px solid var(--border);
    border-radius: 10px;
    cursor: pointer;
  }
  .row:hover { background: var(--bg-3); }
  .row.track:not(.done) { cursor: default; }
  .icon { font-size: 18px; flex-shrink: 0; }
  .info { flex: 1; min-width: 0; }
  .name { font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .folder .name { flex: 1; }
  .meta {
    margin-top: 4px;
    color: var(--fg-dim);
    font-size: 13px;
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
  }
  .status { padding: 2px 8px; border-radius: 4px; font-weight: 500; }
  .status-pending { background: rgba(243, 156, 18, 0.2); color: var(--orange); }
  .status-done { background: rgba(46, 204, 113, 0.18); color: var(--green); }
  .status-error { background: rgba(231, 76, 60, 0.2); color: var(--red); }

  .move {
    background: var(--bg-3);
    color: var(--fg-dim);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 6px 8px;
    font-size: 12px;
    max-width: 120px;
  }
  .act {
    background: transparent;
    color: var(--fg-dim);
    border: none;
    font-size: 18px;
    line-height: 1;
    padding: 4px 8px;
    border-radius: 6px;
    flex-shrink: 0;
  }
  .act:hover { background: var(--bg); color: var(--fg); }

  .empty { color: var(--fg-dim); }
  .err { color: var(--red); margin: 8px 0 0; }
  .err.small { font-size: 12px; margin-top: 4px; }
</style>
