.PHONY: install bootstrap extract build validate refresh-sources reproduce run-diagnostics run-all run-all-available test quality clean

install:
	poetry install

bootstrap:
	poetry run peg bootstrap

extract:
	poetry run peg refresh-sources

build:
	poetry run peg build

audit-comtrade:
	poetry run peg audit-comtrade-coverage

review-bpstat:
	poetry run peg review-bpstat-registry

prepare-ine:
	poetry run peg prepare-ine-transcription

reconcile-trade:
	poetry run peg reconcile-trade-sources

map-products:
	poetry run peg build-sitc-industry-mapping

describe-trade:
	poetry run peg build-descriptive-results

prepare-empirical:
	poetry run peg prepare-empirical-extension

validate:
	poetry run peg validate

refresh-sources:
	poetry run peg refresh-sources

reproduce:
	poetry run peg reproduce-from-local

run-diagnostics:
	poetry run peg run-diagnostics

run-all-available:
	poetry run peg run-all-available

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
