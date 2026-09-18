from database import SessionLocal
import models
db = SessionLocal()
users = db.query(models.User).all()
for u in users:
    print(f'User: {u.username}, Role: {u.role}, Full Name: {u.full_name}, Employee ID: {u.employee_id}')
db.close()