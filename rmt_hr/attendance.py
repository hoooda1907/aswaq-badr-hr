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
    dup_minutes: int = 10           # بصمات أقرب من هذا الفارق تُعتبر بصمة واحدة (تكرار)
    max_shift_hours: int = 18       # أطول شيفت مقبول بين الدخول والخروج


@dataclass
class Day:
    day: date
    in_dt: datetime = None
    out_dt: datetime = None
    shift: str = "day"          # day / night
    change: str = ""            # علامة تحوّل الشيفت عن آخر يوم سابق
    extra: float = 0.0          # ساعات شيفت ثانٍ في نفس اليوم (نادر)
    extra_note: str = ""

    @property
    def night(self):
        return self.shift == "night"

    @property
    def hours(self):
        if self.in_dt is None or self.out_dt is None:
            return 0.0
        return (self.out_dt - self.in_dt).total_seconds() / 3600.0 + self.extra

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
        if self.extra_note:
            n.append(self.extra_note)
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


class DayMap(dict):
    """قاموس الأيام + بصمات خروج يتيمة (بلا دخول) {تاريخ يوم الشيفت المفقود: [وقت البصمة]}."""
    orphans = {}


def _mark_changes(days):
    prev = None
    for d in sorted(days):
        rec = days[d]
        if prev is not None and prev.shift != rec.shift:
            rec.change = "⇄ تحوّل إلى " + SHIFT_LABELS[rec.shift]
        prev = rec
    return days


def _normalize(punches):
    """يقبل datetime أو (datetime, kind) ويرجع {datetime: 'I'/'O'/'IO'/''}."""
    recs = {}
    for p in punches:
        dt, k = (p[0], p[1] or "") if isinstance(p, tuple) else (p, "")
        recs[dt] = "".join(sorted(set(recs.get(dt, "")) | set(k)))
    return recs


def _cluster(recs, cfg):
    """يدمج البصمات المتقاربة (تكرار الجهاز) في بصمة واحدة: [(datetime, 'I'/'O'/None)]."""
    win = timedelta(minutes=cfg.dup_minutes)
    groups = []
    for t in sorted(recs):
        if groups and t - groups[-1][0] <= win:
            groups[-1][1] = t
            groups[-1][2] |= set(recs[t])
        else:
            groups.append([t, t, set(recs[t])])
    out = []
    for first, last, ks in groups:
        ks &= {"I", "O"}
        kind = next(iter(ks)) if len(ks) == 1 else None      # تعارض الاتجاه = غير معروف
        out.append((last if kind == "O" else first, kind))
    return out


def _directional(recs, cfg):
    """الحساب عند وجود اتجاه الجهاز (حضور/انصراف) — يعالج الصباحي والمسائي والمتغير:
    1) الشيفت المسائي: دخول ثم أول بصمة تالية في اليوم التالي شكلها خروج (اتجاهها خروج/مجهول أو قبل 06:00) خلال
       أقصى مدة شيفت. يُحسب على يوم الدخول. (اتجاه الجهاز يُصحَّح بالوقت: بصمة بعد منتصف الليل لا تكون دخولاً.)
    2) باقي البصمات: أول وآخر بصمة في اليوم كما في الحساب الصباحي.
    3) بصمة بعد منتصف الليل بلا دخول = يتيمة: تُهمل ويُعتبر اليوم راحة/غياب، وتظهر كتحذير."""
    ps = _cluster(recs, cfg)
    n = len(ps)
    used = [False] * n
    one = timedelta(days=1)
    maxsh = timedelta(hours=cfg.max_shift_hours)
    minm = timedelta(minutes=cfg.min_minutes)
    early, split = cfg.detect_hour, cfg.split_hour

    def outlike(t, k):
        return k in ("O", None) or t.hour < early

    pairs = []
    for pass_no in (1, 2):
        for i in range(n):
            if used[i]:
                continue
            t, k = ps[i]
            if t.hour < early:
                continue
            if pass_no == 1:
                if k == "O":
                    continue
            else:   # خروج بعلامة غلط (حضوره في المساء ولا يسبقه شيء غير مستخدم في نفس اليوم)
                if k != "O" or t.hour < split:
                    continue
                if any(not used[j] and ps[j][0].date() == t.date() for j in range(i)):
                    continue
            j = next((j for j in range(i + 1, n) if not used[j]), None)
            if j is None:
                continue
            q, kq = ps[j]
            if q.date() == t.date() + one and outlike(q, kq) and minm <= q - t <= maxsh:
                used[i] = used[j] = True
                pairs.append((t, q))

    rest, orphans = {}, {}
    first_date = ps[0][0].date() if ps else None
    for i in range(n):
        if used[i]:
            continue
        t, _ = ps[i]
        if t.hour < early:
            if t.date() != first_date:        # أول يوم في البيانات: خروج شيفت الشهر السابق (طبيعي)
                orphans.setdefault(t.date() - one, []).append(t)
            continue
        rest.setdefault(t.date(), []).append(t)

    days = DayMap()
    for t, q in pairs:
        days[t.date()] = Day(t.date(), t, q, shift="night" if q.date() > t.date() else "day")
    has_night = bool(pairs)
    for d, pl in sorted(rest.items()):
        pl.sort()
        if pl[-1] - pl[0] >= minm:
            rec = Day(d, pl[0], pl[-1])
        else:
            rec = Day(d, pl[0], None, shift="night" if has_night and pl[0].hour >= 17 else "day")
        if d in days:                           # شيفتان في نفس اليوم: تُجمع الساعات
            main = days[d]
            if rec.complete and main.complete:
                main.extra += (rec.out_dt - rec.in_dt).total_seconds() / 3600.0
                main.extra_note = "شيفت إضافي %s-%s" % (rec.in_dt.strftime("%H:%M"), rec.out_dt.strftime("%H:%M"))
            continue
        days[d] = rec
    days.orphans = orphans
    return days


def build_days(punches, mode="auto", cfg=None):
    """punches: قائمة datetime أو (datetime, kind) حيث kind = 'I' دخول / 'O' خروج / '' (من عمود اتجاه الشيت).
    mode: auto (يعتمد على الاتجاه لو موجود وإلا على الأوقات) / day / night."""
    cfg = cfg or Cfg()
    recs = _normalize(punches)
    if not recs:
        return DayMap()
    if mode == "night":
        days = _night_shifts(sorted(recs), cfg, auto=False)
    elif mode == "day":
        days = _day_mode(sorted(recs), cfg)
    else:
        typed = sum(1 for k in recs.values() if k in ("I", "O"))
        if typed >= 0.5 * len(recs):
            days = _directional(recs, cfg)
        else:
            days = _night_shifts(sorted(recs), cfg, auto=True)
    if not isinstance(days, DayMap):
        d2 = DayMap(days)
        days = d2
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
