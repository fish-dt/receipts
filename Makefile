.PHONY: install test lint demo
install: ; pip install -e ".[dev,agents,app]"
test: ; python -m pytest -q
lint: ; ruff check src tests
demo: ; python -m receipts.cli demo
