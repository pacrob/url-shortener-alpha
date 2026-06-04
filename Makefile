.PHONY: install test test-all test-slow lint format

install:
	uv sync

test:
	uv run pytest -m "not slow"

test-all:
	uv run pytest

test-slow:
	uv run pytest -m slow

lint:
	uv run ruff check --fix .
	uv run ruff format .

format:
	uv run ruff format .
