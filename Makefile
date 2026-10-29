# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ludovic Stumme
#
# Every target runs inside the playpart-dev container: only Docker is needed
# on the host.

export UID := $(shell id -u)
export GID := $(shell id -g)
export BACKEND_PORT  ?= 8765
export FRONTEND_PORT ?= 5173

COMPOSE := docker compose -f docker-compose.dev.yml
RUN     := $(COMPOSE) run --rm --no-deps
FE      := $(RUN) -w /app/frontend frontend

.DEFAULT_GOAL := help
.PHONY: help image install dev down logs build audit shell image-cpu image-gpu clean

help: ## List the available targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-10s %s\n", $$1, $$2}'

image: ## Build the dev toolbox image (Python 3.11 + Node 24 + torch CPU)
	$(COMPOSE) build backend

install: ## Install frontend dependencies (npm ci)
	$(FE) npm ci

dev: ## Start backend (:BACKEND_PORT, auto-reload) and Vite dev server (:FRONTEND_PORT)
	$(COMPOSE) up

down: ## Stop the dev containers
	$(COMPOSE) down

logs: ## Follow the dev containers logs
	$(COMPOSE) logs -f

build: ## Build the static frontend into frontend/build
	$(FE) npm run build

audit: ## Run npm audit on the frontend dependencies
	$(FE) npm audit

shell: ## Open a shell in the dev container
	$(RUN) backend bash

image-cpu: ## Build the production CPU image (playpart-cpu:local)
	docker build --build-arg TORCH_INDEX=https://download.pytorch.org/whl/cpu -t playpart-cpu:local .

image-gpu: ## Build the production GPU image (playpart-gpu:local)
	docker build --build-arg TORCH_INDEX=https://download.pytorch.org/whl/cu124 -t playpart-gpu:local .

clean: ## Remove frontend build outputs and node_modules
	rm -rf frontend/node_modules frontend/.svelte-kit frontend/build
