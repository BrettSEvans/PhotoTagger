import csv
import io
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Sequence

import requests


RosterRow = Dict[str, str]


class RosterImportError(ValueError):
    """Raised when roster rows cannot be extracted from an import source."""


def parse_roster_file(filename: str, content: bytes) -> List[RosterRow]:
    """Parse roster rows from a supported file type."""
    suffix = Path(filename).suffix.lower()
    if suffix in {".csv", ".txt", ".md"}:
        return RosterImporter.parse_text(content.decode("utf-8-sig", errors="replace"))
    if suffix == ".xlsx":
        return RosterImporter.parse_xlsx(content)
    if suffix == ".pdf":
        return RosterImporter.parse_pdf(content)
    raise RosterImportError("Unsupported roster file type. Use CSV, TXT, MD, XLSX, or PDF.")


class RosterImporter:
    """Extract roster jersey/name rows from files and roster webpages."""

    @staticmethod
    def parse_text(text: str) -> List[RosterRow]:
        rows = _parse_markdown_table(text)
        if rows:
            return rows

        rows = _parse_delimited_text(text)
        if rows:
            return rows

        rows = _parse_number_name_lines(text)
        if rows:
            return rows

        raise RosterImportError("No roster rows found. Include jersey/number and player/name data.")

    @staticmethod
    def parse_xlsx(content: bytes) -> List[RosterRow]:
        try:
            import openpyxl
        except ImportError as exc:
            raise RosterImportError("XLSX roster import requires openpyxl. Run pip install -r requirements.txt.") from exc

        workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        for sheet in workbook.worksheets:
            table = [[_clean_cell(cell) for cell in row] for row in sheet.iter_rows(values_only=True)]
            rows = _rows_from_table(table)
            if rows:
                return rows
        raise RosterImportError("No roster rows found in XLSX file.")

    @staticmethod
    def parse_pdf(content: bytes) -> List[RosterRow]:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RosterImportError("PDF roster import requires pypdf. Run pip install -r requirements.txt.") from exc

        reader = PdfReader(io.BytesIO(content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        return RosterImporter.parse_text(text)

    @staticmethod
    def parse_html(html: str) -> List[RosterRow]:
        tables = _extract_html_tables(html)
        for table in tables:
            rows = _rows_from_table(table)
            if rows:
                return rows

        text = _html_to_text(html)
        try:
            return RosterImporter.parse_text(text)
        except RosterImportError as exc:
            raise RosterImportError("No roster table found on that page.") from exc

    @staticmethod
    def fetch_url(url: str) -> List[RosterRow]:
        try:
            response = requests.get(
                url,
                timeout=20,
                headers={"User-Agent": "PhotoTagger roster importer"},
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RosterImportError(f"Could not fetch roster URL: {exc}") from exc
        return RosterImporter.parse_html(response.text)


def _clean_cell(value) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()


def _normalize_header(value: str) -> str:
    return re.sub(r"[^a-z#]", "", value.lower())


def _is_jersey_header(value: str) -> bool:
    normalized = _normalize_header(value)
    return normalized in {"#", "no", "num", "number", "jersey", "jerseynumber"}


def _is_name_header(value: str) -> bool:
    normalized = _normalize_header(value)
    return normalized in {"name", "player", "playername"}


def _rows_from_table(table: Sequence[Sequence[str]]) -> List[RosterRow]:
    cleaned = [[_clean_cell(cell) for cell in row] for row in table if any(_clean_cell(cell) for cell in row)]
    for header_idx, row in enumerate(cleaned[:10]):
        jersey_idx = next((i for i, cell in enumerate(row) if _is_jersey_header(cell)), -1)
        name_idx = next((i for i, cell in enumerate(row) if _is_name_header(cell)), -1)
        if jersey_idx < 0 or name_idx < 0:
            continue

        rows: List[RosterRow] = []
        for data_row in cleaned[header_idx + 1:]:
            if max(jersey_idx, name_idx) >= len(data_row):
                continue
            jersey = _normalize_jersey(data_row[jersey_idx])
            name = _normalize_name(data_row[name_idx])
            if jersey and name:
                rows.append({"jersey_number": jersey, "player_name": name})
        if rows:
            return _dedupe_rows(rows)
    return []


def _normalize_jersey(value: str) -> str:
    match = re.search(r"\d{1,3}", _clean_cell(value))
    return match.group(0) if match else ""


def _normalize_name(value: str) -> str:
    name = _clean_cell(value)
    name = re.sub(r"\s+\([^)]*\)$", "", name)
    if not re.search(r"[A-Za-z]", name):
        return ""
    return name


def _dedupe_rows(rows: Sequence[RosterRow]) -> List[RosterRow]:
    seen = set()
    unique: List[RosterRow] = []
    for row in rows:
        key = (row["jersey_number"], row["player_name"].casefold())
        if key not in seen:
            seen.add(key)
            unique.append(dict(row))
    return unique


def _parse_markdown_table(text: str) -> List[RosterRow]:
    table_rows = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if cells and not all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells):
            table_rows.append(cells)
    return _rows_from_table(table_rows)


def _parse_delimited_text(text: str) -> List[RosterRow]:
    sample = "\n".join(line for line in text.splitlines() if line.strip())
    if not sample:
        return []

    delimiters = [",", "\t", ";"]
    for delimiter in delimiters:
        if delimiter not in sample:
            continue
        reader = csv.reader(io.StringIO(sample), delimiter=delimiter)
        rows = [list(row) for row in reader]
        parsed = _rows_from_table(rows)
        if parsed:
            return parsed
    return []


def _parse_number_name_lines(text: str) -> List[RosterRow]:
    rows = []
    for line in text.splitlines():
        line = _clean_cell(line)
        if not line or _is_header_like(line):
            continue
        match = re.match(r"^#?\s*(\d{1,3})\s+(.+?)\s*$", line)
        if not match:
            continue
        name = _normalize_name(match.group(2))
        if name:
            rows.append({"jersey_number": match.group(1), "player_name": name})
    return _dedupe_rows(rows)


def _is_header_like(line: str) -> bool:
    lower = line.lower()
    return ("player" in lower or "name" in lower) and ("no" in lower or "number" in lower or "jersey" in lower)


class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables: List[List[List[str]]] = []
        self._table: List[List[str]] | None = None
        self._row: List[str] | None = None
        self._cell: List[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self._row is not None and self._cell is not None:
            self._row.append(_clean_cell(" ".join(self._cell)))
            self._cell = None
        elif tag == "tr" and self._table is not None and self._row is not None:
            self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            self.tables.append(self._table)
            self._table = None


class _TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: List[str] = []

    def handle_data(self, data):
        if data.strip():
            self.parts.append(data.strip())


def _extract_html_tables(html: str) -> List[List[List[str]]]:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        soup = None
    else:
        soup = BeautifulSoup(html, "html.parser")

    if soup is not None:
        tables = []
        for table in soup.find_all("table"):
            parsed_table = []
            for tr in table.find_all("tr"):
                cells = [_clean_cell(cell.get_text(" ")) for cell in tr.find_all(["th", "td"])]
                if cells:
                    parsed_table.append(cells)
            if parsed_table:
                tables.append(parsed_table)
        return tables

    parser = _TableParser()
    parser.feed(html)
    return parser.tables


def _html_to_text(html: str) -> str:
    parser = _TextParser()
    parser.feed(html)
    return "\n".join(parser.parts)
