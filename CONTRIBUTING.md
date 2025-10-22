# Contributing

Thanks for taking the time to improve the Fantasy Football Research Assistant! Even for a personal project, having a consistent workflow keeps future changes smooth. :)

## Quick Checklist

1. **Set up tooling**
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   pre-commit install
   ```

2. **Run the tests**
   ```bash
   make test
   ```

3. **Lint before committing**
   ```bash
   make lint
   ```

4. **Regenerate fixtures / reports** when behaviour changes the output
   ```bash
   make fixtures WEEK=<week-number>
   ```

5. **Open an issue or leave a note** in `fantasy_football_research_assistant_dev_plan.md` summarising the change.

## Branch & Commit Style

- Work from feature branches (`feature/<topic>`).
- Squash or keep commits tidy and descriptive.
- Reference GitHub issues (if any) in commit messages: `git commit -m "feat: add waiver radar (#12)"`.

## Pull Request Checklist

- [ ] Tests pass locally (`make test`).
- [ ] Reports/fixtures updated if relevant (`make report` or `make fixtures`).
- [ ] README or docs touched when behaviour changes.
- [ ] Added/updated unit tests.

Any small improvement is welcome – even documenting a rough idea in an issue helps future-you. Enjoy tinkering! 🚀
