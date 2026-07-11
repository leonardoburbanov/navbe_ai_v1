.PHONY: check lint typecheck test fmt

fmt:
	uv run ruff format packages/ apps/cli/

lint:
	uv run ruff check packages/ apps/cli/
	uv run ruff format --check packages/ apps/cli/

typecheck:
	uv run ty check packages/ apps/cli/

test:
	-uv run pytest packages/

check: lint typecheck test
	@echo All checks passed
