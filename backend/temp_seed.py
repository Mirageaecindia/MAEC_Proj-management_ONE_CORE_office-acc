import hashlib
import secrets
import sqlite3

DB = r"C:\Users\SUBHIKA\OneDrive\MACE\project\Create Project\backend\promanage.db"
ITERATIONS = 100_000
ALGO = "pbkdf2_sha256"


def hash_pw(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), ITERATIONS)
    return f"{ALGO}${salt}${digest.hex()}"


c = sqlite3.connect(DB)
c.execute("DELETE FROM users")
c.execute("DELETE FROM login_sessions")

users = [
        ("buhead", "BuHead@123", "Test BU Head", "bu_head", None),
        ("lead", "Lead@123", "Anita Kumar", "lead", None),
        ("engineer", "Engineer@123", "Arjun Mehta", "engineer", 1),
    ]
for username, pw, name, role, eid in users:
    c.execute(
        "INSERT INTO users (username, password_hash, full_name, role, employee_id) VALUES (?, ?, ?, ?, ?)",
        (username, hash_pw(pw), name, role, eid),
    )
c.commit()
print("inserted:", c.execute("SELECT id, username, role, employee_id FROM users").fetchall())
c.close()
