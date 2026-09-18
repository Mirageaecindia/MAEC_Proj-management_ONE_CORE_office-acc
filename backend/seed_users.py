import sys
sys.path.insert(0, r"C:\Users\SUBHIKA\OneDrive\MACE\project\Create Project\backend")

from sqlalchemy.orm import Session
from database import Base, SessionLocal, engine
import models
from auth import hash_password

Base.metadata.create_all(bind=engine)

db = SessionLocal()
try:
    # Create test users
    users_to_create = [
        ("buhead", "BuHead@123", "Test BU Head", "bu_head", None),
        ("lead", "Lead@123", "Anita Kumar", "lead", None),
        ("engineer", "Engineer@123", "Arjun Mehta", "engineer", 1),
    ]
    
    for username, password, full_name, role, employee_id in users_to_create:
        if not db.query(models.User).filter_by(username=username).first():
            user = models.User(
                username=username,
                password_hash=hash_password(password),
                full_name=full_name,
                role=role,
                employee_id=employee_id,
            )
            db.add(user)
            print(f"Created: {username} ({role})")
        else:
            print(f"Exists: {username}")
    db.commit()
finally:
    db.close()