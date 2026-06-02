import pytest
import numpy as np
from src.db import Database
from src.face_cluster import FaceClusterer
from src import config as cfg


@pytest.fixture
def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    database.init_schema()
    yield database
    database.close()


def _add_face(db, tmp_path, name, embedding, sharpness, face_size_ratio, confidence=0.9):
    photo_file = tmp_path / f"{name}.jpg"
    # Unique bytes per photo so the hash constraint is never violated
    photo_file.write_bytes(f"fake-{name}".encode())
    photo_id = db.add_photo(str(photo_file))
    return db.add_face(photo_id, embedding, [10, 20, 100, 120], confidence,
                       sharpness=sharpness, face_size_ratio=face_size_ratio)


# ── Quality filter: exclusion ────────────────────────────────────────────────

def test_blurry_face_excluded_from_clustering(db, tmp_path, monkeypatch):
    """A face with sharpness below MIN_FACE_SHARPNESS must not appear in any cluster."""
    monkeypatch.setattr(cfg, "MIN_FACE_SHARPNESS", 30.0)
    monkeypatch.setattr(cfg, "MIN_FACE_SIZE_RATIO", 0.0)

    emb = np.ones(384, dtype=np.float32)
    _add_face(db, tmp_path, "blurry", emb.tolist(), sharpness=5.0, face_size_ratio=0.05)

    result = FaceClusterer(db).run()

    assert result["clusters_created"] == 0

def test_tiny_face_excluded_from_clustering(db, tmp_path, monkeypatch):
    """A face with face_size_ratio below MIN_FACE_SIZE_RATIO must not appear in any cluster."""
    monkeypatch.setattr(cfg, "MIN_FACE_SHARPNESS", 0.0)
    monkeypatch.setattr(cfg, "MIN_FACE_SIZE_RATIO", 0.002)

    emb = np.ones(384, dtype=np.float32)
    _add_face(db, tmp_path, "tiny", emb.tolist(), sharpness=80.0, face_size_ratio=0.0001)

    result = FaceClusterer(db).run()

    assert result["clusters_created"] == 0


# ── Quality filter: inclusion ────────────────────────────────────────────────

def test_sharp_large_face_included_in_clustering(db, tmp_path, monkeypatch):
    """A face exceeding both thresholds must be clustered."""
    monkeypatch.setattr(cfg, "MIN_FACE_SHARPNESS", 30.0)
    monkeypatch.setattr(cfg, "MIN_FACE_SIZE_RATIO", 0.002)

    emb = np.ones(384, dtype=np.float32)
    _add_face(db, tmp_path, "sharp", emb.tolist(), sharpness=100.0, face_size_ratio=0.05)

    result = FaceClusterer(db).run()

    assert result["clusters_created"] == 1

def test_quality_filter_log_counts_removed_faces(db, tmp_path, monkeypatch, caplog):
    """Clusterer must log how many faces were removed by the quality filter."""
    import logging
    monkeypatch.setattr(cfg, "MIN_FACE_SHARPNESS", 30.0)
    monkeypatch.setattr(cfg, "MIN_FACE_SIZE_RATIO", 0.002)

    emb = np.ones(384, dtype=np.float32)
    _add_face(db, tmp_path, "good", emb.tolist(), sharpness=80.0, face_size_ratio=0.05)
    _add_face(db, tmp_path, "bad",  emb.tolist(), sharpness=5.0,  face_size_ratio=0.0001)

    with caplog.at_level(logging.INFO, logger="src.face_cluster"):
        FaceClusterer(db).run()

    assert "Quality filter" in caplog.text
    assert "removed 1" in caplog.text


# ── Null quality values (pre-migration rows) ─────────────────────────────────

def test_null_sharpness_face_excluded(db, tmp_path, monkeypatch):
    """A face with NULL sharpness (pre-migration) must be excluded by the filter."""
    monkeypatch.setattr(cfg, "MIN_FACE_SHARPNESS", 30.0)
    monkeypatch.setattr(cfg, "MIN_FACE_SIZE_RATIO", 0.0)

    emb = np.ones(384, dtype=np.float32)
    _add_face(db, tmp_path, "legacy", emb.tolist(), sharpness=None, face_size_ratio=0.05)

    result = FaceClusterer(db).run()

    assert result["clusters_created"] == 0

def test_null_face_size_ratio_excluded(db, tmp_path, monkeypatch):
    """A face with NULL face_size_ratio (pre-migration) must be excluded by the filter."""
    monkeypatch.setattr(cfg, "MIN_FACE_SHARPNESS", 0.0)
    monkeypatch.setattr(cfg, "MIN_FACE_SIZE_RATIO", 0.002)

    emb = np.ones(384, dtype=np.float32)
    _add_face(db, tmp_path, "legacy", emb.tolist(), sharpness=80.0, face_size_ratio=None)

    result = FaceClusterer(db).run()

    assert result["clusters_created"] == 0


# ── Thumbnail selection ──────────────────────────────────────────────────────

def test_thumbnail_is_sharpest_face_in_cluster(db, tmp_path, monkeypatch):
    """The cluster thumbnail should be the face with the highest sharpness."""
    monkeypatch.setattr(cfg, "MIN_FACE_SHARPNESS", 0.0)
    monkeypatch.setattr(cfg, "MIN_FACE_SIZE_RATIO", 0.0)

    # Two nearly identical embeddings → same cluster
    base = np.ones(384, dtype=np.float32)
    sharp_id = _add_face(db, tmp_path, "sharp", base.tolist(),      sharpness=200.0, face_size_ratio=0.05)
    _add_face(db,          tmp_path, "blurry", (base * 0.999).tolist(), sharpness=10.0,  face_size_ratio=0.05)

    FaceClusterer(db, similarity_threshold=0.40).run()

    clusters = db.get_all_player_clusters()
    assert len(clusters) == 1
    assert clusters[0]["thumbnail_face_id"] == sharp_id
