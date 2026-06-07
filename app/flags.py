from __future__ import annotations

import re


DEFAULT_FLAG_RE = re.compile(r"[A-Z0-9]{31}=")


def extract_flags(text: str) -> list[str]:
    flags = DEFAULT_FLAG_RE.findall(text.upper())
    if flags:
        return sorted(set(flags))

    candidates = []
    for token in re.split(r"[\s,;]+", text.strip()):
        token = token.strip()
        if token:
            candidates.append(token)
    return sorted(set(candidates))


def classify_submit_message(message: str) -> str:
    lowered = message.lower()
    if "accepted" in lowered:
        return "accepted"
    if "already" in lowered:
        return "rejected"
    if "invalid" in lowered or "old" in lowered or "own" in lowered:
        return "rejected"
    return "rejected"
