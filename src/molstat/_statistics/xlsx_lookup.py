"""Read the first worksheet of an Excel lookup without losing sparse cells."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import posixpath
import re
from xml.etree import ElementTree
import zipfile


_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_DOCUMENT_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PACKAGE_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_CELL_REFERENCE = re.compile(r"([A-Z]+)[1-9][0-9]*")
_MAX_XML_BYTES = 64_000_000


def _read_xml(archive: zipfile.ZipFile, name: str) -> ElementTree.Element:
    if archive.getinfo(name).file_size > _MAX_XML_BYTES:
        raise ValueError("Lookup-filen har et for stort regneark.")
    return ElementTree.fromstring(archive.read(name))


def _rich_text(item: ElementTree.Element) -> str:
    # Phonetic annotations are not part of the cell's displayed value.
    nodes = list(item.findall(f"{_MAIN}t")) + list(item.findall(f"{_MAIN}r/{_MAIN}t"))
    return "".join(node.text or "" for node in nodes)


def _sheet_target(archive: zipfile.ZipFile) -> str:
    workbook = _read_xml(archive, "xl/workbook.xml")
    first = workbook.find(f"{_MAIN}sheets/{_MAIN}sheet")
    if first is None:
        raise ValueError("Lookup-filen mangler regneark.")
    relationships = _read_xml(archive, "xl/_rels/workbook.xml.rels")
    relationship = next((rel for rel in relationships.findall(f"{_PACKAGE_REL}Relationship")
                         if rel.get("Id") == first.get(f"{_DOCUMENT_REL}id")), None)
    if (relationship is None or relationship.get("TargetMode") == "External"
            or not relationship.get("Type", "").endswith("/worksheet")):
        raise ValueError("Lookup-filen har en ugyldig regnearkreferanse.")
    target = relationship.get("Target", "")
    target = posixpath.normpath(target.lstrip("/") if target.startswith("/") else posixpath.join("xl", target))
    if not target.startswith("xl/worksheets/") or not target.endswith(".xml"):
        raise ValueError("Lookup-filen har en ugyldig regnearkreferanse.")
    return target


def _cell_text(cell: ElementTree.Element, shared: list[str]) -> str:
    kind = cell.get("t")
    if kind == "e":
        raise ValueError(f"Lookup-filen har en Excel-feil i celle {cell.get('r', '?')}.")
    inline = cell.find(f"{_MAIN}is")
    if kind == "inlineStr" and inline is not None:
        return _rich_text(inline)
    value = cell.find(f"{_MAIN}v")
    if value is None or value.text is None:
        if cell.find(f"{_MAIN}f") is not None:
            raise ValueError(f"Lookup-filen har en uberegnet formel i celle {cell.get('r', '?')}. Åpne og lagre filen i Excel.")
        return ""
    if kind == "s":
        index = int(value.text)
        if not 0 <= index < len(shared):
            raise ValueError("Lookup-filen har en ugyldig tekstreferanse.")
        return shared[index]
    return value.text


def _column_index(reference: str) -> int:
    match = _CELL_REFERENCE.fullmatch(reference)
    if match is None:
        raise ValueError("Lookup-filen har en ugyldig cellereferanse.")
    index = 0
    for character in match[1]:
        index = index * 26 + ord(character) - ord("A") + 1
    if index > 16_384:
        raise ValueError("Lookup-filen har for mange kolonner.")
    return index - 1


def read_lookup(path: Path, clean: Callable[[object], str]) -> dict[str, dict[str, str]]:
    """Return cleaned records keyed by Analyse, rejecting ambiguous input."""
    try:
        with zipfile.ZipFile(path) as archive:
            shared_root = (_read_xml(archive, "xl/sharedStrings.xml")
                           if "xl/sharedStrings.xml" in archive.namelist() else None)
            shared = [_rich_text(item) for item in shared_root.findall(f"{_MAIN}si")] if shared_root is not None else []
            sheet = _read_xml(archive, _sheet_target(archive))
        header: dict[int, str] | None = None
        lookup: dict[str, dict[str, str]] = {}
        for row in sheet.findall(f"{_MAIN}sheetData/{_MAIN}row"):
            values: dict[int, str] = {}
            next_index = 0
            for cell in row.findall(f"{_MAIN}c"):
                index = _column_index(cell.attrib["r"]) if "r" in cell.attrib else next_index
                if index in values:
                    raise ValueError("Lookup-filen har duplikate cellereferanser.")
                values[index] = clean(_cell_text(cell, shared))
                next_index = index + 1
            if not any(values.values()):
                continue
            if header is None:
                header = {index: text for index, text in values.items() if text}
                if "Analyse" not in header.values():
                    raise ValueError("Lookup-filen mangler kolonnen Analyse på første ark.")
                if len(set(header.values())) != len(header):
                    raise ValueError("Lookup-filen har duplikate kolonnenavn.")
                continue
            if any(value and index not in header for index, value in values.items()):
                raise ValueError(f"Lookup-filen har data uten kolonnenavn på rad {row.get('r', '?')}.")
            record = {name: values.get(index, "") for index, name in header.items()}
            key = record["Analyse"]
            if not key:
                raise ValueError(f"Lookup-filen mangler analyse på rad {row.get('r', '?')}.")
            if key in lookup:
                raise ValueError(f"Lookup-filen har duplikat analyse: {key}.")
            lookup[key] = record
        if not lookup:
            raise ValueError("Lookup-filen er tom eller mangler analyser.")
        return lookup
    except (OSError, KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise ValueError(f"Lookup-filen {path.name} kunne ikke leses som en gyldig Excel-fil.") from exc
