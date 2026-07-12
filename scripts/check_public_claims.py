#!/usr/bin/env python3
"""Fail-closed contract for current public copy and research claims."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = ROOT / "evaluation/research/current-public-copy-v1.json"


def load_inventory(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != "current-public-copy-v1":
        raise ValueError("current public copy inventory schema mismatch")
    return value


def _paths(inventory: dict[str, Any]) -> list[str]:
    scope = inventory.get("scope")
    if not isinstance(scope, dict):
        raise ValueError("scope must be an object")
    paths = scope.get("runtime_pages", []) + scope.get("current_documents", [])
    if not paths or not all(isinstance(path, str) and path for path in paths):
        raise ValueError("inventory paths must be non-empty strings")
    if len(paths) != len(set(paths)):
        raise ValueError("inventory paths must be unique")
    return paths


def validate(inventory_path: Path = DEFAULT_INVENTORY, root: Path = ROOT) -> list[str]:
    try:
        inventory = load_inventory(inventory_path)
        paths = _paths(inventory)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return [f"cannot load inventory: {exc}"]
    errors: list[str] = []
    contents: dict[str, str] = {}
    for relative in paths:
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts:
            errors.append(f"unsafe inventory path: {relative}")
            continue
        target = root / path
        if not target.is_file():
            errors.append(f"missing public copy surface: {relative}")
            continue
        contents[relative] = target.read_text(encoding="utf-8")
    forbidden = inventory.get("forbidden_patterns")
    if not isinstance(forbidden, list) or not forbidden:
        errors.append("forbidden_patterns must be a non-empty list")
    else:
        for pattern in forbidden:
            if not isinstance(pattern, str) or not pattern:
                errors.append("forbidden pattern must be a non-empty string")
                continue
            for relative, text in contents.items():
                if pattern.casefold() in text.casefold():
                    errors.append(f"forbidden public claim {pattern!r} in {relative}")
    rules = inventory.get("required_context")
    if not isinstance(rules, list) or not rules:
        errors.append("required_context must be a non-empty list")
    else:
        for index, rule in enumerate(rules):
            if not isinstance(rule, dict) or set(rule) != {"path", "patterns"}:
                errors.append(f"required_context[{index}] schema mismatch")
                continue
            text = contents.get(rule["path"])
            if text is None:
                errors.append(f"required context path is outside inventory: {rule['path']}")
                continue
            for pattern in rule["patterns"]:
                if pattern not in text:
                    errors.append(f"missing required context {pattern!r} in {rule['path']}")
    context_rules = inventory.get("context_rules")
    if not isinstance(context_rules, list) or not context_rules:
        errors.append("context_rules must document ambiguous claim terms")
    readability = inventory.get("readability_contract")
    required_readability = {"first_use", "two_layers", "actionable_states", "buttons", "restatement_test"}
    if not isinstance(readability, dict) or set(readability) != required_readability:
        errors.append("readability_contract must define all five public-copy rules")
    elif not all(isinstance(value, str) and value.strip() for value in readability.values()):
        errors.append("readability_contract rules must be non-empty strings")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    args = parser.parse_args()
    errors = validate(args.inventory.resolve())
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("current public copy claim contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
