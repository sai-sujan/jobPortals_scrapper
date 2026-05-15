.PHONY: setup test dashboard docker-build docker-up docker-down docker-logs clean-runtime

PYTHON ?= python3
VENV ?= .venv
VENV_PYTHON := $(VENV)/bin/python

setup:
	$(PYTHON) -m venv $(VENV)
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PYTHON) -m pip install -r requirements.txt

test:
	PYTHONPATH=src $(VENV_PYTHON) -m pytest -q

dashboard:
	PYTHONPATH=src $(VENV_PYTHON) job_portal_dashboard.py --port 8766

docker-build:
	docker compose build

docker-up:
	docker compose up --build

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f dashboard

clean-runtime:
	rm -rf data logs reports
	find . -path "*/output/*" -type f -delete
