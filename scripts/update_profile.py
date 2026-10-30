#!/usr/bin/env python3
"""Refresh the profile README with live GitHub metrics and featured repositories."""

from __future__ import annotations

import datetime as dt
import json
import os
import random
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

OWNER = os.getenv("PROFILE_OWNER", "lowji194")
API_BASE = "https://api.github.com"
FEATURED_COUNT = 6
RANDOM_POOL_SIZE = 15
README_FILES = (
    ("README.md", "en"),
    ("README-EN.md", "en"),
    ("README-VI.md", "vi"),
)


def request_json(url: str, token: str | None = None, optional: bool = False):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{OWNER}-profile-readme-updater",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if optional and exc.code in (401, 403, 404):
            return {"_http_error": exc.code}
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"GitHub API returned HTTP {exc.code} for {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        if optional:
            return {"_network_error": str(exc.reason)}
        raise RuntimeError(f"Could not reach GitHub API: {exc.reason}") from exc


def fetch_profile():
    profile = request_json(f"{API_BASE}/users/{urllib.parse.quote(OWNER)}")
    if not isinstance(profile, dict):
        raise RuntimeError("GitHub returned an invalid user profile response.")
    return profile


def fetch_public_repositories():
    repositories = []
    page = 1

    while True:
        query = urllib.parse.urlencode({
            "type": "owner",
            "sort": "updated",
            "per_page": 100,
            "page": page,
        })
        batch = request_json(
            f"{API_BASE}/users/{urllib.parse.quote(OWNER)}/repos?{query}"
        )
        if not isinstance(batch, list):
            raise RuntimeError("GitHub returned an invalid repository list.")
        repositories.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    return repositories


def load_traffic(repositories, token: str | None):
    if not token:
        return False, 0, 0, 0

    successes = 0
    total_views = 0
    total_uniques = 0
    auth_failures = 0

    for repository in repositories:
        name = repository.get("name")
        if not name:
            continue

        url = (
            f"{API_BASE}/repos/{urllib.parse.quote(OWNER)}/"
            f"{urllib.parse.quote(name)}/traffic/views?per=week"
        )
        result = request_json(url, token=token, optional=True)

        if not isinstance(result, dict) or "_http_error" in result or "_network_error" in result:
            status = result.get("_http_error") if isinstance(result, dict) else None
            if status in (401, 403):
                auth_failures += 1
                if successes == 0 and auth_failures >= 3:
                    print("Traffic access is unavailable; falling back to repository stars.")
                    break
            continue

        successes += 1
        views = int(result.get("count", 0) or 0)
        uniques = int(result.get("uniques", 0) or 0)
        repository["_views_14d"] = views
        repository["_unique_views_14d"] = uniques
        total_views += views
        total_uniques += uniques

    minimum_coverage = max(1, (len(repositories) + 1) // 2)
    available = (
        successes >= minimum_coverage
        and any(int(repo.get("_unique_views_14d", 0) or 0) > 0 for repo in repositories)
    )
    if not available:
        return False, 0, 0, successes

    return True, total_views, total_uniques, successes


def safe_description(value):
    description = re.sub(r"\s+", " ", str(value or "Open-source project.")).strip()
    description = description.replace(chr(96), "'")
    description = description.replace("<", "&lt;").replace(">", "&gt;")
    description = re.sub(r"([\\*_{}\[\]()#+\-.!|>])", r"\\\1", description)
    if len(description) > 170:
        description = description[:167].rstrip() + "..."
    return description


def number(value):
    return f"{int(value or 0):,}"


def select_featured(repositories, mode, traffic_available, day_key):
    rng = random.Random(f"{OWNER}:{day_key}:{mode}")

    if mode == "stars":
        metric = "stars"
    elif mode == "views":
        metric = "views" if traffic_available else "stars"
    elif traffic_available:
        metric = rng.choice(("views", "stars"))
    else:
        metric = "stars"

    def rank_key(repository):
        stars = int(repository.get("stargazers_count", 0) or 0)
        views = int(repository.get("_unique_views_14d", 0) or 0)
        updated = repository.get("pushed_at") or repository.get("updated_at") or ""
        if metric == "views":
            return (views, stars, updated)
        return (stars, views, updated)

    ranked = sorted(repositories, key=rank_key, reverse=True)

    if mode == "random":
        pool = ranked[: min(RANDOM_POOL_SIZE, len(ranked))]
        selected = rng.sample(pool, min(FEATURED_COUNT, len(pool)))
        selected.sort(key=rank_key, reverse=True)
    else:
        selected = ranked[:FEATURED_COUNT]

    return selected, metric


def render_featured(repositories, metric, traffic_available, locale, mode):
    if not repositories:
        return "_No public repositories are currently available to feature._"

    lines = []
    for repository in repositories:
        name = repository.get("name", "Repository")
        url = repository.get("html_url", f"https://github.com/{OWNER}/{name}")
        description = safe_description(repository.get("description"))
        stars = number(repository.get("stargazers_count", 0))
        forks = number(repository.get("forks_count", 0))
        language = repository.get("language") or "Multiple languages"

        lines.append(f"- **[{name}]({url})** — {description}")

        details = [f"⭐ {stars} stars", f"🍴 {forks} forks", language]
        if traffic_available:
            unique_views = number(repository.get("_unique_views_14d", 0))
            details.append(f"👀 {unique_views} unique views / 14d")
        lines.append(f"  <sub>{' · '.join(details)}</sub>")

    if metric == "views":
        if mode == "random":
            note_en = "Daily random rotation from the 15 most-viewed repositories, measured by unique visitors over the last 14 days"
            note_vi = "Tự động chọn ngẫu nhiên mỗi ngày trong 15 repository có lượt xem duy nhất cao nhất trong 14 ngày gần nhất"
        else:
            note_en = "Ranked by unique repository views over the last 14 days"
            note_vi = "Xếp hạng theo lượt xem duy nhất của repository trong 14 ngày gần nhất"
    elif mode == "random":
        note_en = "Daily random rotation from the 15 most-starred repositories"
        note_vi = "Tự động chọn ngẫu nhiên mỗi ngày trong 15 repository có nhiều star nhất"
    else:
        note_en = "Ranked by GitHub stars"
        note_vi = "Xếp hạng theo số star trên GitHub"

    if locale == "vi":
        lines.append("")
        lines.append(f"<sub>{note_vi}. Dữ liệu lượt xem cần secret tùy chọn PROFILE_TRAFFIC_TOKEN; nếu chưa cấu hình, hệ thống tự động dùng số star.</sub>")
    else:
        lines.append("")
        lines.append(f"<sub>{note_en}. View-based ranking requires the optional PROFILE_TRAFFIC_TOKEN secret; without it, the updater falls back to stars.</sub>")

    return "\n".join(lines)


def render_stats(profile, all_repositories, traffic_available, total_views, total_uniques, traffic_successes, locale):
    public_repositories = int(profile.get("public_repos", len(all_repositories)) or 0)
    total_stars = sum(int(repo.get("stargazers_count", 0) or 0) for repo in all_repositories)
    total_forks = sum(int(repo.get("forks_count", 0) or 0) for repo in all_repositories)
    followers = int(profile.get("followers", 0) or 0)
    following = int(profile.get("following", 0) or 0)
    refreshed = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if locale == "vi":
        rows = [
            ("Repository công khai", number(public_repositories)),
            ("Tổng star trên các repository", number(total_stars)),
            ("Tổng fork trên các repository", number(total_forks)),
            ("Người theo dõi", number(followers)),
            ("Đang theo dõi", number(following)),
        ]
        if traffic_available:
            rows.extend([
                ("Lượt xem repository trong 14 ngày", number(total_views)),
                ("Lượt xem duy nhất trong 14 ngày", number(total_uniques)),
            ])
        table = ["| Chỉ số | Giá trị |", "|:--|--:|"]
        table.extend(f"| {label} | **{value}** |" for label, value in rows)
        table.append("")
        if traffic_available:
            table.append(f"<sub>Cập nhật: {refreshed} · Nguồn: GitHub REST API · Traffic API truy cập được trên {traffic_successes} repository.</sub>")
        else:
            table.append(f"<sub>Cập nhật: {refreshed} · Nguồn: GitHub REST API. Không dùng ảnh thống kê từ dịch vụ bên thứ ba.</sub>")
        return "\n".join(table)

    rows = [
        ("Public repositories", number(public_repositories)),
        ("Stars across public repositories", number(total_stars)),
        ("Forks across public repositories", number(total_forks)),
        ("Followers", number(followers)),
        ("Following", number(following)),
    ]
    if traffic_available:
        rows.extend([
            ("Repository views (last 14 days)", number(total_views)),
            ("Unique repository views (last 14 days)", number(total_uniques)),
        ])
    table = ["| Metric | Value |", "|:--|--:|"]
    table.extend(f"| {label} | **{value}** |" for label, value in rows)
    table.append("")
    if traffic_available:
        table.append(f"<sub>Last refreshed: {refreshed} · Source: GitHub REST API · Traffic data available for {traffic_successes} repositories.</sub>")
    else:
        table.append(f"<sub>Last refreshed: {refreshed} · Source: GitHub REST API. No third-party stats image services are used.</sub>")
    return "\n".join(table)


def replace_generated_block(content, name, body):
    start_marker = f"<!-- {name}_START -->"
    end_marker = f"<!-- {name}_END -->"
    start = content.find(start_marker)
    end = content.find(end_marker)

    if start < 0 or end < 0 or end < start:
        raise RuntimeError(f"Missing generated markers for {name}.")

    body_start = start + len(start_marker)
    return content[:body_start] + "\n" + body.strip() + "\n" + content[end:]


def main():
    mode = os.getenv("PROFILE_MODE", "random").strip().lower()
    if mode not in ("random", "stars", "views"):
        mode = "random"

    profile = fetch_profile()
    all_repositories = fetch_public_repositories()

    featured_candidates = [
        repo for repo in all_repositories
        if not repo.get("fork")
        and not repo.get("archived")
        and not repo.get("disabled")
        and repo.get("name", "").lower() != OWNER.lower()
    ]

    traffic_token = os.getenv("PROFILE_TRAFFIC_TOKEN", "").strip()
    traffic_available, total_views, total_uniques, traffic_successes = load_traffic(
        featured_candidates, traffic_token
    )

    day_key = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    featured, metric = select_featured(
        featured_candidates, mode, traffic_available, day_key
    )

    print(
        f"Found {len(all_repositories)} public repositories; "
        f"featured {len(featured)} using {metric} ranking."
    )

    for path, locale in README_FILES:
        readme_path = Path(path)
        if not readme_path.exists():
            raise RuntimeError(f"Required README file not found: {path}")

        content = readme_path.read_text(encoding="utf-8")
        content = replace_generated_block(
            content,
            "FEATURED_REPOS",
            render_featured(featured, metric, traffic_available, locale, mode),
        )
        content = replace_generated_block(
            content,
            "PROFILE_STATS",
            render_stats(
                profile,
                all_repositories,
                traffic_available,
                total_views,
                total_uniques,
                traffic_successes,
                locale,
            ),
        )
        readme_path.write_text(content, encoding="utf-8")
        print(f"Updated {path}")


if __name__ == "__main__":
    main()
