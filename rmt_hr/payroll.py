from .constants import DEFAULT_FP_RULES


def fp_days(count, rules=None):
    """عدد أيام الخصم حسب عدد البصمات المنسية في الشهر."""
    r = rules or DEFAULT_FP_RULES
    if count < r["t1"]:
        return float(r["d0"])
    if count <= r["t2"]:
        return float(r["d1"])
    if count <= r["t3"]:
        return float(r["d2"])
    return float(r["d3"])


def calculate(emp, s, rules=None):
    """emp: dict بيانات الموظف للشهر، s: Summary. يرجع dict بكل بنود المرتب."""
    md = s.month_days
    salary = float(emp.get("salary") or 0)
    allowances = float(emp.get("allowances") or 0)
    penalties = float(emp.get("penalties") or 0)
    insurance = float(emp.get("insurance") or 0)
    advance = float(emp.get("advance") or 0)
    req = float(emp.get("req_hours") or 10) or 10.0
    rate = float(emp.get("ot_rate") or 1.0)
    leave = max(0, min(int(emp.get("leave_days") or 0), s.remaining))
    absent = s.remaining - leave

    daily = salary / md if md else 0.0
    hourly = daily / req
    ot_manual = emp.get("ot_manual")
    ot_hours = float(ot_manual) if ot_manual not in (None, "") else s.ot_hours
    ot_pay = ot_hours * hourly * rate
    absence_ded = absent * daily
    leave_ded = 0.0 if emp.get("leave_paid", 1) else leave * daily
    short_ded = s.short_hours * hourly if emp.get("deduct_short") else 0.0

    fp_count = s.missing_punches
    fp_d = fp_days(fp_count, rules)
    fp_auto = fp_d * daily
    fp_manual = emp.get("fp_manual")
    fp_edited = fp_manual not in (None, "")
    fp_amount = float(fp_manual) if fp_edited else fp_auto

    gross = salary + allowances + ot_pay
    total_ded = absence_ded + leave_ded + short_ded + penalties + fp_amount + insurance + advance
    net = gross - total_ded
    r = lambda x: round(x + 1e-9, 2)
    return {
        "salary": r(salary), "allowances": r(allowances), "penalties": r(penalties),
        "insurance": r(insurance), "advance": r(advance), "leave": leave, "absent": absent,
        "daily": r(daily), "hourly": r(hourly), "ot_hours": round(ot_hours, 2), "ot_pay": r(ot_pay),
        "absence_ded": r(absence_ded), "leave_ded": r(leave_ded), "short_ded": r(short_ded),
        "fp_count": fp_count, "fp_days": fp_d, "fp_auto": r(fp_auto), "fp_amount": r(fp_amount),
        "fp_edited": fp_edited, "penalties_total": r(penalties + fp_amount),
        "gross": r(gross), "total_ded": r(total_ded), "net": r(net),
    }
