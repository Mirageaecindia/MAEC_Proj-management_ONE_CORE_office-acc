"""Reading WBS node sheets and adding their rows to a project (the "+" of a node card).

A node's sheet (app/blueprints/, app/domain/wbs_nodes.py) lists its tasks and subtasks, one per
row: a **bold** row is a task, a normal row a subtask of the task above it. Bold lives in the cell
styles (xl/styles.xml), so this module parses the .xlsx itself. The WBS Excel upload and its
template were removed on 2026-10-15: the node cards add the WBS.
"""

import io
import re
import zipfile
from dataclasses import dataclass
from xml.etree import ElementTree

from sqlalchemy.orm import Session

import models
from app.domain.wbs import TO_DO, child_prefix, next_code

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


@dataclass
class OutlineRow:
    row: int  # Excel row number, for error messages
    phase: str
    name: str
    is_task: bool


def _bold_styles(workbook: zipfile.ZipFile) -> set[int]:
    """Cell style indexes (the `s` attribute) whose font is bold."""
    if "xl/styles.xml" not in workbook.namelist():
        return set()
    root = ElementTree.fromstring(workbook.read("xl/styles.xml"))
    fonts = [font.find("m:b", NS) is not None for font in root.findall("m:fonts/m:font", NS)]
    styles = set()
    for index, xf in enumerate(root.findall("m:cellXfs/m:xf", NS)):
        font_id = int(xf.get("fontId") or 0)
        if font_id < len(fonts) and fonts[font_id]:
            styles.add(index)
    return styles


def read_cells(
    content: bytes, sheet: str = "xl/worksheets/sheet1.xml"
) -> list[tuple[int, dict[str, tuple[str, bool]]]]:
    """Every row of a sheet (the first by default): (row number, {column letter: (text, bold)})."""
    with zipfile.ZipFile(io.BytesIO(content)) as workbook:
        shared = []
        if "xl/sharedStrings.xml" in workbook.namelist():
            shared_root = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
            shared = ["".join(node.itertext()) for node in shared_root.findall("m:si", NS)]
        bold = _bold_styles(workbook)
        root = ElementTree.fromstring(workbook.read(sheet))
        rows = []
        for row in root.findall(".//m:row", NS):
            cells = {}
            for cell in row.findall("m:c", NS):
                letter = "".join(ch for ch in (cell.get("r") or "") if ch.isalpha()).upper()
                value = cell.find("m:v", NS)
                text = value.text if value is not None and value.text else ""
                if cell.get("t") == "s" and text:
                    text = shared[int(text)]
                elif cell.get("t") == "inlineStr":
                    text = "".join(cell.itertext())
                cells[letter] = (text, int(cell.get("s") or 0) in bold)
            rows.append((int(row.get("r") or 0), cells))
    return rows


NOT_INCLUDED = re.compile(r"not\s*included", re.IGNORECASE)


def parse_node_sheet(content: bytes, phase: str, sheet: str = "xl/worksheets/sheet1.xml") -> list[OutlineRow]:
    """A WBS node's sheet (app/blueprints/, app/domain/wbs_nodes.py), taken as it is: a **bold** row
    is a task and the normal rows under it its subtasks.

    - The items are in one column, the one holding the most text (A, or another, as in DD).
    - A row marked "NOT INCLUDED" (in any of its cells) is left out.
    - Text in other columns (notes such as "NO TASKS" or "Custom Requirement") is left out.
    - Subtasks before the sheet's first task go under a task named after the node, since a
      subtask always has a task.
    """
    table = read_cells(content, sheet)
    excluded = {number for number, cells in table if any(NOT_INCLUDED.search(text) for text, _ in cells.values())}
    columns: dict[str, int] = {}
    for number, cells in table:
        if number in excluded:
            continue
        for letter, (text, _) in cells.items():
            if text.strip():
                columns[letter] = columns.get(letter, 0) + 1
    if not columns:
        return []
    column = max(sorted(columns, key=lambda letter: (len(letter), letter)), key=columns.get)  # leftmost on a tie
    rows: list[OutlineRow] = []
    for number, cells in table:
        name, is_bold = cells.get(column, ("", False))
        name = name.strip()
        if not name or number in excluded:
            continue
        if not is_bold and not rows:
            rows.append(OutlineRow(number, phase, phase, True))  # the node's own task
        rows.append(OutlineRow(number, phase, name, is_bold))
    return rows


def match_rows(nodes: list[models.WbsNode], rows: list[OutlineRow]) -> list:
    """For each row, the item already in the project that it stands for, or None. A task matches
    by phase and name, a subtask by name under its matched task. Repeats count: the second
    "review the model" under a task matches the second one there, if there is one."""
    tasks: dict[tuple, list[models.WbsNode]] = {}  # (phase, name) -> existing tasks, oldest first
    subtasks: dict[tuple, list[models.WbsNode]] = {}  # (task id, name) -> existing subtasks, oldest first
    for n in sorted(nodes, key=lambda n: n.id):
        key = n.task_name.strip().lower()
        if n.parent_id is None:
            tasks.setdefault((n.phase, key), []).append(n)
        else:
            subtasks.setdefault((n.parent_id, key), []).append(n)
    seen: dict[tuple, int] = {}
    matches: list[models.WbsNode | None] = []
    task = None
    for row in rows:
        key = row.name.strip().lower()
        group = (("task", row.phase, key), tasks.get((row.phase, key), []))
        if not row.is_task:
            if task is None:  # under a task that is new: new as well
                matches.append(None)
                continue
            group = ((task.id, key), subtasks.get((task.id, key), []))
        (counter, existing) = group
        nth = seen[counter] = seen.get(counter, 0) + 1
        match = existing[nth - 1] if nth <= len(existing) else None
        if row.is_task:
            task = match
        matches.append(match)
    return matches


def add_rows(
    db: Session,
    project: models.Project,
    user: models.User,
    rows: list[OutlineRow],
    again: bool = False,
) -> dict:
    """Add tasks and subtasks to the project. By default what is already there is skipped, so the
    same rows can be added again safely; with `again`, every row is added as a new copy, and
    `same_as` names, for each copy, the code of the item it repeats. New tasks are numbered after
    the project's highest task, so they come at the bottom; new subtasks take the next free code
    under their task. The caller commits."""
    nodes = db.query(models.WbsNode).filter_by(project_id=project.id).all()
    matches = match_rows(nodes, rows)
    codes = [n.wbs_code for n in nodes]
    roots = [int(m.group(1)) for n in nodes if n.wbs_code and (m := re.match(r"(\d+)", str(n.wbs_code)))]
    next_root = max(roots, default=0) + 1
    created_ids: list[int] = []
    same_as: dict[int, str | None] = {}
    skipped = 0
    task = None
    for row, match in zip(rows, matches, strict=True):
        if match is not None and not again:
            skipped += 1
            if row.is_task:
                task = match  # missing subtasks go under the task already there
            continue
        if row.is_task:
            node = models.WbsNode(
                project_id=project.id,
                wbs_code=f"{next_root}.",
                task_name=row.name,
                phase=row.phase,
                deliverable_status=TO_DO,
                assigned_lead=user.full_name,
                assigned_lead_user_id=user.id,
                created_by_user_id=user.id,
            )
            next_root += 1
        else:
            prefix = child_prefix(task.wbs_code)
            code = next_code(prefix, codes) if prefix else None
            codes.append(code)
            node = models.WbsNode(
                project_id=project.id,
                parent_id=task.id,
                wbs_code=code,
                task_name=row.name,
                phase=row.phase,
                deliverable_status=TO_DO,
                assigned_lead=task.assigned_lead,
                assigned_lead_user_id=task.assigned_lead_user_id,
                assigned_engineer_id=task.assigned_engineer_id,
                created_by_user_id=user.id,
                start_date=task.start_date,
                target_due_date=task.target_due_date,
                end_date=task.end_date,
            )
        db.add(node)
        db.flush()
        created_ids.append(node.id)
        if match is not None:
            same_as[node.id] = match.wbs_code
        if row.is_task:
            task = node
    return {
        "created": len(created_ids),
        "updated": skipped,
        "created_ids": created_ids,
        "same_as": same_as,
    }
