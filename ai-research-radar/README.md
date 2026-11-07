# AI Research Radar

A daily research-discovery agent added to the existing OpenSourceRadar repository. It searches Google through SerpAPI, ranks recent AI research leads, deduplicates links, writes Markdown/JSON reports, and creates a dated Google Doc.

## What it searches

- LLM architectures
- AI agents and multi-agent systems
- RAG and retrieval
- Interpretability and AI safety
- Training, inference and efficiency
- AI for software engineering
- Multimodal AI and robotics

The first version uses deterministic heuristics rather than an LLM to score and structure search results. Research questions are prompts for investigation, not claims extracted from the paper. Always read and verify the original source.

## Schedule

GitHub Actions runs daily at 01:30 UTC (07:00 Asia/Kolkata). GitHub scheduled workflows are not guaranteed to start at the exact minute and can be delayed during periods of high load. Use **Actions → AI Research Radar → Run workflow** for a manual run.

## Required GitHub Actions secrets

Add these under **Repository → Settings → Secrets and variables → Actions → New repository secret**:

- `SERPAPI_API_KEY`: API key from https://serpapi.com/
- `GOOGLE_OAUTH_CLIENT_JSON`: JSON containing `client_id`, `client_secret`, `refresh_token`, and optionally `token_uri`.

Never put API keys, OAuth client secrets or refresh tokens in source code or commit them to Git.

## Google Docs setup

1. Open https://console.cloud.google.com/ and create/select a Google Cloud project.
2. Enable **Google Docs API** for the project.
3. Configure the OAuth consent screen. Add your Google account as a test user while testing.
4. Create an OAuth Client ID of type **Desktop app** and download its client-secret JSON.
5. On your computer, install dependencies:
   ```bash
   python -m pip install -r ai-research-radar/requirements.txt
   ```
6. Run the OAuth helper:
   ```bash
   python ai-research-radar/auth_google.py /path/to/client_secret.json
   ```
7. Complete Google's browser consent flow. Copy the JSON printed by the script into the GitHub secret `GOOGLE_OAUTH_CLIENT_JSON`.
8. Do not commit the downloaded client-secret file or the printed token JSON.

**Important OAuth note:** Google OAuth refresh tokens issued while an external consent screen is in Testing mode generally expire after 7 days. For unattended daily operation, configure the consent screen for an appropriate Production status and comply with any Google verification requirements for the scopes used. For a personal-only setup, review Google's current OAuth policies before relying on long-lived refresh tokens.

The agent creates a new Google Doc in the Google account that granted OAuth consent each day. It does not need a pre-existing document ID.

## SerpAPI setup

1. Create an account at https://serpapi.com/.
2. Copy your API key.
3. Add it as `SERPAPI_API_KEY` in GitHub Actions secrets.

The workflow makes seven Google searches per run (one per research category). Check your SerpAPI plan and usage quota.

## Run locally

Set the two environment variables, then run:

```bash
export SERPAPI_API_KEY="..."
export GOOGLE_OAUTH_CLIENT_JSON='{"client_id":"...","client_secret":"...","refresh_token":"..."}'
python -m pip install -r ai-research-radar/requirements.txt
python ai-research-radar/src/agent.py
```

## Output

- `ai-research-radar/reports/latest.md`
- `ai-research-radar/reports/latest.json`
- `ai-research-radar/reports/YYYY-MM-DD.md`
- `ai-research-radar/reports/state.json` (deduplication state)

The Google Doc URL is printed in the GitHub Actions run log. Reports are also committed to the repository and uploaded as a workflow artifact.

## Ranking and limitations

The 0–100 priority score is a transparent heuristic based on topic relevance, research signals, trusted research-domain matches and the Google past-week filter. It is not a scientific quality score. Google snippets may be incomplete or misleading; verify publication date, paper status, methodology, baselines, code and claims at the original source.

The agent reports new links not seen in the previous 30 days. If a source is rediscovered within that period, it is suppressed. Clear `reports/state.json` to reset deduplication.

## Security

- Keep repository secrets private.
- OAuth tokens should only be stored in GitHub Actions secrets.
- The workflow has `contents: write` only to save its generated reports and deduplication state.
- The agent is read-only with respect to research sources; it does not scrape login-protected pages or interact with third-party accounts.
