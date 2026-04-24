"""Filesystem blob orphan cleanup helpers."""

from __future__ import annotations

from pathlib import Path


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _normalize_referenced_paths(blob_root: Path, referenced_paths: set[Path]) -> set[Path]:
    normalized: set[Path] = set()
    for referenced_path in referenced_paths:
        candidate = referenced_path
        if not candidate.is_absolute():
            candidate = blob_root / candidate
        resolved = candidate.resolve(strict=False)
        if _is_relative_to(resolved, blob_root):
            normalized.add(resolved)
    return normalized


def reap_orphan_blobs(blob_dir: Path, referenced_paths: set[Path]) -> list[Path]:
    """Delete temp and unreferenced blob files under the configured blob directory."""

    if not blob_dir.exists():
        return []

    blob_root = blob_dir.resolve(strict=False)
    referenced = _normalize_referenced_paths(blob_root, referenced_paths)
    deleted: list[Path] = []

    for candidate in sorted(blob_dir.iterdir()):
        resolved = candidate.resolve(strict=False)
        if not _is_relative_to(resolved, blob_root):
            continue
        if candidate.is_dir():
            continue
        if candidate.suffix == ".tmp" or resolved not in referenced:
            candidate.unlink()
            deleted.append(candidate)

    return deleted


__all__ = ["reap_orphan_blobs"]
