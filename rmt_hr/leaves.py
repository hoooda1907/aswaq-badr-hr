"""توزيع أيام الشهر: حضور + راحة أسبوعية + إجازة سنوية + إجازة بدون أجر + غياب + خصم من رصيد البدلات = أيام الشهر.
والأجازات الرسمية: أجر مقابل العمل فيها (0 / 1 / 1.5 / 2 يوم) أو بدل إجازة يضاف للرصيد."""
import calendar
from dataclasses import dataclass, field
from datetime import date

STATUS_LABELS = {
    "rest": "راحة أسبوعية", "annual": "إجازة سنوية", "unpaid": "إجازة بدون أجر",
    "absent": "غياب", "comp": "خصم من رصيد البدلات", "leave": "إجازة بدون أجر",   # leave = العدّاد القديم «إجازة بإذن»
}
PICKABLE = ("rest", "annual", "absent", "unpaid", "comp")          # ما يختاره المستخدم يدوياً لكل يوم
HOLIDAY_MULTS = ((0.0, "لا يحتسب"), (1.0, "يوم"), (1.5, "يوم ونصف"), (2.0, "يومان"))
CHOICE_LABELS = {"pay": "أجر إضافي", "comp": "بدل إجازة (يوم يضاف للرصيد)"}


@dataclass
class Plan:
    statuses: dict = field(default_factory=dict)      # {date: status} لكل يوم بلا حضور
    explicit: set = field(default_factory=set)        # التواريخ المختارة يدوياً
    counts: dict = field(default_factory=dict)
    holidays: list = field(default_factory=list)      # [{date, name, mult, worked, choice, pay_days, comp_days}]
    holiday_pay_days: float = 0.0
    comp_credit: float = 0.0                          # أيام بدل الإجازة المكتسبة من الأجازات الرسمية هذا الشهر
    rest_allowed: int = 0

    @property
    def rest_excess(self):
        return max(0, self.counts.get("rest", 0) - self.rest_allowed)

    def dates_of(self, *statuses):
        return sorted(d for d, st in self.statuses.items() if st in statuses)


def month_dates(ym):
    y, m = int(ym[:4]), int(ym[5:7])
    return [date(y, m, d) for d in range(1, calendar.monthrange(y, m)[1] + 1)]


def build_plan(ym, days, allowed_rest, legacy_leave=0, explicit=None, holidays=(), choices=None):
    """days: الأيام التي فيها حضور (من attendance). explicit: {date: status} اختيارات يدوية.
    الأيام غير المختارة تُوزَّع تلقائياً: الراحة المستحقة أولاً، ثم العدّاد القديم (إجازة بإذن)، والباقي غياب."""
    explicit, choices = explicit or {}, choices or {}
    dates = month_dates(ym)
    present = {d for d in dates if d in days}
    nonpresent = [d for d in dates if d not in present]
    chosen = {d: st for d, st in explicit.items() if d in nonpresent and st in PICKABLE}
    unset = [d for d in nonpresent if d not in chosen]
    statuses = dict(chosen)
    explicit_rest = sum(1 for st in chosen.values() if st == "rest")
    auto_rest = max(0, min(len(unset), allowed_rest - explicit_rest))
    for d in unset[:auto_rest]:
        statuses[d] = "rest"
    rest_unset = unset[auto_rest:]
    n_leave = max(0, min(int(legacy_leave or 0), len(rest_unset)))
    for d in rest_unset[:n_leave]:
        statuses[d] = "leave"
    for d in rest_unset[n_leave:]:
        statuses[d] = "absent"
    counts = {k: 0 for k in ("rest", "annual", "unpaid", "leave", "absent", "comp")}
    for st in statuses.values():
        counts[st] += 1

    rows, pay_days, comp_credit = [], 0.0, 0.0
    for h in holidays:
        d = h["day"]
        worked = d in days and getattr(days[d], "in_dt", None) is not None
        choice = choices.get(d, "pay")
        mult = float(h.get("mult") or 0)
        pd_ = mult if (worked and choice == "pay") else 0.0
        cd = 1.0 if (worked and choice == "comp") else 0.0
        pay_days += pd_
        comp_credit += cd
        rows.append({"date": d, "name": h.get("name", ""), "mult": mult, "worked": worked, "choice": choice,
                     "pay_days": pd_, "comp_days": cd})
    return Plan(statuses=statuses, explicit=set(chosen), counts=counts, holidays=rows,
                holiday_pay_days=pay_days, comp_credit=comp_credit, rest_allowed=allowed_rest)
