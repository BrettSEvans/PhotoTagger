from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import xml.etree.ElementTree as ET


XMP_NS = "adobe:ns:meta/"
RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
DC_NS = "http://purl.org/dc/elements/1.1/"
IPTC_EXT_NS = "http://iptc.org/std/Iptc4xmpExt/2008-02-29/"

ET.register_namespace("x", XMP_NS)
ET.register_namespace("rdf", RDF_NS)
ET.register_namespace("dc", DC_NS)
ET.register_namespace("Iptc4xmpExt", IPTC_EXT_NS)


@dataclass(frozen=True)
class PhotoMetadata:
    player_name: str
    team_name: str
    team_year: int
    jersey_number: str
    opponent_name: Optional[str] = None


@dataclass(frozen=True)
class SidecarWriteResult:
    sidecar_path: Path
    written: bool
    opponent_omitted: bool
    error: Optional[str] = None


def write_xmp_sidecar(photo_path: str | Path, metadata: PhotoMetadata) -> SidecarWriteResult:
    """Create or update an XMP sidecar next to a photo without touching the original."""
    photo = Path(photo_path)
    sidecar = photo.with_suffix(".xmp")
    if not photo.exists():
        return SidecarWriteResult(sidecar, written=False, opponent_omitted=metadata.opponent_name is None, error=f"Photo not found: {photo}")

    try:
        root, description = _load_or_create_xmp(sidecar)
        _merge_bag(description, f"{{{IPTC_EXT_NS}}}PersonInImage", [metadata.player_name])
        organisations = [metadata.team_name]
        if metadata.opponent_name:
            organisations.append(metadata.opponent_name)
        _merge_bag(description, f"{{{IPTC_EXT_NS}}}OrganisationInImageName", organisations)
        _set_text(description, f"{{{IPTC_EXT_NS}}}Event", _event_name(metadata))
        _merge_bag(description, f"{{{DC_NS}}}subject", _keywords(metadata))
        ET.ElementTree(root).write(sidecar, encoding="utf-8", xml_declaration=True)
        return SidecarWriteResult(sidecar, written=True, opponent_omitted=metadata.opponent_name is None)
    except Exception as exc:
        return SidecarWriteResult(sidecar, written=False, opponent_omitted=metadata.opponent_name is None, error=str(exc))


def _event_name(metadata: PhotoMetadata) -> str:
    if metadata.opponent_name:
        return f"{metadata.team_name} vs {metadata.opponent_name} ({metadata.team_year})"
    return f"{metadata.team_name} ({metadata.team_year})"


def _keywords(metadata: PhotoMetadata) -> list[str]:
    values = [
        metadata.player_name,
        metadata.team_name,
        metadata.opponent_name,
        str(metadata.team_year),
        f"#{metadata.jersey_number}" if metadata.jersey_number else None,
        "Ultimate Frisbee",
    ]
    return [value for value in values if value]


def _load_or_create_xmp(sidecar: Path):
    if sidecar.exists():
        root = ET.parse(sidecar).getroot()
    else:
        root = ET.Element(f"{{{XMP_NS}}}xmpmeta")

    rdf = root.find(f"{{{RDF_NS}}}RDF")
    if rdf is None:
        rdf = ET.SubElement(root, f"{{{RDF_NS}}}RDF")

    description = rdf.find(f"{{{RDF_NS}}}Description")
    if description is None:
        description = ET.SubElement(rdf, f"{{{RDF_NS}}}Description")

    return root, description


def _set_text(parent: ET.Element, tag: str, value: str) -> None:
    element = parent.find(tag)
    if element is None:
        element = ET.SubElement(parent, tag)
    element.text = value


def _merge_bag(parent: ET.Element, tag: str, values: list[str]) -> None:
    element = parent.find(tag)
    if element is None:
        element = ET.SubElement(parent, tag)

    bag = element.find(f"{{{RDF_NS}}}Bag")
    if bag is None:
        bag = ET.SubElement(element, f"{{{RDF_NS}}}Bag")

    existing = [li.text for li in bag.findall(f"{{{RDF_NS}}}li") if li.text]
    # casefold dedup so "Carleton CUT" and "carleton cut" are treated as the same entry.
    existing_keys = {value.casefold() for value in existing}
    for value in values:
        cleaned = str(value).strip()
        if cleaned and cleaned.casefold() not in existing_keys:
            ET.SubElement(bag, f"{{{RDF_NS}}}li").text = cleaned
            existing_keys.add(cleaned.casefold())
