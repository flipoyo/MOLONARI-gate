"""molosite: pull, plan, push, check. `pixi run site plan` writes nothing."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import GATE_ROOT, ConfigError, Site, load, save
from .source import BranchSource, GithubSource, SourceError, find_cgshome
from .sync import DRIFT, SyncError, plan, pull, push, read_managed, render_generated
from .wp import WordPress, WPError, credentials

PUSH_HELP = "pixi run site plan first; push applies exactly that plan"


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="molosite", description=__doc__)
    p.add_argument("--version", action="version", version=f"molosite {__version__}")
    p.add_argument("--site", type=Path, default=GATE_ROOT / "website" / "site.toml", help="the page map")
    p.add_argument("--github", action="store_true", help="read the sources from GitHub (CGS-MOLO head) instead of the Operating Space")
    p.add_argument("--allow-behind", action="store_true", help="read repositories that are behind origin/CGS-MOLO (preview)")
    sub = p.add_subparsers(dest="command", required=True)
    for name, text in (("pull", "write the raw pages of the live site into website/pages/"), ("plan", "show what push would do; writes nothing"),
                       ("push", PUSH_HELP), ("check", "offline: config, templates and sources are consistent")):
        s = sub.add_parser(name, help=text)
        s.add_argument("slugs", nargs="*", help="limit to these pages")
        if name == "push":
            s.add_argument("--adopt", action="append", default=[], metavar="SLUG", help="overwrite this page even in drift")
    return p


def _source_factory(args, site: Site):
    def make():
        if args.github:
            return GithubSource(site.branch)
        return BranchSource(find_cgshome(GATE_ROOT), site.branch, args.allow_behind)
    return make


def _wordpress(site: Site) -> WordPress:
    return WordPress(site.base_url, credentials())


def _check(site: Site, make_source) -> list[str]:
    problems = []
    source = facts = None
    for page in site.pages:
        try:
            if page.mode == "managed":
                read_managed(GATE_ROOT, page)
            elif page.mode == "generated":
                from .facts import gather
                if facts is None:
                    source = make_source()
                    facts = gather(source, site)
                render_generated(GATE_ROOT, page, facts, source, lambda n, d: f"{site.base_url}/wp-content/uploads/{n}")
        except (SyncError, SourceError) as exc:
            problems.append(str(exc))
    return problems


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        site = load(args.site)
        make_source = _source_factory(args, site)
        if args.command == "check":
            problems = _check(site, make_source)
            for line in problems:
                print(f"check: {line}", file=sys.stderr)
            print(f"check: {len(site.pages)} page(s), {len(problems)} problem(s)")
            return 1 if problems else 0
        wp = _wordpress(site)
        if args.command == "pull":
            site, written = pull(site, GATE_ROOT, wp, args.slugs)
            save(site, args.site)
            print(f"pulled {len(written)} page(s): {', '.join(written)}")
            return 0
        entries = plan(site, GATE_ROOT, wp, make_source, args.slugs)
        for e in entries:
            print(f"{e.action:<9} {e.page.slug}" + (f"  {e.note}" if e.note else ""))
            if e.diff:
                print(e.diff)
        if args.command == "plan":
            return 1 if any(e.action == DRIFT for e in entries) else 0
        return push(site, GATE_ROOT, wp, entries, set(args.adopt), make_source)
    except (ConfigError, SyncError, SourceError, WPError) as exc:
        print(f"molosite: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
