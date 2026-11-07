"""استيراد بيانات الموظفين (المرتب والبدلات والجزاءات...) من شيت Excel، والمعامل هو كود الموظف."""
import re

from .excel_reader import norm_code, ReadError
from .service import compute_employee

# المفتاح، عنوان العمود في القالب، كلمات التعرف على العنوان (بعد التطبيع)
FIELDS = [
    ("code", "الكود", ("كود", "رقم الموظف", "code", "ac-no", "acno")),
    ("name", "الاسم", ("اسم", "name")),
    ("salary", "الراتب الأساسي", ("راتب", "مرتب", "اساسي", "salary", "basic")),
    ("allowances", "البدلات", ("بدل", "allowance")),
    ("penalties", "الجزاءات", ("جزاء", "عقوب", "penalt")),
    ("insurance", "خصم التأمينات", ("تامين", "insurance")),
    ("advance", "السلف", ("سلف", "advance")),
    ("notes", "ملاحظات", ("ملاحظ", "note")),
    ("absent", "غياب", ("غياب", "absen")),
    ("leave", "إجازة بإذن", ("اجاز", "leave")),
]
MONEY_KEYS = ("allowances", "penalties", "insurance", "advance")

_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٬٫", "0123456789,.")


def norm_ar(s):
    s = str(s or "").strip().lower().translate(_AR_DIGITS)
    s = re.sub("[\u064b-\u065f\u0640]", "", s)
    s = s.translate(str.maketrans("أإآىة", "ااايه"))
    return re.sub(r"\s+", " ", s)


def _match(header):
    h = norm_ar(header)
    if not h:
        return None
    for key, _, words in FIELDS:
        if any(w in h for w in words):
            return key
    return None


def to_num(v):
    """يرجع (قيمة أو None لو الخلية فارغة، سليمة؟)"""
    if v is None or (isinstance(v, str) and not v.strip()):
        return None, True
    if isinstance(v, (int, float)):
        return float(v), True
    try:
        return float(str(v).translate(_AR_DIGITS).replace(",", "").replace(" ", "")), True
    except ValueError:
        return None, False


def parse_employee_sheet(rows):
    """يرجع (قائمة الأعمدة الموجودة، السجلات، التحذيرات)."""
    header_i, colmap = None, {}
    for i, row in enumerate(rows[:15]):
        m = {}
        for c, cell in enumerate(row):
            if isinstance(cell, str):
                k = _match(cell)
                if k and k not in m.values():
                    m[c] = k
        if "code" in m.values() and len(m) >= 2:
            header_i, colmap = i, m
            break
    if header_i is None:
        raise ReadError("لم أجد صف العناوين. لازم يكون في الشيت عمود «الكود» وعمود آخر على الأقل "
                        "(استخدم «تصدير شيت بيانات فارغ» للحصول على الشكل الصحيح).")
    cols = list(colmap.values())
    recs, warns, seen = [], [], {}
    for i in range(header_i + 1, len(rows)):
        row = rows[i]
        rec = {"row": i + 1}
        for c, k in colmap.items():
            rec[k] = row[c] if c < len(row) else None
        code = norm_code(rec["code"])
        if not code:
            continue
        rec["code"] = code
        for k in ("salary", "absent", "leave") + MONEY_KEYS:
            if k in colmap.values():
                val, ok = to_num(rec.get(k))
                if not ok:
                    warns.append("الصف %d (كود %s): قيمة غير رقمية في «%s» اعتُبرت فارغة" % (i + 1, code, dict((f[0], f[1]) for f in FIELDS)[k]))
                rec[k] = val
        for k in ("name", "notes"):
            if k in colmap.values():
                rec[k] = str(rec.get(k) or "").strip()
        if code in seen:
            warns.append("الكود %s مكرر (الصف %d والصف %d) — أُخذ الصف الأخير" % (code, seen[code], i + 1))
            recs = [r for r in recs if r["code"] != code]
        seen[code] = i + 1
        recs.append(rec)
    if not recs:
        raise ReadError("لا توجد صفوف بيانات تحتها عناوين الأعمدة")
    return cols, recs, warns


def apply_employee_data(db, branch, ym, cols, recs):
    """يكتب البيانات على موظفي الشهر (وينشئ الموظف لو الكود غير موجود). الخلية الفارغة:
    في أعمدة المبالغ = صفر، وفي الراتب والاسم والملاحظات = يبقى القديم."""
    rep = {"updated": 0, "created": 0, "no_punches": [], "mismatch": [], "clipped": []}
    for rec in recs:
        code = rec["code"]
        emp = db.get_employee(branch, ym, code)
        if emp is None:
            db.ensure_employee(branch, ym, code, rec.get("name") or code)
            emp = db.get_employee(branch, ym, code)
            rep["created"] += 1
        else:
            rep["updated"] += 1
        if rec.get("name"):
            emp["name"] = rec["name"]
        if rec.get("notes"):
            emp["notes"] = rec["notes"]
        if "salary" in cols and rec.get("salary") is not None:
            emp["salary"] = rec["salary"]
        for k in MONEY_KEYS:
            if k in cols:
                emp[k] = rec.get(k) or 0.0
        has_punch = bool(db.punches_of(branch, ym, code))
        if not has_punch:
            rep["no_punches"].append(code)
        if "leave" in cols or "absent" in cols:
            _, s, _ = compute_employee(db, branch, ym, emp)
            if "leave" in cols:
                lv = int(round(rec.get("leave") or 0))
            else:
                lv = s.remaining - int(round(rec.get("absent") or 0))
            lv = max(0, lv)
            if lv > s.remaining:
                rep["clipped"].append((code, emp["name"], lv, s.remaining))
                lv = s.remaining
            emp["leave_days"] = lv
            if "absent" in cols and rec.get("absent") is not None:
                calc = s.remaining - lv
                if int(round(rec["absent"])) != calc:
                    rep["mismatch"].append((code, emp["name"], int(round(rec["absent"])), calc))
        db.save_employee(emp)
    return rep


def report_text(ym_label, cols, rep, warns):
    lines = ["تم استيراد بيانات الموظفين لشهر %s." % ym_label,
             "• موظفون تم تحديثهم: %d" % rep["updated"],
             "• موظفون جدد (غير موجودين في بصمات الشهر): %d" % rep["created"]]
    if rep["no_punches"]:
        lines.append("• بدون أي بصمات هذا الشهر (سيُحسب غيابهم كاملاً): " + "، ".join(rep["no_punches"][:15])
                     + (" ..." if len(rep["no_punches"]) > 15 else ""))
    if rep["clipped"]:
        lines.append("• إجازات أكبر من الأيام المتبقية فاختُصرت: " + "، ".join(
            "%s (%d ← %d)" % (c, a, b) for c, _, a, b in rep["clipped"][:10]))
    if rep["mismatch"]:
        lines.append("• غياب الشيت يختلف عن حساب البرنامج (الغياب = المتبقي − الإجازة)، والمعتمد حساب البرنامج: "
                     + "، ".join("%s (شيت %d / برنامج %d)" % (c, a, b) for c, _, a, b in rep["mismatch"][:10]))
    lines += warns[:8]
    return "\n".join(lines)
