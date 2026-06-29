// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Ludovic Stumme

// Minimal i18n for PlayPart. Reactive locale via Svelte 5 $state, so every
// t() call inside a component template re-evaluates when the locale changes.
//
// Auto-detection: navigator.language → 'fr' or 'en' (default 'en').
// User override persisted in localStorage.

const SUPPORTED = ['en', 'fr'];
const DEFAULT = 'en';
const STORAGE_KEY = 'playpart-lang';

const messages = {
  fr: {
    'brand.tagline': 'Extract · Mute · Play',

    'nav.back': '← Retour',
    'nav.root': 'Racine',

    'action.rename': 'Renommer',
    'action.delete': 'Supprimer',
    'action.move_to': 'Déplacer…',
    'action.apply': 'Appliquer',
    'status.processing': 'Traitement…',
    'status.ready': 'Prêt',
    'status.error': 'Erreur',

    'home.new_folder_placeholder': 'Nouveau dossier',
    'home.new_folder_button': '+ Dossier',
    'home.upload_button': '↑ Ajouter un morceau',
    'home.uploading': 'Upload…',
    'home.empty_folder': 'Dossier vide. Ajoute un sous-dossier ou un morceau.',
    'home.confirm_delete_folder': 'Supprimer "{name}" ? Son contenu remontera au niveau parent.',
    'home.prompt_rename_folder': 'Renommer le dossier :',
    'home.confirm_delete_track': 'Supprimer ce morceau et tous ses stems ?',

    'track.notes_indicator': 'Contient des notes',
    'track.attachments_indicator': 'Pièces jointes',

    'mixer.not_processed': "Ce morceau n'est pas encore traité.",
    'mixer.loading': 'Chargement…',
    'mixer.play_refused': 'Lecture refusée par le navigateur : {error}',
    'mixer.pitch_failed': 'Transposition échouée : {error}',
    'mixer.play': '▶ Lecture',
    'mixer.pause': '⏸ Pause',
    'mixer.play_with_countin': 'Lecture avec décompte',
    'mixer.key_placeholder': 'Tonalité',

    'mixer.label_volume': 'Volume',
    'mixer.label_loop': 'Boucle',
    'mixer.label_speed': 'Vitesse',
    'mixer.label_semitones': 'Demi-tons',
    'mixer.reset_mix': 'Réinitialiser le mix',

    'notes.section_title': 'Notes / réglages',
    'notes.placeholder': 'Réglages guitare, ampli, effets, accordage…',
    'notes.saved': 'Enregistré',
    'notes.save_error': 'Erreur de sauvegarde',

    'attach.section_title': 'Pièces jointes',
    'attach.add': '+ Ajouter',
    'attach.uploading': 'Envoi…',
    'attach.empty': 'Aucune pièce jointe (partition PDF, fichier Guitar Pro…).',
    'attach.confirm_delete': 'Supprimer "{filename}" ?',

    'pitch.transposing_to': 'Transposition vers {signed} demi-ton{plural}',
    'pitch.modal_hint': 'Les transpositions déjà en cache sont instantanées ; les autres sont générées maintenant (≈ 20 s par piste).',

    'aria.master_volume': 'Volume général',
    'aria.transposition_in_progress': 'Transposition en cours',
    'aria.rename': 'Renommer',
    'aria.delete': 'Supprimer',
    'lang.label': 'Langue',
    'support.label': 'Soutenir le projet sur Ko-fi',
    'support.short': 'Soutenir',
  },

  en: {
    'brand.tagline': 'Extract · Mute · Play',

    'nav.back': '← Back',
    'nav.root': 'Root',

    'action.rename': 'Rename',
    'action.delete': 'Delete',
    'action.move_to': 'Move to…',
    'action.apply': 'Apply',
    'status.processing': 'Processing…',
    'status.ready': 'Ready',
    'status.error': 'Error',

    'home.new_folder_placeholder': 'New folder',
    'home.new_folder_button': '+ Folder',
    'home.upload_button': '↑ Add a track',
    'home.uploading': 'Uploading…',
    'home.empty_folder': 'Empty folder. Add a subfolder or a track.',
    'home.confirm_delete_folder': 'Delete "{name}"? Its contents will move up to the parent folder.',
    'home.prompt_rename_folder': 'Rename folder:',
    'home.confirm_delete_track': 'Delete this track and all its stems?',

    'track.notes_indicator': 'Has notes',
    'track.attachments_indicator': 'Attachments',

    'mixer.not_processed': 'This track has not been processed yet.',
    'mixer.loading': 'Loading…',
    'mixer.play_refused': 'Playback refused by browser: {error}',
    'mixer.pitch_failed': 'Pitch shift failed: {error}',
    'mixer.play': '▶ Play',
    'mixer.pause': '⏸ Pause',
    'mixer.play_with_countin': 'Play with count-in',
    'mixer.key_placeholder': 'Key',

    'mixer.label_volume': 'Volume',
    'mixer.label_loop': 'Loop',
    'mixer.label_speed': 'Speed',
    'mixer.label_semitones': 'Semitones',
    'mixer.reset_mix': 'Reset mix',

    'notes.section_title': 'Notes / settings',
    'notes.placeholder': 'Guitar settings, amp, effects, tuning…',
    'notes.saved': 'Saved',
    'notes.save_error': 'Save error',

    'attach.section_title': 'Attachments',
    'attach.add': '+ Add',
    'attach.uploading': 'Uploading…',
    'attach.empty': 'No attachments (PDF score, Guitar Pro file…).',
    'attach.confirm_delete': 'Delete "{filename}"?',

    'pitch.transposing_to': 'Transposing to {signed} semitone{plural}',
    'pitch.modal_hint': 'Pitches already in cache are instant; the others are being generated now (≈ 20 s per stem).',

    'aria.master_volume': 'Master volume',
    'aria.transposition_in_progress': 'Transposition in progress',
    'aria.rename': 'Rename',
    'aria.delete': 'Delete',
    'lang.label': 'Language',
    'support.label': 'Support the project on Ko-fi',
    'support.short': 'Support',
  },
};

function detect() {
  if (typeof window === 'undefined') return DEFAULT;
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved && SUPPORTED.includes(saved)) return saved;
  } catch {
    /* localStorage disabled — fall back to navigator */
  }
  const nav = (navigator.language || '').slice(0, 2).toLowerCase();
  return SUPPORTED.includes(nav) ? nav : DEFAULT;
}

let _locale = $state(detect());

export function locale() {
  return _locale;
}

export function setLocale(loc) {
  if (!SUPPORTED.includes(loc)) return;
  _locale = loc;
  try {
    if (typeof window !== 'undefined') localStorage.setItem(STORAGE_KEY, loc);
  } catch {
    /* ignore */
  }
}

export const supportedLocales = SUPPORTED;

export function t(key, params) {
  const dict = messages[_locale] || messages[DEFAULT];
  let msg = dict[key] ?? messages[DEFAULT][key] ?? key;
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      msg = msg.replaceAll(`{${k}}`, String(v));
    }
  }
  return msg;
}

// French plural rule: |n| > 1. English: n != 1.
export function plural(n) {
  if (_locale === 'fr') return Math.abs(n) > 1 ? 's' : '';
  return n !== 1 ? 's' : '';
}

// Format a signed integer like "+2" / "0" / "-3".
export function signed(n) {
  return n > 0 ? `+${n}` : String(n);
}
