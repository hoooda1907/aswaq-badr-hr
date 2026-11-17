"""طبقة تربط قاعدة البيانات بالحسابات: تحسب حضور وراتب كل موظف."""
from .attendance import build_days, summarize
from .payroll import calculate


def compute_employee(db, branch, ym, emp, punches=None, rules=None):
    if punches is None:
        punches = db.punches_of(branch, ym, emp["code"], with_kind=True)
    days = build_days(punches, emp.get("shift_mode") or "auto")
    s = summarize(days, ym, emp.get("req_hours") or 10, emp.get("grace_min") or 0)
    pay = calculate(emp, s, rules or db.fp_rules())
    return days, s, pay


def compute_all(db, branch, ym):
    emps = db.employees(branch, ym)
    out = []
    rules = db.fp_rules()
    for e in emps:
        pun = db.punches_of(branch, ym, e["code"], with_kind=True)
        days, s, pay = compute_employee(db, branch, ym, e, pun, rules)
        out.append((e, days, s, pay))
    return out
