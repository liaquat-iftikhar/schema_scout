.PHONY: setup lint format test check docker

# Extras for local development; change to match your LLM provider and database.
EXTRAS ?= dev,anthropic,postgres

setup:  ## create .venv and install the project
	python3 -m venv .venv
	.venv/bin/pip install -e ".[$(EXTRAS)]"
	@echo "Activate with: source .venv/bin/activate"

lint:
	ruff check .
	ruff format --check .

format:
	ruff check --fix .
	ruff format .

test:
	pytest -q

check: lint test  ## what CI runs, minus the Docker job

docker:
	docker build -t schema-scout .
