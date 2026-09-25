"""A small User-Agent parser.

Deliberately dependency-free: the User-Agent string is only used for coarse
device/browser buckets, so a handful of ordered regex checks is enough. The order
matters - Edge's UA also contains "Chrome", and Chrome's also contains "Safari".
"""

import re

# (bucket, pattern) - first match wins, so more specific patterns come first.
_DEVICE_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("bot", re.compile(r"bot|crawler|spider|curl|wget|python-requests|httpx", re.I)),
    ("tablet", re.compile(r"ipad|tablet|kindle|silk|playbook", re.I)),
    (
        "mobile",
        re.compile(r"mobi|iphone|ipod|android.*mobile|windows phone|blackberry", re.I),
    ),
    ("desktop", re.compile(r".")),  # fallback
]

_BROWSER_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("Edge", re.compile(r"edg[e/]", re.I)),
    ("Opera", re.compile(r"opr/|opera", re.I)),
    ("Samsung Internet", re.compile(r"samsungbrowser", re.I)),
    ("Firefox", re.compile(r"firefox|fxios", re.I)),
    ("Chrome", re.compile(r"chrome|crios|chromium", re.I)),
    ("Safari", re.compile(r"safari", re.I)),
    ("Internet Explorer", re.compile(r"msie|trident", re.I)),
]


def parse_device(user_agent: str | None) -> str:
    if not user_agent:
        return "unknown"
    for label, pattern in _DEVICE_RULES:
        if pattern.search(user_agent):
            return label
    return "unknown"


def parse_browser(user_agent: str | None) -> str:
    if not user_agent:
        return "unknown"
    for label, pattern in _BROWSER_RULES:
        if pattern.search(user_agent):
            return label
    return "Other"


def parse_all(user_agent: str | None) -> tuple[str, str]:
    """Return (device, browser) in one pass."""
    return parse_device(user_agent), parse_browser(user_agent)