.PHONY: install bootstrap extract build validate run-all test quality clean

install:
	poetry install

bootstrap:
	poetry run peg bootstrap

extract:
	poetry run peg extract-world-bank
	poetry run peg extract-comtrade
	poetry run peg extract-bpstat

build:
	poetry run peg build

audit-comtrade:
	poetry run peg audit-comtrade-coverage

validate:
	poetry run peg validate

run-all:
	poetry run peg run-all

test:
	poetry run pytest --cov

quality:
	poetry run ruff format --check .
	poetry run ruff check .
	poetry run mypy src tests

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage dist
