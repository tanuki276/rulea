"""Parser for the intentionally small .rulea policy format."""

from __future__ import annotations

import re
from pathlib import Path


class RuleParseError(ValueError):
    """Raised when a .rulea file is malformed."""


_RULE_RE = re.compile(r"^rule\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*$")
_FIELD_RE = re.compile(r"^(when|reason|description|tags|priority|enabled):(?:\s*)(.*)$")


def parse_rule_file(path: str):
    """Parse a UTF-8 .rulea file into immutable-policy-like dictionaries.

    The format is deliberately declarative: one rule followed by simple
    ``field: value`` entries. Python statements, imports and executable
    actions are rejected rather than silently accepted.
    """
    rules = {}
    current = None
    current_name = None

    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise RuleParseError("could not read rule file") from exc

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        match = _RULE_RE.match(line)
        if match:
            name = match.group(1)
            if name in rules:
                raise RuleParseError(f"duplicate rule at line {lineno}")
            current_name = name
            current = {
                "when": "",
                "reason": "Permission denied",
                "description": "",
                "tags": [],
                "priority": 100,
                "enabled": True,
            }
            rules[name] = current
            continue

        if current is None:
            raise RuleParseError(f"content outside a rule at line {lineno}")

        field = _FIELD_RE.match(line)
        if not field:
            raise RuleParseError(f"invalid syntax at line {lineno}")

        key, value = field.groups()
        if key == "when":
            current["when"] = value
        elif key == "reason":
            current["reason"] = _parse_string(value, lineno)
        elif key == "description":
            current["description"] = _parse_string(value, lineno)
        elif key == "tags":
            current["tags"] = [x.strip() for x in value.split(",") if x.strip()]
            if len(current["tags"]) > 32:
                raise RuleParseError(f"too many tags at line {lineno}")
        elif key == "priority":
            try:
                priority = int(value)
            except ValueError as exc:
                raise RuleParseError(f"invalid priority at line {lineno}") from exc
            if not 0 <= priority <= 1000:
                raise RuleParseError(f"priority out of range at line {lineno}")
            current["priority"] = priority
        elif key == "enabled":
            normalized = value.lower()
            if normalized not in {"true", "false"}:
                raise RuleParseError(f"enabled must be true or false at line {lineno}")
            current["enabled"] = normalized == "true"

    if not rules:
        raise RuleParseError("rule file contains no rules")
    for name, rule in rules.items():
        if not rule["when"]:
            raise RuleParseError(f"rule '{name}' has no when expression")
    return rules


def _parse_string(value: str, lineno: int) -> str:
    if len(value) < 2 or value[0] != '"' or value[-1] != '"':
        raise RuleParseError(f"string value must use double quotes at line {lineno}")
    # Avoid Python eval: accept JSON-compatible escaped strings only.
    import json
    try:
        result = json.loads(value)
    except json.JSONDecodeError as exc:
        raise RuleParseError(f"invalid string at line {lineno}") from exc
    if not isinstance(result, str):
        raise RuleParseError(f"expected a string at line {lineno}")
    return result
