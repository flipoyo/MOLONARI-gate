import subprocess
from pathlib import Path

import pytest

CGS = '''project = "MOLONARI"
repos = [
    { repository = "github:flipoyo/MOLONARI1D", relative_path = ".", default_branch = "CGS-MOLO" },
    { repository = "github:flipoyo/MOLONARI-computo", relative_path = "computo", default_branch = "CGS-MOLO" },
    { repository = "github:flipoyo/ComplexGitSync", relative_path = "dev-hub", private = true },
]
'''


def git(path: Path, *args: str) -> str:
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
           "GIT_AUTHOR_DATE": "2026-11-11T10:00:00", "GIT_COMMITTER_DATE": "2026-11-11T10:00:00", "PATH": "/usr/bin:/bin:/usr/local/bin"}
    return subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True, text=True, env=env).stdout


def make_repo(path: Path, files: dict[str, str], branch: str = "CGS-MOLO") -> None:
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-b", branch)
    for name, text in files.items():
        (path / name).parent.mkdir(parents=True, exist_ok=True)
        (path / name).write_text(text)
    git(path, "add", "-A")
    git(path, "commit", "-m", "init")


@pytest.fixture
def space(tmp_path):
    """A fake Operating Space: .cgitsync/, MOLONARI1D at the root, computo and a private dev-hub mounted inside it."""
    home = tmp_path / "space"
    (home / ".cgitsync").mkdir(parents=True)
    make_repo(home, {".config/molonari.cgs": CGS, "pixi.toml": '[workspace]\nname = "m"\nversion = "1.0.2"\n',
                     "README.md": "# MOLONARI1D\n\nThe river temperature project.\n\n## Recompose\n\nRun molo load.\n\n## Other\n\nx\n"})
    make_repo(home / "computo", {"pixi.toml": '[workspace]\nname = "c"\nversion = "1.0.1"\n', "README.md": "# computo\n\n[![b](x)](y)\n\nInverse modelling of heat transport.\n"})
    make_repo(home / "dev-hub", {"README.md": "secret\n"})
    return home
