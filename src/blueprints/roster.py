"""Roster and game context management endpoints."""

import logging
import requests
from flask import Blueprint, jsonify, request, current_app
from src.roster_import import RosterImportError, RosterImporter, parse_roster_file, infer_team_and_year, extract_team_and_year_from_html

logger = logging.getLogger(__name__)

bp = Blueprint("roster", __name__)


@bp.route("/api/roster", methods=["GET"])
def get_roster():
    """Get all roster entries."""
    try:
        db = current_app.db
        entries = db.roster.get_all_roster_entries()
        return jsonify({"entries": entries, "total": len(entries)}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/game-context", methods=["GET"])
def get_game_context():
    """Get current game context (active teams)."""
    try:
        db = current_app.db
        teams = db.context.get_game_context()
        return jsonify({"teams": teams}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/game-context", methods=["PUT"])
def set_game_context():
    """Set game context (active teams for a matchup)."""
    data = request.get_json() or {}
    teams = data.get("teams", [])
    if not isinstance(teams, list):
        return jsonify({"error": "teams must be a list"}), 400

    normalized = []
    for idx, team in enumerate(teams, start=1):
        team_name = str(team.get("team_name", "")).strip() if isinstance(team, dict) else ""
        uniform_color = str(team.get("uniform_color", "")).strip().lower() if isinstance(team, dict) else ""
        try:
            team_year = int(team.get("team_year", 2026)) if isinstance(team, dict) else 2026
        except (TypeError, ValueError):
            return jsonify({"error": f"teams[{idx}].team_year must be an integer"}), 400
        if not team_name:
            return jsonify({"error": f"teams[{idx}] requires team_name"}), 400
        normalized.append({
            "team_name": team_name,
            "team_year": team_year,
            "uniform_color": uniform_color or None,
        })

    try:
        db = current_app.db
        db.context.set_game_context(normalized)
        return jsonify({"success": True, "teams": db.context.get_game_context()}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/roster", methods=["POST"])
def add_roster():
    """Add a player to the roster."""
    data = request.get_json() or {}
    jersey = str(data.get("jersey_number", "")).strip()
    name = str(data.get("player_name", "")).strip()
    team = str(data.get("team_name", "Manual Entry")).strip()
    try:
        year = int(data.get("team_year", 2026))
    except (TypeError, ValueError):
        return jsonify({"error": "team_year must be an integer"}), 400
    uniform_color = str(data.get("uniform_color", "")).strip().lower() or None
    if not jersey or not name:
        return jsonify({"error": "jersey_number and player_name are required"}), 400
    try:
        db = current_app.db
        db.roster.add_roster_entry(team, year, jersey, name, uniform_color=uniform_color)
        return jsonify({"success": True}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/roster/infer", methods=["POST"])
def infer_roster_data():
    """Infer team name and year from a roster filename."""
    data = request.get_json() or {}
    filename = data.get("filename", "").strip()
    if not filename:
        return jsonify({"error": "filename is required"}), 400

    team, year = infer_team_and_year(filename)
    return jsonify({
        "team_name": team,
        "team_year": year,
    }), 200


@bp.route("/api/roster/import", methods=["POST"])
def import_roster_file():
    """Import roster entries from an uploaded file."""
    team = str(request.form.get("team_name", "Manual Entry")).strip() or "Manual Entry"
    uniform_color = str(request.form.get("uniform_color", "")).strip().lower() or None
    try:
        year = int(request.form.get("team_year", 2026))
    except (TypeError, ValueError):
        return jsonify({"error": "team_year must be an integer"}), 400

    duplicate_policy = str(request.form.get("duplicate_policy", "replace")).strip()
    if duplicate_policy not in {"replace", "skip"}:
        return jsonify({"error": "duplicate_policy must be 'replace' or 'skip'"}), 400

    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return jsonify({"error": "file is required"}), 400

    try:
        db = current_app.db
        rows = parse_roster_file(uploaded.filename, uploaded.read())
        result = db.roster.import_roster_entries(team, year, rows, duplicate_policy, uniform_color=uniform_color)
        return jsonify(result), 200
    except RosterImportError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"roster file import error: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/api/roster/infer-url", methods=["POST"])
def infer_roster_url():
    """Infer team name and year from a USA Ultimate roster URL."""
    data = request.get_json() or {}
    url = str(data.get("url", "")).strip()
    if not url:
        return jsonify({"error": "url is required"}), 400

    try:
        response = requests.get(url, timeout=20, headers={"User-Agent": "PhotoTagger roster importer"})
        response.raise_for_status()
        team, year = extract_team_and_year_from_html(response.text)
        return jsonify({
            "team_name": team,
            "team_year": year,
        }), 200
    except Exception as e:
        logger.warning(f"Could not infer team/year from URL: {e}")
        return jsonify({"team_name": None, "team_year": None}), 200


@bp.route("/api/roster/import-url", methods=["POST"])
def import_roster_url():
    """Import roster entries from a USA Ultimate roster URL."""
    data = request.get_json() or {}
    url = str(data.get("url", "")).strip()
    team = str(data.get("team_name", "Manual Entry")).strip() or "Manual Entry"
    uniform_color = str(data.get("uniform_color", "")).strip().lower() or None
    duplicate_policy = str(data.get("duplicate_policy", "replace")).strip()

    if not url:
        return jsonify({"error": "url is required"}), 400
    try:
        year = int(data.get("team_year", 2026))
    except (TypeError, ValueError):
        return jsonify({"error": "team_year must be an integer"}), 400
    if duplicate_policy not in {"replace", "skip"}:
        return jsonify({"error": "duplicate_policy must be 'replace' or 'skip'"}), 400

    try:
        db = current_app.db
        rows = RosterImporter.fetch_url(url)
        result = db.roster.import_roster_entries(team, year, rows, duplicate_policy, uniform_color=uniform_color)
        return jsonify(result), 200
    except RosterImportError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"roster URL import error: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/api/roster/<int:entry_id>", methods=["DELETE"])
def delete_roster(entry_id: int):
    """Delete a roster entry."""
    try:
        db = current_app.db
        db.roster.delete_roster_entry(entry_id)
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/roster/<int:entry_id>", methods=["PUT"])
def update_roster(entry_id: int):
    """Update a roster entry."""
    data = request.get_json() or {}
    try:
        db = current_app.db
        updates = {}
        if "player_name" in data:
            updates["player_name"] = str(data["player_name"]).strip()
        if "jersey_number" in data:
            updates["jersey_number"] = str(data["jersey_number"]).strip()
        if "team_name" in data:
            updates["team_name"] = str(data["team_name"]).strip()
        if "team_year" in data:
            updates["team_year"] = int(data["team_year"])
        if "uniform_color" in data:
            updates["uniform_color"] = str(data["uniform_color"]).strip() if data["uniform_color"] else None

        updated_entry = db.roster.update_roster_entry(entry_id, **updates)
        return jsonify(updated_entry), 200

    except ValueError as e:
        return jsonify({"error": str(e)}), 409
    except Exception as e:
        logger.exception(f"Error updating roster entry {entry_id}: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/api/roster/search", methods=["GET"])
def search_roster():
    """Search roster by player name or jersey number."""
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"results": []}), 200
    try:
        db = current_app.db
        results = db.roster.search_roster(q)
        return jsonify({"results": results}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
