"""Guards the code split between main.py (Lead/Engineer) and app/ (auth, BU Head,
shared helpers). A merge-conflict resolution that restores an old main.py makes
these tests fail instead of silently shadowing the app/ code.

If a test here fails after a merge: do NOT delete the test. Remove the re-added
code from main.py and make any intended change in its home under backend/app/
(see CONTRIBUTING.md, "Where did shared code go?").
"""

import ast
from pathlib import Path

from fastapi import FastAPI

from app.api import api_router

MAIN_PY = Path(__file__).resolve().parents[1] / "main.py"

# Helpers that live in app/ and are imported into main.py under these names.
SHARED_HELPERS = {
    "require_role",
    "user_can_access_project",
    "lead_project_ids",
    "engineer_wbs_condition",
    "engineer_wbs_ids",
    "engineer_approved_project_ids",
    "time_entry_total",
    "_get_month_key",
    "_distribute_hours_over_months",
    "executive_dashboard_data",
    "booking_approval_status",
    "BOOKING_APPROVAL_LABELS",
    "create_bu_head_notification",
    "notification_output",
    "extension_request_output",
    "find_pending_extension_request",
    "decide_extension_request",
    "record_governance_action",
    "EXTENSION_STATUS_LABELS",
    "enforce_governance",
    "upgrade_schema",
}

HTTP_METHODS = {"get", "post", "put", "delete", "patch"}


def _main_tree() -> ast.Module:
    return ast.parse(MAIN_PY.read_text(encoding="utf-8"))


def _main_routes(tree: ast.Module) -> dict[tuple[str, str], int]:
    """(METHOD, path) -> line for every `@app.<method>("<path>")` route in main.py."""
    routes = {}
    for node in tree.body:
        for decorator in getattr(node, "decorator_list", []):
            if (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and isinstance(decorator.func.value, ast.Name)
                and decorator.func.value.id == "app"
                and decorator.func.attr in HTTP_METHODS
                and decorator.args
                and isinstance(decorator.args[0], ast.Constant)
            ):
                routes[(decorator.func.attr.upper(), decorator.args[0].value)] = decorator.lineno
    return routes


def _app_package_routes() -> set[tuple[str, str]]:
    """Every (METHOD, path) served by the app/ routers."""
    probe = FastAPI()
    probe.include_router(api_router)
    return {(method.upper(), path) for path, ops in probe.openapi()["paths"].items() for method in ops}


def test_main_py_does_not_serve_routes_owned_by_app_package():
    duplicated = {route: line for route, line in _main_routes(_main_tree()).items() if route in _app_package_routes()}

    assert not duplicated, (
        "These routes are served by backend/app/ but were re-added to main.py (line numbers shown). "
        f"Remove them from main.py and make any change in app/api/routers instead: {duplicated}"
    )


def test_main_py_does_not_redefine_shared_helpers():
    redefined = {}
    for node in _main_tree().body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in SHARED_HELPERS:
            redefined[node.name] = node.lineno
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in SHARED_HELPERS:
                    redefined[target.id] = node.lineno

    assert not redefined, (
        "These helpers live in backend/app/ and are imported by main.py, but main.py redefines them "
        f"(line numbers shown), silently overriding the app/ version: {redefined}. "
        "Delete the definitions in main.py and change the app/ version instead."
    )


def test_app_routers_are_mounted_before_main_py_routes():
    tree = _main_tree()
    include_lines = [
        node.lineno
        for node in tree.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and node.value.func.attr == "include_router"
    ]
    route_lines = list(_main_routes(tree).values())

    assert include_lines, "main.py must call app.include_router(api_router)."
    assert not route_lines or include_lines[0] < min(route_lines), (
        f"app.include_router(api_router) (line {include_lines[0]}) must come before the first @app route "
        f"(line {min(route_lines)}), otherwise same-path routes in main.py shadow the app/ routers."
    )
