import pytest

from conftest import git
from molosite.facts import gather, first_paragraph, section
from molosite.config import Site
from molosite.source import BranchSource, SourceError, find_cgshome


def test_cgshome_is_nearest_dir_with_cgitsync(space):
    assert find_cgshome(space / "computo") == space
    with pytest.raises(SourceError):
        find_cgshome(space.parent.parent)


def test_reads_commit_not_working_tree(space):
    (space / "pixi.toml").write_text('[workspace]\nversion = "9.9.9"\n')  # uncommitted
    src = BranchSource(space)
    assert "1.0.2" in src.read(".", "pixi.toml")
    assert src.sha(".") == git(space, "rev-parse", "CGS-MOLO").strip()


def test_wrong_branch_is_refused(space):
    git(space / "computo", "checkout", "-b", "other")
    with pytest.raises(SourceError, match="molo update"):
        BranchSource(space).read("computo", "README.md")


def test_behind_origin_is_refused_unless_allowed(space, tmp_path):
    git(space / "computo", "update-ref", "refs/remotes/origin/CGS-MOLO", "HEAD")
    (space / "computo" / "n").write_text("n")
    git(space / "computo", "add", "n")
    git(space / "computo", "commit", "-m", "ahead")
    git(space / "computo", "update-ref", "refs/remotes/origin/CGS-MOLO", "HEAD")
    git(space / "computo", "reset", "--hard", "HEAD~1")
    with pytest.raises(SourceError, match="behind"):
        BranchSource(space).read("computo", "README.md")
    assert BranchSource(space, allow_behind=True).read("computo", "README.md")


def test_facts_skip_private_and_read_versions(space):
    facts = gather(BranchSource(space), Site(sections={"r": "README.md#Recompose"}))
    assert [r["name"] for r in facts["repos"]] == ["MOLONARI1D", "MOLONARI-computo"]
    assert facts["repos"][1]["version"] == "1.0.1"
    assert facts["repos"][1]["role"] == "Inverse modelling of heat transport."
    assert facts["sections"]["r"] == "Run molo load."
    assert facts["date"] == "2026-11-11"


def test_section_missing_heading_fails():
    with pytest.raises(SourceError):
        section("# A\n\nx", "B")


def test_first_paragraph_skips_badges():
    assert first_paragraph("# T\n\n![x](y)\n\nHello\nworld.\n\nmore") == "Hello world."


def test_relative_links_point_at_github():
    from molosite.facts import absolute_links
    out = absolute_links("[a](pixi.toml) [b](https://x.y) [c](#top) [d](.config)", "o/r", "CGS-MOLO")
    assert out == "[a](https://github.com/o/r/blob/CGS-MOLO/pixi.toml) [b](https://x.y) [c](#top) [d](https://github.com/o/r/blob/CGS-MOLO/.config)"
