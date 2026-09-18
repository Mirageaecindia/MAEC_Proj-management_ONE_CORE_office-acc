import sqlite3
import sys

DB = r"C:\Users\SUBHIKA\OneDrive\MACE\project\Create Project\backend\promanage.db"
c = sqlite3.connect(DB)
tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
print("tables:", tables)
print("employees:", c.execute("SELECT id, name, role_title FROM employees").fetchall())
print("project_leads:", c.execute("SELECT id, name FROM project_leads").fetchall())
print("users:", c.execute("SELECT id, username, role, employee_id FROM users").fetchall() if "users" in tables else "table not yet created")
c.close()
