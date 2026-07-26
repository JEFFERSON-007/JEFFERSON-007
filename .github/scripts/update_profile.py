from __future__ import annotations

import datetime as dt
import base64
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
README_PATH = ROOT / "README.md"
OWNER = os.environ.get("PROFILE_OWNER", "JEFFERSON-007")
PROFILE_REPO = os.environ.get("PROFILE_REPO", OWNER).lower()


def github_get(path: str):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "profile-readme-updater",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(f"https://api.github.com{path}", headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def repository_candidates():
    owner = urllib.parse.quote(OWNER, safe="")
    repositories = github_get(f"/users/{owner}/repos?per_page=100&sort=updated")
    return [
        repo
        for repo in repositories
        if repo.get("name", "").lower() != PROFILE_REPO
        and not repo.get("fork")
        and not repo.get("archived")
        and not repo.get("disabled")
        and repo.get("size", 0) > 0
    ]


def days_since(updated_at: str) -> int:
    updated = dt.datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    return max(0, (dt.datetime.now(dt.timezone.utc) - updated).days)


def project_score(repo: dict) -> tuple[float, str]:
    age = days_since(repo.get("updated_at", "2000-01-01T00:00:00Z"))
    recency = max(0, 365 - age)
    stars = min(repo.get("stargazers_count", 0), 25)
    description_bonus = 10 if repo.get("description") else 0
    topics_bonus = min(len(repo.get("topics", [])), 5) * 2
    score = recency + (stars * 20) + description_bonus + topics_bonus
    return score, repo.get("updated_at", "")


def readme_summary(repo: dict) -> str:
    owner = urllib.parse.quote(OWNER, safe="")
    name = urllib.parse.quote(repo["name"], safe="")
    try:
        payload = github_get(f"/repos/{owner}/{name}/readme")
        content = base64.b64decode(payload.get("content", "")).decode("utf-8", errors="ignore")
    except Exception:
        return ""

    for line in content.splitlines():
        candidate = line.strip()
        if not candidate or candidate.startswith(("#", "!", "<", "<!--", "---", "|")):
            continue
        candidate = re.sub(r"[`*_]", "", candidate)
        candidate = re.sub(r"\[[^\]]+\]\([^\)]+\)", "", candidate)
        candidate = re.sub(r"\s+", " ", candidate).strip(" -:")
        if (
            candidate.startswith("]")
            or "](" in candidate
            or "![" in candidate
            or "http" in candidate.lower()
            or "badge" in candidate.lower()
        ):
            continue
        if len(candidate) >= 24:
            return candidate
    return ""


def short_description(repo: dict) -> str:
    description = (repo.get("description") or "")
    description = re.sub(r"\s+", " ", description).strip()
    if not description:
        description = readme_summary(repo)
    if not description:
        language = repo.get("language") or "software"
        description = f"A {language} project from my active public portfolio."
    if len(description) > 125:
        description = description[:122].rstrip() + "..."
    return description


def featured_work(repositories: list[dict]) -> str:
    selected = sorted(repositories, key=project_score, reverse=True)[:6]
    rows = [
        "| Project | What it shows | Primary stack |",
        "| --- | --- | --- |",
    ]
    for repo in selected:
        name = repo["name"]
        url = repo["html_url"]
        language = repo.get("language") or "Multiple technologies"
        rows.append(f"| [{name}]({url}) | {short_description(repo)} | {language} |")
    updated = dt.datetime.now().strftime("%Y-%m-%d")
    rows.append("")
    rows.append(f"<sub>Automatically selected from recent public activity. Last refreshed: {updated}.</sub>")
    return "\n".join(rows)


def classify(repo: dict) -> set[str]:
    searchable = " ".join(
        [
            repo.get("name", ""),
            repo.get("description", "") or "",
            " ".join(repo.get("topics", [])),
        ]
    ).lower()
    language = (repo.get("language") or "").lower()
    categories = set()

    if any(word in searchable for word in (
        "security", "phish", "vulnerab", "encrypt", "password", "scanner",
        "integrity", "port-scanner", "wifi", "arkshield", "cyber",
    )):
        categories.add("security")
    if language in {"javascript", "typescript", "html", "css"} or any(
        word in searchable for word in ("web", "frontend", "portfolio", "browser", "extension", "react", "next")
    ):
        categories.add("web")
    if language == "python" or any(
        word in searchable for word in ("data", "machine-learning", "ml", "classification", "analytics", "ai")
    ):
        categories.add("python")
    if any(word in searchable for word in ("terminal", "docker", "system", "automation", "tooling", "chess")):
        categories.add("systems")
    return categories


def current_direction(repositories: list[dict]) -> str:
    counts = {"security": 0, "web": 0, "python": 0, "systems": 0}
    for repo in repositories:
        for category in classify(repo):
            counts[category] += 1

    bullets = []
    if counts["security"]:
        bullets.append(
            f"- Security engineering: {counts['security']} public repositories focused on defensive tooling, scanning, encryption, or integrity."
        )
    if counts["web"]:
        bullets.append(
            f"- Full-stack web development: {counts['web']} repositories using JavaScript, TypeScript, and browser or frontend technologies."
        )
    if counts["python"]:
        bullets.append(
            f"- Python, data, and machine learning: {counts['python']} repositories covering automation, APIs, analytics, or classification."
        )
    if counts["systems"]:
        bullets.append(
            f"- Systems and developer tooling: {counts['systems']} repositories exploring terminals, automation, Docker, or technical utilities."
        )
    if not bullets:
        bullets.append("- Building and documenting new software projects in public.")

    refreshed = dt.datetime.now().strftime("%Y-%m-%d")
    bullets.append(f"<sub>Automatically derived from public repository activity. Last refreshed: {refreshed}.</sub>")
    return "\n".join(bullets)


def replace_generated_block(text: str, name: str, content: str) -> str:
    start = f"<!-- {name}:START -->"
    end = f"<!-- {name}:END -->"
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    replacement = f"{start}\n{content}\n{end}"
    updated, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise RuntimeError(f"Could not find exactly one generated block for {name}")
    return updated


def main() -> None:
    repositories = repository_candidates()
    readme = README_PATH.read_text(encoding="utf-8")
    readme = replace_generated_block(readme, "CURRENT_DIRECTION", current_direction(repositories))
    readme = replace_generated_block(readme, "FEATURED_WORK", featured_work(repositories))
    README_PATH.write_text(readme, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
