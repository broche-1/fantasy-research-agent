# Fantasy Football Research Assistant

Automation toolkit that pulls weekly data from the Yahoo Fantasy Football API, computes insights about your roster, and generates a Tuesday morning Markdown report.

## Getting Started

1. Create and activate a Python 3.11 virtual environment.
2. Install dependencies: `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and fill in your Yahoo OAuth credentials.
4. Confirm `.env` is excluded from version control (already covered by `.gitignore`).
5. Run `pre-commit install` to enable linting and formatting hooks.

Project structure and implementation milestones are tracked in `fantasy_football_research_assistant_dev_plan.md`. OAuth tokens are cached locally in `config/tokens.json`, which is gitignored—never commit live credentials.

## Generating Weekly Reports

Once credentials are in place and tokens fetched, you can produce a weekly insight bundle and Markdown report from cached API data or the provided fixtures.

1. Source your environment variables so the CLI sees Yahoo credentials and `PYTHONPATH`:  
   ```bash
   set -a; source .env; set +a
   ```
2. Summarize the current or specified week, writing both JSON and Markdown outputs:
   ```bash
   # Using live API data (requires valid OAuth tokens)
   python3 src/main.py summarize-week --week 8 --format markdown --output reports/week_8_report.md

   # Using cached fixtures for testing or development
   python3 src/main.py summarize-week --use-fixtures --format markdown --output reports/week_8_report.md
   python3 src/main.py summarize-week --use-fixtures --format json --output reports/week_8_summary.json --pretty
   ```

Markdown reports land under `reports/` by default (configurable via `config/settings.yaml`).
