import xml.etree.ElementTree as ET

from src.metadata_sidecar import PhotoMetadata, write_xmp_sidecar


NS = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "iptc": "http://iptc.org/std/Iptc4xmpExt/2008-02-29/",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
}


def bag_values(root, field):
    bag = root.find(f".//{field}/rdf:Bag", NS)
    if bag is None:
        return []
    return [li.text for li in bag.findall("rdf:li", NS)]


def test_write_xmp_sidecar_creates_iptc_metadata(tmp_path):
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"fake jpg")

    result = write_xmp_sidecar(
        photo,
        PhotoMetadata(
            player_name="Thomas Shope",
            team_name="Carleton CUT",
            team_year=2026,
            jersey_number="12",
            opponent_name="Pittsburgh En Sabah Nur",
        ),
    )

    root = ET.parse(result.sidecar_path).getroot()
    assert result.written is True
    assert result.opponent_omitted is False
    assert bag_values(root, "iptc:PersonInImage") == ["Thomas Shope"]
    assert bag_values(root, "iptc:OrganisationInImageName") == ["Carleton CUT", "Pittsburgh En Sabah Nur"]
    assert bag_values(root, "dc:subject") == [
        "Thomas Shope",
        "Carleton CUT",
        "Pittsburgh En Sabah Nur",
        "2026",
        "#12",
        "Ultimate Frisbee",
    ]
    assert root.find(".//iptc:Event", NS).text == "Carleton CUT vs Pittsburgh En Sabah Nur (2026)"


def test_write_xmp_sidecar_merges_existing_arrays_without_duplicates(tmp_path):
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"fake jpg")
    sidecar = tmp_path / "photo.xmp"
    sidecar.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
    <rdf:Description xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/">
      <Iptc4xmpExt:PersonInImage><rdf:Bag><rdf:li>Existing Player</rdf:li></rdf:Bag></Iptc4xmpExt:PersonInImage>
      <dc:subject><rdf:Bag><rdf:li>Existing Keyword</rdf:li><rdf:li>Carleton CUT</rdf:li></rdf:Bag></dc:subject>
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>
""",
        encoding="utf-8",
    )

    write_xmp_sidecar(
        photo,
        PhotoMetadata(
            player_name="Existing Player",
            team_name="Carleton CUT",
            team_year=2026,
            jersey_number="12",
            opponent_name=None,
        ),
    )

    root = ET.parse(sidecar).getroot()
    assert bag_values(root, "iptc:PersonInImage") == ["Existing Player"]
    assert bag_values(root, "dc:subject") == ["Existing Keyword", "Carleton CUT", "Existing Player", "2026", "#12", "Ultimate Frisbee"]
    assert root.find(".//iptc:Event", NS).text == "Carleton CUT (2026)"
