"""Robust helpers for pulling structured output out of free-form model text."""

from __future__ import annotations

import json
import re
from typing import Any

_THINK_PATTERNS = (
    re.compile(r"<think>(.*?)(?:</think>|$)", re.S | re.I),
    re.compile(r"\[THINK\](.*?)(?:\[/THINK\]|$)", re.S),
)
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S | re.I)
_TRAILING_COMMA = re.compile(r",\s*([}\]])")


def split_reasoning(text: str) -> tuple[str | None, str]:
    """Separate inline chain-of-thought (``<think>`` / ``[THINK]``) from the answer."""
    for pattern in _THINK_PATTERNS:
        match = pattern.search(text)
        if match:
            reasoning = match.group(1).strip()
            rest = (text[: match.start()] + text[match.end() :]).strip()
            return reasoning or None, rest
    return None, text.strip()


def _balanced_objects(text: str) -> list[str]:
    """Return every top-level ``{...}`` span, respecting strings and escapes."""
    spans: list[str] = []
    depth = 0
    start = -1
    in_string = False
    escaped = False
    for i, ch in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = depth > 0
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0:
                spans.append(text[start : i + 1])
    return spans


def _loads(candidate: str) -> Any:
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return json.loads(_TRAILING_COMMA.sub(r"\1", candidate))


def extract_json(text: str) -> dict[str, Any]:
    """Parse the model's JSON object, tolerating fences, prose and trailing commas.

    Candidates are tried in order: fenced blocks (last first), the whole body, then every
    balanced ``{...}`` span (last first) - when a model drafts several objects, the last wins.
    """
    _, body = split_reasoning(text)
    candidates = [
        *reversed([m.strip() for m in _FENCE.findall(body)]),
        body,
        *reversed(_balanced_objects(body)),
    ]
    saw_non_object = False
    for candidate in candidates:
        try:
            value = _loads(candidate)
        except ValueError:  # JSONDecodeError is a ValueError
            continue
        if isinstance(value, dict):
            return value
        saw_non_object = True
    if saw_non_object:
        raise ValueError("model returned JSON but not an object")
    raise ValueError("no JSON object found in model output")
