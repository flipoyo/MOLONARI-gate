"""The sync marker: the last line of a pushed page, an HTML comment WordPress keeps and readers never see."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from . import __version__

_MARKER = re.compile(r"\n?<!-- molosite (\{.*?\}) -->\s*\Z", re.S)


def digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def write(content: str, src: str) -> str:
    """The content followed by its marker; the hash covers the content above the marker."""
    body = content.rstrip("\n")
    meta = {"src": src, "sha256": digest(body), "v": __version__}
    return f"{body}\n<!-- molosite {json.dumps(meta, separators=(',', ':'))} -->"


@dataclass(frozen=True)
class Marker:
    src: str
    sha256: str
    v: str


def split(raw: str) -> tuple[str, Marker | None]:
    """(content above the marker, marker). No marker, or an unreadable one: (raw, None)."""
    found = _MARKER.search(raw)
    if not found:
        return raw, None
    try:
        meta = json.loads(found.group(1))
        marker = Marker(str(meta["src"]), str(meta["sha256"]), str(meta.get("v", "")))
    except (ValueError, KeyError, TypeError):
        return raw, None
    return raw[: found.start()], marker


def intact(raw: str) -> bool:
    """True when the live content still hashes to its marker (nobody edited it by hand)."""
    body, marker = split(raw)
    return marker is not None and digest(body) == marker.sha256
