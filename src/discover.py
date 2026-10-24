import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.github.com"
TOKEN = os.getenv("GITHUB_TOKEN", "")
HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
if TOKEN:
    HEADERS["Authorization"] = f"Bearer {TOKEN}"

def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default

def api_get(url, params=None):
    response = requests.get(url, headers=HEADERS, params=params, timeout=25)
    if response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0":
        reset = response.headers.get("X-RateLimit-Reset", "unknown")
        raise RuntimeError(f"GitHub API rate limit reached; reset epoch: {reset}")
    response.raise_for_status()
    return response.json()

def search_issues(query, per_page=20):
    data = api_get(f"{API}/search/issues", {
        "q": query, "sort": "updated", "order": "desc", "per_page": per_page
    })
    return data.get("items", [])

def score_issue(issue, preferred_topics):
    labels = {x.get("name", "").lower() for x in issue.get("labels", [])}
    text = f"{issue.get('title', '')} {issue.get('body') or ''}".lower()
    repo_name = issue.get("repository_url", "").replace(f"{API}/repos/", "")
    points = 15
    reasons = []

    if "good first issue" in labels:
        points += 25
        reasons.append("labelled good first issue")
    if "help wanted" in labels:
        points += 18
        reasons.append("maintainer requests help")
    if any(word in text for word in ("documentation", "docs", "readme", "example")):
        points += 5
        reasons.append("may suit a docs/example contribution")
    if issue.get("comments", 0) > 0:
        points += 8
        reasons.append("has community discussion")
    if issue.get("comments", 0) >= 3:
        points += 4
        reasons.append("has multiple comments")
    if any(topic in (repo_name + " " + text) for topic in preferred_topics):
        points += 8
        reasons.append("matches preferred technology keywords")

    updated = issue.get("updated_at")
    if updated:
        try:
            age_days = (datetime.now(timezone.utc) -
                        datetime.fromisoformat(updated.replace("Z", "+00:00"))).days
            if age_days <= 7:
                points += 12
                reasons.append("updated in the last week")
            elif age_days <= 30:
                points += 6
                reasons.append("updated in the last month")
        except ValueError:
            pass

    if issue.get("assignee") or issue.get("assignees"):
        points -= 15
        reasons.append("may already be assigned; verify before investing time")
    return max(0, min(points, 100)), reasons

def funding_signals(repo_full_name):
    """Look for public funding metadata. These are leads, not proof an issue is paid."""
    result = {"funding": [], "topics": [], "stars": None, "pushed_at": None}
    repo = api_get(f"{API}/repos/{repo_full_name}")
    result["stars"] = repo.get("stargazers_count")
    result["pushed_at"] = repo.get("pushed_at")
    result["topics"] = repo.get("topics", [])

    # GitHub's funding endpoint is convenient where available.
    try:
        data = api_get(f"{API}/repos/{repo_full_name}/community/profile")
        # Community profile doesn't consistently expose funding; keep as supplementary metadata.
        result["community_health"] = data.get("health_percentage")
    except requests.RequestException:
        pass

    try:
        funding = api_get(f"{API}/repos/{repo_full_name}/contents/.github/FUNDING.yml")
        import base64
        content = base64.b64decode(funding.get("content", "")).decode("utf-8", "replace")
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            key, value = line.split(":", 1)
            value = value.strip().strip("'\"")
            if value and key.strip().lower() not in ("custom",):
                result["funding"].append(f"{key.strip()}: {value}")
            elif value and key.strip().lower() == "custom":
                result["funding"].append(f"custom: {value}")
    except requests.RequestException:
        pass

    # README/HTML pages are not fetched; use repo homepage and metadata links only.
    homepage = repo.get("homepage") or ""
    if homepage and any(x in homepage.lower() for x in ("opencollective", "github.com/sponsors", "polar.sh", "ko-fi.com", "buymeacoffee.com")):
        result["funding"].append(f"homepage: {homepage}")
    return result

def safe_repo_name(issue):
    return issue.get("repository_url", "").replace(f"{API}/repos/", "")

def telegram_send(message):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Telegram not configured; skipping notification.")
        return False
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": message, "disable_web_page_preview": True},
        timeout=25,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError("Telegram API did not confirm message delivery.")
    return True

def telegram_message(items):
    lines = ["🔎 OpenSourceRadar — new opportunities", ""]
    for index, item in enumerate(items, 1):
        issue = item["issue"]
        funding = item.get("funding", [])
        funding_text = "Funding signal: " + "; ".join(funding[:2]) if funding else "Funding: no signal found"
        title = issue.get("title", "(untitled issue)")
        if len(title) > 110:
            title = title[:107] + "..."
        lines.extend([
            f"{index}. {title}",
            f"Score: {item['score']}/100 | Repo: {item['repo']}",
            issue.get("html_url", ""),
            funding_text,
            ""
        ])
    lines.append("Scores are heuristic. Verify issue status, contribution rules, and any funding/bounty terms.")
    return "\n".join(lines)[:3900]

def main():
    config = load_json(ROOT / "config/preferences.json", {})
    state_path = ROOT / "reports/state.json"
    state = load_json(state_path, {"notified_urls": []})
    previously_notified = set(state.get("notified_urls", []))
    preferred_topics = [x.lower() for x in config.get("preferred_topics", [])]
    all_issues = {}

    for query in config.get("queries", []):
        try:
            for issue in search_issues(query, config.get("max_issues_per_query", 20)):
                if issue.get("pull_request") or not issue.get("html_url"):
                    continue
                all_issues[issue["html_url"]] = issue
            time.sleep(0.25)
        except requests.RequestException as exc:
            print(f"Search failed for query {query!r}: {exc}")
        except RuntimeError as exc:
            print(str(exc))
            break

    scored = []
    for issue in all_issues.values():
        score, reasons = score_issue(issue, preferred_topics)
        scored.append({"issue": issue, "repo": safe_repo_name(issue), "score": score, "reasons": reasons, "funding": []})
    scored.sort(key=lambda x: (x["score"], x["issue"].get("updated_at", "")), reverse=True)

    # Keep metadata lookups bounded to conserve API quota.
    checked_repos = set()
    for item in scored:
        if len(checked_repos) >= config.get("repository_metadata_checks", 12):
            break
        repo = item["repo"]
        if not repo or repo in checked_repos:
            continue
        checked_repos.add(repo)
        try:
            meta = funding_signals(repo)
            item["funding"] = meta.get("funding", [])
            item["stars"] = meta.get("stars")
            item["topics"] = meta.get("topics", [])
            if item["funding"]:
                item["score"] = min(100, item["score"] + 8)
                item["reasons"].append("public funding metadata detected; verify details")
        except requests.RequestException as exc:
            print(f"Repository metadata unavailable for {repo}: {exc}")
        time.sleep(0.2)

    scored.sort(key=lambda x: (x["score"], x["issue"].get("updated_at", "")), reverse=True)
    report_items = scored[:config.get("max_report_items", 25)]
    new_items = [
        x for x in scored
        if x["issue"]["html_url"] not in previously_notified
        and x["score"] >= config.get("minimum_score_for_telegram", 45)
    ][:config.get("max_telegram_items", 5)]

    now = datetime.now(timezone.utc).isoformat()
    report_lines = [
        "# OpenSourceRadar report", "",
        f"Generated: {now}", f"Unique issues discovered: {len(all_issues)}",
        f"Repositories checked for funding metadata: {len(checked_repos)}", ""
    ]
    for item in report_items:
        issue = item["issue"]
        funding = "; ".join(item.get("funding", [])) or "No public funding signal found in checked metadata"
        report_lines += [
            f"## [{issue.get('title', 'Untitled issue')}]({issue['html_url']})",
            f"- **Repository:** [{item['repo']}](https://github.com/{item['repo']})",
            f"- **Score:** {item['score']}/100",
            f"- **Updated:** {issue.get('updated_at', 'unknown')}",
            f"- **Labels:** {', '.join(x.get('name', '') for x in issue.get('labels', [])) or 'none'}",
            f"- **Comments:** {issue.get('comments', 0)}",
            f"- **Stars:** {item.get('stars', 'not checked')}",
            f"- **Why it ranked:** {', '.join(item['reasons']) or 'matched search filters'}",
            f"- **Funding signals:** {funding}",
            ""
        ]

    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "latest.md").write_text("\n".join(report_lines), encoding="utf-8")
    (reports / "latest.json").write_text(json.dumps({
        "generated_at": now,
        "discovered_count": len(all_issues),
        "items": [{
            "title": x["issue"].get("title"),
            "url": x["issue"].get("html_url"),
            "repository": x["repo"],
            "score": x["score"],
            "funding_signals": x.get("funding", []),
            "reasons": x["reasons"],
        } for x in report_items]
    }, indent=2), encoding="utf-8")

    if new_items:
        try:
            telegram_send(telegram_message(new_items))
            previously_notified.update(x["issue"]["html_url"] for x in new_items)
        except requests.RequestException as exc:
            print(f"Telegram notification failed: {exc}")
    else:
        print("No new items met the notification threshold.")

    # Bound state size to the most recent 2,000 URLs.
    state_path.write_text(json.dumps({
        "notified_urls": list(previously_notified)[-2000:],
        "updated_at": now
    }, indent=2), encoding="utf-8")
    print(f"Report created: {len(report_items)} ranked items; {len(new_items)} new notification candidates.")

if __name__ == "__main__":
    main()
