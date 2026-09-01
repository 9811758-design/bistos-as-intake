from __future__ import annotations

import posixpath
import zipfile
from copy import deepcopy
from pathlib import Path
from xml.etree import ElementTree as ET

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
DRAWING_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing"

ET.register_namespace("", MAIN_NS)
ET.register_namespace("r", DOC_REL_NS)


def _rels_path(owner: str) -> str:
    return posixpath.join(posixpath.dirname(owner), "_rels", f"{posixpath.basename(owner)}.rels")


def _resolve(owner: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join(posixpath.dirname(owner), target))


def _sheet_part(files: dict[str, bytes], model: str) -> str:
    workbook = ET.fromstring(files["xl/workbook.xml"])
    relations = ET.fromstring(files["xl/_rels/workbook.xml.rels"])
    relation_targets = {
        item.attrib["Id"]: item.attrib["Target"]
        for item in relations.findall(f"{{{PKG_REL_NS}}}Relationship")
    }
    for sheet in workbook.findall(f".//{{{MAIN_NS}}}sheet"):
        if sheet.attrib.get("name") == model:
            relation_id = sheet.attrib[f"{{{DOC_REL_NS}}}id"]
            return _resolve("xl/workbook.xml", relation_targets[relation_id])
    raise ValueError(f"워크북에서 모델 시트를 찾을 수 없습니다: {model}")


def _drawing_relation(files: dict[str, bytes], sheet_part: str) -> ET.Element | None:
    relation_part = _rels_path(sheet_part)
    if relation_part not in files:
        return None
    relations = ET.fromstring(files[relation_part])
    return next(
        (
            item
            for item in relations.findall(f"{{{PKG_REL_NS}}}Relationship")
            if item.attrib.get("Type") == DRAWING_REL
        ),
        None,
    )


def _next_relation_id(root: ET.Element) -> str:
    used = {item.attrib.get("Id", "") for item in root}
    number = 1
    while f"rId{number}" in used:
        number += 1
    return f"rId{number}"


def _copy_drawing_parts(
    template_files: dict[str, bytes], output_files: dict[str, bytes], drawing_part: str
) -> set[str]:
    copied = {drawing_part}
    output_files[drawing_part] = template_files[drawing_part]
    drawing_rels = _rels_path(drawing_part)
    if drawing_rels in template_files:
        output_files[drawing_rels] = template_files[drawing_rels]
        copied.add(drawing_rels)
        relations = ET.fromstring(template_files[drawing_rels])
        for relation in relations.findall(f"{{{PKG_REL_NS}}}Relationship"):
            target_part = _resolve(drawing_part, relation.attrib["Target"])
            if target_part in template_files:
                output_files[target_part] = template_files[target_part]
                copied.add(target_part)
    return copied


def _merge_content_types(
    template_files: dict[str, bytes], output_files: dict[str, bytes], copied: set[str]
) -> None:
    source = ET.fromstring(template_files["[Content_Types].xml"])
    target = ET.fromstring(output_files["[Content_Types].xml"])
    existing_overrides = {
        item.attrib["PartName"] for item in target.findall(f"{{{CONTENT_NS}}}Override")
    }
    existing_defaults = {
        item.attrib["Extension"] for item in target.findall(f"{{{CONTENT_NS}}}Default")
    }
    copied_names = {f"/{item}" for item in copied}
    copied_extensions = {Path(item).suffix.lstrip(".") for item in copied}
    for item in source:
        is_override = (
            item.tag == f"{{{CONTENT_NS}}}Override"
            and item.attrib["PartName"] in copied_names
            and item.attrib["PartName"] not in existing_overrides
        )
        is_default = (
            item.tag == f"{{{CONTENT_NS}}}Default"
            and item.attrib["Extension"] in copied_extensions
            and item.attrib["Extension"] not in existing_defaults
        )
        if is_override or is_default:
            target.append(deepcopy(item))
    output_files["[Content_Types].xml"] = ET.tostring(
        target, encoding="utf-8", xml_declaration=True
    )


def restore_selected_sheet_drawing(template: Path, output: Path, model: str) -> None:
    with zipfile.ZipFile(template) as archive:
        template_files = {name: archive.read(name) for name in archive.namelist()}
    source_sheet = _sheet_part(template_files, model)
    source_relation = _drawing_relation(template_files, source_sheet)
    if source_relation is None:
        return
    drawing_part = _resolve(source_sheet, source_relation.attrib["Target"])
    with zipfile.ZipFile(output) as archive:
        output_files = {name: archive.read(name) for name in archive.namelist()}
    output_sheet = _sheet_part(output_files, model)
    output_rels_part = _rels_path(output_sheet)
    if output_rels_part in output_files:
        output_relations = ET.fromstring(output_files[output_rels_part])
    else:
        output_relations = ET.Element(f"{{{PKG_REL_NS}}}Relationships")
    relation_id = _next_relation_id(output_relations)
    ET.SubElement(
        output_relations,
        f"{{{PKG_REL_NS}}}Relationship",
        {"Id": relation_id, "Type": DRAWING_REL, "Target": source_relation.attrib["Target"]},
    )
    output_files[output_rels_part] = ET.tostring(
        output_relations, encoding="utf-8", xml_declaration=True
    )
    sheet_xml = ET.fromstring(output_files[output_sheet])
    drawing = ET.Element(f"{{{MAIN_NS}}}drawing", {f"{{{DOC_REL_NS}}}id": relation_id})
    extension = sheet_xml.find(f"{{{MAIN_NS}}}extLst")
    position = list(sheet_xml).index(extension) if extension is not None else len(sheet_xml)
    sheet_xml.insert(position, drawing)
    output_files[output_sheet] = ET.tostring(sheet_xml, encoding="utf-8", xml_declaration=True)
    copied = _copy_drawing_parts(template_files, output_files, drawing_part)
    _merge_content_types(template_files, output_files, copied)
    temporary = output.with_suffix(".drawing.tmp")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in output_files.items():
            archive.writestr(name, data)
    temporary.replace(output)
