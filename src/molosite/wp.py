"""The WordPress REST client (namespace wp/v2). Credentials come from the environment and are never printed."""

from __future__ import annotations

import os

import requests


class WPError(RuntimeError):
    pass


def credentials() -> tuple[str, str]:
    user, password = os.environ.get("MOLO_WP_USER", ""), os.environ.get("MOLO_WP_APP_PASSWORD", "")
    if not user or not password:
        raise WPError("set MOLO_WP_USER and MOLO_WP_APP_PASSWORD in the environment (an application password of the Editor account)")
    return user, password


class WordPress:
    def __init__(self, base_url: str, auth: tuple[str, str], session: requests.Session | None = None):
        if not base_url.startswith("https://"):
            raise WPError(f"{base_url}: application passwords need HTTPS; refusing")
        self.api = base_url.rstrip("/") + "/wp-json/wp/v2"
        self.http = session or requests.Session()
        self.auth = auth

    def _call(self, method: str, path: str, **kw):
        # the URL and the message carry no credential
        try:
            resp = self.http.request(method, self.api + path, auth=self.auth, timeout=60, **kw)
        except requests.RequestException as exc:
            raise WPError(f"{method} {path}: {type(exc).__name__}") from None
        if not resp.ok:
            try:
                code = f" ({resp.json().get('code')})"  # WordPress's own error code; it never holds a credential
            except (ValueError, AttributeError):
                code = ""
            raise WPError(f"{method} {path}: HTTP {resp.status_code}{code}")
        try:
            return resp.json()
        except ValueError:
            raise WPError(f"{method} {path}: the answer is not JSON") from None

    def whoami(self) -> str:
        """The login the server sees for these credentials; fails clearly when it does not accept them."""
        try:
            return self._call("GET", "/users/me", params={"context": "edit"})["slug"]
        except WPError as exc:
            raise WPError(f"the server did not accept the credentials ({exc}). Check MOLO_WP_USER and the application password; "
                          "if they are right, Apache may be dropping the Authorization header") from None

    def list_pages(self) -> list[dict]:
        pages, number = [], 1
        while True:
            batch = self._call("GET", "/pages", params={"context": "edit", "per_page": 100, "page": number, "status": "publish,draft,private"})
            pages += batch
            if len(batch) < 100:
                return pages
            number += 1

    def get_page(self, page_id: int) -> dict:
        return self._call("GET", f"/pages/{page_id}", params={"context": "edit"})

    def find_page(self, slug: str) -> dict | None:
        found = self._call("GET", "/pages", params={"context": "edit", "slug": slug, "status": "publish,draft,private"})
        return found[0] if found else None

    def update_page(self, page_id: int, content: str) -> dict:
        return self._call("POST", f"/pages/{page_id}", json={"content": content})

    def create_page(self, slug: str, title: str, content: str, parent: int = 0, menu_order: int = 0) -> dict:
        body = {"slug": slug, "title": title, "content": content, "parent": parent, "menu_order": menu_order, "status": "publish"}
        return self._call("POST", "/pages", json=body)

    def get_media(self, media_id: int) -> dict:
        return self._call("GET", f"/media/{media_id}")

    def download(self, url: str) -> bytes:
        try:
            resp = self.http.get(url, timeout=60)
        except requests.RequestException as exc:
            raise WPError(f"GET media: {type(exc).__name__}") from None
        if not resp.ok:
            raise WPError(f"GET media: HTTP {resp.status_code}")
        return resp.content

    def find_media(self, name: str) -> str | None:
        stem = name.rsplit(".", 1)[0]
        for item in self._call("GET", "/media", params={"search": stem, "per_page": 20}):
            if item.get("source_url", "").rsplit("/", 1)[-1] == name:
                return item["source_url"]
        return None

    def upload_media(self, name: str, data: bytes, mime: str = "image/png") -> str:
        headers = {"Content-Disposition": f'attachment; filename="{name}"', "Content-Type": mime}
        return self._call("POST", "/media", data=data, headers=headers)["source_url"]
