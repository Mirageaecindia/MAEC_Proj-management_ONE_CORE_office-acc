"""The WBS outline workbook: the Excel layout leads fill in to upload a project's tasks.

Column A: the phase (one of the five fixed phases), written once at the top of
its block or on every row; the rest of the block is blank. When the blocks are
merged cells and a block has no name (the company's breakdown sheet leaves the
first two blank), the block takes the phase by its position, the five phases
in order. Column B: the
tasks and subtasks of that phase, one per row: a **bold** row is a task, a
normal row is a subtask of the task above it. Nothing else is needed: codes,
dates and hours are set in the app afterwards.

Reading the workbook needs the cell styles (bold lives in xl/styles.xml), so
this module parses the .xlsx itself; writing the template is `write_template`.
"""

import io
import re
import zipfile
from dataclasses import dataclass
from xml.etree import ElementTree
from xml.sax.saxutils import escape

from sqlalchemy.orm import Session

import models
from app.core.errors import BadRequestError
from app.domain.wbs import TO_DO, child_prefix, next_code

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
PHASES = ("Space Planning", "STR Coordination", "ID Coordination", "BoH Area RCP Coordination", "Submission")
_PHASE_BY_KEY = {re.sub(r"[^a-z]", "", p.lower()): p for p in PHASES}

# The example rows in the downloadable template, per phase: (name, is_task).
TEMPLATE_ROWS = {
    "Space Planning": [
        ("Carry out electrical load estimate & compare with the concept report", True),
        ("Indicate the location of substations / LV rooms", False),
        ("Indicate the major services routing", False),
    ],
    "STR Coordination": [
        ("MEP equipment plinths / equipment weights", True),
        ("Provide equipment plinth locations to STR", False),
        ("Review the structure model and highlight clashes", False),
    ],
    "ID Coordination": [
        ("Electrical distribution strategy", True),
        ("Obtain the power requirements for VT", False),
        ("Prepare the overall LV schematics", False),
    ],
    "BoH Area RCP Coordination": [
        ("BoH RCP coordination", True),
        ("Coordinate the ceiling services in the BoH areas", False),
        ("Issue the coordinated RCP layouts", False),
    ],
    "Submission": [
        ("Design submission", True),
        ("Compile the drawings and calculations", False),
        ("Issue the submission package", False),
    ],
}


@dataclass
class OutlineRow:
    row: int  # Excel row number, for error messages
    phase: str
    name: str
    is_task: bool


def phase_from(text: str) -> str | None:
    """'BOH Area RCP Coordination' -> 'BoH Area RCP Coordination'; None when unknown."""
    return _PHASE_BY_KEY.get(re.sub(r"[^a-z]", "", (text or "").lower()))


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


def read_cells(content: bytes) -> list[tuple[int, dict[str, tuple[str, bool]]]]:
    """Every row of the first sheet: (row number, {column letter: (text, bold)})."""
    with zipfile.ZipFile(io.BytesIO(content)) as workbook:
        shared = []
        if "xl/sharedStrings.xml" in workbook.namelist():
            shared_root = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
            shared = ["".join(node.itertext()) for node in shared_root.findall("m:si", NS)]
        bold = _bold_styles(workbook)
        sheet = ElementTree.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
        rows = []
        for row in sheet.findall(".//m:row", NS):
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


def merged_blocks(content: bytes) -> list[tuple[int, int]]:
    """The merged ranges of column A, as (first row, last row), top to bottom."""
    with zipfile.ZipFile(io.BytesIO(content)) as workbook:
        sheet = ElementTree.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
    blocks = []
    for merge in sheet.findall(".//m:mergeCell", NS):
        match = re.fullmatch(r"A(\d+):A(\d+)", merge.get("ref") or "")
        if match:
            blocks.append((int(match.group(1)), int(match.group(2))))
    return sorted(blocks)


def _phase_by_block(content: bytes) -> dict[int, str]:
    """First row of each merged block -> the phase it stands for, when the sheet has the five blocks
    in order (a named block must agree with its position)."""
    blocks = merged_blocks(content)
    if len(blocks) != len(PHASES):
        return {}
    return {first: phase for (first, _), phase in zip(blocks, PHASES, strict=True)}


def parse_outline(content: bytes) -> list[OutlineRow]:
    """The outline rows of a workbook, or a BadRequestError naming the first bad row."""
    rows: list[OutlineRow] = []
    by_block = _phase_by_block(content)
    phase = None
    have_task = False
    for number, cells in read_cells(content):
        phase_text, _ = cells.get("A", ("", False))
        name, is_bold = cells.get("B", ("", False))
        name = name.strip()
        new_phase = None
        if phase_text.strip():
            new_phase = phase_from(phase_text)
            if new_phase is None:
                raise BadRequestError(
                    f"Row {number}: '{phase_text.strip()}' is not one of the five phases ({', '.join(PHASES)})."
                )
        elif number in by_block:
            new_phase = by_block[number]  # an unnamed block: the phase by its position
        if new_phase is not None and new_phase != phase:
            phase, have_task = new_phase, False
        if not name:
            continue
        if phase is None:
            raise BadRequestError(f"Row {number}: put the phase in column A before the first task.")
        if is_bold:
            have_task = True
        elif not have_task:
            raise BadRequestError(f"Row {number}: '{name}' is a subtask (not bold) but no task comes before it.")
        rows.append(OutlineRow(number, phase, name, is_bold))
    if not rows:
        raise BadRequestError("The workbook has no tasks: put tasks (bold) and subtasks in column B.")
    return rows


def looks_like_outline(content: bytes) -> bool:
    """A workbook without a header row (no 'WBS Code' / 'Task Name' cell) is an outline."""
    for _, cells in read_cells(content)[:10]:
        for text, _ in cells.values():
            token = re.sub(r"[^a-z]", "", text.lower())
            if token in {"wbscode", "taskname"}:
                return False
    return True


# --- the template ------------------------------------------------------------------------------


def parse_blueprint(content: bytes, phase: str) -> list[OutlineRow]:
    """A phase blueprint (app/blueprints/): one column, a **bold** row is a task and the normal
    rows under it its subtasks; the phase is the blueprint's own."""
    rows: list[OutlineRow] = []
    for number, cells in read_cells(content):
        name, is_bold = cells.get("A", ("", False))
        name = name.strip()
        if not name:
            continue
        if not is_bold and not rows:
            raise BadRequestError(f"Row {number}: '{name}' is a subtask (not bold) but no task comes before it.")
        rows.append(OutlineRow(number, phase, name, is_bold))
    return rows


def import_outline(db: Session, project: models.Project, user: models.User, content: bytes, phase: str | None) -> dict:
    """Create the outline workbook's tasks and subtasks in the project. `phase` overrides column A.
    The caller commits."""
    result = add_rows(db, project, user, parse_outline(content), phase)
    return {key: result[key] for key in ("created", "updated", "phase")}


def match_rows(nodes: list[models.WbsNode], rows: list[OutlineRow], phase: str | None = None) -> list:
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
        group = (("task", phase or row.phase, key), tasks.get((phase or row.phase, key), []))
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
    phase: str | None = None,
    again: bool = False,
) -> dict:
    """Add tasks and subtasks to the project. By default what is already there is skipped, so the
    same rows can be added again safely; with `again`, every row is added as a new copy, and
    `same_as` names, for each copy, the code of the item it repeats. New tasks are numbered after
    the project's highest task, so they come at the bottom; new subtasks take the next free code
    under their task. The caller commits."""
    nodes = db.query(models.WbsNode).filter_by(project_id=project.id).all()
    matches = match_rows(nodes, rows, phase)
    codes = [n.wbs_code for n in nodes]
    roots = [int(m.group(1)) for n in nodes if n.wbs_code and (m := re.match(r"(\d+)", str(n.wbs_code)))]
    next_root = max(roots, default=0) + 1
    created_ids: list[int] = []
    same_as: dict[int, str | None] = {}
    skipped = 0
    task = None
    for row, match in zip(rows, matches, strict=True):
        row_phase = phase or row.phase
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
                phase=row_phase,
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
                phase=row_phase,
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
        "phase": phase,
        "created_ids": created_ids,
        "same_as": same_as,
    }


def write_template(rows_by_phase: dict[str, list[tuple[str, bool]]] = TEMPLATE_ROWS) -> bytes:
    """An outline workbook (the template by default), built with the standard library."""
    strings: list[str] = []
    index = {}

    def shared(text: str) -> int:
        if text not in index:
            index[text] = len(strings)
            strings.append(text)
        return index[text]

    sheet_rows, merges, number = [], [], 0
    for phase, phase_rows in rows_by_phase.items():
        first = number + 1
        for name, is_task in phase_rows:
            number += 1
            cells = []
            if number == first and not phase.startswith("_"):  # "_n" keys: an unnamed merged block
                cells.append(f'<c r="A{number}" s="3" t="s"><v>{shared(phase)}</v></c>')
            cells.append(f'<c r="B{number}" s="{1 if is_task else 2}" t="s"><v>{shared(name)}</v></c>')
            sheet_rows.append(f'<row r="{number}">{"".join(cells)}</row>')
        merges.append(f'<mergeCell ref="A{first}:A{number}"/>')

    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<cols><col min="1" max="1" width="30" customWidth="1"/><col min="2" max="2" width="70" customWidth="1"/></cols>'  # noqa: E501  (XML literal)
        f"<sheetData>{''.join(sheet_rows)}</sheetData>"
        f'<mergeCells count="{len(merges)}">{"".join(merges)}</mergeCells>'
        "</worksheet>"
    )
    shared_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="{len(strings)}" uniqueCount="{len(strings)}">'  # noqa: E501  (XML literal)
        + "".join(f"<si><t>{escape(text)}</t></si>" for text in strings)
        + "</sst>"
    )
    # fonts: 0 normal, 1 bold (tasks), 2 bold blue (phases); cellXfs: 0 default, 1 task, 2 subtask, 3 phase
    styles = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="3"><font><sz val="11"/><name val="Calibri"/></font>'
        '<font><b/><sz val="11"/><name val="Calibri"/></font>'
        '<font><b/><sz val="11"/><color rgb="FF1F3A93"/><name val="Calibri"/></font></fonts>'
        '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'  # noqa: E501  (XML literal)
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="4"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
        '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment vertical="top"/></xf></cellXfs>'  # noqa: E501  (XML literal)
        "</styleSheet>"
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="WBS" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'  # noqa: E501  (XML literal)
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'  # noqa: E501  (XML literal)
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>'  # noqa: E501  (XML literal)
        "</Relationships>"
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'  # noqa: E501  (XML literal)
        "</Relationships>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'  # noqa: E501  (XML literal)
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'  # noqa: E501  (XML literal)
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'  # noqa: E501  (XML literal)
        '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'  # noqa: E501  (XML literal)
        "</Types>"
    )
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        z.writestr("xl/styles.xml", styles)
        z.writestr("xl/sharedStrings.xml", shared_xml)
        z.writestr("xl/worksheets/sheet1.xml", sheet)
    return out.getvalue()
