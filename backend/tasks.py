# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ludovic Stumme
"""Audio processing pipeline: tempo detection + demucs stem separation.

Runs inside ProcessPoolExecutor workers. The demucs model is loaded once per
worker process via worker_init() and reused across jobs.
"""

from __future__ import annotations

import os
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
import torch
from demucs.apply import apply_model
from demucs.audio import AudioFile
from demucs.pretrained import get_model

_MODEL = None
_DEVICE: str = "cpu"

# Krumhansl-Schmuckler key profiles. Empirically derived weights for the 12
# pitch classes (C, C#, D, ..., B) of major and minor keys. The two profiles
# are rotated by each tonic and correlated against the song's chroma vector.
_MAJOR_PROFILE = np.array(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
)
_MINOR_PROFILE = np.array(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
)
_PC_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def worker_init(model_name: str = "htdemucs_6s") -> None:
    global _MODEL, _DEVICE
    _DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    _MODEL = get_model(model_name)
    _MODEL.to(_DEVICE)
    _MODEL.eval()


def _key_from_chroma(y, sr) -> str:
    """Return the key in the standard short notation: 'C', 'G', 'F#' for major
    and 'Cm', 'Gm', 'F#m' for minor. This is the convention used in lead
    sheets, tabs and chord charts worldwide."""
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    pcp = chroma.mean(axis=1)
    best_score = -np.inf
    best = "?"
    for tonic in range(12):
        for is_minor, profile in ((False, _MAJOR_PROFILE), (True, _MINOR_PROFILE)):
            score = float(np.corrcoef(pcp, np.roll(profile, tonic))[0, 1])
            if score > best_score:
                best_score = score
                best = f"{_PC_NAMES[tonic]}{'m' if is_minor else ''}"
    return best


def analyze_audio(audio_path: Path) -> tuple[float, float, str]:
    """Return (bpm, duration_seconds, key) from a single audio load."""
    y, sr = librosa.load(str(audio_path), mono=True, sr=22050)
    duration = float(len(y) / sr)
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    bpm = float(np.atleast_1d(tempo)[0])
    key = _key_from_chroma(y, sr)
    return bpm, duration, key


def detect_key_from_file(audio_path_str: str) -> str:
    """Standalone key detection for backfilling existing tracks."""
    y, sr = librosa.load(audio_path_str, mono=True, sr=22050)
    return _key_from_chroma(y, sr)


def render_pitch_shifted(input_path: str, output_path: Path, semitones: int) -> None:
    """Pitch-shift an audio file by N semitones while preserving duration.

    Loads the original at its native sample rate, shifts each channel via
    librosa's STFT-based pitch shifter, and writes the result via an atomic
    rename so concurrent readers never see a partial file.
    """
    y, sr = librosa.load(input_path, mono=False, sr=None)
    if y.ndim == 1:
        data = librosa.effects.pitch_shift(y, sr=sr, n_steps=semitones)
    else:
        chans = [librosa.effects.pitch_shift(c, sr=sr, n_steps=semitones) for c in y]
        data = np.stack(chans).T  # soundfile: (samples, channels)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_name(output_path.name + ".tmp")
    sf.write(str(tmp), data, sr, format="WAV")
    tmp.replace(output_path)


def separate(audio_path: Path, out_dir: Path, shifts: int = 5) -> list[str]:
    assert _MODEL is not None, "worker_init() must run first"
    out_dir.mkdir(parents=True, exist_ok=True)

    wav = AudioFile(str(audio_path)).read(
        streams=0,
        samplerate=_MODEL.samplerate,
        channels=_MODEL.audio_channels,
    )
    ref = wav.mean(0)
    wav_norm = ((wav - ref.mean()) / ref.std()).unsqueeze(0).to(_DEVICE)

    with torch.no_grad():
        sources = apply_model(
            _MODEL, wav_norm, shifts=shifts, split=True, overlap=0.25,
            progress=False, device=_DEVICE,
        )[0]
    sources = sources * ref.std() + ref.mean()

    stem_names = list(_MODEL.sources)
    for name, src in zip(stem_names, sources):
        sf.write(
            str(out_dir / f"{name}.wav"),
            src.cpu().numpy().T,
            _MODEL.samplerate,
            format="WAV",
        )
    return stem_names


def _default_shifts() -> int:
    """More passes on GPU (fast); a single pass on CPU to keep jobs bearable.
    Override with the DEMUCS_SHIFTS env var."""
    override = os.environ.get("DEMUCS_SHIFTS")
    if override:
        return int(override)
    return 5 if _DEVICE == "cuda" else 1


def process_track(audio_path_str: str, stems_dir_str: str, shifts: int | None = None) -> dict:
    audio_path = Path(audio_path_str)
    stems_dir = Path(stems_dir_str)
    if shifts is None:
        shifts = _default_shifts()
    bpm, duration, key = analyze_audio(audio_path)
    stems = separate(audio_path, stems_dir, shifts=shifts)
    return {"bpm": bpm, "duration": duration, "key": key, "stems": stems}
