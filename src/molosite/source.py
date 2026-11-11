"""Where the facts come from: files of the repositories of the Operating Space, read at a commit of CGS-MOLO.

BranchSource reads `git show <ref>:<path>`, never the working tree, so an uncommitted change never reaches the site.
GithubSource reads the same files from raw.githubusercontent.com when there is no Operating Space.
"""

from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

import requests


class SourceError(RuntimeError):
    pass


def find_cgshome(start: Path) -> Path:
    """The nearest directory above `start` (or `start`) that holds `.cgitsync/`."""
    here = start.resolve()
    for candidate in (here, *here.parents):
        if (candidate / ".cgitsync").is_dir():
            return candidate
    raise SourceError(f"no .cgitsync/ above {start}: not inside an Operating Space (try --github)")


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if done.returncode != 0:
        raise SourceError(f"git {' '.join(args)} in {repo}: {done.stderr.strip()}")
    return done.stdout


class BranchSource:
    def __init__(self, cgshome: Path, ref: str = "CGS-MOLO", allow_behind: bool = False):
        self.home, self.ref, self.allow_behind = cgshome, ref, allow_behind
        self._checked: set[str] = set()

    def register(self, repos: dict[str, str]) -> None:
        """Mount paths are known to the Operating Space already; nothing to learn."""

    def _repo(self, mount: str) -> Path:
        path = (self.home / mount).resolve()
        if not (path / ".git").exists():
            raise SourceError(f"{mount}: not a git repository in the Operating Space")
        if mount not in self._checked:
            self._check(mount, path)
            self._checked.add(mount)
        return path

    def _check(self, mount: str, path: Path) -> None:
        branch = _git(path, "rev-parse", "--abbrev-ref", "HEAD").strip()
        if branch != self.ref:
            raise SourceError(f"{mount} is on '{branch}', not '{self.ref}'. Run: pixi run molo update .config/molonari.cgs")
        if self.allow_behind:
            return
        try:
            behind = int(_git(path, "rev-list", "--count", f"{self.ref}..origin/{self.ref}").strip())
        except SourceError:
            return  # no remote tracking ref: nothing to compare with
        if behind:
            raise SourceError(f"{mount} is {behind} commit(s) behind origin/{self.ref}. Run: pixi run molo update .config/molonari.cgs")

    def read(self, mount: str, path: str) -> str:
        return _git(self._repo(mount), "show", f"{self.ref}:{path}")

    def exists(self, mount: str, path: str) -> bool:
        try:
            self.read(mount, path)
            return True
        except SourceError:
            return False

    def read_bytes(self, mount: str, path: str) -> bytes:
        done = subprocess.run(["git", "-C", str(self._repo(mount)), "show", f"{self.ref}:{path}"], capture_output=True)
        if done.returncode != 0:
            raise SourceError(f"{mount}:{path} not found at {self.ref}")
        return done.stdout

    def sha(self, mount: str) -> str:
        return _git(self._repo(mount), "rev-parse", self.ref).strip()

    def date(self, mount: str) -> str:
        return _git(self._repo(mount), "show", "-s", "--format=%cs", self.ref).strip()

    def list(self, mount: str, directory: str) -> list[str]:
        out = _git(self._repo(mount), "ls-tree", "--name-only", self.ref, directory.rstrip("/") + "/")
        return [line for line in out.splitlines() if line]


class GithubSource:
    def __init__(self, ref: str = "CGS-MOLO", main_repo: str = "flipoyo/MOLONARI1D", session: requests.Session | None = None):
        self.ref = ref
        self.repos = {".": main_repo}
        self.http = session or requests.Session()

    def register(self, repos: dict[str, str]) -> None:
        self.repos.update(repos)

    def _name(self, mount: str) -> str:
        try:
            return self.repos[mount]
        except KeyError:
            raise SourceError(f"{mount}: not a repository of the Operating Space file") from None

    def _get(self, url: str, **kw) -> requests.Response:
        resp = self.http.get(url, timeout=30, **kw)
        if resp.status_code != 200:
            raise SourceError(f"GET {url}: HTTP {resp.status_code}")
        return resp

    def read(self, mount: str, path: str) -> str:
        return self.read_bytes(mount, path).decode("utf-8")

    def read_bytes(self, mount: str, path: str) -> bytes:
        return self._get(f"https://raw.githubusercontent.com/{self._name(mount)}/{self.ref}/{path}").content

    def exists(self, mount: str, path: str) -> bool:
        try:
            self.read_bytes(mount, path)
            return True
        except SourceError:
            return False

    def sha(self, mount: str) -> str:
        url = f"https://api.github.com/repos/{self._name(mount)}/commits/{self.ref}"
        return self._get(url, headers={"Accept": "application/vnd.github.sha"}).text.strip()

    def date(self, mount: str) -> str:
        url = f"https://api.github.com/repos/{self._name(mount)}/commits/{self.ref}"
        return self._get(url).json()["commit"]["committer"]["date"][:10]

    def list(self, mount: str, directory: str) -> list[str]:
        url = f"https://api.github.com/repos/{self._name(mount)}/contents/{directory}?ref={self.ref}"
        return [item["path"] for item in self._get(url).json()]


def load_toml(source, mount: str, path: str) -> dict:
    return tomllib.loads(source.read(mount, path))
