# Fantasy Football Research Assistant

Automation toolkit that pulls weekly data from the Yahoo Fantasy Football API, computes insights about your roster, and produces a Tuesday morning Markdown report with lineup advice and waiver recommendations.

---

## Highlights

- **Yahoo OAuth + data fetcher** – wraps token refresh, league metadata, roster, matchup, and free-agent endpoints with local caching.
- **Insight engine** – converts weekly data into projected optimal lineup, bench upgrade suggestions, and top free-agent targets.
- **Markdown report generator** – produces a ready‑to‑share weekly recap plus a JSON bundle for downstream tooling.
- **Fixture-driven development** – captured responses under `fixtures/` allow offline iteration and reproducible tests.

---

## Quickstart

```bash
# 1. Python 3.11+ virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy env template and fill in Yahoo OAuth details
cp .env.example .env

# 4. Install pre-commit hooks (recommended)
pre-commit install
```

⚠️ OAuth tokens are cached at `config/tokens.json` and excluded from git. Never commit live credentials.

Implementation milestones live in `fantasy_football_research_assistant_dev_plan.md`.

---

## Dev Tooling

A lightweight `Makefile` is included for common tasks:

```bash
make help        # list available commands
make install     # pip install -r requirements.txt
make lint        # run pre-commit hooks across the repo
make test        # execute pytest suite
make report      # regenerate current-week markdown + json outputs
make fixtures    # refresh fixtures using live Yahoo data (requires auth)
```

The `fixtures` target overwrites JSON under `fixtures/` and `reports/` using live API calls. Run it whenever your lineup or league settings change.

---

## Generating Weekly Reports

Once credentials are configured and tokens obtained:

```bash
# Ensure environment variables are available to the CLI
set -a; source .env; set +a

# Generate live week report (adjust --week as needed)
python3 src/main.py summarize-week --week 8 \
  --format markdown --output reports/week_8_report.md \
  --free-agent-count 15

# Development mode: reuse fixtures (no network calls)
python3 src/main.py summarize-week --use-fixtures \
  --format markdown --output reports/week_8_report.md
python3 src/main.py summarize-week --use-fixtures \
  --format json --output reports/week_8_summary.json --pretty
```

The default output directory is `reports/` (override via `config/settings.yaml:app.report_output_dir`).

---

## Testing

```bash
make test
# or
python3 -m pytest
```

The test suite covers:
- Yahoo client caching/unit behavior (`tests/test_yahoo_client.py`)
- Metrics engine edge cases and projection logic (`tests/test_metrics.py`)
- Markdown rendering and CLI fixture integration (`tests/test_report_markdown.py`)

Fixtures are stored under `fixtures/`; update them with `make fixtures` when league data changes.

---

## Project Layout

```
.
├── src/
│   ├── data_fetcher/       # Yahoo OAuth client + cache
│   ├── data_processor/     # Insight calculations + projections
│   ├── report_generator/   # Markdown rendering
│   └── main.py             # CLI entrypoint
├── tests/                  # pytest suites (use fixtures)
├── fixtures/               # sample Yahoo responses (regenerate via make fixtures)
├── reports/                # generated markdown/json outputs
├── config/settings.yaml    # runtime configuration (report dir, schedule, OAuth endpoints)
└── Makefile                # developer convenience commands
```

---

## Next Steps / Ideas

- Enable a basic CI workflow (`.github/workflows/ci.yml`) to run `make lint` and `make test` on pushes/PRs.
- Schedule the CLI via cron or GitHub Actions to auto-refresh the weekly report.
- Integrate additional projection sources (e.g., FantasyPros) and annotate the report with comparative stats.

Contributions (even future-you) are welcome—see `CONTRIBUTING.md` for guidance.
