import json
import re
import shutil
from pathlib import Path

import pytest
import responses

from conftest import git, make_repo
from molosite import marker
from molosite.config import Page, Site, load, save
from molosite.source import BranchSource
from molosite.sync import DRIFT, UNCHANGED, UPDATE, CREATE, SyncError, plan, pull, push
from molosite.wp import WordPress, WPError, credentials

API = "https://molonari.io/wp-json/wp/v2"
TEMPLATE = """## Operating Space {#os}

{% for r in repos %}- [{{ r.name }}]({{ r.url }}) `{{ r.path }}` {{ r.version }}: {{ r.role }}
{% endfor %}
{{ sections.r }}
"""


@pytest.fixture
def gate(tmp_path):
    """A MOLONARI-gate checkout (a clean git repo) with one managed, one generated and one editorial page."""
    root = tmp_path / "gate"
    (root / "website" / "pages").mkdir(parents=True)
    (root / "website" / "templates").mkdir()
    (root / "website" / "templates" / "operating-space.md.j2").write_text(TEMPLATE)
    (root / "website" / "pages" / "molonari.html").write_text("<!-- wp:paragraph -->\n<p>Front</p>\n<!-- /wp:paragraph -->\n")
    make_repo(root, {".gitignore": ".dev/.backup/\n"})
    return root


@pytest.fixture
def site():
    return Site(sections={"r": "README.md#Recompose"}, pages=(
        Page("molonari", 6, "Molonari", "managed"),
        Page("operating-space", None, "Operating Space", "generated", "operating-space.md.j2"),
        Page("gallery", 112, "Gallery", "editorial"),
    ))


def wp():
    return WordPress("https://molonari.io", ("u", "p"))


def live(content, pid=6):
    return {"id": pid, "slug": "x", "title": {"raw": "T"}, "content": {"raw": content}}


def factory(space):
    return lambda: BranchSource(space)


def test_plan_after_pull_is_empty_and_editorial_gets_no_request(gate, site, space):
    raw = "<!-- wp:paragraph -->\n<p>Front</p>\n<!-- /wp:paragraph -->\n"
    site = Site(pages=(Page("molonari", 6, mode="managed", pulled_sha256=marker.digest(raw)), site.pages[2]))
    with responses.RequestsMock() as rsps:
        rsps.get(f"{API}/pages/6", json=live(raw))
        entries = plan(site, gate, wp(), factory(space))
    assert [(e.page.slug, e.action) for e in entries] == [("molonari", UNCHANGED)]
    assert all("112" not in c.request.url for c in rsps.calls)


@responses.activate
def test_generated_page_is_created_then_unchanged(gate, site, space):
    responses.get(f"{API}/pages/6", json=live(marker.write("<!-- wp:paragraph -->\n<p>Front</p>\n<!-- /wp:paragraph -->", "g")))
    responses.get(f"{API}/pages", json=[])
    entries = {e.page.slug: e for e in plan(site, gate, wp(), factory(space))}
    assert entries["operating-space"].action == CREATE
    body = entries["operating-space"].body
    assert "MOLONARI-computo" in body and "dev-hub" not in body and "Run molo load." in body and "CGS-MOLO" in body
    assert entries["operating-space"].src.startswith("MOLONARI1D@")
    # the same page, now live with its marker: nothing to do
    responses.replace(responses.GET, f"{API}/pages", json=[live(marker.write(body, "x"), 9)])
    again = {e.page.slug: e.action for e in plan(site, gate, wp(), factory(space))}
    assert again["operating-space"] == UNCHANGED


@responses.activate
def test_hand_edit_is_drift_push_refuses_adopt_overwrites(gate, site, space):
    good = marker.write("<p>old</p>", "g")
    responses.get(f"{API}/pages/6", json=live(good.replace("old", "HAND EDIT")))
    responses.get(f"{API}/pages", json=[])
    post = responses.post(f"{API}/pages/6", json={"id": 6})
    responses.post(f"{API}/pages", json={"id": 9})
    entries = plan(site, gate, wp(), factory(space))
    assert {e.page.slug: e.action for e in entries}["molonari"] == DRIFT
    lines = []
    assert push(site, gate, wp(), entries, set(), factory(space), lines.append) == 1
    assert post.call_count == 0 and any("refused" in l and "pull molonari" in l for l in lines)
    backup = list((gate / ".dev" / ".backup").glob("*/molonari.html"))
    assert backup == []  # the refused page was not touched, so nothing to back up
    push(site, gate, wp(), plan(site, gate, wp(), factory(space)), {"molonari"}, factory(space), lines.append)
    assert post.call_count == 1
    sent = json.loads(post.calls[0].request.body)["content"]
    assert marker.intact(sent) and "Front" in sent
    assert "HAND EDIT" in next((gate / ".dev" / ".backup").glob("*/molonari.html")).read_text()


@responses.activate
def test_a_401_stops_with_no_partial_write(gate, site, space):
    responses.get(f"{API}/pages/6", json=live("<p>old</p>"))
    responses.get(f"{API}/pages", json=[])
    responses.post(f"{API}/pages/6", status=401)
    created = responses.post(f"{API}/pages", json={"id": 9})
    site = Site(**{**site.__dict__, "pages": (Page("molonari", 6, mode="managed", pulled_sha256=marker.digest("<p>old</p>")), site.pages[1])})
    entries = plan(site, gate, wp(), factory(space))
    with pytest.raises(WPError, match="401"):
        push(site, gate, wp(), entries, set(), factory(space), lambda s: None)
    assert created.call_count == 0


def test_push_refuses_a_dirty_gate(gate, site, space):
    (gate / "stray.txt").write_text("x")
    with pytest.raises(SyncError, match="uncommitted"):
        push(site, gate, wp(), [], set(), factory(space))


@responses.activate
def test_pull_is_lossless_and_keeps_modes(gate, tmp_path):
    raw = '<!-- wp:group -->\n<div class="x">é\r\n</div>\n<!-- /wp:group -->'
    responses.get(f"{API}/pages", json=[{**live(raw, 32), "slug": "molonari-1d", "parent": 2, "menu_order": 3}])
    site = Site(pages=(Page("molonari-1d", None, mode="managed"),))
    new, written = pull(site, gate := tmp_path, wp())
    assert (gate / "website/pages/molonari-1d.html").read_bytes() == raw.encode()
    page = new.pages[0]
    assert (page.id, page.mode, page.parent, page.menu_order) == (32, "managed", 2, 3)
    path = tmp_path / "site.toml"
    save(new, path)
    assert load(path) == new


def test_https_only_and_credentials_from_env(monkeypatch):
    with pytest.raises(WPError, match="HTTPS"):
        WordPress("http://molonari.io", ("u", "p"))
    monkeypatch.delenv("MOLO_WP_USER", raising=False)
    with pytest.raises(WPError, match="MOLO_WP_USER"):
        credentials()


def test_golden_and_determinism(gate, site, space):
    from molosite.facts import gather
    from molosite.sync import render_generated
    src = BranchSource(space)
    facts = gather(src, site)
    out = render_generated(gate, site.pages[1], facts, src, lambda n, d: n)
    assert out == render_generated(gate, site.pages[1], facts, src, lambda n, d: n)
    out = re.sub(r"`[0-9a-f]{7}`", "`<sha>`", out)
    golden = Path(__file__).parent / "golden" / "operating-space.html"
    if not golden.exists():
        golden.write_text(out)
    assert out == golden.read_text()


def test_unsupported_markdown_in_template_is_syncerror(gate, site, space):
    from molosite.facts import gather
    from molosite.sync import render_generated
    (gate / "website/templates/operating-space.md.j2").write_text("> quote\n")
    src = BranchSource(space)
    with pytest.raises(SyncError, match="operating-space"):
        render_generated(gate, site.pages[1], gather(src, site), src, lambda n, d: n)


def test_not_a_git_checkout_fails_closed(tmp_path):
    from molosite.sync import gate_dirty
    with pytest.raises(SyncError):
        gate_dirty(tmp_path)


@responses.activate
def test_pull_lists_media_and_save_keeps_header(gate, tmp_path):
    raw = '<!-- wp:image {"id":41} -->\n<figure><img class="wp-image-41" src="x"/></figure>\n<!-- /wp:image -->'
    responses.get(f"{API}/pages", json=[{**live(raw, 32), "slug": "a"}])
    responses.get(f"{API}/media/41", json={"source_url": "https://molonari.io/wp-content/uploads/a.png"})
    responses.get("https://molonari.io/wp-content/uploads/a.png", body=b"PNG")
    new, _ = pull(Site(), gate, wp())
    import tomllib, hashlib
    media = tomllib.loads((gate / "website/media.toml").read_text())["media"]
    assert media == [{"id": 41, "url": "https://molonari.io/wp-content/uploads/a.png", "sha256": hashlib.sha256(b"PNG").hexdigest()}]
    path = tmp_path / "site.toml"
    path.write_text("# header\nbase_url = \"https://molonari.io\"\n")
    save(new, path)
    assert path.read_text().startswith("# header\n") and load(path) == new


@responses.activate
def test_push_refuses_a_page_changed_since_plan(gate, site, space):
    old = "<p>old</p>"
    site = Site(pages=(Page("molonari", 6, mode="managed", pulled_sha256=marker.digest(old)),))
    responses.get(f"{API}/pages/6", json=live(old))
    post = responses.post(f"{API}/pages/6", json={"id": 6})
    entries = plan(site, gate, wp(), factory(space))
    assert entries[0].action == UPDATE
    responses.replace(responses.GET, f"{API}/pages/6", json=live("<p>edited meanwhile</p>"))
    lines = []
    assert push(site, gate, wp(), entries, set(), factory(space), lines.append) == 1
    assert post.call_count == 0 and "changed on the site" in lines[0]


@responses.activate
def test_page_found_by_slug_is_updated_by_its_live_id(gate, space):
    site = Site(sections={"r": "README.md#Recompose"}, pages=(Page("operating-space", None, "OS", "generated", "operating-space.md.j2"),))
    responses.get(f"{API}/pages", json=[{**live(marker.write("<p>stale</p>", "x"), 9), "slug": "operating-space"}])
    responses.get(f"{API}/pages/9", json=live(marker.write("<p>stale</p>", "x"), 9))
    post = responses.post(f"{API}/pages/9", json={"id": 9})
    entries = plan(site, gate, wp(), factory(space))
    assert entries[0].action == UPDATE and entries[0].page.id == 9
    push(site, gate, wp(), entries, set(), factory(space), lambda s: None)
    assert post.call_count == 1


@responses.activate
def test_created_page_records_its_id(gate, space):
    site = Site(sections={"r": "README.md#Recompose"}, pages=(Page("operating-space", None, "OS", "generated", "operating-space.md.j2"),))
    responses.get(f"{API}/pages", json=[])
    responses.post(f"{API}/pages", json={"id": 77})
    entries = plan(site, gate, wp(), factory(space))
    push(site, gate, wp(), entries, set(), factory(space), lambda s: None)
    assert entries[0].page.id == 77
