from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from plannerme.errors import PlannerUsError
from plannerme.settings import PlannerMeSettings


class PlannerUsClient:
    """Minimal OpenProject API v3 client for PlannerUs."""

    def __init__(self, settings: PlannerMeSettings) -> None:
        self.settings = settings

    def get(self, path: str, params: dict[str, str] | None = None) -> Any:
        return self.request("GET", path, params=params)

    def post(self, path: str, body: Any | None = None) -> Any:
        return self.request("POST", path, body=body)

    def patch(self, path: str, body: Any | None = None) -> Any:
        return self.request("PATCH", path, body=body)

    def delete(self, path: str) -> Any:
        return self.request("DELETE", path)

    def collection(
        self,
        path: str,
        params: dict[str, str] | None = None,
        *,
        page_size: int = 100,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        params = dict(params or {})
        params["pageSize"] = str(page_size)
        offset = int(params.get("offset", "1"))
        elements: list[dict[str, Any]] = []

        while True:
            params["offset"] = str(offset)
            page = self.get(path, params)
            embedded = page.get("_embedded", {}) if isinstance(page, dict) else {}
            page_elements = embedded.get("elements", [])
            elements.extend(page_elements)
            if limit is not None and len(elements) >= limit:
                return elements[:limit]

            count = int(page.get("count", len(page_elements))) if isinstance(page, dict) else 0
            total = int(page.get("total", len(elements))) if isinstance(page, dict) else len(elements)
            if count <= 0 or len(elements) >= total:
                return elements
            offset += 1

    def request(self, method: str, path: str, *, params: dict[str, str] | None = None, body: Any | None = None) -> Any:
        url = self._url(path, params)
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {
            "Accept": "application/hal+json, application/json",
            "User-Agent": "plannerme/0.1.0",
            "Authorization": self._authorization_header(),
        }
        if data is not None:
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return self._decode_payload(response.read())
        except urllib.error.HTTPError as exc:
            details = self._decode_payload(exc.read())
            message = details.get("message") if isinstance(details, dict) else str(details)
            raise PlannerUsError(f"{method} {url} failed with HTTP {exc.code}: {message}") from exc
        except urllib.error.URLError as exc:
            raise PlannerUsError(f"{method} {url} failed: {exc.reason}") from exc

    def current_user_id(self) -> str:
        user = self.get("/users/me")
        if "id" not in user:
            raise PlannerUsError("Could not determine the current PlannerUs user id.")
        return str(user["id"])

    def ping(self) -> dict[str, Any]:
        root = self.get("/")
        current_user = self.get("/users/me")
        return {
            "base_url": self.settings.base_url,
            "api_root": root.get("_links", {}).get("self", {}).get("href"),
            "user": {
                "id": current_user.get("id"),
                "name": current_user.get("name"),
                "login": current_user.get("login"),
                "email": current_user.get("email"),
            },
        }

    def _url(self, path: str, params: dict[str, str] | None = None) -> str:
        if path.startswith(("http://", "https://")):
            url = path
        else:
            clean_path = path.strip()
            if clean_path.startswith("/api/v3"):
                clean_path = clean_path[len("/api/v3") :]
            clean_path = clean_path if clean_path.startswith("/") else f"/{clean_path}"
            url = f"{self.settings.base_url}/api/v3{clean_path}"

        if params:
            delimiter = "&" if urllib.parse.urlparse(url).query else "?"
            url = f"{url}{delimiter}{urllib.parse.urlencode(params)}"
        return url

    def _authorization_header(self) -> str:
        if self.settings.auth == "bearer":
            return f"Bearer {self.settings.api_key}"
        token = f"apikey:{self.settings.api_key}".encode("utf-8")
        return f"Basic {base64.b64encode(token).decode('ascii')}"

    @staticmethod
    def _decode_payload(payload: bytes) -> Any:
        if not payload:
            return None
        try:
            return json.loads(payload.decode("utf-8"))
        except json.JSONDecodeError as exc:
            preview = payload[:200].decode("utf-8", errors="replace")
            raise PlannerUsError(f"PlannerUs returned non-JSON data: {preview}") from exc
