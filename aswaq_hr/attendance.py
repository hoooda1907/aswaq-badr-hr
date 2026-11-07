"""تجميع حركات كل موظف: صباحي (أول بصمة دخول وآخر بصمة خروج في نفس اليوم) أو مسائي (يمتد لليوم التالي)."""
import calendar
from dataclasses import dataclass
from datetime import datetime, date, time, timedelta

from .constants import WORK_DAYS_PER_REST, SHIFT_LABELS


@dataclass
class Cfg:
    split_hour: int = 12            # الشيفت المسائي: قبل هذه الساعة = بصمة خروج لليوم السابق، بعدها = بصمة دخول
    detect_hour: int = 6            # للكشف التلقائي: بصمة بين 00:00 وهذه الساعة تدل على شيفت مسائي
    min_minutes: int = 30           # أقل فارق بين الدخول والخروج (غيره يعتبر تكرار بصمة)


@dataclass
class Day:
    day: date
    in_dt: datetime = None
    out_dt: datetime = None
    shift: str = "day"          # day / night
    change: str = ""            # علامة تحوّل الشيفت عن آخر يوم سابق

    @property
    def night(self):
        return self.shift == "night"

    @property
    def hours(self):
        if self.in_dt is None or self.out_dt is None:
            return 0.0
        return (self.out_dt - self.in_dt).total_seconds() / 3600.0

    @property
    def complete(self):
        return self.in_dt is not None and self.out_dt is not None

    @property
    def note(self):
        n = []
        if self.change:
            n.append(self.change)
        if self.in_dt is None:
            n.append("بصمة دخول ناقصة")
        elif self.out_dt is None:
            n.append("بصمة ناقصة")
        return " - ".join(n)


def _day_record(d, plist, cfg):
    plist = sorted(plist)
    first, last = plist[0], plist[-1]
    if (last - first) < timedelta(minutes=cfg.min_minutes):
        return Day(d, first, None)
    return Day(d, first, last)


def _day_mode(ps, cfg):
    return {d: _day_record(d, pl, cfg) for d, pl in _by_date(ps).items()}


def _by_date(ps):
    by = {}
    for p in ps:
        by.setdefault(p.date(), []).append(p)
    return by


def detect_mode(ps, cfg=None):
    """الموظف مسائي (على مستوى الشهر كله) لو بصماته بعد منتصف الليل (00:00 - detect_hour) متكررة في نصف أيامه.
    بصمة بعد منتصف الليل لا يمكن أن تكون دخول، فهي خروج شيفت اليوم السابق."""
    cfg = cfg or Cfg()
    by = _by_date(ps)
    early = sum(1 for pl in by.values() if any(p.hour < cfg.detect_hour for p in pl))
    return "night" if early >= 2 and early >= 0.5 * len(by) else "day"


def _night_shifts(ps, cfg, auto):
    """يوم العمل المسائي = تاريخ بصمة الدخول.
    الدخول = أول بصمة بعد الساعة 12 ظهراً. الخروج = آخر بصمة قبل الساعة 12 ظهراً في اليوم التالي.

    auto=False: كل يوم فيه بصمة بعد الظهر يُعتبر شيفت مسائي.
    auto=True : يُصنَّف كل يوم على حدة (للموظفين الذين يغيّرون الشيفت):
        مسائي لو تلاه بصمة بعد منتصف الليل وفي محيطه (يومين) شيفت مسائي آخر، أو كان اليوم السابق مسائياً؛
        وغير ذلك يُحسب صباحي بالطريقة القديمة (أول بصمة دخول وآخر بصمة خروج في نفس اليوم)."""
    by = _by_date(sorted(ps))
    dates = sorted(by)
    one = timedelta(days=1)
    split, early_h = cfg.split_hour, cfg.detect_hour
    ev = lambda d: [p for p in by.get(d, ()) if p.hour >= split]
    mo = lambda d: [p for p in by.get(d, ()) if p.hour < split]
    cand = {d for d in dates if ev(d) and any(p.hour < early_h for p in by.get(d + one, ()))}
    days, nights, claimed = {}, set(), set()

    def orphan_out(d):
        # بصمة صباحية لا يقابلها دخول في اليوم السابق = يوم ناقص بصمة الدخول
        # (أول يوم في البيانات يُهمل: هو خروج آخر شيفت في الشهر السابق)
        m = mo(d)
        if m and d not in claimed and d != dates[0] and (d - one) not in days:
            days[d - one] = Day(d - one, None, m[-1], shift="night")

    for d in dates:
        if auto:
            night = bool(ev(d)) and ((d in cand and any(d + k * one in cand for k in (-2, -1, 1, 2)))
                                     or (d - one) in nights)
        else:
            night = bool(ev(d))
        if night:
            nights.add(d)
            orphan_out(d)
            s = ev(d)[0]
            morning = mo(d + one)
            out = morning[-1] if morning and morning[-1] - s >= timedelta(minutes=cfg.min_minutes) else None
            days[d] = Day(d, s, out, shift="night")
            if morning:
                claimed.add(d + one)
        elif d in claimed:
            continue
        elif auto:
            if d == dates[0] and all(p.hour < early_h for p in by[d]):
                continue    # خروج شيفت مسائي من الشهر السابق
            days[d] = _day_record(d, by[d], cfg)
        else:
            orphan_out(d)
    return days


def _mark_changes(days):
    prev = None
    for d in sorted(days):
        rec = days[d]
        if prev is not None and prev.shift != rec.shift:
            rec.change = "⇄ تحوّل إلى " + SHIFT_LABELS[rec.shift]
        prev = rec
    return days


def build_days(punches, mode="auto", cfg=None):
    cfg = cfg or Cfg()
    ps = sorted(set(punches))
    if not ps:
        return {}
    if mode == "night":
        days = _night_shifts(ps, cfg, auto=False)
    elif mode == "day":
        days = _day_mode(ps, cfg)
    else:
        days = _night_shifts(ps, cfg, auto=True)
    return _mark_changes(days)


@dataclass
class Summary:
    month_days: int = 30
    present: int = 0
    rest: int = 0
    remaining: int = 0
    complete_days: int = 0
    total_hours: float = 0.0
    avg_hours: float = 0.0
    ot_hours: float = 0.0
    short_hours: float = 0.0
    in_punches: int = 0         # عدد بصمات الدخول
    out_punches: int = 0        # عدد بصمات الخروج
    missing_punches: int = 0    # عدد الأيام الناقصة (بدون دخول أو بدون خروج)
    day_shifts: int = 0
    night_shifts: int = 0
    last_shift: str = ""        # شيفت آخر يوم في الشهر

    @property
    def shift_label(self):
        if not self.last_shift:
            return ""
        cur = SHIFT_LABELS[self.last_shift]
        if self.day_shifts and self.night_shifts:
            return "متغيّر (الآن %s)" % cur
        return cur


def month_days_of(ym):
    y, m = int(ym[:4]), int(ym[5:7])
    return calendar.monthrange(y, m)[1]


def summarize(days, ym, req_hours, grace_min):
    md = month_days_of(ym)
    y, m = int(ym[:4]), int(ym[5:7])
    mine = [d for d in days.values() if d.day.year == y and d.day.month == m]
    s = Summary(month_days=md)
    s.present = len(mine)
    s.rest = min(s.present // WORK_DAYS_PER_REST, md - s.present)
    s.remaining = md - s.present - s.rest
    ot = sh = 0.0
    for d in mine:
        s.in_punches += d.in_dt is not None
        s.out_punches += d.out_dt is not None
        s.missing_punches += not d.complete
        if d.night:
            s.night_shifts += 1
        else:
            s.day_shifts += 1
        if not d.complete:
            continue
        s.complete_days += 1
        s.total_hours += d.hours
        diff = (d.hours - req_hours) * 60.0
        if diff > grace_min:
            ot += diff
        elif diff < -grace_min:
            sh += -diff
    if mine:
        s.last_shift = max(mine, key=lambda d: d.day).shift
    s.avg_hours = s.total_hours / s.complete_days if s.complete_days else 0.0
    s.ot_hours = ot / 60.0
    s.short_hours = sh / 60.0
    return s
