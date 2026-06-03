.PHONY: install test lint format

install:
	uv sync

test:
	uv run pytest

lint:
	uv run ruff check --fix .
	uv run ruff format .

format:
	uv run ruff format .
