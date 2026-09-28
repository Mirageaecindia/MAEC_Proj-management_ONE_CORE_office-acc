"""Write the WBS upload template (frontend/public/wbs-upload-template.xlsx). Run from backend/:

    .venv\\Scripts\\python.exe make_wbs_template.py

The layout is described in app/services/wbs_outline.py; re-run after changing TEMPLATE_ROWS.
"""

from pathlib import Path

from app.services.wbs_outline import write_template

TARGET = Path(__file__).resolve().parents[1] / "frontend" / "public" / "wbs-upload-template.xlsx"

if __name__ == "__main__":
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_bytes(write_template())
    print(f"Wrote {TARGET}")
