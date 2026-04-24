"""Filesystem blob storage safety contracts."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.storage.blob_store import atomic_write_blob
from app.storage.reaper import reap_orphan_blobs


def test_atomic_write_blob_rejects_path_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        atomic_write_blob(tmp_path, "../evil.png", b"not allowed")

    assert not (tmp_path.parent / "evil.png").exists()


def test_atomic_write_blob_uses_temp_until_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    final_name = "portrait.png"
    replace_calls: list[tuple[Path, Path]] = []
    real_replace = os.replace

    def record_replace(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        src_path = Path(src)
        dst_path = Path(dst)
        assert src_path.parent == tmp_path
        assert src_path.name.endswith(".tmp")
        assert not dst_path.exists()
        assert src_path.read_bytes() == b"portrait bytes"
        replace_calls.append((src_path, dst_path))
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", record_replace)

    final_path = atomic_write_blob(tmp_path, final_name, b"portrait bytes")

    assert final_path == tmp_path / final_name
    assert final_path.read_bytes() == b"portrait bytes"
    assert replace_calls == [(replace_calls[0][0], tmp_path / final_name)]


def test_atomic_write_blob_removes_temp_file_when_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_replace(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        atomic_write_blob(tmp_path, "portrait.png", b"portrait bytes")

    assert not (tmp_path / "portrait.png").exists()
    assert list(tmp_path.glob("*.tmp")) == []


def test_reap_orphan_blobs_deletes_only_inside_blob_dir(tmp_path: Path) -> None:
    blob_dir = tmp_path / "blobs"
    outside_dir = tmp_path / "outside"
    blob_dir.mkdir()
    outside_dir.mkdir()

    referenced = blob_dir / "referenced.png"
    orphan = blob_dir / "orphan.png"
    stale_tmp = blob_dir / ".upload.tmp"
    outside_file = outside_dir / "outside.png"
    nested_dir = blob_dir / "nested"
    nested_dir.mkdir()

    referenced.write_bytes(b"keep")
    orphan.write_bytes(b"delete")
    stale_tmp.write_bytes(b"delete tmp")
    outside_file.write_bytes(b"outside")
    (nested_dir / "nested.png").write_bytes(b"not enumerated")

    deleted = reap_orphan_blobs(
        blob_dir,
        {
            referenced,
            outside_file,
            Path("../outside/outside.png"),
        },
    )

    assert sorted(path.name for path in deleted) == [".upload.tmp", "orphan.png"]
    assert referenced.exists()
    assert not orphan.exists()
    assert not stale_tmp.exists()
    assert outside_file.exists()
    assert (nested_dir / "nested.png").exists()
