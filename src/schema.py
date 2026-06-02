"""Database schema initialization."""

import sqlite3


def init_schema(conn: sqlite3.Connection) -> None:
    """Create database tables if they don't exist."""
    cursor = conn.cursor()

    # Photos table: metadata about each photo file
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT UNIQUE NOT NULL,
            file_hash TEXT UNIQUE NOT NULL,
            file_size INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # OCR results table: jersey numbers extracted from each photo
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ocr_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            photo_id INTEGER NOT NULL,
            jersey_number TEXT,
            uniform_color TEXT,
            confidence REAL,
            raw_text TEXT,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (photo_id) REFERENCES photos(id) ON DELETE CASCADE
        )
    """)

    # Faces table: store detected faces and embeddings (Phase 2A)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS faces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            photo_id INTEGER NOT NULL,
            embedding BLOB NOT NULL,
            bbox_x0 INTEGER,
            bbox_y0 INTEGER,
            bbox_x1 INTEGER,
            bbox_y1 INTEGER,
            confidence REAL,
            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (photo_id) REFERENCES photos(id) ON DELETE CASCADE
        )
    """)

    # Rosters table: player name mapping (Phase 2A)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rosters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_name TEXT NOT NULL,
            team_year INTEGER NOT NULL,
            jersey_number TEXT NOT NULL,
            player_name TEXT NOT NULL,
            uniform_color TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(team_name, team_year, jersey_number)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_context_teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_name TEXT NOT NULL,
            team_year INTEGER NOT NULL,
            uniform_color TEXT NOT NULL,
            position INTEGER NOT NULL DEFAULT 0
        )
    """)

    # Player clusters table: grouped face identities
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS player_clusters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            face_count INTEGER DEFAULT 0,
            photo_count INTEGER DEFAULT 0,
            thumbnail_face_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS processing_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            progress INTEGER NOT NULL DEFAULT 0,
            payload TEXT,
            result TEXT,
            error TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            finished_at TIMESTAMP
        )
    """)

    # Photo batches table: group photos by import folder with metadata
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS photo_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            source_folder TEXT UNIQUE NOT NULL,
            team_name TEXT,
            team_year INTEGER,
            tournament TEXT,
            photo_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Add cluster_id column to faces if it doesn't exist yet
    try:
        cursor.execute("ALTER TABLE faces ADD COLUMN cluster_id INTEGER REFERENCES player_clusters(id)")
    except Exception:
        pass  # Column already exists

    try:
        cursor.execute("ALTER TABLE faces ADD COLUMN sharpness REAL")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE faces ADD COLUMN face_size_ratio REAL")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE ocr_results ADD COLUMN uniform_color TEXT")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE rosters ADD COLUMN uniform_color TEXT")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE faces ADD COLUMN quality_score REAL")
    except Exception:
        pass

    # Per-face jersey color sampled from the torso patch below the face bbox.
    # Used (with face size) to separate foreground players from background spectators.
    try:
        cursor.execute("ALTER TABLE faces ADD COLUMN jersey_color TEXT")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE faces ADD COLUMN jersey_color_conf REAL")
    except Exception:
        pass

    # Add player_name / jersey_number to player_clusters if not present
    try:
        cursor.execute("ALTER TABLE player_clusters ADD COLUMN player_name TEXT")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE player_clusters ADD COLUMN jersey_number TEXT")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE player_clusters ADD COLUMN roster_entry_id INTEGER REFERENCES rosters(id)")
    except Exception:
        pass

    # Add source_folder and batch_id columns to photos table
    try:
        cursor.execute("ALTER TABLE photos ADD COLUMN source_folder TEXT")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE photos ADD COLUMN batch_id INTEGER REFERENCES photo_batches(id)")
    except Exception:
        pass

    conn.commit()
