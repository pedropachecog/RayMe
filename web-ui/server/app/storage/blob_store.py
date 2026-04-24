"""Filesystem blob storage helpers."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path, PurePath, PureWindowsPath


def _validate_blob_name(final_name: str) -> str:
    if not final_name or final_name in {".", ".."}:
        raise ValueError("blob name must be a non-empty filename")
    if "\x00" in final_name or "/" in final_name or "\\" in final_name:
        raise ValueError("blob name must not contain path separators")
    if PurePath(final_name).is_absolute() or PureWindowsPath(final_name).is_absolute():
        raise ValueError("blob name must be relative")
    if PurePath(final_name).name != final_name:
        raise ValueError("blob name must not contain path components")
    return final_name


def atomic_write_blob(blob_dir: Path, final_name: str, data: bytes) -> Path:
    """Write blob bytes through a same-directory temp file and atomic rename."""

    safe_name = _validate_blob_name(final_name)
    blob_dir.mkdir(parents=True, exist_ok=True)
    final_path = blob_dir / safe_name

    fd: int | None = None
    tmp_path: Path | None = None
    try:
        fd, tmp_name = tempfile.mkstemp(prefix=f".{safe_name}.", suffix=".tmp", dir=blob_dir)
        tmp_path = Path(tmp_name)
        with os.fdopen(fd, "wb") as tmp:
            fd = None
            tmp.write(data)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_path, final_path)
        return final_path
    except Exception:
        if fd is not None:
            os.close(fd)
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
        raise


__all__ = ["atomic_write_blob"]
