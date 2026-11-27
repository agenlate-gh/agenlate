"""Keeping invented links out of what agents deliver.

A model asked for sources will sometimes skip the search and write links from
memory. They look right — a real news site, a plausible article path — and
lead nowhere. In a research brief that is worse than no link at all, because
the reader trusts the citation and the product along with it.

So a link an agent writes has to be traceable to something: a search result
the provider reported for this turn, or text the agent was given (its
instructions, the objective, the transcript — which is how a link a user
pasted, or one a researcher found earlier, stays usable). Anything else is
unsupported.

Matching is on the whole address, not the site. A real site with an invented
article path is exactly the failure this exists to catch.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import urlsplit

_URL = re.compile(r"https?://[^\s<>()\[\]{}\"'`|]+", re.IGNORECASE)
_MARKDOWN_LINK = re.compile(r"\[([^\]\n]*)\]\((https?://[^\s)]+)\)", re.IGNORECASE)
_TRAILING = ".,;:!?*_~"

REMOVED_MARKER = "(unverified link removed)"


def find_links(text: str) -> list[str]:
    """Every web address in ``text``, in order, without trailing punctuation."""
    return [match.group(0).rstrip(_TRAILING) for match in _URL.finditer(text or "")]


def normalize(url: str) -> str:
    """One spelling per address, so trivial differences do not count as new.

    Scheme, a leading ``www.``, letter case in the host, a fragment and a
    trailing slash are all ignored. The path and query are kept: they are what
    distinguishes a real article from an invented one.
    """
    parts = urlsplit(url.strip().rstrip(_TRAILING))
    host = (parts.hostname or "").lower().removeprefix("www.")
    path = parts.path.rstrip("/")
    query = f"?{parts.query}" if parts.query else ""
    return f"{host}{path}{query}"


def unsupported_links(content: str, known: Iterable[str]) -> list[str]:
    """Links in ``content`` that match none of ``known``, each listed once."""
    allowed = {normalize(url) for url in known}
    seen: set[str] = set()
    result: list[str] = []
    for url in find_links(content):
        key = normalize(url)
        if key not in allowed and key not in seen:
            seen.add(key)
            result.append(url)
    return result


def remove_links(content: str, links: Iterable[str]) -> str:
    """``content`` without ``links``.

    A markdown link keeps its text, so a sentence still reads; a bare address
    is replaced with a short marker, so the reader can see something was taken
    out rather than wondering why a "Source:" line is empty.
    """
    targets = {normalize(url) for url in links}
    if not targets:
        return content

    def unlink(match: re.Match[str]) -> str:
        return match.group(1) if normalize(match.group(2)) in targets else match.group(0)

    content = _MARKDOWN_LINK.sub(unlink, content)

    def drop(match: re.Match[str]) -> str:
        url = match.group(0)
        trimmed = url.rstrip(_TRAILING)
        if normalize(trimmed) not in targets:
            return url
        return REMOVED_MARKER + url[len(trimmed):]

    return _URL.sub(drop, content)
