import pytest
from src.db import Database

@pytest.fixture
def test_db():
    db = Database(":memory:")
    db.init_schema()
    yield db
    db.close()

def test_faces_table_exists(test_db):
    """Verify faces table created."""
    cursor = test_db.conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='faces'")
    assert cursor.fetchone() is not None

def test_add_face(test_db, tmp_path):
    """Test adding a face record."""
    photo_file = tmp_path / "test.jpg"
    photo_file.write_bytes(b"fake jpg")
    photo_id = test_db.photos.add_photo(str(photo_file))

    # Add face with embedding
    embedding = [0.1, 0.2, 0.3] * 128  # 384-dim vector
    face_id = test_db.faces.add_face(
        photo_id=photo_id,
        embedding=embedding,
        bbox=[10, 20, 100, 150],
        confidence=0.95
    )

    assert face_id is not None
    assert face_id > 0

def test_get_faces_by_photo(test_db, tmp_path):
    """Test retrieving faces for a photo."""
    photo_file = tmp_path / "test.jpg"
    photo_file.write_bytes(b"fake jpg")
    photo_id = test_db.photos.add_photo(str(photo_file))

    # Add 2 faces
    embedding1 = [0.1] * 384
    embedding2 = [0.2] * 384
    test_db.faces.add_face(photo_id, embedding1, [10, 20, 100, 150], 0.95)
    test_db.faces.add_face(photo_id, embedding2, [150, 20, 200, 150], 0.88)

    faces = test_db.faces.get_faces_by_photo(photo_id)
    assert len(faces) == 2
    assert faces[0]["confidence"] == 0.95


def test_deassign_faces_deletes_empty_cluster(test_db, tmp_path):
    """Removing the last face from a cluster should delete the empty cluster."""
    photo_file = tmp_path / "test.jpg"
    photo_file.write_bytes(b"fake jpg")
    photo_id = test_db.photos.add_photo(str(photo_file))
    face_id = test_db.faces.add_face(photo_id, [0.1] * 384, [10, 20, 100, 150], 0.95)
    cluster_id = test_db.clusters.add_player_cluster(face_count=1, photo_count=1, thumbnail_face_id=face_id)
    test_db.clusters.assign_face_to_cluster(face_id, cluster_id)

    result = test_db.faces.deassign_faces([face_id])

    assert result["deassigned"] == 1
    assert result["deleted_cluster_ids"] == [cluster_id]
    assert test_db.clusters.get_all_player_clusters() == []


def test_deassign_faces_updates_cluster_counts(test_db, tmp_path):
    """Removing one face from a multi-face cluster should refresh counts and thumbnail."""
    photo_file1 = tmp_path / "one.jpg"
    photo_file2 = tmp_path / "two.jpg"
    photo_file1.write_bytes(b"fake jpg one")
    photo_file2.write_bytes(b"fake jpg two")
    photo_id1 = test_db.photos.add_photo(str(photo_file1))
    photo_id2 = test_db.photos.add_photo(str(photo_file2))
    face_id1 = test_db.faces.add_face(photo_id1, [0.1] * 384, [10, 20, 100, 150], 0.95)
    face_id2 = test_db.faces.add_face(photo_id2, [0.2] * 384, [20, 30, 110, 160], 0.88)
    cluster_id = test_db.clusters.add_player_cluster(face_count=2, photo_count=2, thumbnail_face_id=face_id1)
    test_db.clusters.assign_face_to_cluster(face_id1, cluster_id)
    test_db.clusters.assign_face_to_cluster(face_id2, cluster_id)

    result = test_db.faces.deassign_faces([face_id1])

    assert result["deleted_cluster_ids"] == []
    cluster = test_db.clusters.get_all_player_clusters()[0]
    assert cluster["id"] == cluster_id
    assert cluster["face_count"] == 1
    assert cluster["photo_count"] == 1
    assert cluster["thumbnail_face_id"] == face_id2

def test_rosters_table_exists(test_db):
    """Verify rosters table created."""
    cursor = test_db.conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='rosters'")
    assert cursor.fetchone() is not None


def test_roster_entries_store_uniform_color(test_db):
    """Roster rows should keep team uniform color for game-context matching."""
    test_db.roster.add_roster_entry("Carleton CUT", 2026, "12", "Thomas Shope", uniform_color="red")

    entry = test_db.roster.search_roster("Thomas Shope")[0]

    assert entry["uniform_color"] == "red"


def test_game_context_round_trip(test_db):
    """A photo set should keep the active matchup and each team's uniform color."""
    test_db.context.set_game_context([
        {"team_name": "Carleton CUT", "team_year": 2026, "uniform_color": "red"},
        {"team_name": "Pittsburgh En Sabah Nur", "team_year": 2026, "uniform_color": "white"},
    ])

    context = test_db.context.get_game_context()

    assert context == [
        {"team_name": "Carleton CUT", "team_year": 2026, "uniform_color": "red"},
        {"team_name": "Pittsburgh En Sabah Nur", "team_year": 2026, "uniform_color": "white"},
    ]


def test_player_clusters_has_roster_entry_id(test_db):
    """Clusters should keep a stable roster-player link independent of jersey text."""
    cursor = test_db.conn.cursor()
    cursor.execute("PRAGMA table_info(player_clusters)")
    columns = {row[1] for row in cursor.fetchall()}
    assert "roster_entry_id" in columns

def test_add_roster_entry(test_db):
    """Test adding roster entry."""
    test_db.roster.add_roster_entry("Test Team", 2026, "16", "Test Player")

    name = test_db.roster.get_player_name("Test Team", 2026, "16")
    assert name == "Test Player"


def test_roster_thumbnail_uses_roster_entry_id_when_jersey_changes(test_db, tmp_path):
    """Roster setup face should populate from cleanup assignment even if jersey changes."""
    test_db.roster.add_roster_entry("Test Team", 2026, "22", "Test Player")
    roster_entry = test_db.roster.search_roster("Test Player")[0]

    photo_file = tmp_path / "test.jpg"
    photo_file.write_bytes(b"fake jpg")
    photo_id = test_db.photos.add_photo(str(photo_file))
    face_id = test_db.faces.add_face(photo_id, [0.1] * 384, [10, 20, 100, 150], 0.95)
    cluster_id = test_db.clusters.add_player_cluster(face_count=1, photo_count=1, thumbnail_face_id=face_id)
    test_db.clusters.assign_face_to_cluster(face_id, cluster_id)
    test_db.clusters.assign_cluster_to_player(
        cluster_id,
        "Test Player",
        "16",
        roster_entry_id=roster_entry["id"],
    )

    entries = test_db.roster.get_all_roster_entries()
    assert entries[0]["jersey_number"] == "22"
    assert entries[0]["thumbnail_face_id"] == face_id

def test_get_player_name_not_found(test_db):
    """Test lookup when player not found."""
    name = test_db.roster.get_player_name("Unknown Team", 2026, "99")
    assert name is None


def test_duplicate_jersey_without_uniform_color_requires_review(test_db, tmp_path):
    """Same-number players on active teams must not be auto-confirmed without uniform color."""
    test_db.roster.add_roster_entry("Carleton CUT", 2026, "12", "Thomas Shope", uniform_color="red")
    test_db.roster.add_roster_entry("Pittsburgh En Sabah Nur", 2026, "12", "Ezra Biedler Schenk", uniform_color="white")
    test_db.context.set_game_context([
        {"team_name": "Carleton CUT", "team_year": 2026, "uniform_color": "red"},
        {"team_name": "Pittsburgh En Sabah Nur", "team_year": 2026, "uniform_color": "white"},
    ])
    photo_file = tmp_path / "number12.jpg"
    photo_file.write_bytes(b"fake jpg")
    photo_id = test_db.photos.add_photo(str(photo_file))
    test_db.add_ocr_result(photo_id, "12", 0.95, "12")

    assert test_db.get_processing_summary() == {"total_photos": 1, "tagged": 0, "needs_review": 1}
    assert test_db.get_confirmed_photos() == []
    review = test_db.get_review_photos()
    assert review[0]["jersey_number"] == "12"
    assert {c["player_name"] for c in review[0]["roster_candidates"]} == {"Thomas Shope", "Ezra Biedler Schenk"}


def test_duplicate_jersey_with_matching_uniform_color_confirms_player(test_db, tmp_path):
    """Uniform color should resolve same-number players in the active game context."""
    test_db.roster.add_roster_entry("Carleton CUT", 2026, "12", "Thomas Shope", uniform_color="red")
    test_db.roster.add_roster_entry("Pittsburgh En Sabah Nur", 2026, "12", "Ezra Biedler Schenk", uniform_color="white")
    test_db.context.set_game_context([
        {"team_name": "Carleton CUT", "team_year": 2026, "uniform_color": "red"},
        {"team_name": "Pittsburgh En Sabah Nur", "team_year": 2026, "uniform_color": "white"},
    ])
    photo_file = tmp_path / "red12.jpg"
    photo_file.write_bytes(b"fake jpg")
    photo_id = test_db.photos.add_photo(str(photo_file))
    test_db.add_ocr_result(photo_id, "12", 0.95, "12", uniform_color="red")

    assert test_db.get_processing_summary() == {"total_photos": 1, "tagged": 1, "needs_review": 0}
    confirmed = test_db.get_confirmed_photos()
    assert confirmed[0]["player_name"] == "Thomas Shope"
    assert confirmed[0]["team_name"] == "Carleton CUT"
    assert confirmed[0]["uniform_color"] == "red"


# ── Quality signal storage (sharpness + face_size_ratio) ────────────────────

def test_add_face_stores_sharpness(test_db, tmp_path):
    """add_face should persist the sharpness value."""
    photo_file = tmp_path / "p.jpg"
    photo_file.write_bytes(b"fake")
    photo_id = test_db.photos.add_photo(str(photo_file))
    face_id = test_db.faces.add_face(photo_id, [0.1] * 384, [10, 20, 100, 150], 0.9, sharpness=75.3)

    cursor = test_db.conn.cursor()
    cursor.execute("SELECT sharpness FROM faces WHERE id = ?", (face_id,))
    assert cursor.fetchone()[0] == pytest.approx(75.3)

def test_add_face_stores_face_size_ratio(test_db, tmp_path):
    """add_face should persist the face_size_ratio value."""
    photo_file = tmp_path / "p.jpg"
    photo_file.write_bytes(b"fake")
    photo_id = test_db.photos.add_photo(str(photo_file))
    face_id = test_db.faces.add_face(photo_id, [0.1] * 384, [10, 20, 100, 150], 0.9, face_size_ratio=0.045)

    cursor = test_db.conn.cursor()
    cursor.execute("SELECT face_size_ratio FROM faces WHERE id = ?", (face_id,))
    assert cursor.fetchone()[0] == pytest.approx(0.045)

def test_add_face_allows_null_sharpness(test_db, tmp_path):
    """add_face should accept None sharpness (pre-migration rows)."""
    photo_file = tmp_path / "p.jpg"
    photo_file.write_bytes(b"fake")
    photo_id = test_db.photos.add_photo(str(photo_file))
    face_id = test_db.faces.add_face(photo_id, [0.1] * 384, [10, 20, 100, 150], 0.9)

    cursor = test_db.conn.cursor()
    cursor.execute("SELECT sharpness FROM faces WHERE id = ?", (face_id,))
    assert cursor.fetchone()[0] is None

def test_get_all_faces_returns_sharpness(test_db, tmp_path):
    """get_all_faces should include 'sharpness' in each row."""
    photo_file = tmp_path / "p.jpg"
    photo_file.write_bytes(b"fake")
    photo_id = test_db.photos.add_photo(str(photo_file))
    test_db.faces.add_face(photo_id, [0.1] * 384, [10, 20, 100, 150], 0.9, sharpness=42.0)

    faces = test_db.get_all_faces()
    assert "sharpness" in faces[0]

def test_get_all_faces_returns_face_size_ratio(test_db, tmp_path):
    """get_all_faces should include 'face_size_ratio' in each row."""
    photo_file = tmp_path / "p.jpg"
    photo_file.write_bytes(b"fake")
    photo_id = test_db.photos.add_photo(str(photo_file))
    test_db.faces.add_face(photo_id, [0.1] * 384, [10, 20, 100, 150], 0.9, face_size_ratio=0.01)

    faces = test_db.get_all_faces()
    assert "face_size_ratio" in faces[0]

def test_get_all_faces_sharpness_value_roundtrips(test_db, tmp_path):
    """Sharpness stored via add_face must come back unchanged via get_all_faces."""
    photo_file = tmp_path / "p.jpg"
    photo_file.write_bytes(b"fake")
    photo_id = test_db.photos.add_photo(str(photo_file))
    test_db.faces.add_face(photo_id, [0.1] * 384, [10, 20, 100, 150], 0.9, sharpness=123.456)

    faces = test_db.get_all_faces()
    assert faces[0]["sharpness"] == pytest.approx(123.456)
