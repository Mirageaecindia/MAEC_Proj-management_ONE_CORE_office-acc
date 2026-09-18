import json
import urllib.request
import urllib.error

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
    assert code == 200, (code, text)
    return json.loads(text)["token"]


bu = tok("buhead", "BuHead@123")
lead = tok("lead", "Lead@123")
eng = tok("engineer", "Engineer@123")

checks = [
    ("no-token /api/projects", "GET", "/api/projects", None, None, 401),
    ("lead /api/projects", "GET", "/api/projects", lead, None, 200),
    ("eng /api/projects (scoped)", "GET", "/api/projects", eng, None, 200),
    ("lead POST create (forbidden)", "POST", "/api/projects", lead,
     {"project_code": "E2E-TMP", "project_name": "tmp", "client_organization": "tmp",
      "project_lead": "Anita Kumar"}, 403),
    ("eng /api/employees", "GET", "/api/employees", eng, None, 403),
    ("eng /api/engineers", "GET", "/api/engineers", eng, None, 200),
    ("eng /api/engineer-performance", "GET", "/api/engineer-performance", eng, None, 200),
    ("eng /api/projects/1/wbs-structure", "GET", "/api/projects/1/wbs-structure", eng, None, 200),
    ("eng /api/projects/1/timesheet", "GET", "/api/projects/1/timesheet", eng, None, 200),
    ("lead exec-dash (forbidden)", "GET", "/api/projects/1/executive-dashboard", lead, None, 403),
    ("bu exec-dash (404 no project)", "GET", "/api/projects/1/executive-dashboard", bu, None, 404),
    ("bu work-summary (404 no project)", "GET", "/api/projects/1/work-summary", bu, None, 404),
    ("lead wbs-structure", "GET", "/api/projects/1/wbs-structure", lead, None, 200),
    ("bu wbs-structure", "GET", "/api/projects/1/wbs-structure", bu, None, 200),
    ("bu /api/projects", "GET", "/api/projects", bu, None, 200),
]

ok = True
for name, method, path, tk, body, expected in checks:
    code, text = req(method, path, tk, body) if body is not None else req(method, path, tk)
    status = "PASS" if code == expected else "FAIL"
    if status == "FAIL":
        ok = False
    print(f"[{status}] {name}: got {code}, expected {expected}" + ("" if status == "PASS" else f" ({text[:120]})"))

code, _ = req("POST", "/api/auth/logout", eng)
code2, _ = req("GET", "/api/auth/me", eng)
print(f"[{'PASS' if code == 200 and code2 == 401 else 'FAIL'}] logout invalidates token: logout={code}, me-after={code2}")

print("ALL PASS" if ok else "SOME FAILED")