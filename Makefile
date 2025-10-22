PYTHON ?= python3
WEEK   ?= 8
FREE_AGENT_COUNT ?= 15

.PHONY: help install lint test report fixtures clean

help:
	@echo "Available commands:"
	@echo "  make install   # pip install -r requirements.txt"
	@echo "  make lint      # run pre-commit hooks"
	@echo "  make test      # run pytest"
	@echo "  make report    # regenerate week report (override WEEK=)"
	@echo "  make fixtures  # refresh fixtures & reports from live API"
	@echo "  make clean     # remove caches and build artifacts"

install:
	$(PYTHON) -m pip install -r requirements.txt

lint:
	pre-commit run --all-files

test:
	$(PYTHON) -m pytest

report:
	@if [ ! -f .env ]; then echo "Missing .env – copy .env.example first." && exit 1; fi
	set -a; . ./.env; set +a; \
	$(PYTHON) src/main.py summarize-week --week $(WEEK) --free-agent-count $(FREE_AGENT_COUNT) --no-cache --format markdown --output reports/week_$(WEEK)_report.md && \
	$(PYTHON) src/main.py summarize-week --week $(WEEK) --free-agent-count $(FREE_AGENT_COUNT) --no-cache --format json --output reports/week_$(WEEK)_summary.json --pretty

fixtures:
	@if [ ! -f .env ]; then echo "Missing .env – copy .env.example first." && exit 1; fi
	set -a; . ./.env; set +a; \
	$(PYTHON) scripts/refresh_fixtures.py --week $(WEEK) --free-agent-count $(FREE_AGENT_COUNT)

clean:
	rm -rf .pytest_cache .mypy_cache .cache
	rm -f .coverage coverage.xml
	rm -rf config/cache/*
