# Lenny Growth Assistant — developer convenience targets
# Usage: make <target>
# Requires: Python 3.12+, Docker, Ollama running locally

.PHONY: help install db db-stop run ingest test lint typecheck clean docker-up docker-down

PYTHON   := python
VENV     := .venv
PIP      := $(VENV)/Scripts/pip
UVICORN  := $(VENV)/Scripts/uvicorn
PYTEST   := $(VENV)/Scripts/pytest
RUFF     := $(VENV)/Scripts/ruff
MYPY     := $(VENV)/Scripts/mypy

## Show this help message
help:
	@echo ""
	@echo "Lenny Growth Assistant — available targets"
	@echo "------------------------------------------"
	@grep -E '^## ' Makefile | sed 's/## /  /'
	@echo ""

## Create virtualenv and install all dependencies
install:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@echo "Done. Activate with: .venv\\Scripts\\activate"

## Start PostgreSQL (pgvector) in Docker
db:
	docker compose up db -d
	@echo "PostgreSQL available at localhost:5432"

## Stop PostgreSQL
db-stop:
	docker compose stop db

## Run the API server locally (requires DB running)
run:
	$(UVICORN) backend.app.main:app --reload --host 0.0.0.0 --port 8000

## Ingest the bundled sample transcripts
ingest:
	curl -s -X POST http://localhost:8000/documents/ingest-directory | python -m json.tool

## Run the full test suite (requires PostgreSQL)
test:
	$(PYTEST) -q --tb=short

## Run tests with coverage report
test-cov:
	$(PYTEST) --cov=backend/app --cov-report=term-missing -q

## Lint all Python source files
lint:
	$(RUFF) check .

## Fix auto-fixable lint issues
lint-fix:
	$(RUFF) check --fix .

## Run static type checking
typecheck:
	$(MYPY) backend/app --ignore-missing-imports

## Start the full stack with Docker Compose (DB + API)
docker-up:
	docker compose up --build

## Stop and remove Docker Compose containers
docker-down:
	docker compose down

## Remove virtualenv and Python cache files
clean:
	@if exist $(VENV) rmdir /s /q $(VENV)
	@for /r . %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d" 2>nul
	@for /r . %%f in (*.pyc) do @del /q "%%f" 2>nul
	@echo "Cleaned."

## Quick smoke test — create session, ask a question, show response
smoke:
	@echo "Creating session..."
	@curl -s -X POST http://localhost:8000/sessions \
	  -H "Content-Type: application/json" \
	  -d "{\"title\": \"smoke test\"}" | python -m json.tool
