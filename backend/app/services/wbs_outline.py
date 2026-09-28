"""The WBS outline workbook: the Excel layout leads fill in to upload a project's tasks.

Column A: the phase (one of the five fixed phases), written once at the top of
its block or on every row; the rest of the block is blank. Column B: the
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
from app.domain.wbs import TO_DO

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


def parse_outline(content: bytes) -> list[OutlineRow]:
    """The outline rows of a workbook, or a BadRequestError naming the first bad row."""
    rows: list[OutlineRow] = []
    phase = None
    have_task = False
    for number, cells in read_cells(content):
        phase_text, _ = cells.get("A", ("", False))
        name, is_bold = cells.get("B", ("", False))
        name = name.strip()
        if phase_text.strip():
            new_phase = phase_from(phase_text)
            if new_phase is None:
                raise BadRequestError(
                    f"Row {number}: '{phase_text.strip()}' is not one of the five phases ({', '.join(PHASES)})."
                )
            if new_phase != phase:
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


def import_outline(db: Session, project: models.Project, user: models.User, content: bytes, phase: str | None) -> dict:
    """Create the outline's tasks and subtasks in the project (a row whose name already exists in
    that place is kept, so the same workbook can be uploaded again). `phase` overrides column A.
    The caller commits."""
    rows = parse_outline(content)
    nodes = db.query(models.WbsNode).filter_by(project_id=project.id).all()
    tasks = {(n.phase, n.task_name.strip().lower()): n for n in nodes if n.parent_id is None}
    subtasks = {(n.parent_id, n.task_name.strip().lower()): n for n in nodes if n.parent_id is not None}
    children = {}
    for n in nodes:
        if n.parent_id is not None:
            children[n.parent_id] = children.get(n.parent_id, 0) + 1
    roots = [int(m.group(1)) for n in nodes if n.wbs_code and (m := re.match(r"(\d+)", str(n.wbs_code)))]
    next_root = max(roots, default=0) + 1
    created = updated = 0
    task = None
    for row in rows:
        row_phase = phase or row.phase
        key = row.name.strip().lower()
        if row.is_task:
            task = tasks.get((row_phase, key))
            if task is None:
                task = models.WbsNode(
                    project_id=project.id,
                    wbs_code=f"{next_root}.",
                    task_name=row.name,
                    phase=row_phase,
                    deliverable_status=TO_DO,
                    assigned_lead=user.full_name,
                    assigned_lead_user_id=user.id,
                )
                next_root += 1
                db.add(task)
                db.flush()
                tasks[(row_phase, key)] = task
                created += 1
            else:
                updated += 1
            continue
        if (task.id, key) in subtasks:
            updated += 1
            continue
        children[task.id] = children.get(task.id, 0) + 1
        subtask = models.WbsNode(
            project_id=project.id,
            parent_id=task.id,
            wbs_code=f"{str(task.wbs_code).rstrip('.')}.{children[task.id]}",
            task_name=row.name,
            phase=row_phase,
            deliverable_status=TO_DO,
            assigned_lead=task.assigned_lead,
            assigned_lead_user_id=task.assigned_lead_user_id,
            assigned_engineer_id=task.assigned_engineer_id,
            start_date=task.start_date,
            target_due_date=task.target_due_date,
            end_date=task.end_date,
        )
        db.add(subtask)
        db.flush()
        subtasks[(task.id, key)] = subtask
        created += 1
    return {"created": created, "updated": updated, "phase": phase}


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
            if number == first:
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
