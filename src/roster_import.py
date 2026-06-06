import csv
import io
import re
import socket
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Sequence
from urllib.parse import urljoin, urlparse
import ipaddress

import requests


RosterRow = Dict[str, str]


class RosterImportError(ValueError):
    """Raised when roster rows cannot be extracted from an import source."""


def extract_team_and_year_from_html(html: str) -> tuple[str | None, int | None]:
    """Extract team name and year from a USA Ultimate event-team HTML page.

    Strategy (in priority order):
    1. Pull the team name from the ``profile_info > h4`` heading — found on
       event-team pages like Carleton College (CUT).
    2. Pull from the known element ID ``CT_Main_0_ucTeamDetails_lnkTeamName`` —
       found on team detail pages like Massachusetts (Zoodisc).
    3. Fall back to a regex that matches ``Name (Nickname)`` anywhere on the
       page, but only if no "MemberSession" or other noise has appeared first.
    4. Year: look for "2026 D-I College Championships" or similar heading.

    Returns:
      (team_name, year) where either or both may be None if not found.
    """
    team: str | None = None
    year: int | None = None

    # ── 1. Primary: profile_info > h4 (USA Ultimate event-team pages) ────────
    profile_match = re.search(
        r'<div\s+class="profile_info">\s*<h4>\s*(.*?)\s*</h4>',
        html,
        re.DOTALL,
    )
    if profile_match:
        raw = re.sub(r'<[^>]+>', '', profile_match.group(1)).strip()
        if raw:
            team = re.sub(r'\s+', ' ', raw)

    # ── 2. Secondary: known element ID (some USA Ultimate pages) ─────────────
    if not team:
        id_match = re.search(
            r'id="CT_Main_0_ucTeamDetails_lnkTeamName"[^>]*>(.*?)</a>',
            html,
            re.DOTALL,
        )
        if id_match:
            raw = re.sub(r'<[^>]+>', '', id_match.group(1)).strip()
            if raw:
                team = re.sub(r'\s+', ' ', raw)

    # ── 3. Fallback: "Name (Nickname)" anywhere — mixed-case nickname allowed
    # Only use if no team found yet (avoids matching "MemberSession (true)" etc.)
    if not team:
        fallback = re.search(
            r'([A-Z][a-zA-Z\s\-\']+?)\s*\(([A-Za-z][A-Za-z\s]{1,})\)',
            html,
        )
        if fallback:
            name_part = fallback.group(1).strip()
            nick_part = fallback.group(2).strip()
            # Additional sanity check: reject common false positives
            if not name_part.lower().startswith(('membersession', 'college', 'member')):
                team = re.sub(r'\s+', ' ', f"{name_part} ({nick_part})")

    # ── 4. Year from event heading ────────────────────────────────────────────
    year_match = re.search(
        r'(20\d{2})\s+(?:D-[IMX]|Men\'s|Women\'s|Mixed)?.*?(?:Championships|Nationals|Tournament)',
        html,
    )
    if year_match:
        year = int(year_match.group(1))

    return (team or None, year)


def infer_team_and_year(filename: str) -> tuple[str | None, int | None]:
    """Infer team name and year from a roster filename.

    Examples:
      "Carleton CUT 2026.csv" → ("Carleton CUT", 2026)
      "2026 - Team Name.xlsx" → ("Team Name", 2026)
      "team_roster.txt" → (None, None)
      "Finals_2024_Roster.xlsx" → ("Finals Roster", 2024)

    Returns:
      (team_name, year) where either or both may be None if not found
    """
    basename = Path(filename).stem  # Remove extension

    # Try to extract year (4-digit number, 2000-2099 range)
    # Look for year with optional separators before/after
    year_match = re.search(r'[_\-\s]?(20\d{2})[_\-\s]?', basename)
    year = int(year_match.group(1)) if year_match else None

    # Remove year and separators to get team name
    team = basename
    if year_match:
        # Remove the year match including surrounding separators
        team = team[:year_match.start()] + ' ' + team[year_match.end():]

    # Clean up separators and whitespace
    team = re.sub(r'[_\-]+', ' ', team)
    team = re.sub(r'\s+', ' ', team).strip()

    # Only remove trailing suffixes that are very unlikely to be part of a team name
    team = re.sub(r'\s+(roster|export|data|file)$', '', team, flags=re.IGNORECASE).strip()

    # Return None for team if it's empty or too short
    if not team or len(team) < 2:
        team = None

    return (team, year)


# Cloud metadata endpoints (AWS/Azure IMDS, ECS task metadata, GCP).
_METADATA_HOSTNAMES = {"metadata.google.internal"}
# Cloud IMDS endpoints use link-local IPs that won't resolve via DNS — must be blocked by IP.
_METADATA_IPS = {"169.254.169.254", "169.254.170.2"}  # AWS/GCP IMDS; Azure ECS task metadata
_LOCALHOST_HOSTNAMES = {"localhost", "ip6-localhost"}
_MAX_REDIRECTS = 5


def _blocked_ip_reason(ip_str: str) -> "str | None":
    """Return a human reason if the IP must be blocked, else None.

    The message wording is categorized (metadata / localhost / private) so callers
    and tests can distinguish why a destination was rejected.
    """
    if ip_str in _METADATA_IPS:
        return "URLs pointing to cloud metadata services are not allowed"
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return "URLs pointing to private or reserved IP addresses are not allowed"
    if ip.is_loopback:
        return "URLs pointing to localhost are not allowed"
    if (
        ip.is_private
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        return "URLs pointing to private or reserved IP addresses are not allowed"
    return None


def _validate_public_url(url: str) -> None:
    """Raise RosterImportError unless the URL resolves only to public IP addresses.

    Resolving the hostname and checking every returned address blocks SSRF via
    attacker-controlled domains that point at internal IPs (e.g. 127.0.0.1 or the
    cloud metadata endpoint). A narrow DNS-rebinding window remains between this
    check and the actual socket connection.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise RosterImportError("Only HTTP/HTTPS URLs are supported")

    hostname = parsed.hostname
    if not hostname:
        raise RosterImportError("Invalid URL: missing hostname")

    host_lower = hostname.lower()
    if host_lower in _LOCALHOST_HOSTNAMES:
        raise RosterImportError("URLs pointing to localhost are not allowed")
    if host_lower in _METADATA_HOSTNAMES:
        raise RosterImportError("URLs pointing to cloud metadata services are not allowed")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise RosterImportError(f"Could not fetch roster URL: cannot resolve host {hostname}") from exc

    for info in infos:
        reason = _blocked_ip_reason(info[4][0])
        if reason:
            raise RosterImportError(reason)


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
        # Follow redirects manually so each hop is re-validated against SSRF rules.
        # Using allow_redirects=True would validate only the initial URL — an attacker
        # could use a public redirect service that points at 169.254.169.254 or localhost.
        current = url
        for _ in range(_MAX_REDIRECTS + 1):
            _validate_public_url(current)
            try:
                response = requests.get(
                    current,
                    timeout=20,
                    allow_redirects=False,
                    headers={"User-Agent": "PhotoTagger roster importer"},
                )
            except requests.RequestException as exc:
                raise RosterImportError(f"Could not fetch roster URL: {exc}") from exc

            if getattr(response, "is_redirect", False) or getattr(response, "is_permanent_redirect", False):
                location = response.headers.get("Location")
                if not location:
                    break
                current = urljoin(current, location)
                continue

            try:
                response.raise_for_status()
            except requests.RequestException as exc:
                raise RosterImportError(f"Could not fetch roster URL: {exc}") from exc
            return RosterImporter.parse_html(response.text)

        raise RosterImportError("Too many redirects while fetching roster URL")


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
