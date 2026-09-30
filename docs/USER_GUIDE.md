# MAEC ProManage: User Guide

How to use every feature, role by role, and how an action in one account shows up
in the others. Use it to walk through the app by hand. For the architecture and
business rules behind it, see [PROJECT_GUIDE.md](PROJECT_GUIDE.md); for what is
still to be built, see [TODO.md](TODO.md).

Last updated: 2026-09-26.

---

## 1. Getting started

### 1.1 Run the app
```powershell
# terminal 1: API on http://localhost:8000 (interactive API docs at /docs)
cd backend
.\start_backend.ps1

# terminal 2: web app on http://localhost:5173
cd frontend
npm run dev
```
Open **http://localhost:5173** and log in. After pulling new code, run
`backend\.venv\Scripts\python.exe -m pip install -r requirements.txt` once
(new dependencies), then start the API; database changes are applied
automatically at startup.

### 1.2 Accounts
Accounts are created from the command line (there is no sign-up page yet), in `backend/`:

```powershell
# BU Head
.venv\Scripts\python.exe create_user.py --username buhead --role bu_head --full-name "BU Head"
# Everyone else is an engineer, linked to an employee row (employees come from backend/data/employee_leads.csv).
# There are no lead accounts: the BU Head picks any engineer as a project's lead on Create Project.
.venv\Scripts\python.exe create_user.py --username eng.arjun --role engineer --full-name "Arjun Mehta" --employee-id 1
# A leaver
.venv\Scripts\python.exe create_user.py --username eng.arjun --deactivate
```
You are prompted for the password. For testing, create **one BU Head and at
least four engineers** (some will be chosen as leads), and use three browsers
(or one normal and two private windows) to be logged in as several people at once.

### 1.3 After login
| Role | Lands on | Tabs |
|---|---|---|
| **BU Head** | Projects | Projects · Create Project · Resource Booking · WBS Structure · Timeline & Logs · Executive Dashboard · Work Summary · SharePoint Mirror |
| **Engineer who leads a project** | Resource Booking | Resource Booking · WBS Structure · Timeline & Logs · Executive Dashboard · Performance Dashboard · SharePoint Mirror |
| **Engineer** | WBS Structure | WBS Structure · Timeline & Logs · Performance Dashboard · SharePoint Mirror |

Lead is a role on a project, not a kind of account: each page follows your role
on the **selected project**. On a project you lead you see the lead view
(bookings, WBS editing, approvals); on a project you only work on, the engineer
view. The account badge reads "Lead / Engineer" once you lead any project.

The **bell** in the header (BU Head and project leads) shows notifications: bookings to
approve, decisions, threshold alerts, locks, archive notices. Open it to read
them; **Mark read** clears one. A session lasts 12 hours; five wrong passwords lock that
username for 15 minutes.

### 1.4 Who sees which project
- **BU Head:** every project. Archived ones only with **Show archived** on the Projects page.
- Lead and engineer are roles **on a project**, not account types: the same person can lead one project and work as an engineer on another.
- **Lead of a project:** they are one of its three project leads, or the lead of any WBS task in it.
- **Engineer on a project:** only where the BU Head has **approved** a resource booking for them. A draft or pending booking, or a WBS task on its own, gives no access.
- **Archived projects** disappear for Leads and Engineers entirely.

---

## 2. The project lifecycle at a glance

1. **BU Head creates the project** with its commercial baseline and three Leads.
2. **Lead books engineers** (Resource Booking) and **submits** the booking.
3. **BU Head approves** (engineers now see the project) or **rejects with a reason**.
4. **Lead builds the WBS**: main tasks per phase, subtasks, engineer assignments.
5. **Engineer works** subtasks: tracks time (Login/Logout) and moves statuses forward.
6. **The task's lead approves each day** (the BU Head for a lead's own hours). Approved hours now count.
7. **Governance runs automatically**: alert at the threshold, automatic lock at 100% of the baseline.
8. **Lead requests an extension**; **BU Head decides**. The BU Head can also stop, resume, edit or archive the project.

---

## 3. BU Head features

### 3.1 Create a project (Create Project tab)
Fill in: project name, **unique** project code, client, target start date, a
lead for each discipline the project needs (Electrical, Mechanical, BIM: each is
optional, but at least one is required), contract currency and value, **target
effort hours** (the governance baseline) and the **alert threshold** (slider,
default 80%). Tick the SharePoint discipline folders to create.

**Choosing leads.** Any engineer can lead a project: the dropdowns list everyone
with an employee record, with their designation. For each lead you give a
**start date, an end date and a utilization %**: the share of their time the
project takes over that period. It counts toward their 100% like a booking, so
someone already booked 90% in those months can't be made a lead at 20%; the
form tells you how much is left. One person can't hold two lead roles on the
same project, and a person already booked as an engineer on the project must be
removed from the bookings before becoming its lead.

On **Create**, the project is saved and SharePoint folders are provisioned. The
Projects page shows the outcome; if SharePoint fails (for example no Azure
credentials), the project is still created and the error is shown.

**Effect on others:** the leads see the project immediately (Resource Booking,
WBS, Timeline, Executive Dashboard). Engineers see nothing yet. The leads appear
on the Resource Booking page as approved rows that only you can change (edit the
project), and in the subtask assignee list, so a lead can do subtasks and use
Login/Logout too. **A lead's own hours are approved by you**, not by the leads.

### 3.2 Projects page
Each project card shows its baseline. Buttons:
- **Dashboard**: opens the Executive Dashboard for that project (also for archived projects).
- **Edit** (active projects): see 3.3.
- **Archive** / **Reopen**: see 3.4.
- **Delete**: only for a project with **no history** at all (created by mistake). Otherwise the dialog says to archive it instead, so the audit log survives.
- **Show archived**: lists archived projects too (greyed, "Archived" badge).

### 3.3 Edit a project
The Create form, filled in (the SharePoint section is hidden; folders are not renamed).
- Every changed field is written to the **audit log** as before → after.
- **Currency change**: asks for confirmation. Amounts are relabelled, not converted, so enter the value in the new currency too.
- **Replacing a lead**: their WBS tasks move to the new lead of that discipline, and their lead booking is replaced by the new lead's. The old lead loses the project (unless booked on it as an engineer); both are notified.
- **Changing target hours re-checks the lock**: lowering it past 100% usage locks timesheets; raising it back under 100% reopens an *automatic* lock (a manual stop stays).

### 3.4 Archive / Reopen
**Archive** closes a finished project:
- read-only for everyone (any change is refused with "archived and read-only");
- hidden from Leads and Engineers;
- no longer counts toward engineers' allocation or governance alerts;
- any open Login on its subtasks is logged out (the time is kept) and a pending extension request is cancelled;
- Leads are notified; the action is in the audit log.

**Reopen** restores it exactly as it was, including any timesheet lock.

### 3.5 Resource Booking (approve / reject)
Pick the project. While the Lead's submission is **pending**, a banner and the
bell tell you. Click **Approve** (the booked engineers gain access to the project)
or **Reject**, which asks for a **reason** that the Leads receive; the bookings
go back to draft for the Lead to adjust and resubmit. Approval covers the whole
submission (per-engineer approval is planned, TODO C5).

### 3.6 Executive Dashboard
Per project:
- **Commercial Budget Burn**: contract value × (approved ÷ target hours). Past the contract value the card turns red: "Over budget by …".
- **Approved Hours Consumption**: approved hours against the baseline (target + approved extensions); pending hours are shown as "not yet counted".
- **Governance Threshold Status**: NORMAL, ALERT (at the threshold) or BASELINE REACHED (100%), and whether timesheets are locked.
- **Schedule Index (SPI)**: approved ÷ WBS planned hours (to be replaced by a real SPI, TODO N4).
- **Monthly chart**: planned vs approved hours per month; hours past the alert level show as exceeded.
- **Governance controls**: the pending extension request with **Approve / Reject Extension**, **Stop the Execution** (comment required) or **Resume Execution**, each with a confirmation. An archived project is shown read-only.
- **Audit log**: every governance action with who and when.

### 3.7 Work Summary
Per Lead: phases, tasks managed, completion per phase, approved/logged hours,
pending approvals. Per engineer: assigned tasks, baseline, approved/logged/pending
hours, overall progress (Not Started / In Progress / Completed).

### 3.8 Read-only views
WBS Structure and Timeline & Logs show the Leads' and Engineers' work for any
project, read-only. SharePoint Mirror shows the project's folder tree and files.

---

## 4. Lead features

### 4.1 Resource Booking
1. Pick one of your projects.
2. **Assign engineer**: choose the employee, start and end date and utilisation %. Planned hours are calculated from the dates (weekdays × 8). An engineer can't be booked beyond **100% across all active projects** (archived projects don't count).
3. **Edit / Delete** a booking. Editing is possible at any status, and an approved booking stays approved after an edit (to be changed, TODO C6).
4. **Submit for Approval**: every booking becomes pending; the BU Head is notified.

**Effect on others:** after the BU Head approves, the engineers see the project.
After a rejection you get a notification with the reason, and the bookings are
back in draft.

### 4.2 WBS Structure (build the plan)
- **Phase cards** (Space Planning … Submission): click a phase to add a **main task** in it, or **+** to upload a workbook into that phase.
- **Upload WBS (Excel)** / **Download the Excel template** for bulk import. The template (same layout as the company's WBS breakdown sheet) has two columns: **column A the phase** (one of the five, written once at the top of its merged block; a block left unnamed takes the phase by its position, so the company's breakdown sheet uploads as it is), **column B the tasks and subtasks**: a **bold** row is a task, a normal row is a subtask of the task above it. Codes are assigned automatically (1., 1.1, 1.2 …); dates, hours and engineers are set in the app afterwards. Uploading the same workbook again adds nothing: rows that already exist are kept. The older header-based CSV (`WBS Code, Task Name, Parent WBS Code, …`) still works.
- **+ Add WBS Node**: task name, WBS code (unique in the project), phase, assigned engineer (only engineers booked on the project), start/end dates (estimated hours are calculated from the dates).
- **+ Subtask** on a task: a child item for the engineer's day-to-day work.
- **Edit / Delete** a task or subtask (deleting a task deletes its subtasks). **Hours already worked are kept**: the day rows stay in the timesheet under the subtask's name, still count toward the engineer's working time, and the BU Head reviews any that are still pending. Anyone logged in to a deleted subtask is logged out and their time is saved.
- **Delete many at once**: tick the boxes in front of tasks and subtasks (a phase's box ticks the whole phase, the header box everything; ticking a task ticks its subtasks), then **Delete N tasks and M subtasks** above the table. One confirmation lists what goes; nothing is deleted if any item is refused.

**Effect on others:** the assigned engineer sees the task in their WBS Structure
(once their booking is approved); the BU Head sees everything read-only.

### 4.3 Task Details (approve a task)
Click a task row. The Lead can move **subtasks** forward and **Approve Task**
once the engineer has submitted it ("Submitted for Approval"). Main-task
statuses are otherwise driven by the engineer; comments are added by engineers.

### 4.4 Timeline & Logs (approve hours)
Hours are recorded **per subtask and per day**, and approved **per day** by the
lead of the task they were worked on. There is no week submission: the week is
just the sum of its days.

- The weekly sheet shows each engineer's hours per day, coloured by that day's
  status, with the week's status and e.g. **"2 of 3 days approved"**.
- **Approve week** on an engineer's row approves every pending, finished day of
  theirs on *your* tasks. **Approve all on my tasks** does it for every engineer
  at once. Approved days count toward the project's usage straight away.
- Click the engineer to open their **weekly log**: one row per subtask and day,
  with **Approve** / **Reject** per day. Rejecting hours that were already
  approved needs a **reason**; it is recorded in the audit log and shown on the
  BU Head's dashboard. Rejected hours are never approved again: the engineer
  corrects them instead (TODO H2).
- **Only a finished day can be reviewed** (yesterday or earlier), so approved
  hours never change under a later Logout on the same day.

Who approves what:
- **An engineer's hours:** the lead of the task they logged them on.
- **A project lead's own hours** (subtasks they did themselves): the **BU Head**,
  never the lead. The same goes for **a task the lead worked on**: it is approved
  by the BU Head, not by the lead (see §4.3).
- **Hours on a task with no lead, or whose lead's period has ended:** the BU Head,
  so no hours are left without someone to approve them.
- Nobody can approve while the project is locked, the BU Head included.
- New hours logged on an already-approved day (a session that ran past midnight)
  put that day back to "pending review".

### 4.5 Executive Dashboard (Lead view)
The project's governance figures for your projects, the audit log, and the
**extension request**: enter additional hours and a justification and submit.
Only a Lead allocated to the project can request, one pending request at a time.

**Effect on others:** the BU Head gets a notification and sees the request on
their dashboard. You are notified of the decision.

---

## 5. Engineer features

### 5.1 WBS Structure
Only the tasks and subtasks assigned to you (with their parent tasks). Click one
to open Task Details. You can **delete your own subtasks** (one with the bin icon, or tick several and
**Delete N subtasks**); only the project's lead deletes main tasks. Hours you already worked on a deleted
subtask are kept and still count.

### 5.2 Task Details (work and track time)
- **Status**: move a task To Do → In-Progress → Submitted for Approval (only once **all its subtasks are Done**); a subtask To Do → In-Progress → Done. The Lead approves the task.
- **Comments** on your tasks.
- **Login / Logout** (subtasks only) records your working time: the time from **Login** to **Logout** counts, including idle time and time spent in Revit, AutoCAD or other programs. Before 8 hours in a day nothing logs you out automatically. There is no screen to type hours.
  - **Log in** when you start a subtask and **log out** when you stop. If a subtask takes longer than planned, keep working; when it's done, create the next subtask and log in there.
  - **Keep MAEC open in a browser tab** while you work (minimised or behind other windows is fine). The tab tells the server once a minute that your laptop is on.
  - **Laptop switched off, asleep or offline** for more than 5 minutes: the time stops at the last signal and that gap is not counted. When you open MAEC again **on the same day**, it carries on by itself on the same subtask; you don't need to log in again. Closing every MAEC tab has the same effect as switching off. **The next day you always log in afresh**: yesterday's subtask never carries on by itself.
  - **More than 8 hours in a day** (all your subtasks and projects together): every hour still counts and your Lead reviews the day. Past the 8-hour mark, **visit MAEC at least every 30 minutes**: switch to its tab, click or press a key there. Task Details shows an "Over 8 hours today" note. If 30 minutes pass without a visit, you are logged out at your last visit, the time up to then is saved, and MAEC does not log you in again by itself. Task Details tells you when it happened; log in again if you are still working.
  - **Forgot to log out** with the laptop on: before the 8-hour mark the time keeps counting until you log out; after it, the rule above stops the clock within 30 minutes of your last visit (or of the mark, if that came later). The server checks every 5 minutes, so this also happens when the laptop is closed or MAEC is not open.
  - One subtask at a time. **Logout** adds the time to that day's row for the subtask (the day you logged in).
  - Edge "sleeping tabs" and Chrome "Memory Saver" can freeze a background tab. Add the MAEC address under *Always keep these sites active* in the browser settings.

### 5.3 Timeline & Logs
Your hours for the week, one row per subtask and day, each with its status:
Pending review, Approved or Rejected. Nothing to submit: each day is reviewed by
the task's lead once the day is over. Open your weekly log for the day-by-day
detail, the reviewer's name and any rejection reason.

### 5.4 Performance Dashboard
Your own figures per project: hours consumption, governance status, schedule
index, task completion and a monthly chart.

---

## 6. How actions affect the other accounts

| When… | BU Head sees | Lead sees | Engineer sees |
|---|---|---|---|
| BU Head **creates** a project | It on Projects and all pages | It in all their lists | Nothing yet |
| Lead **books** an engineer (draft) | Bookings on Resource Booking | Their draft | Nothing |
| Lead **submits** the booking | Bell + banner: approval needed | "Pending approval" | Nothing |
| BU Head **approves** the booking | "Approved" | Bell: approved | **The project appears** |
| BU Head **rejects** (with reason) | Back to draft | Bell with the reason; can edit and resubmit | Nothing |
| Lead **creates a task** assigned to an engineer | It in WBS (read-only) | It in WBS | It in their WBS |
| Engineer **tracks time** (Logout) | Pending hours on the dashboard | Hours in Timeline & Logs | Hours in Timeline & Logs |
| Task lead **approves a day** (or the week's pending days) | **Usage, budget burn and SPI go up** | Same figures | "Approved"; Performance Dashboard updates |
| Approved hours reach the **alert threshold** | Bell: threshold alert; ALERT on the card | Bell: threshold alert | — |
| Approved hours reach **100% of the baseline** | Bell: locked; BASELINE REACHED | Bell: locked; approvals refused | Logging and tracking refused |
| Lead **requests an extension** | Bell + request on the dashboard | "Pending BU Head approval" | — |
| BU Head **approves the extension** | Baseline raised; automatic lock lifted if usage is now under 100% | Bell: approved (and reopened) | Can log and track again |
| BU Head **stops / resumes** execution | Lock state, audit entry | Bell: locked / reopened | Logging refused / allowed |
| BU Head **edits** the project | Audit entry per change | Replaced Lead loses it, new Lead gains it; figures update | Figures update |
| BU Head **archives** | Only with Show archived; read-only | Bell; project disappears | Project disappears; active tracking ended |
| BU Head **reopens** | Back in the list, as before | Bell; project back | Project back (if booking approved) |
| An account is **deactivated** | — | A deactivated Lead disappears from the Create/Edit dropdowns | The person is logged out and can't log in |

---

## 7. Manual test script (end to end)

Use three windows: **BU** (BU Head), **LEAD** (the Electrical lead), **ENG** (an engineer).

1. **BU:** Create Project: target effort **100 h**, threshold **80%**, contract **100,000 USD**, your three Leads. It appears on Projects.
2. **LEAD:** Resource Booking: the project is listed. Book **ENG** at 50% for this month. **Submit for Approval**.
3. **BU:** bell shows the request. Resource Booking: **Reject** with a reason. **LEAD:** bell shows the reason; bookings are draft. Resubmit. **BU:** **Approve**.
4. **ENG:** the project now appears in WBS Structure (empty until tasks exist).
5. **LEAD:** WBS Structure: add a main task in *Space Planning* assigned to ENG, then **+ Subtask** on it.
6. **ENG:** WBS shows the task and subtask. Open the subtask: **Login**, keep the tab active a few minutes, **Logout**.
7. **ENG:** Timeline & Logs: the hours appear as Pending review (they can be reviewed from the next day).
8. **LEAD:** the next day, Timeline & Logs: **Approve week** on ENG's row. **BU:** Executive Dashboard: approved hours and budget burn go up.
9. **Threshold and lock.** Hours come only from Login/Logout, so use a small target: **BU:** Edit the project → target effort **1 h**, threshold **50%**. **ENG:** Login on a subtask, wait about **35 minutes**, Logout; submit the week. **LEAD:** approve the week → **ALERT** (bell for BU and LEAD). **ENG:** another **30 minutes**, Logout, submit; **LEAD:** approve → at 100% the project **locks** (BASELINE REACHED, bell). **ENG:** Login on the subtask is refused.
10. **LEAD:** Executive Dashboard: request an extension of, say, 10 h with a justification. **BU:** bell; dashboard: **Approve Extension**. If usage is now under 100%, the lock lifts automatically ("System" in the audit log); LEAD is notified.
11. **BU:** **Stop the Execution** (comment, confirm) → locked; **Resume Execution** → reopened. Both in the audit log.
12. **BU:** Edit: change the currency → confirmation dialog. Replace the Electrical Lead → the old Lead's window no longer lists the project.
13. **BU:** Projects → **Archive** → the project disappears for LEAD and ENG; **Show archived** → open its Dashboard (read-only banner). **Reopen** → everything is back as before.
14. **BU:** try **Delete** on this project → refused (it has history). Create an empty test project and delete it → allowed.

---

## 8. Known limitations while testing

- **Hours come only from Login/Logout** (decided 2026-09-27: no manual timesheet). Testing the threshold and lock therefore needs a small target (step 9).
- **Booking approval is all-or-nothing** per project (TODO C5); editing an approved booking keeps it approved (C6); planned hours ignore the booking % (N11).
- **Resuming at or above 100%** leaves the project unlocked without re-locking (TODO N14e).
- **The Lead's WBS edit dialog** can set any status, skipping the engineer's steps (TODO C13).
- **SPI** is not a real schedule index yet (TODO N4); "discipline" on the dashboard is the job title (N7).
- **SharePoint** provisioning needs the Azure credentials; without them projects are still created and the failure is shown.
- **Timeline & Logs** for the BU Head shows the weekly sheet but little schedule detail (TODO W1).
