"""HTTP client for one axibridge server. Every failure becomes a ToolError
carrying a sentence a person can act on — never a traceback."""

from __future__ import annotations

from typing import Any, Callable

import httpx
from mcp.server.mcpserver.exceptions import ToolError

#: echoed by the server as the project event's `origin` (live sync)
CLIENT_ID = "mcp"


class ApiClient:
    def __init__(self, base_url: str, label: str, unreachable_hint: Callable[[], str],
                 timeout: float = 300.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.label = label
        self._hint = unreachable_hint
        self._http = httpx.Client(base_url=self.base_url, timeout=timeout,
                                  headers={"X-Axb-Client": CLIENT_ID})

    def request(self, method: str, path: str, body: Any = None,
                params: dict[str, Any] | None = None) -> httpx.Response:
        try:
            r = self._http.request(method, path, json=body, params=params)
        except httpx.ConnectError:
            raise ToolError(self._hint()) from None
        except httpx.TimeoutException:
            raise ToolError(f"{self.label}: {method} {path} timed out") from None
        except httpx.TransportError as exc:
            raise ToolError(f"{self.label}: {method} {path} failed: {exc}") from None
        if r.status_code >= 400:
            raise ToolError(f"{self.label}: {method} {path} → {r.status_code}: {_detail(r)}")
        return r

    def json(self, method: str, path: str, body: Any = None,
             params: dict[str, Any] | None = None) -> Any:
        r = self.request(method, path, body, params)
        if not r.content:
            return None
        try:
            return r.json()
        except ValueError:
            raise ToolError(f"{self.label}: {method} {path} returned a non-JSON body: "
                            f"{r.text[:200]!r}") from None

    def get(self, path: str, **params: Any) -> Any:
        return self.json("GET", path, params={k: v for k, v in params.items() if v is not None} or None)

    def post(self, path: str, body: Any = None) -> Any:
        return self.json("POST", path, {} if body is None else body)

    def put(self, path: str, body: Any) -> Any:
        return self.json("PUT", path, body)

    def patch(self, path: str, body: Any) -> Any:
        return self.json("PATCH", path, body)

    def delete(self, path: str) -> Any:
        return self.json("DELETE", path)

    def alive(self) -> bool:
        try:
            self._http.get("/api/project", timeout=2.0)
            return True
        except httpx.HTTPError:
            return False

    def close(self) -> None:
        self._http.close()


def _detail(r: httpx.Response) -> str:
    try:
        d = r.json().get("detail", r.text)
    except (ValueError, AttributeError):
        return r.text[:500]
    if isinstance(d, dict):
        return str(d.get("message") or d)[:500]
    if isinstance(d, list):
        return "; ".join(str(x.get("msg", x)) if isinstance(x, dict) else str(x) for x in d)[:500]
    return str(d)[:500]
