import pytest

from molosite.config import ConfigError, Page, Site, dump, load, with_page


def write(tmp_path, text):
    path = tmp_path / "site.toml"
    path.write_text(text)
    return path


def test_roundtrip(tmp_path):
    site = Site(pages=(Page("a", 1, "A \"quoted\"", "managed", parent=3, pulled_sha256="ff"), Page("b", None, "B", "generated", "b.md.j2")),
                roles={"x": "y"}, cgs_variants=(".config/a.cgs",))
    path = write(tmp_path, dump(site))
    assert load(path) == site


@pytest.mark.parametrize("text,msg", [
    ('[[pages]]\nslug="a"\nmode="nope"\n', "mode"),
    ('[[pages]]\nslug="a"\nmode="generated"\n', "template"),
    ('[[pages]]\nslug="a"\n[[pages]]\nslug="a"\n', "twice"),
    ('[[pages]]\nslug="a"\nid=1\n[[pages]]\nslug="b"\nid=1\n', "id 1"),
    ('[[pages]]\nslug="a"\nbogus=1\n', "unknown"),
])
def test_invalid(tmp_path, text, msg):
    with pytest.raises(ConfigError, match=msg):
        load(write(tmp_path, text))


def test_with_page_keeps_mode():
    site = Site(pages=(Page("a", 1, mode="managed"),))
    assert with_page(site, Page("a", 1, "T")).pages[0].mode == "managed"
