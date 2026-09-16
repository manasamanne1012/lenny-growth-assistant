# The Lenny Growth Assistant — operator entry points.
#
# Every target is safe to run twice. Every target that can fail for an
# environmental reason (no .env, no Ollama, no model pulled) checks for that
# reason first and says what to do about it, because the most likely reader of
# this file is someone on a fresh laptop with ten minutes.

SHELL := /bin/bash
COMPOSE := docker compose
BACKEND := $(COMPOSE) exec -T backend

.DEFAULT_GOAL := help
.PHONY: help env up down restart logs doctor fetch-transcripts ingest reingest \
        eval test lint typecheck build resize-embeddings psql clean nuke demo-seed

## ---------------------------------------------------------------- lifecycle

help: ## Show this help
	@echo "The Lenny Growth Assistant"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[1m%-22s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "First run:  make up && make doctor && make fetch-transcripts && make ingest LIMIT=25"

env: ## Create .env from the template if it does not exist
	@if [ ! -f .env ]; then cp .env.example .env; echo "Created .env from .env.example."; \
	else echo ".env already exists; leaving it alone."; fi

up: env ## Build and start everything (postgres, backend, frontend)
	$(COMPOSE) up -d --build
	@echo ""
	@echo "  UI       http://localhost:$${FRONTEND_PORT:-5173}"
	@echo "  API docs http://localhost:$${BACKEND_PORT:-8000}/docs"
	@echo ""
	@echo "Next: make doctor"

down: ## Stop everything (data is preserved)
	$(COMPOSE) down

restart: ## Restart the backend only — the usual move after editing .env
	$(COMPOSE) restart backend

logs: ## Follow backend logs
	$(COMPOSE) logs -f backend

## ------------------------------------------------------------------ preflight

doctor: ## Check config, database, model provider, and index health
	@$(BACKEND) python -m scripts.doctor || \
	  (echo ""; echo "The backend container is not running. Try: make up"; exit 1)

## ---------------------------------------------------------------- knowledge

fetch-transcripts: ## Clone/refresh the transcript corpus from GitHub
	@cd backend && bash scripts/fetch_transcripts.sh

# LIMIT=25 makes the first run finish in a couple of minutes on a local model
# instead of an hour. FORCE=1 re-embeds even unchanged files.
ingest: ## Index transcripts (LIMIT=n for a subset, FORCE=1 to re-embed)
	@$(BACKEND) python -m app.rag.ingest \
	  $(if $(LIMIT),--limit $(LIMIT),) $(if $(FORCE),--force,)

reingest: ## Re-embed everything from scratch (after changing embedding model)
	@$(MAKE) ingest FORCE=1

demo-seed: ## Index only the bundled sample transcripts (works with no network)
	@$(BACKEND) python -m app.rag.ingest --source ./data/sample_transcripts

## -------------------------------------------------------------- quality gates

test: ## Run the unit suite (offline providers; no network, no database needed)
	@$(BACKEND) python -m pytest -q

eval: ## Run the golden-set evaluation and print the grounding report
	@$(BACKEND) python -m evals.run_evals $(if $(ONLY),--only $(ONLY),) \
	  $(if $(KIND),--kind $(KIND),) $(if $(LABEL),--label "$(LABEL)",)

lint: ## Lint the backend
	@$(BACKEND) python -m ruff check app evals scripts tests

typecheck: ## Type-check the frontend
	@cd frontend && npm run typecheck

build: ## Build the production frontend bundle
	@cd frontend && npm ci && npm run build

## ----------------------------------------------------------------- database

psql: ## Open a psql shell against the app database
	@$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-lenny} -d $${POSTGRES_DB:-lenny}

# Changing embedding model changes vector width. Postgres will not silently
# accept that, so it is an explicit, destructive, opt-in step.
resize-embeddings: ## Change the vector column width (DIM=1536), clearing the index
	@if [ -z "$(DIM)" ]; then echo "Usage: make resize-embeddings DIM=1536"; exit 1; fi
	@$(BACKEND) python -m scripts.resize_embeddings --dim $(DIM)
	@echo "Column resized. Now run: make ingest FORCE=1"

## -------------------------------------------------------------------- reset

clean: ## Remove build artefacts and caches
	@find backend -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
	@rm -rf frontend/dist frontend/node_modules/.vite backend/evals/results/*.json
	@echo "Cleaned."

nuke: ## Stop everything and DELETE the database volume
	$(COMPOSE) down -v
	@echo "Volumes removed. `make up` will start from an empty database."
