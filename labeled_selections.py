from __future__ import annotations

import datetime
import json
import os
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

# Labeled selections map each label to its candle records, in the order they were added.
Selections = Dict[str, List[Dict[str, Optional[float]]]]

EXPORT_DIRECTORY = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "labeled_data"
)

# Every candle record uses these keys, in this order.
CANDLE_FIELDS = ("open", "high", "low", "close", "rsi", "3d_sma", "7d_sma", "2wk_sma", "1mo_sma")
# Moving average period (in candles) for each moving average field.
MOVING_AVERAGE_FIELDS = {3: "3d_sma", 7: "7d_sma", 14: "2wk_sma", 30: "1mo_sma"}
# XML attribute names cannot start with a digit, so the moving average fields are renamed.
XML_ATTRIBUTE_NAMES = {"3d_sma": "sma_3d", "7d_sma": "sma_7d", "2wk_sma": "sma_2wk", "1mo_sma": "sma_1mo"}


def format_for_path(path: str) -> str:
    extension = os.path.splitext(path)[1].lower()
    if extension == ".json":
        return "json"
    if extension == ".xml":
        return "xml"
    raise ValueError("Labeled selections must be saved as .json or .xml")


def export_path(directory: str, extension: str, now: datetime.datetime) -> str:
    return os.path.join(directory, f"selections_{now:%Y%m%d_%H%M%S}.{extension}")


def merge_selections(base: Selections, extra: Selections) -> Selections:
    merged = {label: list(records) for label, records in base.items()}
    for label, records in extra.items():
        merged.setdefault(label, []).extend(records)
    return merged


def write_selections(path: str, selections: Selections) -> None:
    text = to_xml_text(selections) if format_for_path(path) == "xml" else to_json_text(selections)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        file.write(text)


def read_selections(path: str) -> Selections:
    with open(path, encoding="utf-8") as file:
        text = file.read()
    if format_for_path(path) == "xml":
        return from_xml_text(text)
    return from_json_text(text)


def to_json_text(selections: Selections) -> str:
    document: Dict[str, Dict[str, Dict[str, Optional[float]]]] = {}
    for label, records in selections.items():
        document[label] = {
            f"{label}_candle_{number}": {field: record.get(field) for field in CANDLE_FIELDS}
            for number, record in enumerate(records)
        }
    return json.dumps(document, indent=4) + "\n"


def from_json_text(text: str) -> Selections:
    try:
        document = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"The file is not valid JSON: {error}") from error
    if not isinstance(document, dict):
        raise ValueError("The JSON file must contain an object of labels")
    selections: Selections = {}
    for label, candles in document.items():
        if not isinstance(candles, dict):
            raise ValueError(f"The label '{label}' must contain an object of candles")
        selections[label] = [_record_from_mapping(candle) for candle in candles.values()]
    return selections


def to_xml_text(selections: Selections) -> str:
    root = ET.Element("Selections")
    for label, records in selections.items():
        tag = xml_tag(label)
        group = ET.SubElement(root, tag, {"label": label})
        for number, record in enumerate(records):
            attributes = {
                XML_ATTRIBUTE_NAMES.get(field, field):
                    "" if record.get(field) is None else str(record[field])
                for field in CANDLE_FIELDS
            }
            ET.SubElement(group, f"{tag}Candle{number}", attributes)
    ET.indent(root, space="\t")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def from_xml_text(text: str) -> Selections:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as error:
        raise ValueError(f"The file is not valid XML: {error}") from error
    if root.tag != "Selections":
        raise ValueError("The XML file must have a Selections root element")
    selections: Selections = {}
    for group in root:
        label = group.get("label", group.tag)
        records = selections.setdefault(label, [])
        for candle in group:
            records.append(_record_from_mapping({
                field: candle.get(XML_ATTRIBUTE_NAMES.get(field, field)) or None
                for field in CANDLE_FIELDS
            }))
    return selections


def xml_tag(label: str) -> str:
    """Turn a label into a valid XML element name."""
    tag = re.sub(r"[^A-Za-z0-9_]", "_", label.strip())
    if not re.match(r"[A-Za-z_]", tag) or tag.lower().startswith("xml"):
        tag = "L_" + tag
    return tag


def _record_from_mapping(mapping: Any) -> Dict[str, Optional[float]]:
    if not isinstance(mapping, dict):
        raise ValueError("Each candle must be an object of values")
    record: Dict[str, Optional[float]] = {}
    for field in CANDLE_FIELDS:
        value = mapping.get(field)
        if value is None or value == "":
            record[field] = None
        else:
            try:
                record[field] = float(value)
            except (TypeError, ValueError) as error:
                raise ValueError(f"'{field}' must be a number, not {value!r}") from error
    return record
