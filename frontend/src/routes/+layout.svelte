<!-- SPDX-License-Identifier: MIT
Copyright (c) 2026 Ludovic Stumme
-->
<script>
  import { onMount } from 'svelte';
  import '../app.css';
  import { t, locale, setLocale, supportedLocales } from '$lib/i18n.svelte.js';
  import { getHealth } from '$lib/api.js';

  const KOFI_URL = 'https://ko-fi.com/stummesoft';

  let { children } = $props();
  let version = $state('');

  onMount(() => {
    getHealth().then((h) => { version = h.version ?? ''; }).catch(() => {});
  });
</script>

<div class="app">
  <header>
    <a href="/" class="brand">
      <img src="/favicon.png" alt="" class="brand-icon" width="32" height="32" />
      <span class="brand-text">
        <span class="brand-name">PlayPart</span>
        <span class="brand-tagline">{t('brand.tagline')}</span>
      </span>
    </a>
    <div class="header-right">
      {#if version}<span class="version">v{version}</span>{/if}
      <a
        class="kofi"
        href={KOFI_URL}
        target="_blank"
        rel="noopener"
        title={t('support.label')}
      >☕ <span class="kofi-text">{t('support.short')}</span></a>
    <label class="lang" title={t('lang.label')}>
      <span class="lang-icon" aria-hidden="true">🌐</span>
      <select
        aria-label={t('lang.label')}
        value={locale()}
        onchange={(e) => setLocale(e.target.value)}
      >
        {#each supportedLocales as code (code)}
          <option value={code}>{code.toUpperCase()}</option>
        {/each}
      </select>
    </label>
    </div>
  </header>
  <main>
    {@render children()}
  </main>
</div>

<style>
  .app {
    min-height: 100vh;
    min-height: 100dvh;
    display: flex;
    flex-direction: column;
  }
  header {
    padding: 14px 18px;
    border-bottom: 1px solid var(--border);
    background: var(--bg-2);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  .header-right {
    display: inline-flex;
    align-items: center;
    gap: 14px;
  }
  .version {
    color: var(--fg-dim);
    font-size: 11px;
    font-variant-numeric: tabular-nums;
    letter-spacing: 0.04em;
  }
  .kofi {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 4px 10px;
    border-radius: 6px;
    background: var(--bg-3);
    border: 1px solid var(--border);
    color: var(--fg);
    font-size: 12px;
    transition: background 0.12s, border-color 0.12s;
  }
  .kofi:hover { background: #30303a; border-color: var(--fg-dim); }
  @media (max-width: 480px) {
    .kofi-text { display: none; }
    .kofi { padding: 4px 8px; font-size: 14px; }
  }
  .lang {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    color: var(--fg-dim);
    font-size: 12px;
    cursor: pointer;
  }
  .lang-icon { font-size: 14px; }
  .lang select {
    background: var(--bg-3);
    color: var(--fg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 4px 6px;
    font-size: 12px;
    font-family: inherit;
    cursor: pointer;
  }
  .brand {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    line-height: 1.1;
  }
  .brand-icon {
    width: 32px;
    height: 32px;
    flex-shrink: 0;
    border-radius: 7px;
  }
  .brand-text {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .brand-name {
    font-weight: 600;
    font-size: 17px;
    letter-spacing: 0.3px;
  }
  .brand-tagline {
    font-size: 10.5px;
    letter-spacing: 0.8px;
    text-transform: uppercase;
    color: var(--fg-dim);
  }
  @media (max-width: 480px) {
    .brand-tagline { display: none; }
  }
  main {
    flex: 1;
    padding: 18px;
    max-width: 900px;
    width: 100%;
    margin: 0 auto;
  }
</style>
