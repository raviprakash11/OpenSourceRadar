#!/usr/bin/env python3
"""Daily AI research discovery agent: Google Search -> ranked ideas -> Google Docs."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
STATE_FILE = REPORTS / "state.json"
LATEST_MD = REPORTS / "latest.md"
LATEST_JSON = REPORTS / "latest.json"
SCOPES = ["https://www.googleapis.com/auth/documents"]
SERP_ENDPOINT = "https://serpapi.com/search.json"
DOCS_ENDPOINT = "https://docs.googleapis.com/v1/documents"

SEARCH_QUERIES = [
    ("LLM architectures", 'latest research LLM architecture transformer model innovations paper'),
    ("AI agents", 'latest research AI agents agentic systems planning tool use multi agent benchmarks'),
    ("RAG and retrieval", 'latest research retrieval augmented generation RAG knowledge retrieval evaluation'),
    ("Interpretability and safety", 'latest research mechanistic interpretability LLM evaluation AI safety'),
    ("Training and inference", 'latest research efficient LLM training inference quantization mixture of experts'),
    ("AI for software engineering", 'latest research AI coding agents software engineering benchmarks'),
    ("Multimodal and robotics", 'latest research multimodal models vision language action robotics'),
]

CATEGORY_TERMS = {
    "LLM architectures": ["transformer", "architecture", "attention", "model", "llm", "moe"],
    "AI agents": ["agent", "agentic", "planning", "tool use", "multi-agent", "workflow"],
    "RAG and retrieval": ["rag", "retrieval", "search", "knowledge", "embedding", "vector"],
    "Interpretability and safety": ["interpretability", "mechanistic", "safety", "alignment", "evaluation", "reasoning"],
    "Training and inference": ["training", "inference", "quantization", "gpu", "moe", "distillation"],
    "AI for software engineering": ["coding", "software engineering", "code", "developer", "repository", "programming"],
    "Multimodal and robotics": ["multimodal", "vision", "audio", "robot", "embodied", "video"],
}
TRUSTED_RESEARCH_DOMAINS = (
    "arxiv.org", "openreview.net", "aclanthology.org", "proceedings.neurips.cc",
    "iclr.cc", "proceedings.mlr.press", "nature.com", "science.org",
    "deepmind.google", "research.google", "ai.meta.com", "huggingface.co",
    "openai.com", "anthropic.com", "microsoft.com", "allenai.org",
)


def env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def request_json(method: str, url: str, **kwargs) -> dict:
    last_error = None
    for attempt in range(3):
        try:
            response = requests.request(method, url, timeout=40, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Request failed after retries: {url}: {last_error}")


def google_search(query: str, api_key: str) -> list[dict]:
    payload = request_json(
        "GET",
        SERP_ENDPOINT,
        params={
            "engine": "google",
            "q": query,
            "api_key": api_key,
            "tbs": "qdr:w",
            "num": 10,
            "hl": "en",
            "gl": "us",
        },
    )
    if payload.get("error"):
        raise RuntimeError(f"SerpAPI error: {payload['error']}")
    return payload.get("organic_results", [])


def clean_url(url: str) -> str:
    return (url or "").split("#", 1)[0].rstrip("/")


def domain_of(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def infer_questions(category: str, title: str, snippet: str) -> list[str]:
    subject = title.rstrip(".")
    templates = {
        "LLM architectures": [
            f"What architectural change in {subject} contributes most to its reported performance?",
            "How does this approach compare with a standard decoder-only Transformer under equal compute?",
            "Which component can be ablated to test whether the reported improvement is causal?",
        ],
        "AI agents": [
            f"What failure mode does {subject} attempt to solve in agentic systems?",
            "How does the method affect task success, tool-call efficiency and recovery from errors?",
            "Can the approach be reproduced on a small, open benchmark?",
        ],
        "RAG and retrieval": [
            f"How does {subject} change retrieval quality or answer faithfulness?",
            "Which retriever, chunking and reranking choices most affect the result?",
            "How does the method perform when documents are noisy, stale or contradictory?",
        ],
        "Interpretability and safety": [
            f"What measurable behaviour does {subject} help explain or evaluate?",
            "Can the result be replicated across model sizes and model families?",
            "What are the limitations of the proposed metric or intervention?",
        ],
        "Training and inference": [
            f"What compute, memory or latency bottleneck does {subject} address?",
            "What is the quality-versus-cost trade-off against a strong baseline?",
            "Can the reported efficiency gain be reproduced on a smaller GPU?",
        ],
        "AI for software engineering": [
            f"Which software engineering tasks does {subject} improve, and how are they evaluated?",
            "How does performance change on unseen repositories or longer tasks?",
            "What are the main causes of incorrect edits, regressions or tool failures?",
        ],
        "Multimodal and robotics": [
            f"How does {subject} align or combine information across modalities?",
            "How robust is the approach to distribution shifts and ambiguous inputs?",
            "Which controlled experiment would isolate the contribution of each modality?",
        ],
    }
    return templates.get(category, [
        f"What is the central technical contribution of {subject}?",
        "What baseline and evaluation dataset would provide a fair comparison?",
        "What limitation could form the basis of a follow-up experiment?",
    ])


def score_result(result: dict, category: str) -> int:
    title = (result.get("title") or "").lower()
    snippet = (result.get("snippet") or "").lower()
    url = result.get("link") or ""
    domain = domain_of(url)
    text = f"{title} {snippet}"
    terms = CATEGORY_TERMS.get(category, [])
    relevance = min(35, sum(5 for term in terms if term in text))
    research_signals = ["paper", "research", "study", "benchmark", "dataset", "method", "evaluation", "arxiv", "preprint"]
    research_score = min(25, sum(5 for term in research_signals if term in text))
    trusted_score = 20 if any(domain == d or domain.endswith("." + d) for d in TRUSTED_RESEARCH_DOMAINS) else 0
    title_score = 10 if len(title) > 25 else 0
    recency_score = 10  # Google query is constrained to the past week (tbs=qdr:w).
    return min(100, relevance + research_score + trusted_score + title_score + recency_score)


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            print("Warning: state file unreadable; starting with empty deduplication state.")
    return {"seen": {}}


def collect_topics(api_key: str, state: dict) -> list[dict]:
    seen = state.get("seen", {})
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    seen = {
        url: stamp for url, stamp in seen.items()
        if _parse_timestamp(stamp) and _parse_timestamp(stamp) >= cutoff
    }
    found: dict[str, dict] = {}
    for category, query in SEARCH_QUERIES:
        print(f"Searching: {category}")
        for result in google_search(query, api_key):
            url = clean_url(result.get("link", ""))
            title = (result.get("title") or "").strip()
            if not url.startswith("https://") or not title:
                continue
            key = url.lower()
            if key in seen:
                continue
            score = score_result(result, category)
            candidate = {
                "title": title,
                "url": url,
                "domain": domain_of(url),
                "snippet": (result.get("snippet") or "").strip(),
                "date": result.get("date") or result.get("published_date") or "Not provided by Google",
                "category": category,
                "score": score,
            }
            if key not in found or score > found[key]["score"]:
                found[key] = candidate
        time.sleep(0.4)
    topics = sorted(found.values(), key=lambda item: item["score"], reverse=True)[:15]
    now = datetime.now(timezone.utc).isoformat()
    for topic in topics:
        seen[topic["url"].lower()] = now
        topic["research_questions"] = infer_questions(topic["category"], topic["title"], topic["snippet"])
        topic["research_direction"] = (
            f"Reproduce the core claim from '{topic['title']}' using a small open-weight model or public benchmark; "
            "compare against a simple baseline and report quality, latency and compute."
        )
    state["seen"] = seen
    state["updated_at"] = now
    return topics


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def build_report(topics: list[dict], now: datetime) -> str:
    local_date = now.astimezone(timezone(timedelta(hours=5, minutes=30))).strftime("%A, %d %B %Y")
    lines = [
        f"AI RESEARCH RADAR — {local_date}",
        "Daily discovery digest | Search window: past 7 days | Ranked by heuristic relevance",
        "",
        "EXECUTIVE SUMMARY",
        f"New research leads discovered: {len(topics)}",
        "Scores are heuristic discovery priorities, not peer-review or scientific-quality ratings.",
        "Search snippets are leads only. Open the original source and verify methods, claims and publication status before citing.",
        "",
    ]
    if not topics:
        lines += ["No new links passed today's deduplication and relevance filters.", "Try widening the search window or clearing reports/state.json if you want to rediscover older links.", ""]
    for index, item in enumerate(topics, 1):
        lines += [
            f"{index}. {item['title']}",
            f"Category: {item['category']} | Priority: {item['score']}/100 | Source: {item['domain']}",
            f"Published/date label: {item['date']}",
            f"Original source: {item['url']}",
            f"What Google surfaced: {item['snippet'] or 'No snippet returned.'}",
            "Why investigate: Potentially relevant to current work in " + item["category"].lower() + ". Validate the paper's contribution and baselines in the full source.",
            "Research questions:",
        ]
        lines += [f"  - {question}" for question in item["research_questions"]]
        lines += [f"Suggested experiment: {item['research_direction']}", ""]
    lines += [
        "SUGGESTED RESEARCH WORKFLOW",
        "1. Read the original paper, technical report or project documentation.",
        "2. Record the exact claim, baseline, dataset, compute budget and limitations.",
        "3. Reproduce one result before extending the method.",
        "4. Run an ablation and compare against a simple baseline.",
        "5. Save code, environment details, metrics and negative results.",
        "",
        "Generated automatically by OpenSourceRadar / AI Research Radar.",
    ]
    return "\n".join(lines)


def google_docs_credentials() -> Credentials:
    config = json.loads(env("GOOGLE_OAUTH_CLIENT_JSON"))
    credentials = Credentials(
        token=None,
        refresh_token=config["refresh_token"],
        token_uri=config.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=config["client_id"],
        client_secret=config["client_secret"],
        scopes=SCOPES,
    )
    credentials.refresh(Request())
    return credentials


def publish_google_doc(report: str, date_label: str) -> str:
    credentials = google_docs_credentials()
    headers = {"Authorization": f"Bearer {credentials.token}", "Content-Type": "application/json"}
    created = request_json(
        "POST",
        DOCS_ENDPOINT,
        headers=headers,
        json={"title": f"AI Research Radar — {date_label}"},
    )
    document_id = created["documentId"]
    request_json(
        "POST",
        f"{DOCS_ENDPOINT}/{document_id}:batchUpdate",
        headers=headers,
        json={"requests": [{"insertText": {"location": {"index": 1}, "text": report}}]},
    )
    return f"https://docs.google.com/document/d/{document_id}/edit"


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    api_key = env("SERPAPI_API_KEY")
    state = load_state()
    topics = collect_topics(api_key, state)
    now = datetime.now(timezone.utc)
    report = build_report(topics, now)
    date_slug = now.strftime("%Y-%m-%d")
    date_label = now.astimezone(timezone(timedelta(hours=5, minutes=30))).strftime("%d %b %Y")
    LATEST_MD.write_text(report, encoding="utf-8")
    LATEST_JSON.write_text(json.dumps({"generated_at": now.isoformat(), "topics": topics}, indent=2), encoding="utf-8")
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    archive = REPORTS / f"{date_slug}.md"
    archive.write_text(report, encoding="utf-8")
    doc_url = publish_google_doc(report, date_label)
    print(f"Published {len(topics)} topics to {doc_url}")
    print(f"Report: {LATEST_MD}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"AI Research Radar failed: {exc}", file=sys.stderr)
        raise
