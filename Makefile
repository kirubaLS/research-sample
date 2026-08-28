.PHONY: help install dev test lint api web seed

help:
	@echo "install  install backend and frontend dependencies"
	@echo "api      run the API on :8000"
	@echo "web      run the web app on :3000"
	@echo "test     run the backend test suite"
	@echo "lint     ruff check"
	@echo "seed     create a demo school, section and taxonomy"

install:
	cd backend && pip install -e ".[dev]"
	cd frontend && npm install

api:
	cd backend && uvicorn app.main:app --reload --port 8000

web:
	cd frontend && npm run dev

test:
	cd backend && python -m pytest -q

lint:
	cd backend && ruff check app tests

seed:
	cd backend && python -m scripts.seed
