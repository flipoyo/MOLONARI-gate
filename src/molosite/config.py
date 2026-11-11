"""website/site.toml: the page map (slug -> id, mode, template, parent) and the settings of the sync."""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path

MODES = ("generated", "managed", "editorial")
GATE_ROOT = Path(__file__).resolve().parents[2]


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Page:
    slug: str
    id: int | None = None
    title: str = ""
    mode: str = "editorial"
    template: str = ""  # generated pages: website/templates/<template>
    parent: int = 0
    menu_order: int = 0
    pulled_sha256: str = ""  # managed pages: hash of the live raw content when it was pulled


@dataclass(frozen=True)
class Site:
    base_url: str = "https://molonari.io"
    branch: str = "CGS-MOLO"
    cgs_file: str = ".config/molonari.cgs"
    cgs_variants: tuple[str, ...] = ()
    roles: dict[str, str] = field(default_factory=dict)
    sections: dict[str, str] = field(default_factory=dict)  # name -> "<path>#<heading>"
    pages: tuple[Page, ...] = ()

    def page(self, slug: str) -> Page:
        for page in self.pages:
            if page.slug == slug:
                return page
        raise ConfigError(f"no page '{slug}' in site.toml")


def load(path: Path) -> Site:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(f"{path} not found") from None
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: {exc}") from None
    pages = []
    for raw in data.get("pages", []):
        unknown = set(raw) - set(Page.__dataclass_fields__)
        if unknown:
            raise ConfigError(f"page {raw.get('slug')}: unknown keys {sorted(unknown)}")
        if "slug" not in raw:
            raise ConfigError("a page has no slug")
        page = Page(**raw)
        if page.mode not in MODES:
            raise ConfigError(f"page {page.slug}: mode '{page.mode}' is not one of {MODES}")
        if page.mode == "generated" and not page.template:
            raise ConfigError(f"page {page.slug}: a generated page needs a template")
        pages.append(page)
    slugs = [p.slug for p in pages]
    for slug in sorted({s for s in slugs if slugs.count(s) > 1}):
        raise ConfigError(f"page '{slug}' appears twice")
    ids = [p.id for p in pages if p.id is not None]
    for pid in sorted({i for i in ids if ids.count(i) > 1}):
        raise ConfigError(f"page id {pid} appears twice")
    return Site(
        base_url=str(data.get("base_url", Site.base_url)).rstrip("/"),
        branch=data.get("branch", Site.branch),
        cgs_file=data.get("cgs_file", Site.cgs_file),
        cgs_variants=tuple(data.get("cgs_variants", ())),
        roles=dict(data.get("roles", {})),
        sections=dict(data.get("sections", {})),
        pages=tuple(pages),
    )


def _q(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)  # a JSON string or number is valid TOML


def dump(site: Site) -> str:
    out = [f"base_url = {_q(site.base_url)}", f"branch = {_q(site.branch)}", f"cgs_file = {_q(site.cgs_file)}"]
    out.append(f"cgs_variants = {_q(list(site.cgs_variants))}")
    for table, values in (("roles", site.roles), ("sections", site.sections)):
        if values:
            out += ["", f"[{table}]"] + [f"{_q(k)} = {_q(v)}" for k, v in values.items()]
    for page in site.pages:
        out += ["", "[[pages]]"]
        out += [f"{name} = {_q(getattr(page, name))}" for name in Page.__dataclass_fields__ if getattr(page, name) not in ("", None)]
    return "\n".join(out) + "\n"


def save(site: Site, path: Path) -> None:
    path.write_text(dump(site), encoding="utf-8")


def with_page(site: Site, page: Page) -> Site:
    """The site with this page added, or replacing the page of the same slug (its mode and template are kept)."""
    pages = list(site.pages)
    for i, old in enumerate(pages):
        if old.slug == page.slug:
            pages[i] = replace(page, mode=old.mode, template=old.template)
            break
    else:
        pages.append(page)
    return replace(site, pages=tuple(pages))
