.PHONY: brain hands test test-python test-ts lint

brain:
	cd python && uv run python -m boros_brain.main --mode=paper

hands:
	cd ts && pnpm exec tsx src/boros_hands/main.ts

test-python:
	cd python && uv run pytest -q

test-ts:
	cd ts && pnpm vitest run

test: test-python test-ts

lint:
	cd python && uv run ruff check . && uv run mypy src
	cd ts && pnpm lint && pnpm typecheck
