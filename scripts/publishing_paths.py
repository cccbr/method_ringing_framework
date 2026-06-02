#!/usr/bin/env python3
"""Shared helpers for version ids and generated edition output folders."""

from __future__ import annotations

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
