"""Fetching and extracting readable text from a URL.

Two things here are not optional:

1. **SSRF guard.** The model chooses URLs. A model can be steered by page text it
   already read (prompt injection), so "fetch this URL" is attacker-controlled
   input. Without a guard, `http://169.254.169.254/` (cloud metadata) or
   `http://localhost:11434` reaches services the model should never touch.

2. **Size cap while streaming.** `await response.read()` on a 2GB video is how
   you run out of memory. We stop reading at 2MB.

Extraction uses trafilatura, which strips navigation, ads and boilerplate.
Raw HTML is mostly chrome; feeding it to a 4B model is expensive and confusing.
"""

from __future__ import annotations

import asyncio
import ipaddress
import time
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
import trafilatura

from .cache import Cache

MAX_BYTES = 2_000_000
MAX_REDIRECTS = 5
ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {None, 80, 443}
ALLOWED_CONTENT_TYPES = (
    "text/html",
    "application/xhtml+xml",
    "text/plain",
    "text/xml",
    "application/xml",
)
USER_AGENT = "research-agent/0.1 (+https://github.com/; educational project)"


class FetchError(Exception):
    """Anything the caller should show the model rather than crash on."""


@dataclass(slots=True)
class Document:
    url: str
    final_url: str
    title: str
    text: str
    status: int = 0
    content_type: str = ""
    truncated: bool = False
    from_cache: bool = False
    elapsed_ms: float = 0.0


# --------------------------------------------------------------------------- #
# SSRF guard
# --------------------------------------------------------------------------- #
async def assert_public_url(url: str) -> None:
    """Reject anything that is not a public http(s) endpoint."""
    parts = urlsplit(url)
    if parts.scheme not in ALLOWED_SCHEMES:
        raise FetchError(
            f"only http/https URLs can be fetched, got {parts.scheme or 'no scheme'!r}"
        )
    if not parts.hostname:
        raise FetchError("URL has no host")
    if parts.port not in ALLOWED_PORTS:
        raise FetchError(f"port {parts.port} is not allowed (only 80 and 443)")

    host = parts.hostname
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None

    if literal is not None:
        if not literal.is_global:
            raise FetchError(
                f"{host} is a non-public address ({literal}); refusing to fetch it"
            )
        return

    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, None)
    except OSError as exc:
        raise FetchError(f"could not resolve {host}: {exc}") from exc

    addresses = {str(info[4][0]).split("%")[0] for info in infos}
    blocked = [a for a in addresses if not ipaddress.ip_address(a).is_global]
    if blocked:
        raise FetchError(
            f"{host} resolves to non-public address(es) {sorted(blocked)}; refusing to fetch"
        )


def _normalize(url: str) -> str:
    url = url.strip()
    if not url:
        raise FetchError("empty URL")
    if "://" not in url:
        url = "https://" + url
    return url.split("#", 1)[0]


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #
class _TextExtractor(HTMLParser):
    """Last-resort fallback when trafilatura finds nothing."""

    SKIP = {"script", "style", "noscript", "svg", "head"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skipping = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in self.SKIP:
            self._skipping += 1
        elif tag in {"p", "br", "div", "li", "h1", "h2", "h3", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP and self._skipping:
            self._skipping -= 1

    def handle_data(self, data: str) -> None:
        if not self._skipping:
            self.parts.append(data)

    def text(self) -> str:
        raw = "".join(self.parts)
        lines = [" ".join(line.split()) for line in raw.splitlines()]
        return "\n".join(line for line in lines if line)


def extract_text(html: str, url: str, content_type: str) -> tuple[str | None, str]:
    if content_type in {"text/plain", "text/xml", "application/xml"}:
        return None, html.strip()

    title: str | None = None
    text: str | None = None
    try:
        metadata = trafilatura.extract_metadata(html, default_url=url)
        if metadata is not None:
            title = metadata.title
    except Exception:
        pass

    try:
        text = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=True,
            favor_recall=True,
        )
    except Exception:
        text = None

    if not text:
        fallback = _TextExtractor()
        fallback.feed(html)
        text = fallback.text()[:20_000]

    return title, text


# --------------------------------------------------------------------------- #
# Fetch
# --------------------------------------------------------------------------- #
async def fetch(
    url: str,
    *,
    cache: Cache | None = None,
    timeout: float = 20.0,
) -> Document:
    url = _normalize(url)
    cache_key = f"fetch:{url}"
    if cache is not None:
        hit = await cache.aget(cache_key)
        if hit is not None:
            document = Document(**hit)
            document.from_cache = True
            document.elapsed_ms = 0.0
            return document

    started = time.perf_counter()
    document = await _download(url, timeout)
    document.elapsed_ms = (time.perf_counter() - started) * 1000.0

    if cache is not None and document.text:
        await cache.aset(cache_key, asdict(document))
    return document


async def _download(url: str, timeout: float) -> Document:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.1",
    }
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout), headers=headers
    ) as client:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            # Checked on EVERY hop: a public URL can redirect to 127.0.0.1.
            await assert_public_url(current)

            async with client.stream(
                "GET", current, follow_redirects=False
            ) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise FetchError(f"redirect from {current} without Location")
                    current = urljoin(current, location)
                    continue

                if response.status_code >= 400:
                    raise FetchError(f"HTTP {response.status_code} for {current}")

                content_type = (
                    (response.headers.get("content-type") or "").split(";")[0].strip().lower()
                )
                if content_type and not any(
                    content_type.startswith(t) for t in ALLOWED_CONTENT_TYPES
                ):
                    raise FetchError(
                        f"unsupported content-type {content_type!r}; "
                        "only text pages are supported"
                    )

                chunks: list[bytes] = []
                size = 0
                truncated = False
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        keep = len(chunk) - (size - MAX_BYTES)
                        chunks.append(chunk[:keep])
                        truncated = True
                        break
                    chunks.append(chunk)

                raw = b"".join(chunks)
                encoding = response.charset_encoding or "utf-8"
                final_url = str(response.url)
                status = response.status_code
                break
        else:
            raise FetchError(f"too many redirects (>{MAX_REDIRECTS}) for {url}")

    html = raw.decode(encoding, errors="replace")
    title, text = extract_text(html, final_url, content_type)

    if not text:
        raise FetchError(f"no readable text extracted from {final_url}")

    return Document(
        url=url,
        final_url=final_url,
        title=title or "",
        text=text,
        status=status,
        content_type=content_type,
        truncated=truncated,
    )
