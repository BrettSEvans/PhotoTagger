"""Embed/remove player names in JPEG IPTC (XMP-iptcExt:PersonInImage) metadata via exiftool.

Supersedes the XMP-sidecar write path (metadata_sidecar.py) for player-in-photo
tagging: this writes directly into the JPEG's own metadata rather than a
sidecar file, so it must be atomic and backed up (see backup_directory).
"""

import os
import secrets
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Iterable

# List-type XMP tags require a two-invocation clear-then-add — combining
# "-TAG=" and "-TAG+=value" in one exiftool command was empirically verified
# (exiftool 13.55) to NOT clear before adding: the old values survive. See
# docs/product/04-architecture.md "Risks & open technical questions".
_PERSON_TAG = "XMP-iptcExt:PersonInImage"

# Serializes every write across the whole process. Embed writes are
# human-paced (one assign/unassign click at a time) and infrequent, so a
# single process-wide lock is simpler than per-path locking and closes the
# race where two rapid assign/unassign actions on the same multi-face photo
# would otherwise run two exiftool subprocesses against the same file
# concurrently (critic finding, architect review pass 1).
_write_lock = threading.Lock()


class IptcWriteError(Exception):
    """Raised when an exiftool-based IPTC read or write fails."""


def _run_exiftool(args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["exiftool", *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError as exc:
        raise IptcWriteError("exiftool not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise IptcWriteError(f"exiftool timed out: {args}") from exc
    if result.returncode != 0:
        raise IptcWriteError(result.stderr.strip() or f"exiftool failed: {args}")
    return result.stdout


def read_person_in_image(filepath: str) -> list[str]:
    """Return the current PersonInImage values for a JPEG, in file order."""
    output = _run_exiftool([f"-{_PERSON_TAG}", "-s3", "-sep", ", ", filepath]).strip()
    if not output:
        return []
    return [name for name in output.split(", ") if name]


def write_iptc(
    filepath: str,
    names_to_add: Iterable[str] = (),
    names_to_remove: Iterable[str] = (),
) -> None:
    """Merge names_to_add into / drop names_to_remove from a JPEG's PersonInImage bag.

    Atomic: computes the full merged list, writes it to a uniquely-named temp
    copy, verifies the copy, then replaces the original with os.replace (atomic
    on the same filesystem). A true no-op (nothing to add/remove, or the merge
    doesn't change anything) never touches the file.
    """
    path = Path(filepath)
    if not path.exists():
        raise IptcWriteError(f"Photo not found: {filepath}")

    add_set = [n.strip() for n in names_to_add if n and n.strip()]
    remove_keys = {n.strip().casefold() for n in names_to_remove if n and n.strip()}

    with _write_lock:
        current = read_person_in_image(filepath)
        existing_keys = {n.casefold() for n in current}

        merged = [n for n in current if n.casefold() not in remove_keys]
        for name in add_set:
            key = name.casefold()
            if key not in existing_keys and key not in remove_keys:
                merged.append(name)
                existing_keys.add(key)
            elif key in remove_keys:
                # Adding and removing the same name in one call: add wins.
                if name not in merged:
                    merged.append(name)

        if merged == current:
            return

        tmp_path = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
        shutil.copy2(path, tmp_path)
        try:
            _run_exiftool(["-overwrite_original", f"-{_PERSON_TAG}=", str(tmp_path)])
            if merged:
                add_args = [f"-{_PERSON_TAG}+={name}" for name in merged]
                _run_exiftool(["-overwrite_original", *add_args, str(tmp_path)])

            if not tmp_path.exists() or tmp_path.stat().st_size == 0:
                raise IptcWriteError(f"exiftool produced an empty/missing output for {filepath}")

            os.replace(tmp_path, path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)


def is_backup_ready(dest_dir: str = "uploads_backup") -> bool:
    """Whether the one-time uploads backup has completed.

    Callers must check this before the first write_iptc() call and skip the
    embed (non-fatal, matching the exiftool-missing degradation path) if the
    backup job hasn't finished yet — writes must never race ahead of it.
    """
    return Path(dest_dir).exists()


def backup_directory(source_dir: str, dest_dir: str) -> dict:
    """One-time copy of every JPEG from source_dir into dest_dir.

    Idempotent: if dest_dir already exists on disk, does nothing and returns
    performed=False. This on-disk check is the source of truth across process
    restarts (an in-memory "already backed up" flag is an optional fast-path
    layered on top by the caller, not a replacement for this check).
    """
    dest = Path(dest_dir)
    if dest.exists():
        return {"performed": False, "reason": "backup already exists", "files_copied": 0}

    source = Path(source_dir)
    if not source.exists():
        raise IptcWriteError(f"Source directory not found: {source_dir}")

    dest.mkdir(parents=True, exist_ok=True)
    copied = 0
    for entry in source.iterdir():
        if entry.is_file() and entry.suffix.lower() in {".jpg", ".jpeg"}:
            shutil.copy2(entry, dest / entry.name)
            copied += 1
    return {"performed": True, "files_copied": copied}
