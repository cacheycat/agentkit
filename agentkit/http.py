"""JSON over HTTPS with a certifi trust store, retries and a polite timeout."""
from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.request

try:
    import certifi
    _CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:  # fall back to the system store
    _CTX = ssl.create_default_context()


def fetch_json(url: str, body: dict | None = None, timeout: int = 30, retries: int = 2):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Accept": "application/json", "User-Agent": "agentkit/0.1"}
    if data:
        headers["Content-Type"] = "application/json"
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
                return json.loads(r.read())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last = e
            if isinstance(e, urllib.error.HTTPError) and e.code in (400, 404, 422):
                break
            time.sleep(0.8 * (attempt + 1))
    raise RuntimeError(f"request failed: {url.split('?')[0]} ({last})")
