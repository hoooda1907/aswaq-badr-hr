"""طبقة تربط قاعدة البيانات بالحسابات: تحسب حضور وراتب كل موظف، ودفتر الإجازات والأرصدة."""
from .attendance import build_days, summarize
from .leaves import build_plan
from .payroll import calculate


def _month_state(db, branch, ym, emp, punches=None):
    if punches is None:
        punches = db.punches_of(branch, ym, emp["code"], with_kind=True)
    days = build_days(punches, emp.get("shift_mode") or "auto")
    s = summarize(days, ym, emp.get("req_hours") or 10, emp.get("grace_min") or 0)
    plan = build_plan(ym, days, s.rest, emp.get("leave_days") or 0,
                      explicit=db.day_statuses(branch, emp["code"], ym),
                      holidays=db.holidays_of(branch, ym),
                      choices=db.holiday_choices(branch, emp["code"], ym))
    return days, s, plan


def compute_employee(db, branch, ym, emp, punches=None, rules=None):
    days, s, plan = _month_state(db, branch, ym, emp, punches)
    pay = calculate(emp, s, rules or db.fp_rules(), plan)
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


YEAR_KEYS = ("rest", "annual", "unpaid", "absent", "comp")


def ledger(db, branch, code, ym, override=None):
    """دفتر الموظف حتى الشهر ym:
    - الإجازة السنوية: المستحق (من قائمة الموظفين، الافتراضي 21) − المستخدم في السنة = المتبقي.
    - تجميع السنة: تواريخ الراحة والإجازة السنوية وبدون الأجر والغياب والخصم من رصيد البدلات (لكل رقم تفاصيله).
    - رصيد بدلات الإجازة = (بدل الأجازات الرسمية + الأيام المضافة يدوياً) − الأيام المخصومة من الرصيد (كل الشهور السابقة).
    override = (emp, plan) لحساب الشهر الحالي بما هو معروض في الشاشة قبل الحفظ."""
    year = ym[:4]
    master = db.master_get(branch, code) or {}
    entitlement = float(master.get("annual_days") if master.get("annual_days") is not None else 21)
    year_dates = {k: [] for k in YEAR_KEYS}
    month_dates = {k: [] for k in YEAR_KEYS}
    comp_credit = comp_debit = 0.0
    for m in sorted(x for x in db.months(branch) if x <= ym):
        if override and m == ym:
            emp, plan = override
        else:
            emp = db.get_employee(branch, m, code)
            if emp is None:
                continue
            _, _, plan = _month_state(db, branch, m, emp)
        comp_credit += plan.comp_credit + float(emp.get("comp_added") or 0)
        comp_debit += plan.counts["comp"]
        if m[:4] == year:
            for d, st in plan.statuses.items():
                key = "unpaid" if st == "leave" else st
                if key in year_dates:
                    year_dates[key].append(d)
                    if m == ym:
                        month_dates[key].append(d)
    used = len(year_dates["annual"])
    return {"entitlement": entitlement, "annual_used": used, "annual_left": entitlement - used,
            "year_dates": {k: sorted(v) for k, v in year_dates.items()},
            "month_dates": {k: sorted(v) for k, v in month_dates.items()},
            "comp_balance": comp_credit - comp_debit, "comp_credit": comp_credit, "comp_debit": comp_debit}
