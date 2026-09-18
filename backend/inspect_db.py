from database import SessionLocal
import models
db = SessionLocal()
print('=== USERS ===')
for u in db.query(models.User).all():
    print(f'  id={u.id} username={u.username} role={u.role} full_name={u.full_name} employee_id={u.employee_id}')
print('=== EMPLOYEES ===')
for e in db.query(models.Employee).all():
    print(f'  id={e.id} code={e.employee_code} name={e.name} role={e.role_title} disc={e.discipline}')
print('=== PROJECTS ===')
for p in db.query(models.Project).all():
    print(f'  id={p.id} code={p.project_code} name={p.project_name} threshold={p.governance_threshold_pct} soft_locked={p.timesheets_soft_locked} contract={p.contract_value}')
print('=== WBS NODES ===')
for n in db.query(models.WbsNode).all():
    print(f'  id={n.id} proj={n.project_id} code={n.wbs_code} eng={n.assigned_engineer_id} est={n.estimated_hours} status={n.deliverable_status} phase={n.phase}')
print('=== TIME LOG ENTRIES ===')
for t in db.query(models.TimeLogEntry).all():
    print(f'  id={t.id} proj={t.project_id} task={t.task_id} emp={t.employee_id} week={t.week_start_date} status={t.approval_status} total={sum(getattr(t,f) or 0 for f in models.DAY_FIELDS)}')
db.close()