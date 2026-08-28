"""Regenerate the generated blocks in README.md from the GitHub API.

The public stats-card services (github-readme-stats and friends) go down often
enough that a profile depending on them ends up showing broken images, so the
project table and language breakdown are built here instead and committed as
plain markdown.

Standard library only, so the workflow needs no install step.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

USER = "thesammy2010"
API = "https://api.github.com"

# The profile repo itself is just this README, so it would be noise in a list of
# things worth looking at.
EXCLUDED_REPOS = {USER}

README = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "README.md")

# Languages that describe packaging rather than the work, and would otherwise
# crowd out the real ones in the breakdown.
IGNORED_LANGUAGES = {"Dockerfile", "Mako", "Shell", "Makefile", "Batchfile"}

BAR_WIDTH = 28


def get(path):
    request = urllib.request.Request(f"{API}{path}", headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{USER}-profile-readme",
    })
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def fetch_repos():
    repos = get(f"/users/{USER}/repos?per_page=100&sort=pushed")
    return [
        repo for repo in repos
        if not repo["fork"]
        and not repo["archived"]
        and repo["name"] not in EXCLUDED_REPOS
    ]


def humanise_age(timestamp):
    pushed = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    days = (datetime.now(timezone.utc) - pushed).days
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 30:
        return f"{days} days ago"
    if days < 365:
        return f"{days // 30} months ago"
    years = days // 365
    return "1 year ago" if years == 1 else f"{years} years ago"


def render_projects(repos):
    lines = [
        "| Project | What it is | Stack | Last pushed |",
        "| --- | --- | --- | --- |",
    ]
    for repo in repos:
        description = repo["description"] or "—"
        language = repo["language"] or "—"
        lines.append(
            f"| [{repo['name']}]({repo['html_url']}) | {description} "
            f"| {language} | {humanise_age(repo['pushed_at'])} |"
        )
    return "\n".join(lines)


def render_languages(repos):
    totals = {}
    for repo in repos:
        for language, count in get(f"/repos/{USER}/{repo['name']}/languages").items():
            if language in IGNORED_LANGUAGES:
                continue
            totals[language] = totals.get(language, 0) + count

    if not totals:
        return "_No language data available._"

    overall = sum(totals.values())
    ranked = sorted(totals.items(), key=lambda item: -item[1])[:6]

    lines = ["```text"]
    width = max(len(language) for language, _ in ranked)
    for language, count in ranked:
        share = count / overall
        filled = round(share * BAR_WIDTH)
        bar = "█" * filled + "░" * (BAR_WIDTH - filled)
        lines.append(f"{language:<{width}}  {bar}  {share * 100:5.1f}%")
    lines.append("```")
    lines.append("")
    lines.append("<sub>Across my public repositories, by bytes of code.</sub>")
    return "\n".join(lines)


def replace_block(text, marker, body):
    pattern = re.compile(
        rf"(<!-- {marker}:START -->\n).*?(<!-- {marker}:END -->)",
        re.DOTALL,
    )
    if not pattern.search(text):
        raise SystemExit(f"Could not find the {marker} markers in README.md")
    return pattern.sub(lambda m: f"{m.group(1)}{body}\n{m.group(2)}", text)


def main():
    try:
        repos = fetch_repos()
    except urllib.error.URLError as error:
        # A transient API failure should leave the committed README alone rather
        # than replace it with an empty table.
        print(f"Could not reach the GitHub API: {error}", file=sys.stderr)
        return 1

    with open(README, encoding="utf-8") as handle:
        original = handle.read()

    updated = replace_block(original, "PROJECTS", render_projects(repos))
    updated = replace_block(updated, "LANGUAGES", render_languages(repos))

    if updated == original:
        print("README.md is already up to date")
        return 0

    with open(README, "w", encoding="utf-8") as handle:
        handle.write(updated)
    print(f"README.md updated from {len(repos)} repositories")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
