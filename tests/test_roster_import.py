import io

import pytest

from src.roster_import import RosterImportError, RosterImporter, parse_roster_file


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
