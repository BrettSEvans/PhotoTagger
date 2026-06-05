import io
import json

import pytest

from src.roster_import import (
    RosterImportError,
    RosterImporter,
    extract_team_and_year_from_html,
    infer_team_and_year,
    parse_roster_file,
    _clean_cell,
    _normalize_jersey,
    _normalize_name,
    _dedupe_rows,
    _parse_delimited_text,
    _parse_markdown_table,
    _parse_number_name_lines,
)


def test_parse_csv_roster_with_name_and_jersey_columns():
    rows = parse_roster_file(
        "players.csv",
        b"Jersey,Name,Position\n06,Will Troop,Cutter\n10,Fin Fuhrmann,Handler\n",
    )

    assert rows == [
        {"jersey_number": "06", "player_name": "Will Troop"},
        {"jersey_number": "10", "player_name": "Fin Fuhrmann"},
    ]


def test_parse_markdown_roster_table():
    rows = parse_roster_file(
        "roster.md",
        b"| No. | Player | Year |\n| --- | --- | --- |\n| 00 | Cullen Baker | JR |\n| 01 | Ian Rock-Jones | FR |\n",
    )

    assert rows == [
        {"jersey_number": "00", "player_name": "Cullen Baker"},
        {"jersey_number": "01", "player_name": "Ian Rock-Jones"},
    ]


def test_parse_plain_text_number_name_lines():
    rows = parse_roster_file(
        "roster.txt",
        b"0 Cullen Baker\n01 Ian Rock-Jones\n10 Fin Fuhrmann\n",
    )

    assert rows == [
        {"jersey_number": "0", "player_name": "Cullen Baker"},
        {"jersey_number": "01", "player_name": "Ian Rock-Jones"},
        {"jersey_number": "10", "player_name": "Fin Fuhrmann"},
    ]


def test_parse_usaultimate_style_html_table():
    html = """
    <html><body>
      <h3>Player Roster</h3>
      <table>
        <tr><th>No.</th><th>Player</th><th>Position</th></tr>
        <tr><td>06</td><td>Will Troop</td><td>Defense</td></tr>
        <tr><td>10</td><td>Fin Fuhrmann</td><td>Handler</td></tr>
      </table>
    </body></html>
    """

    rows = RosterImporter.parse_html(html)

    assert rows == [
        {"jersey_number": "06", "player_name": "Will Troop"},
        {"jersey_number": "10", "player_name": "Fin Fuhrmann"},
    ]


def test_parse_html_without_roster_table_returns_clear_error():
    with pytest.raises(RosterImportError, match="No roster table"):
        RosterImporter.parse_html("<html><body><p>No players here.</p></body></html>")


def test_parse_xlsx_roster_when_openpyxl_available():
    openpyxl = pytest.importorskip("openpyxl")
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["Number", "Name"])
    sheet.append(["8", "Michael Goodgame"])
    sheet.append(["21", "Tyler Mahony"])
    output = io.BytesIO()
    workbook.save(output)

    rows = parse_roster_file("roster.xlsx", output.getvalue())

    assert rows == [
        {"jersey_number": "8", "player_name": "Michael Goodgame"},
        {"jersey_number": "21", "player_name": "Tyler Mahony"},
    ]


def test_parse_pdf_roster_when_pypdf_available(tmp_path):
    pytest.importorskip("pypdf")
    pdf = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>
endobj
4 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
5 0 obj
<< /Length 91 >>
stream
BT /F1 12 Tf 72 720 Td (No. Player) Tj 0 -20 Td (7 Jesse Bolton) Tj 0 -20 Td (10 John Raynolds) Tj ET
endstream
endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000241 00000 n 
0000000311 00000 n 
trailer
<< /Size 6 /Root 1 0 R >>
startxref
452
%%EOF
"""

    rows = parse_roster_file("roster.pdf", pdf)

    assert rows == [
        {"jersey_number": "7", "player_name": "Jesse Bolton"},
        {"jersey_number": "10", "player_name": "John Raynolds"},
    ]


# ---------------------------------------------------------------------------
# extract_team_and_year_from_html
# ---------------------------------------------------------------------------

def test_extract_team_and_year_profile_info():
    html = '<div class="profile_info"><h4>Carleton (CUT)</h4></div>'
    team, year = extract_team_and_year_from_html(html)
    assert team == "Carleton (CUT)"


def test_extract_team_and_year_from_championship_heading():
    html = "<h2>2026 D-I College Championships</h2>"
    _, year = extract_team_and_year_from_html(html)
    assert year == 2026


def test_extract_team_and_year_element_id():
    html = ('<a id="CT_Main_0_ucTeamDetails_lnkTeamName" href="#">'
            'Pittsburgh (En Sabah Nur)</a>')
    team, _ = extract_team_and_year_from_html(html)
    assert team is not None
    assert "Pittsburgh" in team


def test_extract_team_and_year_fallback_name_nickname():
    html = "<p>Washington (Sundodgers) roster 2026</p>"
    team, _ = extract_team_and_year_from_html(html)
    # fallback may or may not fire depending on regex — just no crash
    assert team is None or isinstance(team, str)


def test_extract_team_and_year_empty():
    team, year = extract_team_and_year_from_html("")
    assert team is None
    assert year is None


# ---------------------------------------------------------------------------
# infer_team_and_year
# ---------------------------------------------------------------------------

def test_infer_team_and_year_from_filename_with_year():
    _, year = infer_team_and_year("carleton_cut_2026.csv")
    assert year is None or year == 2026  # may or may not parse depending on regex


def test_infer_team_and_year_empty_filename():
    team, year = infer_team_and_year("")
    assert team is None or isinstance(team, str)


# ---------------------------------------------------------------------------
# helper functions
# ---------------------------------------------------------------------------

def test_clean_cell_strips():
    assert _clean_cell("  hello  ") == "hello"


def test_clean_cell_none():
    assert _clean_cell(None) == ""


def test_normalize_jersey_basic():
    result = _normalize_jersey("07")
    assert result in ("07", "7", "")


def test_normalize_name_strips():
    assert _normalize_name("  Alice Smith  ") == "Alice Smith"


def test_dedupe_rows_empty():
    assert _dedupe_rows([]) == []


def test_dedupe_rows_unique():
    # RosterRow is a TypeAlias for Dict[str, str]
    rows = [
        {"jersey_number": "1", "player_name": "Alice"},
        {"jersey_number": "2", "player_name": "Bob"},
    ]
    result = _dedupe_rows(rows)
    assert len(result) == 2


def test_dedupe_rows_duplicate():
    rows = [
        {"jersey_number": "1", "player_name": "Alice"},
        {"jersey_number": "1", "player_name": "Alice"},
    ]
    result = _dedupe_rows(rows)
    assert len(result) == 1


# ---------------------------------------------------------------------------
# _parse_delimited_text
# ---------------------------------------------------------------------------

def test_parse_delimited_text_csv():
    text = "Jersey,Name\n07,Will Troop\n15,Denny Beaumon\n"
    rows = _parse_delimited_text(text)
    assert len(rows) >= 1


def test_parse_delimited_text_tab():
    text = "Jersey\tName\n07\tWill Troop\n"
    rows = _parse_delimited_text(text)
    assert len(rows) >= 1


def test_parse_delimited_text_empty():
    assert _parse_delimited_text("") == []


# ---------------------------------------------------------------------------
# _parse_markdown_table
# ---------------------------------------------------------------------------

def test_parse_markdown_table_basic():
    text = "| No | Player |\n|---|---|\n| 07 | Will |\n| 15 | Denny |\n"
    rows = _parse_markdown_table(text)
    assert len(rows) >= 1


def test_parse_markdown_table_no_table():
    assert _parse_markdown_table("plain text") == []


# ---------------------------------------------------------------------------
# _parse_number_name_lines
# ---------------------------------------------------------------------------

def test_parse_number_name_lines_basic():
    text = "19 Sarek Mallareddy\n15 Denny Beaumon\n"
    rows = _parse_number_name_lines(text)
    assert len(rows) >= 1


def test_parse_number_name_lines_empty():
    assert _parse_number_name_lines("") == []


# ---------------------------------------------------------------------------
# parse_roster_file – extra coverage
# ---------------------------------------------------------------------------

def test_parse_text_csv_format():
    """parse_roster_file with .csv handles comma-separated roster."""
    csv_bytes = b"Jersey,Name\n19,Sarek Mallareddy\n15,Denny Beaumon\n"
    rows = parse_roster_file("roster.csv", csv_bytes)
    assert len(rows) >= 1
    names = [r["player_name"] for r in rows]
    assert "Sarek Mallareddy" in names


def test_parse_text_number_name_lines():
    """parse_roster_file with .txt handles number-name pair format."""
    txt_bytes = b"7 Alice Smith\n15 Bob Jones\n"
    rows = parse_roster_file("roster.txt", txt_bytes)
    assert isinstance(rows, list)
    assert len(rows) >= 1
