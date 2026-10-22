from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
import hashlib
import re
import json

import httpx

from app.crypto import decrypt_json
from app.extensions import database
from app.models import SystemSetting


class RagClientError(RuntimeError):
    def __init__(self, status: int = 503):
        super().__init__("RAG request failed")
        self.status = status


@dataclass(frozen=True)
class RagBinary:
    status: int
    content: Iterable[bytes]
    headers: dict[str, str]
    close: Callable[[], None]


class RagClient:
    def __init__(self) -> None:
        row = database.session.get(SystemSetting, "rag.connection")
        if row is None:
            raise RagClientError()
        settings = decrypt_json(row.encrypted_value)
        self.base_url = settings["baseUrl"].rstrip("/")
        self.api_key = settings["apiKey"]
        self.timeout = float(settings.get("timeoutSeconds", 30))
        self.cache_key = hashlib.sha256(
            f"{self.base_url}\0{self.api_key}".encode("utf-8")
        ).hexdigest()

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}
        if extra:
            headers.update(extra)
        return headers

    def json(self, method: str, path: str, payload: dict | None = None):
        try:
            response = httpx.request(method, f"{self.base_url}{path}", json=payload,
                                     headers=self._headers(), timeout=self.timeout)
        except httpx.HTTPError as exc:
            raise RagClientError() from exc
        if response.status_code >= 400:
            raise RagClientError(404 if response.status_code == 404 else 503)
        try:
            return response.json()
        except ValueError as exc:
            raise RagClientError() from exc

    def retrieve_stream(self, path: str, payload: dict):
        try:
            with httpx.stream("POST", f"{self.base_url}{path}/stream", json=payload,
                              headers=self._headers({"Accept": "text/event-stream"}), timeout=self.timeout) as response:
                if response.status_code >= 400:
                    raise RagClientError()
                name, data = "", []
                completed = False
                for line in response.iter_lines():
                    if line.startswith("event:"):
                        name = line[6:].strip()
                    elif line.startswith("data:"):
                        data.append(line[5:].strip())
                    elif not line and data:
                        value = json.loads("\n".join(data))
                        if name == "error":
                            raise RagClientError()
                        if name in {"progress", "retrieval"}:
                            completed = completed or name == "retrieval"
                            yield name, value
                        name, data = "", []
                if not completed:
                    raise RagClientError()
        except (httpx.HTTPError, ValueError) as exc:
            raise RagClientError() from exc

    def binary(self, path: str, range_header: str | None = None) -> RagBinary:
        extra = {"Accept": "*/*"}
        if range_header:
            extra["Range"] = range_header
        client = httpx.Client(timeout=self.timeout)
        try:
            upstream_request = client.build_request(
                "GET", f"{self.base_url}{path}", headers=self._headers(extra))
            response = client.send(upstream_request, stream=True)
        except httpx.HTTPError as exc:
            client.close()
            raise RagClientError() from exc
        if response.status_code not in {200, 206}:
            response.close()
            client.close()
            raise RagClientError(404 if response.status_code == 404 else 503)
        allowed = {name: value for name, value in response.headers.items() if name.lower() in {
            "content-type", "content-range", "accept-ranges", "content-disposition", "content-length"
        }}
        partial = response.status_code == 206 and range_header is None
        total = None
        current_start = 0
        current_end = None
        if partial:
            match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("content-range", ""))
            if not match or int(match[1]) != 0 or int(match[2]) >= int(match[3]):
                response.close()
                client.close()
                raise RagClientError()
            current_end, total = int(match[2]), int(match[3])
            allowed.pop("content-range", None)
            allowed["content-length"] = str(total)
            allowed["accept-ranges"] = "bytes"

        def close() -> None:
            response.close()
            client.close()

        def content():
            nonlocal response, current_start, current_end
            try:
                while True:
                    received = 0
                    for chunk in response.iter_bytes():
                        received += len(chunk)
                        yield chunk
                    if not partial:
                        break
                    if received != current_end - current_start + 1:
                        raise RagClientError()
                    if current_end + 1 >= total:
                        break
                    next_start = current_end + 1
                    response.close()
                    requested_end = min(total - 1, next_start + 1048575)
                    try:
                        request = client.build_request("GET", f"{self.base_url}{path}", headers=self._headers({
                            "Accept": "*/*", "Range": f"bytes={next_start}-{requested_end}"}))
                        response = client.send(request, stream=True)
                    except httpx.HTTPError as exc:
                        raise RagClientError() from exc
                    match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("content-range", ""))
                    if response.status_code != 206 or not match or int(match[1]) != next_start \
                            or int(match[2]) > requested_end or int(match[3]) != total:
                        raise RagClientError()
                    current_start = next_start
                    current_end = int(match[2])
            finally:
                close()

        return RagBinary(200 if partial else response.status_code, content(), allowed, close)
