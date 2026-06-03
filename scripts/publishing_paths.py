#!/usr/bin/env python3
"""Shared helpers for version ids and generated edition output folders."""

from __future__ import annotations

from pathlib import Path
import re


VERSION_DIR_RE = re.compile(r"^(?:version|edition)(\d+)$")


def normalize_version_id(value: str) -> str:
    """Normalize CLI/input identifiers to the internal versionN form."""
    match = VERSION_DIR_RE.fullmatch((value or "").strip())
    if match:
        return f"version{match.group(1)}"
    return (value or "").strip()


def edition_output_dir(version_id: str) -> str:
    """Map an internal version id to the generated edition folder name."""
    match = VERSION_DIR_RE.fullmatch(normalize_version_id(version_id))
    if match:
        return f"edition{match.group(1)}"
    return normalize_version_id(version_id)


def source_site_dir(version_id: str) -> str:
    """Map an internal version id to the published source site folder name."""
    match = VERSION_DIR_RE.fullmatch(normalize_version_id(version_id))
    if match:
        return f"version{match.group(1)}"
    return normalize_version_id(version_id)


def is_revision_stem(stem: str) -> bool:
    """Detect versioned or revision-suffixed page stems such as syntax-v2.1."""
    return bool(re.search(r"-v\d+(?:\.\d+)*$", stem))


def version_sort_key(version_id: str) -> tuple[int, str]:
    """Sort normalized version ids numerically where possible."""
    normalized = normalize_version_id(version_id)
    match = VERSION_DIR_RE.fullmatch(normalized)
    if match:
        return (int(match.group(1)), normalized)
    return (10**9, normalized)


def discover_version_ids(*roots: str | Path, required_file: str | None = "index.xml") -> list[str]:
    """Discover version/edition directories across one or more roots."""
    version_ids: set[str] = set()

    for root in roots:
        root_path = Path(root)
        if not root_path.exists():
            continue

        for child in root_path.iterdir():
            if not child.is_dir() or child.name == "__pycache__":
                continue

            normalized = normalize_version_id(child.name)
            if not VERSION_DIR_RE.fullmatch(normalized):
                continue
            if required_file is not None and not (child / required_file).exists():
                continue
            version_ids.add(normalized)

    return sorted(version_ids, key=version_sort_key)
