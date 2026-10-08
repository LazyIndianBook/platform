# Common tasks. Development runs natively (.venv, SQLite, tasks inline); `make up` runs the docker-compose stack.
PY := .venv/bin/python
.DEFAULT_GOAL := help
.PHONY: help install run migrate worker beat test cov lint format check deploy-check up down logs shell import backup

help: ## list the tasks
	@grep -E '^[a-z-]+:.*## ' Makefile | sed 's/:.*## /\t/'

install: ## create .venv and install the pinned requirements, with the test and lint tools
	python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt

run: ## development server, http://localhost:8000 (admin at /admin/)
	$(PY) manage.py runserver

migrate: ## apply migrations, then bring the role groups up to date
	$(PY) manage.py migrate && $(PY) manage.py bootstrap_roles

worker: ## Celery worker for local testing (needs CELERY_BROKER_URL; threads pool, as prefork fails on macOS)
	.venv/bin/celery -A examleaf worker --loglevel INFO --pool threads --concurrency 4

beat: ## Celery beat (the daily purge of due account deletions and of failed log-ins)
	.venv/bin/celery -A examleaf beat --loglevel INFO

test: ## the test suite (pytest)
	.venv/bin/pytest

cov: ## the test suite with a coverage report
	.venv/bin/pytest --cov --cov-report=term

lint: ## ruff: lint and formatting check (as in CI)
	.venv/bin/ruff check . && .venv/bin/ruff format --check .

format: ## ruff: fix what can be fixed and format the code
	.venv/bin/ruff check --fix . && .venv/bin/ruff format .

check: ## Django checks and missing migrations
	$(PY) manage.py check && $(PY) manage.py makemigrations --check --dry-run

deploy-check: ## Django's deployment checklist (with the production .env, only W005 and W021 remain)
	DEBUG=0 $(PY) manage.py check --deploy

up: ## build and start the docker-compose stack (migrates and bootstraps roles on start)
	docker compose up -d --build

down: ## stop the stack (data stays in the volumes)
	docker compose down

logs: ## follow the stack's logs
	docker compose logs -f --tail 100

shell: ## Django shell in the running web container
	docker compose exec web python manage.py shell

import: ## import (or update) all four subjects' papers into the running stack
	docker compose exec web python manage.py import_papers --all

backup: ## dump the stack's database to backups/ (and upload it when BACKUP_BUCKET is set)
	scripts/backup.sh
