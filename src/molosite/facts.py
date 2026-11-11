"""The facts a generated page is made of, read from the Operating Space at the CGS-MOLO commits (never the README tree)."""

from __future__ import annotations

import re
import tomllib

from .config import Site
from .source import SourceError, load_toml


def first_paragraph(readme: str) -> str:
    """The first plain paragraph of a README: no heading, badge, image, quote or table."""
    para: list[str] = []
    for line in readme.splitlines() + [""]:
        s = line.strip()
        if not s:
            if para:
                break
            continue
        if para or not (s.startswith(("#", "!", "[![", ">", "|", "<", "```", "---"))):
            para.append(s)
    return " ".join(para)


def section(markdown: str, heading: str) -> str:
    """The text under `heading`, up to the next heading of the same or a higher level."""
    lines, start, level = markdown.splitlines(), None, 0
    for n, line in enumerate(lines):
        m = re.match(r"(#+)\s+(.*?)\s*$", line)
        if not m:
            continue
        if start is None:
            if m.group(2) == heading:
                start, level = n + 1, len(m.group(1))
        elif len(m.group(1)) <= level:
            return "\n".join(lines[start:n]).strip("\n")
    if start is None:
        raise SourceError(f"heading '{heading}' not found")
    return "\n".join(lines[start:]).strip("\n")


def gather(source, site: Site) -> dict:
    cgs = load_toml(source, ".", site.cgs_file)
    entries = []
    for item in cgs.get("repos", []):
        if item.get("private"):
            continue  # a private repository is never published
        name = item["repository"].removeprefix("github:")
        mount = item.get("relative_path", ".")
        entries.append((mount, name, item.get("default_branch") or item.get("fallback_branch") or site.branch))
    source.register({mount: name for mount, name, _ in entries})
    repos = []
    for mount, name, branch in entries:
        try:
            workspace = tomllib.loads(source.read(mount, "pixi.toml")).get("workspace", {})
        except SourceError:
            workspace = {}
        role = site.roles.get(mount, "")
        if not role:
            try:
                role = first_paragraph(source.read(mount, "README.md"))
            except SourceError:
                role = ""
        repos.append({"name": name.split("/")[1], "slug": name, "path": mount, "branch": branch,
                      "version": workspace.get("version", ""), "role": role,
                      "url": f"https://github.com/{name}", "sha": source.sha(mount)})
    main = next((r for r in repos if r["path"] == "."), None)
    if main is None:
        raise SourceError(f"{site.cgs_file}: no repository mounted at '.'")
    sections = {}
    for key, spec in site.sections.items():
        path, _, heading = spec.partition("#")
        sections[key] = section(source.read(".", path), heading)
    return {"repos": repos, "main": main, "sha": main["sha"], "date": source.date("."), "branch": site.branch,
            "variants": list(site.cgs_variants), "sections": sections}
