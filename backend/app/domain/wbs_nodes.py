"""The WBS nodes (decided 2026-10-15): one per sheet of the stage workbooks in app/blueprints/.

Each workbook is one stage (wbs_cd.xlsx, wbs_sd.xlsx, wbs_dd.xlsx, in that order); each of its
sheets is a node, named exactly as the sheet, and holds that node's standard tasks (bold rows)
and their subtasks (normal rows) - read by app/services/wbs_outline.py, parse_node_sheet.
The workbooks are loaded as they are: replacing one changes the nodes with it.

A node is stored as the WBS phase of its tasks (wbs_nodes.phase). The five original phases
(app/domain/wbs.py, PHASES) are no longer offered, but their tasks stay valid.
"""

import io
import re
import zipfile
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from xml.etree import ElementTree

BLUEPRINT_DIR = Path(__file__).resolve().parents[1] / "blueprints"
# A node of the lead's own (decided 2026-10-16): no sheet and no standard tasks; the lead adds any
# tasks and subtasks to it by hand. It comes after the DD nodes.
OTHERS_NODE = "Others"
# Stage workbooks, in order: the stage is the part of the file name after "wbs_".
STAGE_WORKBOOKS = ("wbs_cd.xlsx", "wbs_sd.xlsx", "wbs_dd.xlsx")

_M = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


@dataclass(frozen=True)
class NodeSheet:
    key: str  # URL key: the sheet name in lower case, words joined by "-"
    phase: str  # the node's name: the sheet name as it is
    stage: str  # CD / SD / DD
    workbook: str  # file name in app/blueprints/
    sheet: str  # the sheet's part inside the workbook (xl/worksheets/sheetN.xml)


def node_key(name: str) -> str:
    """'SD- STR Coodination' -> 'sd-str-coodination'."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def workbook_sheets(content: bytes) -> list[tuple[str, str]]:
    """(sheet name, sheet part) of every sheet of a workbook, in tab order."""
    with zipfile.ZipFile(io.BytesIO(content)) as workbook:
        book = ElementTree.fromstring(workbook.read("xl/workbook.xml"))
        rels = ElementTree.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))
    targets = {rel.get("Id"): rel.get("Target") for rel in rels}
    sheets = []
    for sheet in book.iter(f"{{{_M}}}sheet"):
        target = targets[sheet.get(f"{{{_R}}}id")].lstrip("/")
        sheets.append((sheet.get("name"), target if target.startswith("xl/") else f"xl/{target}"))
    return sheets


@cache
def node_sheets() -> tuple[NodeSheet, ...]:
    """Every node, stage by stage in sheet order. Read once per process (the files ship with the app)."""
    nodes = []
    for workbook in STAGE_WORKBOOKS:
        path = BLUEPRINT_DIR / workbook
        if not path.exists():
            continue
        stage = Path(workbook).stem.removeprefix("wbs_").upper()
        for name, sheet in workbook_sheets(path.read_bytes()):
            nodes.append(NodeSheet(node_key(name), name.strip(), stage, workbook, sheet))
    keys = [node.key for node in nodes]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        raise RuntimeError(f"Two WBS node sheets have the same name: {', '.join(duplicates)}.")
    return tuple(nodes)


def node_phases() -> tuple[str, ...]:
    """The node names, in order: the sheets', then Others."""
    return (*(node.phase for node in node_sheets()), OTHERS_NODE)
