# syntax=docker/dockerfile:1
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ludovic Stumme

# ---- Stage 1: build the Svelte frontend ----
FROM node:24-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci || npm install
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: Python runtime ----
FROM python:3.11-slim

# torch wheel index. Default cu124 = GPU-capable image that still falls back to
# CPU at runtime when no GPU is present. For a lean CPU-only image build with:
#   --build-arg TORCH_INDEX=https://download.pytorch.org/whl/cpu
ARG TORCH_INDEX=https://download.pytorch.org/whl/cu124

ENV PYTHONUNBUFFERED=1 \
    MUSICAPP_DATA=/data \
    TORCH_HOME=/data/torch_cache

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./backend/requirements.txt
# torch and torchaudio versions must match exactly or torchaudio import fails.
RUN pip install --no-cache-dir torch==2.6.0 torchaudio==2.6.0 --index-url ${TORCH_INDEX} \
    && pip install --no-cache-dir -r backend/requirements.txt
# Fail the build early if the audio stack can't import (e.g. version mismatch).
RUN python -c "import torch, torchaudio, demucs, librosa, soundfile; print('audio stack OK')"

COPY backend/ ./backend/
COPY --from=frontend /app/frontend/build ./frontend/build

EXPOSE 8765
VOLUME ["/data"]

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8765"]
