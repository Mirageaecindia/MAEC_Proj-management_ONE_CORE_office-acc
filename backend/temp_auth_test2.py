import json
import sqlite3
import urllib.request
import urllib.error

DB = r"C:\Users\SUBHIKA\OneDrive\MACE\project\Create Project\backend\promanage.db"

BASE = "http://127.0.0.1:8000"


def req(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def tok(u, p):
    code, text = req("POST", "/api/auth/login", body={"username": u, "password": p})
    return json.loads(text)["token"]


valids = []
bu = tok("buhead", "BuHead@123")
lead = tok("lead", "Lead@123")
eng = tok("engineer", "Engineer@123")

valid_create = {
    "project_code": "E2E-TMP",
    "project_name": "E2E Temp",
    "client_customer": "Acme",
    "project_lead_electrical": "Anita Kumar",
    "project_lead_mechanical": "Mohan Daniel",
    "project_lead_bim": "Priya Nair",
    "target_start_date": "2026-10-01",
    "total_contract_value": 0,
    "contract_currency": "USD",
    "target_effort_hours": 0,
    "alert_override_threshold_pct": 80,
}

code, text = req("POST", "/api/projects", lead, valid_create)
print(f"[{'PASS' if code == 403 else 'FAIL'}] lead valid-create -> {code} (expect 403): {text[:100]}")

code, text = req("POST", "/api/projects", eng, valid_create)
print(f"[{'PASS' if code == 403 else 'FAIL'}] eng valid-create -> {code} (expect 403): {text[:100]}")

code, text = req("POST", "/api/projects", bu, valid_create)
print(f"[{'PASS' if code == 201 else 'FAIL'}] bu valid-create -> {code} (expect 201): {text[:140]}")
if code == 201:
    new_id = json.loads(text)["id"]
    valids.append(new_id)
    print(f"  created project id={new_id}")

code, text = req("GET", "/api/projects", bu)
p_list = json.loads(text)
print(f"projects visible to bu_head: {len(p_list)}")

code, text = req("GET", "/api/projects", eng)
p_eng = json.loads(text)
print(f"projects visible to engineer(1): {len(p_eng)} => {[p['project_code'] for p in p_eng]}")
print(f"[{'PASS' if all(p['project_code'] != 'E2E-TMP' for p in p_eng) else 'FAIL'}] engineer cannot see unassigned E2E-TMP project")

for pid in valids:
    c = sqlite3.connect(DB)
    c.execute("DELETE FROM projects WHERE id = ?", (pid,))
    c.commit()
    c.close()
print(f"cleanup: deleted {len(valids)} temp project(s)")

code, text = req("GET", "/api/projects", bu)
print(f"projects after cleanup: {len(json.loads(text))}")