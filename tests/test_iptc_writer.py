"""Tests for src/iptc_writer.py — IPTC PersonInImage embedding via exiftool."""

import shutil
from pathlib import Path

import pytest
from PIL import Image

from src.iptc_writer import IptcWriteError, backup_directory, read_person_in_image, write_iptc

FIXTURE_PHOTO = Path(__file__).resolve().parent.parent / "uploads" / "DSC_3890-sm.JPG"


@pytest.fixture
def photo(tmp_path) -> Path:
    """A real JPEG copied into a tmp_path so tests never touch uploads/."""
    dest = tmp_path / "photo.jpg"
    shutil.copy2(FIXTURE_PHOTO, dest)
    return dest


def _pixel_hash(path: Path) -> bytes:
    with Image.open(path) as img:
        return img.convert("RGB").tobytes()


def test_read_person_in_image_empty_on_fresh_photo(photo):
    assert read_person_in_image(str(photo)) == []


def test_write_single_name_round_trips(photo):
    write_iptc(str(photo), names_to_add=["Alice Smith"])
    assert read_person_in_image(str(photo)) == ["Alice Smith"]


def test_add_multiple_names_preserves_order(photo):
    write_iptc(str(photo), names_to_add=["Alice Smith"])
    write_iptc(str(photo), names_to_add=["Bob Jones"])
    assert read_person_in_image(str(photo)) == ["Alice Smith", "Bob Jones"]


def test_add_duplicate_name_is_deduped_casefold(photo):
    write_iptc(str(photo), names_to_add=["Alice Smith"])
    write_iptc(str(photo), names_to_add=["alice smith"])
    assert read_person_in_image(str(photo)) == ["Alice Smith"]


def test_remove_name_drops_only_that_name(photo):
    write_iptc(str(photo), names_to_add=["Alice Smith", "Bob Jones"])
    write_iptc(str(photo), names_to_remove=["Bob Jones"])
    assert read_person_in_image(str(photo)) == ["Alice Smith"]


def test_remove_nonexistent_name_is_a_noop(photo):
    write_iptc(str(photo), names_to_add=["Alice Smith"])
    write_iptc(str(photo), names_to_remove=["Nobody Here"])
    assert read_person_in_image(str(photo)) == ["Alice Smith"]


def test_pixel_bytes_unchanged_after_write(photo):
    before = _pixel_hash(photo)
    write_iptc(str(photo), names_to_add=["Alice Smith"])
    after = _pixel_hash(photo)
    assert before == after


def test_write_missing_file_raises(tmp_path):
    missing = tmp_path / "nope.jpg"
    with pytest.raises(IptcWriteError):
        write_iptc(str(missing), names_to_add=["Alice Smith"])


def test_write_leaves_no_temp_file_behind(photo):
    write_iptc(str(photo), names_to_add=["Alice Smith"])
    leftovers = list(photo.parent.glob(f".{photo.name}.*.tmp"))
    assert leftovers == []


def test_write_empty_add_and_remove_is_a_true_noop(photo):
    before_mtime = photo.stat().st_mtime_ns
    write_iptc(str(photo))  # no names_to_add, no names_to_remove
    assert photo.stat().st_mtime_ns == before_mtime


def test_backup_directory_copies_all_jpegs(tmp_path):
    source = tmp_path / "uploads"
    source.mkdir()
    shutil.copy2(FIXTURE_PHOTO, source / "a.jpg")
    shutil.copy2(FIXTURE_PHOTO, source / "b.JPG")
    (source / "notes.txt").write_text("not a photo")
    dest = tmp_path / "uploads_backup"

    result = backup_directory(str(source), str(dest))

    assert result["performed"] is True
    assert result["files_copied"] == 2
    assert (dest / "a.jpg").exists()
    assert (dest / "b.JPG").exists()
    assert not (dest / "notes.txt").exists()


def test_backup_directory_is_idempotent(tmp_path):
    source = tmp_path / "uploads"
    source.mkdir()
    shutil.copy2(FIXTURE_PHOTO, source / "a.jpg")
    dest = tmp_path / "uploads_backup"

    backup_directory(str(source), str(dest))
    second = backup_directory(str(source), str(dest))

    assert second["performed"] is False
