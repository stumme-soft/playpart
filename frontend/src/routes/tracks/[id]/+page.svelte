<!-- SPDX-License-Identifier: MIT
Copyright (c) 2026 Ludovic Stumme
-->
<script>
  import { onMount, onDestroy } from 'svelte';
  import { page } from '$app/stores';
  import {
    getTrack, stemUrl, patchTrack,
    listAttachments, uploadAttachment, deleteAttachment, attachmentUrl,
  } from '$lib/api.js';
  import { scheduleClicks } from '$lib/click.js';
  import { t, plural, signed } from '$lib/i18n.svelte.js';

  let track = $state(null);
  let loadError = $state(null);
  let ready = $state(false);

  // Audio engine: plain element map (not rendered, so not reactive).
  const audios = {}; // { stemName: HTMLAudioElement }

  // Reactive mixer state
  let masterVolume = $state(1);
  let volumes = $state({});
  let mutes = $state({});
  let solos = $state({});
  let isPlaying = $state(false);
  let currentTime = $state(0);
  let duration = $state(0);
  let countdown = $state(false);
  let countdownLeft = $state(0);
  let countdownTimer = null;
  let rafId = null;

  // Per-track note (guitar / FX settings)
  let note = $state('');
  let noteStatus = $state('');
  let noteSaveTimer = null;

  // Editable key (auto-detected, may need correction)
  let trackKey = $state('');
  let keyStatus = $state('');
  let keySaveTimer = null;

  // A/B loop + playback speed (transient, per practice session)
  let loopA = $state(null);
  let loopB = $state(null);
  let looping = $state(false);
  let speed = $state(1);

  // Pitch shift in semitones (server-rendered, transient choice).
  // `pitch` is what's currently loaded; `targetPitch` is what the user is
  // dialing in. Applying happens explicitly to avoid rendering every
  // intermediate semitone on the way to the target.
  let pitch = $state(0);
  let targetPitch = $state(0);
  let pitching = $state(false);
  let pitchProgress = $state({}); // { stemName: 'pending' | 'done' | 'error' }
  const PITCH_MAX = 6;

  // Mix persistence (volumes / mutes)
  let mixLoaded = $state(false);
  let mixSaveTimer = null;

  // Attachments (scores, Guitar Pro files, …)
  let attachments = $state([]);
  let attUploading = $state(false);

  function anySolo() {
    return Object.values(solos).some(Boolean);
  }
  function effectiveVolume(name) {
    if (mutes[name]) return 0;
    if (anySolo() && !solos[name]) return 0;
    return (volumes[name] ?? 1) * masterVolume;
  }

  // Apply gain whenever volumes / mutes / solos change.
  $effect(() => {
    for (const name of track?.stems ?? []) {
      const a = audios[name];
      if (a) a.volume = effectiveVolume(name);
    }
  });

  function tickTime() {
    const primary = audios[track?.stems?.[0]];
    if (primary) {
      if (looping && loopA != null && loopB != null && loopB > loopA && primary.currentTime >= loopB) {
        seekTo(loopA);
      }
      currentTime = primary.currentTime;
      const time = primary.currentTime;
      for (const name of track.stems) {
        const a = audios[name];
        if (a && a !== primary && Math.abs(a.currentTime - time) > 0.08) {
          a.currentTime = time;
        }
      }
    }
    rafId = requestAnimationFrame(tickTime);
  }

  onMount(async () => {
    try {
      track = await getTrack($page.params.id);
      if (track.status !== 'done') {
        loadError = t('mixer.not_processed');
        return;
      }
      for (const s of track.stems) {
        volumes[s] = 1;
        mutes[s] = false;
        solos[s] = false;
        const a = new Audio(stemUrl(track.id, s));
        a.preload = 'auto';
        a.preservesPitch = true;
        a.volume = 1;
        audios[s] = a;
      }
      // Restore saved mix (master / volumes / mutes)
      if (track.mix) {
        if (typeof track.mix.master === 'number') masterVolume = track.mix.master;
        for (const s of track.stems) {
          if (track.mix.volumes && s in track.mix.volumes) volumes[s] = track.mix.volumes[s];
          if (track.mix.mutes && s in track.mix.mutes) mutes[s] = track.mix.mutes[s];
        }
      }
      const primary = audios[track.stems[0]];
      primary.addEventListener('loadedmetadata', () => { duration = primary.duration; });
      primary.addEventListener('ended', () => { isPlaying = false; });
      note = track.note ?? '';
      trackKey = track.key ?? '';
      attachments = await listAttachments(track.id);
      ready = true;
      mixLoaded = true;
      rafId = requestAnimationFrame(tickTime);
    } catch (e) {
      loadError = String(e);
    }
  });

  onDestroy(() => {
    if (rafId) cancelAnimationFrame(rafId);
    if (countdownTimer) clearInterval(countdownTimer);
    if (noteSaveTimer) clearTimeout(noteSaveTimer);
    if (keySaveTimer) clearTimeout(keySaveTimer);
    if (mixSaveTimer) clearTimeout(mixSaveTimer);
    for (const a of Object.values(audios)) a.pause();
  });

  // Persist master / volumes / mutes (debounced) once the initial mix has loaded.
  $effect(() => {
    const snapshot = JSON.stringify([masterVolume, volumes, mutes]);
    if (!mixLoaded) return;
    void snapshot;
    if (mixSaveTimer) clearTimeout(mixSaveTimer);
    mixSaveTimer = setTimeout(saveMix, 600);
  });

  async function playAll() {
    const time = currentTime;
    for (const a of Object.values(audios)) a.currentTime = time;
    try {
      await Promise.all(Object.values(audios).map((a) => a.play()));
      isPlaying = true;
    } catch (e) {
      loadError = t('mixer.play_refused', { error: String(e) });
    }
  }
  function pauseAll() {
    for (const a of Object.values(audios)) a.pause();
    isPlaying = false;
  }
  function togglePlay() {
    if (isPlaying) pauseAll();
    else playAll();
  }
  function seekTo(time) {
    currentTime = time;
    for (const a of Object.values(audios)) a.currentTime = time;
  }

  async function playWithCountIn() {
    if (!track.bpm) return playAll();
    pauseAll();
    seekTo(0);
    const Ctx = window.AudioContext || window.webkitAudioContext;
    const ctx = new Ctx();
    if (ctx.state === 'suspended') await ctx.resume();
    const beats = 4;
    scheduleClicks(ctx, track.bpm, beats, ctx.currentTime + 0.05);
    countdown = true;
    countdownLeft = beats;
    const interval = 60 / track.bpm;
    let n = 0;
    countdownTimer = setInterval(() => {
      n++;
      countdownLeft = beats - n;
      if (n >= beats) {
        clearInterval(countdownTimer);
        countdownTimer = null;
        countdown = false;
        playAll();
      }
    }, interval * 1000);
  }

  function fmtTime(s) {
    if (!isFinite(s)) return '0:00';
    const m = Math.floor(s / 60);
    const r = Math.floor(s % 60);
    return `${m}:${String(r).padStart(2, '0')}`;
  }

  function toggleMute(name) { mutes[name] = !mutes[name]; }
  function toggleSolo(name) { solos[name] = !solos[name]; }

  function resetMix() {
    masterVolume = 1;
    for (const s of track.stems) {
      mutes[s] = false;
      solos[s] = false;
      volumes[s] = 1;
    }
  }

  // A/B loop
  function setA() {
    loopA = currentTime;
    if (loopB != null && loopB <= loopA) loopB = null;
  }
  function setB() {
    if (loopA != null && currentTime > loopA) loopB = currentTime;
  }
  function clearLoop() {
    loopA = null;
    loopB = null;
    looping = false;
  }
  function toggleLoop() {
    looping = !looping;
  }

  // Playback speed (pitch preserved)
  function setSpeed(r) {
    speed = r;
    for (const a of Object.values(audios)) a.playbackRate = r;
  }

  // Pitch shift (whole song, drums excluded). Server renders the stems and
  // caches them per semitone; we swap the audio sources and resume.
  async function setPitch(n) {
    n = Math.max(-PITCH_MAX, Math.min(PITCH_MAX, n));
    if (n === pitch) return;
    const wasPlaying = isPlaying;
    const time = currentTime;
    pauseAll();
    pitch = n;
    // Drums and pitch=0 don't need rendering: mark them done up front.
    pitchProgress = Object.fromEntries(
      track.stems.map((s) => [s, s === 'drums' || n === 0 ? 'done' : 'pending'])
    );
    pitching = true;
    try {
      await Promise.all(track.stems.map((s) => new Promise((resolve, reject) => {
        const a = audios[s];
        const url = stemUrl(track.id, s, s === 'drums' ? 0 : n);
        if (a.src === url) {
          pitchProgress[s] = 'done';
          resolve();
          return;
        }
        const onReady = () => {
          cleanup();
          pitchProgress[s] = 'done';
          resolve();
        };
        const onError = (e) => {
          cleanup();
          pitchProgress[s] = 'error';
          reject(e);
        };
        const cleanup = () => {
          a.removeEventListener('canplay', onReady);
          a.removeEventListener('error', onError);
        };
        a.addEventListener('canplay', onReady);
        a.addEventListener('error', onError);
        a.src = url;
        a.load();
      })));
      for (const a of Object.values(audios)) a.currentTime = time;
      if (wasPlaying) await playAll();
    } catch (e) {
      loadError = t('mixer.pitch_failed', { error: String(e) });
    } finally {
      pitching = false;
    }
  }

  async function saveMix() {
    if (!mixLoaded) return;
    try {
      await patchTrack(track.id, {
        mix: { master: masterVolume, volumes: { ...volumes }, mutes: { ...mutes } },
      });
    } catch (e) {
      /* non-blocking */
    }
  }

  // Attachments
  async function onAttachFile(ev) {
    const file = ev.target.files?.[0];
    if (!file) return;
    attUploading = true;
    try {
      await uploadAttachment(track.id, file);
      ev.target.value = '';
      attachments = await listAttachments(track.id);
    } catch (e) {
      loadError = String(e);
    } finally {
      attUploading = false;
    }
  }
  async function removeAttachment(att) {
    if (!confirm(t('attach.confirm_delete', { filename: att.filename }))) return;
    await deleteAttachment(att.id);
    attachments = await listAttachments(track.id);
  }
  function fmtSize(bytes) {
    if (!bytes) return '';
    if (bytes < 1024) return `${bytes} o`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} Ko`;
    return `${(bytes / 1024 / 1024).toFixed(1)} Mo`;
  }

  function onNoteInput() {
    noteStatus = '';
    if (noteSaveTimer) clearTimeout(noteSaveTimer);
    noteSaveTimer = setTimeout(saveNote, 800);
  }
  async function saveNote() {
    if (noteSaveTimer) { clearTimeout(noteSaveTimer); noteSaveTimer = null; }
    try {
      await patchTrack(track.id, { note });
      noteStatus = t('notes.saved');
    } catch (e) {
      noteStatus = t('notes.save_error');
    }
  }

  function onKeyInput() {
    keyStatus = '';
    if (keySaveTimer) clearTimeout(keySaveTimer);
    keySaveTimer = setTimeout(saveKey, 600);
  }
  async function saveKey() {
    if (keySaveTimer) { clearTimeout(keySaveTimer); keySaveTimer = null; }
    try {
      await patchTrack(track.id, { key: trackKey || null });
      keyStatus = '✓';
      setTimeout(() => { keyStatus = ''; }, 1200);
    } catch (e) {
      keyStatus = 'erreur';
    }
  }
</script>

{#if loadError}
  <p class="err">{loadError}</p>
  <a href="/">{t('nav.back')}</a>
{:else if ready && track}
  <a href="/" class="back">{t('nav.back')}</a>
  <h1>{track.filename}</h1>
  <div class="meta">
    {#if track.bpm}<span>{Math.round(track.bpm)} BPM</span>{/if}
    <span>{fmtTime(duration || track.duration)}</span>
    <span class="key-edit">
      <input
        type="text"
        bind:value={trackKey}
        oninput={onKeyInput}
        onblur={saveKey}
        placeholder={t('mixer.key_placeholder')}
        spellcheck="false"
        size="14"
      />
      {#if keyStatus}<small>{keyStatus}</small>{/if}
    </span>
  </div>

  <div class="transport">
    <button class="primary big" onclick={togglePlay} disabled={countdown}>
      {countdown ? `${countdownLeft}…` : isPlaying ? t('mixer.pause') : t('mixer.play')}
    </button>
    {#if track.bpm}
      <button onclick={playWithCountIn} disabled={countdown}>{t('mixer.play_with_countin')}</button>
    {/if}
  </div>

  <div class="seek">
    <span class="time">{fmtTime(currentTime)}</span>
    <div class="seek-track">
      {#if loopA != null && loopB != null}
        <span class="loop-region"
          style="left:{(loopA / (duration || 1)) * 100}%; width:{((loopB - loopA) / (duration || 1)) * 100}%"
        ></span>
      {/if}
      {#if loopA != null}<span class="marker a" style="left:{(loopA / (duration || 1)) * 100}%"></span>{/if}
      {#if loopB != null}<span class="marker b" style="left:{(loopB / (duration || 1)) * 100}%"></span>{/if}
      <input
        type="range"
        min="0"
        max={duration || 1}
        step="0.1"
        value={currentTime}
        oninput={(e) => seekTo(+e.target.value)}
      />
    </div>
    <span class="time">{fmtTime(duration)}</span>
  </div>

  <div class="controls">
    <div class="ctrl-group">
      <span class="ctrl-label">{t('mixer.label_loop')}</span>
      <button class="small" onclick={setA}>A{loopA != null ? ` ${fmtTime(loopA)}` : ''}</button>
      <button class="small" onclick={setB} disabled={loopA == null}>B{loopB != null ? ` ${fmtTime(loopB)}` : ''}</button>
      <button class="small" class:active={looping} onclick={toggleLoop} disabled={loopA == null || loopB == null}>↻</button>
      <button class="small" onclick={clearLoop} disabled={loopA == null && loopB == null}>✕</button>
    </div>
    <div class="ctrl-group">
      <span class="ctrl-label">{t('mixer.label_speed')}</span>
      {#each [0.5, 0.75, 1] as r (r)}
        <button class="small" class:active={speed === r} onclick={() => setSpeed(r)}>{r}×</button>
      {/each}
    </div>
    <div class="ctrl-group master">
      <span class="ctrl-label">{t('mixer.label_volume')}</span>
      <input
        type="range"
        min="0" max="1" step="0.01"
        bind:value={masterVolume}
        aria-label={t('aria.master_volume')}
      />
      <span class="pitch-val">{Math.round(masterVolume * 100)}%</span>
    </div>
    <div class="ctrl-group">
      <span class="ctrl-label">{t('mixer.label_semitones')}</span>
      <button class="small" onclick={() => targetPitch = Math.max(-PITCH_MAX, targetPitch - 1)} disabled={targetPitch <= -PITCH_MAX}>−</button>
      <span class="pitch-val" class:pending={targetPitch !== pitch}>{targetPitch > 0 ? '+' + targetPitch : targetPitch}</span>
      <button class="small" onclick={() => targetPitch = Math.min(PITCH_MAX, targetPitch + 1)} disabled={targetPitch >= PITCH_MAX}>+</button>
      {#if targetPitch !== 0}<button class="small" onclick={() => targetPitch = 0}>↺</button>{/if}
      <button class="small" onclick={() => setPitch(targetPitch)} disabled={pitching || targetPitch === pitch}>{t('action.apply')}</button>
    </div>
  </div>

  <div class="mixer">
    {#each track.stems as s (s)}
      {@const muted = mutes[s] || (anySolo() && !solos[s])}
      <div class="strip" class:muted>
        <div class="strip-head">
          <span class="strip-name">{s}</span>
          <div class="strip-btns">
            <button class="tag" class:on={mutes[s]} onclick={() => toggleMute(s)}>M</button>
            <button class="tag solo" class:on={solos[s]} onclick={() => toggleSolo(s)}>S</button>
          </div>
        </div>
        <input type="range" min="0" max="1" step="0.01" bind:value={volumes[s]} />
      </div>
    {/each}
  </div>

  <div class="presets">
    <button class="small" onclick={resetMix}>{t('mixer.reset_mix')}</button>
  </div>

  <section class="notes">
    <div class="notes-head">
      <h2>{t('notes.section_title')}</h2>
      {#if noteStatus}<span class="note-status">{noteStatus}</span>{/if}
    </div>
    <textarea
      placeholder={t('notes.placeholder')}
      bind:value={note}
      oninput={onNoteInput}
      onblur={saveNote}
      rows="6"
    ></textarea>
  </section>

  <section class="attachments">
    <div class="att-head">
      <h2>{t('attach.section_title')}</h2>
      <label class="att-add">
        <input type="file" onchange={onAttachFile} disabled={attUploading} />
        <span>{attUploading ? t('attach.uploading') : t('attach.add')}</span>
      </label>
    </div>
    {#if attachments.length}
      <ul class="att-list">
        {#each attachments as a (a.id)}
          <li class="att-row">
            <a href={attachmentUrl(a.id)} target="_blank" rel="noopener" class="att-name">
              📎 {a.filename}
            </a>
            <span class="att-size">{fmtSize(a.size)}</span>
            <button class="act" onclick={() => removeAttachment(a)} aria-label={t('aria.delete')}>×</button>
          </li>
        {/each}
      </ul>
    {:else}
      <p class="att-empty">{t('attach.empty')}</p>
    {/if}
  </section>

  {#if pitching}
    <div class="overlay" role="dialog" aria-label={t('aria.transposition_in_progress')}>
      <div class="progress-card">
        <h3>{t('pitch.transposing_to', { signed: signed(targetPitch), plural: plural(targetPitch) })}</h3>
        <ul class="progress-stems">
          {#each track.stems as s (s)}
            <li class="prog-line" class:done={pitchProgress[s] === 'done'} class:err={pitchProgress[s] === 'error'}>
              <span class="prog-icon">
                {#if pitchProgress[s] === 'done'}✓{:else if pitchProgress[s] === 'error'}✕{:else}⏳{/if}
              </span>
              <span class="prog-name">{s}</span>
            </li>
          {/each}
        </ul>
        <p class="hint">{t('pitch.modal_hint')}</p>
      </div>
    </div>
  {/if}
{:else}
  <p>{t('mixer.loading')}</p>
{/if}

<style>
  .back {
    color: var(--fg-dim);
    font-size: 14px;
    display: inline-block;
    margin-bottom: 12px;
  }
  h1 {
    font-size: 18px;
    font-weight: 600;
    margin: 0 0 4px;
    word-break: break-word;
  }
  .meta {
    color: var(--fg-dim);
    font-size: 13px;
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 18px;
    flex-wrap: wrap;
  }
  .key-edit {
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }
  .key-edit input {
    background: transparent;
    border: 1px dashed var(--border);
    border-radius: 4px;
    color: var(--fg-dim);
    padding: 2px 6px;
    font-size: 13px;
    font-family: inherit;
  }
  .key-edit input:focus,
  .key-edit input:hover {
    outline: none;
    border-style: solid;
    color: var(--fg);
  }
  .key-edit small { color: var(--green); }
  .err { color: var(--red); }

  .transport {
    display: flex;
    gap: 10px;
    margin-bottom: 14px;
    flex-wrap: wrap;
  }
  .big { font-size: 16px; padding: 14px 22px; min-width: 130px; }

  .seek {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 14px;
  }
  .seek .time {
    color: var(--fg-dim);
    font-size: 13px;
    font-variant-numeric: tabular-nums;
    min-width: 42px;
  }
  .seek-track {
    position: relative;
    flex: 1;
    display: flex;
    align-items: center;
  }
  .seek-track input { width: 100%; }
  .marker {
    position: absolute;
    top: 50%;
    transform: translateY(-50%);
    width: 2px;
    height: 18px;
    pointer-events: none;
    z-index: 1;
  }
  .marker.a { background: var(--green); }
  .marker.b { background: var(--accent); }
  .loop-region {
    position: absolute;
    top: 50%;
    transform: translateY(-50%);
    height: 6px;
    background: rgba(46, 204, 113, 0.25);
    border-radius: 3px;
    pointer-events: none;
  }

  .controls {
    display: flex;
    flex-wrap: wrap;
    gap: 18px;
    margin-bottom: 22px;
  }
  .ctrl-group {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
  }
  .ctrl-group.master {
    flex: 1 1 220px;
    min-width: 200px;
  }
  .ctrl-group.master input[type="range"] {
    flex: 1;
    min-width: 120px;
  }
  .ctrl-label {
    color: var(--fg-dim);
    font-size: 13px;
    margin-right: 2px;
  }
  .pitch-val {
    min-width: 32px;
    text-align: center;
    font-variant-numeric: tabular-nums;
    font-weight: 500;
  }
  .pitch-val.pending {
    color: var(--orange);
  }
  .ctrl-status {
    color: var(--orange);
    font-size: 12px;
    margin-left: 6px;
  }

  .overlay {
    position: fixed;
    inset: 0;
    background: rgba(14, 14, 16, 0.85);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 50;
    padding: 20px;
  }
  .progress-card {
    background: var(--bg-2);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 24px;
    max-width: 360px;
    width: 100%;
  }
  .progress-card h3 {
    margin: 0 0 14px;
    font-size: 16px;
    font-weight: 600;
  }
  .progress-stems {
    list-style: none;
    padding: 0;
    margin: 0 0 14px;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .prog-line {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 6px 0;
    color: var(--fg-dim);
  }
  .prog-line.done { color: var(--green); }
  .prog-line.err { color: var(--red); }
  .prog-icon {
    width: 20px;
    text-align: center;
    font-weight: 600;
  }
  .prog-name { text-transform: capitalize; color: var(--fg); }
  .hint {
    color: var(--fg-dim);
    font-size: 12px;
    margin: 0;
  }

  .mixer {
    display: grid;
    grid-template-columns: 1fr;
    gap: 10px;
    margin-bottom: 18px;
  }
  @media (min-width: 720px) {
    .mixer { grid-template-columns: 1fr 1fr; }
  }
  .strip {
    background: var(--bg-2);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 12px 14px;
    transition: opacity 0.15s;
  }
  .strip.muted { opacity: 0.4; }
  .strip-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 4px;
  }
  .strip-name {
    text-transform: capitalize;
    font-weight: 500;
  }
  .strip-btns { display: flex; gap: 6px; }
  .tag {
    width: 36px;
    padding: 6px 0;
    text-align: center;
    font-weight: 600;
    font-size: 12px;
    background: var(--bg-3);
  }
  .tag.on { background: var(--orange); color: #1a1a1f; border-color: var(--orange); }
  .tag.solo.on { background: var(--green); border-color: var(--green); }

  .presets {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: center;
    padding-top: 16px;
    border-top: 1px solid var(--border);
  }
  button.small {
    padding: 6px 12px;
    font-size: 13px;
    text-transform: capitalize;
  }
  button.small.active {
    background: var(--accent);
    color: #fff;
    border-color: var(--accent);
  }

  .notes {
    margin-top: 24px;
    padding-top: 16px;
    border-top: 1px solid var(--border);
  }
  .notes-head {
    display: flex;
    align-items: baseline;
    gap: 12px;
    margin-bottom: 8px;
  }
  .notes-head h2 {
    font-size: 15px;
    font-weight: 600;
    margin: 0;
    color: var(--fg-dim);
  }
  .note-status {
    font-size: 12px;
    color: var(--green);
  }
  .notes textarea {
    width: 100%;
    background: var(--bg-2);
    color: var(--fg);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 12px 14px;
    font-family: inherit;
    font-size: 14px;
    line-height: 1.5;
    resize: vertical;
  }
  .notes textarea:focus {
    outline: none;
    border-color: var(--fg-dim);
  }

  .attachments {
    margin-top: 24px;
    padding-top: 16px;
    border-top: 1px solid var(--border);
  }
  .att-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 10px;
  }
  .att-head h2 {
    font-size: 15px;
    font-weight: 600;
    margin: 0;
    color: var(--fg-dim);
  }
  .att-add {
    display: inline-flex;
    align-items: center;
    background: var(--bg-3);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px 14px;
    cursor: pointer;
    font-size: 13px;
  }
  .att-add:hover { background: #30303a; }
  .att-add input { display: none; }
  .att-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 6px; }
  .att-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    background: var(--bg-2);
    border: 1px solid var(--border);
    border-radius: 8px;
  }
  .att-name {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--fg);
  }
  .att-name:hover { text-decoration: underline; }
  .att-size {
    color: var(--fg-dim);
    font-size: 12px;
    font-variant-numeric: tabular-nums;
    flex-shrink: 0;
  }
  .att-empty { color: var(--fg-dim); font-size: 13px; }
</style>
