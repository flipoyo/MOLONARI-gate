"""pull, plan and push: what the site holds, what git says it should hold, and the writes that close the gap."""

from __future__ import annotations

import datetime
import difflib
import hashlib
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import jinja2

from . import marker
from .config import Page, Site, with_page
from .facts import gather
from .render import RenderError, markdown_to_blocks
from .wp import WordPress

UNCHANGED, UPDATE, CREATE, DRIFT = "unchanged", "update", "create", "drift"


class SyncError(RuntimeError):
    pass


def _norm(text: str) -> str:
    return text.rstrip("\n")


def page_file(root: Path, slug: str) -> Path:
    return root / "website" / "pages" / f"{slug}.html"


# ---------------------------------------------------------------- bodies

def gate_sha(root: Path) -> str:
    done = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True)
    if done.returncode != 0:
        raise SyncError(f"git rev-parse HEAD failed in {root}: not a git checkout")
    return done.stdout.strip()


def gate_dirty(root: Path) -> bool:
    done = subprocess.run(["git", "-C", str(root), "status", "--porcelain"], capture_output=True, text=True)
    if done.returncode != 0:
        raise SyncError(f"git status failed in {root}: not a git checkout")
    return bool(done.stdout.strip())


def footer(facts: dict) -> str:
    links = ", ".join(f"[{r['name']}]({r['url']})" for r in facts["repos"])
    return f"*Generated from MOLONARI1D `{facts['branch']}` @ `{facts['sha'][:7]}` on {facts['date']}. Repositories: {links}.*\n"


def render_generated(root: Path, page: Page, facts: dict, source, media: Callable[[str, bytes], str]) -> str:
    def figure(name: str, alt: str = "") -> str:
        data = source.read_bytes(".", f"Figures/{name}")
        stem, dot, ext = name.rpartition(".")
        final = f"{stem}-{hashlib.sha256(data).hexdigest()[:8]}{dot}{ext}"
        return f"![{alt or stem}]({media(final, data)})"

    env = jinja2.Environment(loader=jinja2.FileSystemLoader(root / "website" / "templates"), undefined=jinja2.StrictUndefined,
                             keep_trailing_newline=True, autoescape=False,
                             comment_start_string="{##", comment_end_string="##}")  # `{#id}` is a heading anchor, not a comment
    try:
        text = env.get_template(page.template).render(**facts, figure=figure)
    except jinja2.TemplateNotFound:
        raise SyncError(f"page {page.slug}: template website/templates/{page.template} not found") from None
    except jinja2.TemplateError as exc:
        raise SyncError(f"page {page.slug}: template {page.template}: {exc}") from None
    try:
        return markdown_to_blocks(text.rstrip("\n") + "\n\n" + footer(facts))
    except RenderError as exc:
        raise SyncError(f"page {page.slug}: {exc}") from None


def read_managed(root: Path, page: Page) -> str:
    path = page_file(root, page.slug)
    if not path.is_file():
        raise SyncError(f"page {page.slug}: {path.relative_to(root)} not found (pixi run site pull {page.slug})")
    return path.read_bytes().decode("utf-8")


@dataclass
class Entry:
    page: Page
    action: str
    body: str = ""          # what the page should hold (without the marker)
    src: str = ""           # marker source
    live: str | None = None  # the live raw content, None when the page does not exist
    diff: str = ""
    note: str = ""


def plan(site: Site, root: Path, wp: WordPress, source_factory: Callable[[], object], pages: list[str] | None = None) -> list[Entry]:
    """Read-only. An editorial page, and a page missing from site.toml, receives no request at all."""
    entries: list[Entry] = []
    source, facts = None, None

    def lookup_media(name: str, data: bytes) -> str:
        return wp.find_media(name) or f"{site.base_url}/wp-content/uploads/{name}"

    for page in site.pages:
        if page.mode == "editorial" or (pages and page.slug not in pages):
            continue
        if page.mode == "generated":
            if facts is None:
                source = source_factory()
                facts = gather(source, site)
            body, src = render_generated(root, page, facts, source, lookup_media), f"MOLONARI1D@{facts['sha']}"
        else:
            body, src = read_managed(root, page), f"MOLONARI-gate@{gate_sha(root)}"
        body = _norm(body)
        live_page = wp.get_page(page.id) if page.id is not None else wp.find_page(page.slug)
        if live_page is None:
            entries.append(Entry(page, CREATE, body, src))
            continue
        live = live_page["content"]["raw"]
        live_body, mark = marker.split(live)
        baseline = bool(page.pulled_sha256) and marker.digest(live) == page.pulled_sha256
        trusted = (mark is not None and marker.intact(live)) or baseline
        entry = Entry(page, UNCHANGED, body, src, live)
        if _norm(live_body) == body and (trusted or mark is None):
            pass
        elif trusted:
            entry.action = UPDATE
            entry.diff = "".join(difflib.unified_diff(_norm(live_body).splitlines(True), (body + "\n").splitlines(True),
                                                      f"{page.slug} (live)", f"{page.slug} (git)"))
        else:
            entry.action = DRIFT
            entry.note = f"edited in WordPress since the last push. Take it into git: pixi run site pull {page.slug}"
        entries.append(entry)
    return entries


def push(site: Site, root: Path, wp: WordPress, entries: list[Entry], adopt: set[str], source_factory: Callable[[], object],
         say: Callable[[str], None] = print) -> int:
    """Apply the plan. Returns a process exit code: 0 when every entry was applied or unchanged."""
    if gate_dirty(root):
        raise SyncError("MOLONARI-gate has uncommitted changes: commit first, so that what is pushed is a commit")
    refused = 0
    backup = root / ".dev" / ".backup" / datetime.date.today().isoformat()
    for e in entries:
        slug = e.page.slug
        if e.action == UNCHANGED:
            continue
        if e.action == DRIFT and slug not in adopt:
            say(f"refused  {slug}: {e.note}  (or --adopt {slug} to overwrite)")
            refused += 1
            continue
        if e.live is not None:
            backup.mkdir(parents=True, exist_ok=True)
            (backup / f"{slug}.html").write_bytes(e.live.encode("utf-8"))
        body = e.body
        if e.page.mode == "generated":  # the media were looked up by plan: upload what is missing, then render again
            source = source_factory()
            facts = gather(source, site)
            body = _norm(render_generated(root, e.page, facts, source, lambda n, d: wp.find_media(n) or wp.upload_media(n, d)))
        content = marker.write(body, e.src)
        if e.action == CREATE:
            wp.create_page(slug, e.page.title or slug, content, e.page.parent, e.page.menu_order)
        else:
            wp.update_page(e.page.id, content)
        say(f"pushed   {slug} ({e.action})")
    return 1 if refused else 0


def pull(site: Site, root: Path, wp: WordPress, slugs: list[str] | None = None) -> tuple[Site, list[str]]:
    """Write the raw block markup of every page to website/pages/<slug>.html, unchanged, and record it in site.toml."""
    written = []
    for live in wp.list_pages():
        slug = live["slug"]
        if slugs and slug not in slugs:
            continue
        raw = live["content"]["raw"]
        body, _ = marker.split(raw)
        path = page_file(root, slug)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body.encode("utf-8"))
        title = live.get("title", {}).get("raw", "") if isinstance(live.get("title"), dict) else ""
        site = with_page(site, Page(slug=slug, id=live["id"], title=title, parent=live.get("parent", 0),
                                    menu_order=live.get("menu_order", 0), pulled_sha256=marker.digest(raw)))
        written.append(slug)
    return site, written
