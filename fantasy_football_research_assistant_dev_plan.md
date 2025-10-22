# ⚙️ Development Plan: Fantasy Football Research Assistant (v1)

## Overview
A Python-based automation that connects to the Yahoo Fantasy Football API, analyzes your team’s weekly performance, generates waiver and start/sit recommendations, and produces a Markdown report each Tuesday.

---

## Phase 0 — Setup & Foundations
**Goal:** Establish project structure, version control, and environment.  

**Deliverables:**
- GitHub repo: `fantasy-research-assistant`
- Python virtual environment
- Initial folder structure:

```
fantasy-research-assistant/
│
├── src/
│   ├── data_fetcher/
│   ├── data_processor/
│   ├── report_generator/
│   └── main.py
│
├── tests/
├── config/
│   └── settings.yaml
├── reports/
├── requirements.txt
└── README.md
```

**Tasks:**
1. Initialize repo and venv.
2. Define dependency list (`requests`, `pandas`, `jinja2`, `matplotlib`, `yahoo-fantasy-api`, `python-dotenv`).
3. Create `.env` file for Yahoo API credentials.
4. Set up pre-commit hooks (linting, formatting).
5. Create logging configuration (`logging.conf`).

**Outcome:** Clean project skeleton with a reproducible environment and version control in place.

---

## Phase 1 — Yahoo API Integration
**Goal:** Authenticate with Yahoo and fetch basic league/team data.

**Deliverables:**
- Reusable API client module.
- Token management (OAuth2).
- Verified access to: League metadata, team roster, matchup results, player stats.

**Tasks:**
1. Implement OAuth2 flow (store tokens securely in local file or Redis).
2. Create `YahooClient` class to wrap requests.
3. Add data caching (local JSON) to reduce API calls.
4. Write unit tests with mocked Yahoo API responses.

**Outcome:** Local script can successfully fetch your team data for a given week.

---

## Phase 2 — Data Processing Engine
**Goal:** Transform raw API data into meaningful metrics and insights.  

**Deliverables:**
- Processing module that computes:
  - Weekly performance summary  
  - Optimal lineup efficiency  
  - Bench/starter comparison  
  - Free agent trends  

**Tasks:**
1. Define core data models.
2. Build functions for weekly summary calculation and efficiency score.
3. Add logic for waiver wire filtering and start/sit comparison.
4. Write test coverage for metric calculations.

**Outcome:** Given a JSON snapshot of a week’s data, system outputs structured insight objects.

---

## Phase 3 — Report Generation
**Goal:** Produce a readable Markdown (and optionally HTML) report.  

**Deliverables:**
- `report_generator` module with Jinja2 templates.
- Local output saved to `/reports/week_X_report.md`.

**Tasks:**
1. Design report template.
2. Add charts using matplotlib.
3. Generate Markdown + render HTML version.
4. Store reports by week with timestamp.

**Outcome:** Running the tool for a week generates a self-contained, shareable report file.

---

## Phase 4 — Automation
**Goal:** Fully automate the weekly workflow.  

**Deliverables:**
- Script runs automatically every Tuesday at 6 AM.
- Logs stored locally.

**Tasks:**
1. Add command-line entrypoint.
2. Schedule job (cron or AWS Lambda).
3. Implement error handling + retry logic.
4. Archive logs by week.

**Outcome:** Hands-free weekly automation that runs reliably each Tuesday.

---

## Phase 5 — Distribution & Notifications (Optional Stretch)
**Goal:** Deliver reports conveniently (email or Slack).  

**Deliverables:**
- Optional Slack webhook or email delivery.

**Tasks:**
1. Add Notifier class (Slack or email).
2. Add CLI flag for notifications.
3. Extend logging for delivery confirmation.

**Outcome:** Reports can be delivered automatically to your inbox or Slack.

---

## Phase 6 — Enhancements & Maintenance
**Goal:** Improve accuracy, performance, and usability.  

**Ideas:**
- Cache league data between weeks.  
- Integrate external projections (FantasyPros).  
- Add CLI arguments for ad-hoc queries.  
- Containerize with Docker.  
- Create lightweight Streamlit dashboard.

---

## Implementation Timeline

| Phase | Duration | Focus |
|-------|-----------|--------|
| 0 – Setup | 1 day | Repo + environment |
| 1 – API Integration | 2–3 days | Auth + data fetch |
| 2 – Processing Engine | 3–4 days | Compute insights |
| 3 – Report Generation | 2 days | Markdown output |
| 4 – Automation | 1–2 days | Scheduler |
| 5 – Notifications | 1 day | Optional delivery |
| 6 – Enhancements | Ongoing | Optimization |

Total: **~2 weeks of part-time work** for a senior engineer.

---

## Definition of Done (for MVP)
✅ Successful OAuth authentication to Yahoo  
✅ Weekly data fetched & processed  
✅ Markdown report generated for a given week  
✅ Cron job automatically runs every Tuesday  
✅ Logs captured and stored  
