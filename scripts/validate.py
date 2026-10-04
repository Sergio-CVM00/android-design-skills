#!/usr/bin/env python3
"""Validate this bundle's deliberately simple metadata, links, and coverage.

Standard library only. This is not a general YAML/Markdown parser or a
behavioral evaluator. Online checks are explicit and read-only.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urljoin, urlsplit
from urllib.request import Request, urlopen

EXPECTED = {
    "android-ui-design", "android-ui-foundations", "android-ui-styles",
    "android-ui-layout-content", "android-ui-components", "android-ui-patterns",
    "android-ui-home-screen", "android-ui-widgets",
}
BASE = "https://developer.android.com"
GUIDES = "/design/ui/mobile/guides/"
LINK = re.compile(r"\[[^\]\n]*\]\(([^\s)]+)\)")


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            value = dict(attrs).get("href", "")
            if value:
                self.urls.append(value)


def fetch(url):
    request = Request(url, headers={"User-Agent": "android-design-skills-source-check/1.0"})
    with urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise ValueError(f"HTTP {response.status}")
        final = response.url
        if urlsplit(final).hostname != "developer.android.com":
            raise ValueError(f"Unexpected redirect: {final}")
        return response.read().decode("utf-8"), final


def validate(root, online=False):
    errors = []
    skills = sorted((root / "skills").glob("*/SKILL.md"))
    actual = {p.parent.name for p in skills}
    if actual != EXPECTED:
        errors.append(f"Skill inventory differs: missing={EXPECTED-actual}, extra={actual-EXPECTED}")
    for path in skills:
        content = path.read_text()
        match = re.match(r"\A---\n(.*?)\n---\n", content, re.S)
        if not match:
            errors.append(f"{path}: missing frontmatter")
            continue
        fields = {}
        for line in match.group(1).splitlines():
            key, separator, value = line.partition(": ")
            if not separator or key in fields:
                errors.append(f"{path}: invalid or duplicate scalar metadata: {line}")
            fields[key] = value
        if set(fields) != {"name", "description", "license"}:
            errors.append(f"{path}: unexpected metadata fields")
        name = fields.get("name", "")
        if name != path.parent.name or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) or len(name) > 64:
            errors.append(f"{path}: invalid skill name")
        desc = fields.get("description", "")
        if not desc or len(desc) > 1024 or any(x in desc for x in ("<", ">", ": ")):
            errors.append(f"{path}: description must be a simple nonempty YAML scalar")
        if fields.get("license") != "Apache-2.0":
            errors.append(f"{path}: missing license")
        metadata = path.parent / "agents/openai.yaml"
        try:
            lines = metadata.read_text().splitlines()
            if not lines or lines[0] != "interface:":
                raise ValueError("expected interface mapping")
            values = {}
            for line in lines[1:]:
                key, separator, raw = line.partition(": ")
                if not separator or not key.startswith("  ") or key.strip() in values:
                    raise ValueError("invalid or duplicate interface field")
                values[key.strip()] = json.loads(raw)
            if set(values) != {"display_name", "short_description", "default_prompt"}:
                raise ValueError("unexpected interface fields")
            if not all(isinstance(v, str) and v for v in values.values()):
                raise ValueError("interface values must be nonempty strings")
            if not 25 <= len(values["short_description"]) <= 64:
                raise ValueError("short description outside 25-64 characters")
            if "$" + name not in values["default_prompt"]:
                raise ValueError("default prompt does not invoke the skill")
        except (OSError, ValueError) as exc:
            errors.append(f"{metadata}: {exc}")

    graph = {}
    external = set()
    for path in sorted(root.rglob("*.md")):
        if ".git" in path.relative_to(root).parts:
            continue
        text = path.read_text()
        if "\u2014" in text or "[TODO:" in text:
            errors.append(f"{path}: unfinished placeholder or unsupported dash")
        graph[path.resolve()] = []
        for link in LINK.findall(text):
            parts = urlsplit(link)
            if parts.scheme in ("http", "https"):
                if parts.hostname == "developer.android.com":
                    external.add(link.split("#")[0])
                continue
            if parts.scheme or not parts.path:
                continue
            target = (path.parent / unquote(parts.path)).resolve()
            if not target.is_relative_to(root.resolve()):
                errors.append(f"{path}: link escapes bundle: {link}")
            elif not target.exists():
                errors.append(f"{path}: broken local link: {link}")
            else:
                graph[path.resolve()].append(target)
    seen = set()
    pending = [p.resolve() for p in skills]
    while pending:
        node = pending.pop()
        if node not in seen:
            seen.add(node)
            pending.extend(graph.get(node, []))
    references = list((root / "skills").glob("*/references/*.md"))
    for path in references:
        if path.resolve() not in seen:
            errors.append(f"{path}: reference unreachable from skill entry points")

    rows = json.loads((root / "docs/coverage.json").read_text())
    urls = set()
    groups = set()
    for row in rows:
        url = row["url"]
        if url in urls:
            errors.append(f"Duplicate coverage URL: {url}")
        urls.add(url)
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.hostname != "developer.android.com" or not parts.path.startswith(GUIDES):
            errors.append(f"Unexpected source URL: {url}")
        groups.add(parts.path.removeprefix(GUIDES).split("/")[0])
        if row["skill"] not in EXPECTED or row["status"] != "covered":
            errors.append(f"Invalid coverage owner/status: {url}")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["reviewed"]):
            errors.append(f"Invalid review date: {url}")
        reference = root / row["reference"]
        expected_parent = root / "skills" / row["skill"] / "references"
        if not reference.resolve().is_relative_to(expected_parent.resolve()):
            errors.append(f"Coverage reference outside owner: {url}")
        elif not reference.is_file() or url not in reference.read_text():
            errors.append(f"Coverage source not cited in primary reference: {url}")
    if len(rows) != 33 or groups != {"foundations", "styles", "layout-and-content", "components", "patterns", "home-screen", "widgets"}:
        errors.append("Expected the reviewed 33-entry, seven-group sidebar inventory")
    for name in ("README.md", "LICENSE", "NOTICE", "docs/source-coverage.md", "docs/validation.md"):
        if not (root / name).is_file():
            errors.append(f"Missing publication file: {name}")

    if online:
        def check(url):
            try:
                content, final = fetch(url)
                if "<article" not in content:
                    raise ValueError("No documentation article found")
                return url, content, None
            except Exception as exc:
                return url, "", str(exc)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(check, sorted(external | urls)))
        pages = {}
        for url, content, error in results:
            if error:
                errors.append(f"Source unavailable: {url}: {error}")
            else:
                pages[url] = content
        seed = BASE + GUIDES + "foundations/system-bars"
        if seed in pages:
            html = pages[seed]
            start = html.find('menu="_book"')
            end = html.find("</nav>", start)
            if start < 0 or end < 0:
                errors.append("Cannot locate live sidebar; inventory comparison unverified")
            else:
                parser = Links()
                parser.feed(html[start:end])
                live = {
                    urljoin(BASE, u).split("?")[0].split("#")[0]
                    for u in parser.urls
                    if urlsplit(urljoin(BASE, u)).path.startswith(GUIDES)
                }
                if live != urls:
                    errors.append(f"Sidebar drift: added={sorted(live-urls)}, removed={sorted(urls-live)}")
        else:
            errors.append("Sidebar source unavailable; inventory comparison unverified")
        print(f"Online sources checked: {len(results)}")

    if errors:
        for error in errors:
            print("FAIL:", error, file=sys.stderr)
        return 1
    print(f"PASS: {len(skills)} skills, {len(references)} reachable references, {len(rows)} mapped sidebar entries")
    print("Scope: structure and source inventory only; no agent or Android runtime acceptance")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--online", action="store_true", help="check official sources and live sidebar")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    return validate(args.root.resolve(), args.online)


if __name__ == "__main__":
    raise SystemExit(main())
