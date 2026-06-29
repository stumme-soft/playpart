// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Ludovic Stumme
// Generate a 4-beat click-track preamble at a given BPM, scheduled relative
// to an AudioContext clock. Returns the duration of the preamble in seconds.
//
// The 4th beat is followed by a regular interval so the song lands on the
// next beat.
export function scheduleClicks(ctx, bpm, beats = 4, startAt = 0) {
  const interval = 60 / bpm;
  for (let i = 0; i < beats; i++) {
    const t = startAt + i * interval;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    // Higher pitch on beat 1, lower on 2-4
    osc.frequency.value = i === 0 ? 1500 : 900;
    osc.type = 'square';
    gain.gain.setValueAtTime(0, t);
    gain.gain.linearRampToValueAtTime(0.4, t + 0.001);
    gain.gain.exponentialRampToValueAtTime(0.001, t + 0.07);
    osc.connect(gain).connect(ctx.destination);
    osc.start(t);
    osc.stop(t + 0.08);
  }
  // Total preamble duration: 4 beats; song should start on the next beat.
  return beats * interval;
}
