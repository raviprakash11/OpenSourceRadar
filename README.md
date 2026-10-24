# OpenSourceRadar

A scheduled open-source discovery agent for React/TypeScript, AI/developer tools, and DevOps/AWS/cloud. It finds contribution issues, ranks opportunities, checks public funding signals, sends a Telegram digest, and maintains a small state file to reduce repeat alerts.

## What it does
- Searches GitHub issues every 3 hours using GitHub Actions.
- Prioritizes `good first issue`, `help wanted`, relevant technologies, recent activity, and maintainer engagement signals.
- Checks candidate repositories for `.github/FUNDING.yml`, GitHub Sponsors, Open Collective, and community funding links.
- Sends up to 5 high-ranked opportunities to Telegram.
- Writes `reports/latest.md` and `reports/latest.json`.
- Persists previously notified issue URLs in `reports/state.json` by committing report changes back to the default branch.

Scores are heuristics, not guarantees of issue difficulty, maintainer responsiveness, or payment. Funding detection means a public signal was found, not that a specific issue is paid.

## Setup

1. Create a new GitHub repository named `OpenSourceRadar` and add these files.
2. In **Settings → Secrets and variables → Actions → Secrets**, add:
   - `TELEGRAM_BOT_TOKEN`: token from Telegram's official BotFather.
   - `TELEGRAM_CHAT_ID`: your personal chat ID or target group ID.
3. `GITHUB_TOKEN` is provided automatically by GitHub Actions. The workflow needs `contents: write` to commit the report/state file.
4. In Telegram, start a chat with your bot and send `/start` before the first notification.
5. Commit everything to the default branch and enable Actions.
6. Run **Actions → OpenSourceRadar → Run workflow** to test immediately.

## Schedule
The workflow runs at minute 11 every 3 hours (`11 */3 * * *`, UTC). GitHub scheduled runs can be delayed and are not a real-time SLA.

## Local run
```bash
python -m pip install -r requirements.txt
export GITHUB_TOKEN="your-github-token"
# Telegram variables are optional for local testing
python -m src.discover
```

## Configuration
Edit `config/preferences.json` to adjust technologies, result count, and minimum score.

## Security
- Never commit bot tokens or personal access tokens.
- The workflow uses the automatically generated `GITHUB_TOKEN`.
- Do not grant write permissions beyond what is needed.
- The agent only discovers and reports; it does not comment on issues, open PRs, or perform actions on other repositories.

## Sponsorship reality
Open-source contributions do not automatically earn sponsorship. Treat funding links and bounties as leads to verify, and follow each project's contribution and payment rules.
