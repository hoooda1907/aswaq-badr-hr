"""قراءة شيت البصمة (xls قديم BIFF2 / xls / xlsx / csv) واستخراج الحركات تلقائياً."""
import csv
import os
import re
import struct
from collections import Counter
from datetime import datetime, timedelta

OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


class ReadError(Exception):
    pass


# ----------------------------------------------------------------- قراءة الملفات
def _legacy_biff_rows(path):
    """قارئ بسيط لملفات xls القديمة (BIFF2/3) التي تصدرها أجهزة البصمة."""
    data = open(path, "rb").read()
    pos, cells, codepage = 0, {}, "cp1256"
    while pos + 4 <= len(data):
        rid, ln = struct.unpack_from("<HH", data, pos)
        body = data[pos + 4: pos + 4 + ln]
        pos += 4 + ln
        try:
            if rid == 0x0042 and len(body) >= 2:                      # CODEPAGE
                cp = struct.unpack_from("<H", body, 0)[0]
                if cp not in (0, 1200):
                    codepage = "cp%d" % cp
            elif rid == 0x0004 and len(body) >= 8:                    # LABEL (BIFF2)
                r, c = struct.unpack_from("<HH", body, 0)
                n = body[7]
                cells[(r, c)] = body[8:8 + n].decode(codepage, "replace")
            elif rid == 0x0204 and len(body) >= 8:                    # LABEL (BIFF3+)
                r, c = struct.unpack_from("<HH", body, 0)
                n = struct.unpack_from("<H", body, 6)[0]
                cells[(r, c)] = body[8:8 + n].decode(codepage, "replace")
            elif rid in (0x0003, 0x0203) and len(body) >= 15:         # NUMBER
                r, c = struct.unpack_from("<HH", body, 0)
                off = 7 if rid == 0x0003 else 6
                cells[(r, c)] = struct.unpack_from("<d", body, off)[0]
            elif rid == 0x0002 and len(body) >= 9:                    # INTEGER (BIFF2)
                r, c = struct.unpack_from("<HH", body, 0)
                cells[(r, c)] = float(struct.unpack_from("<H", body, 7)[0])
        except Exception:
            continue
    if not cells:
        raise ReadError("تعذر قراءة محتوى الملف")
    nr = max(k[0] for k in cells) + 1
    nc = max(k[1] for k in cells) + 1
    return [[cells.get((r, c)) for c in range(nc)] for r in range(nr)]


def read_table(path):
    with open(path, "rb") as f:
        head = f.read(8)
    ext = os.path.splitext(path)[1].lower()

    if head[:4] == b"PK\x03\x04":
        from openpyxl import load_workbook
        ws = load_workbook(path, data_only=True, read_only=True).active
        return [list(r) for r in ws.iter_rows(values_only=True)]

    if head == OLE_MAGIC:
        try:
            import xlrd
        except ImportError:
            raise ReadError("مكتبة xlrd غير متوفرة لقراءة هذا النوع من الملفات")
        sh = xlrd.open_workbook(path).sheet_by_index(0)
        rows = []
        for r in range(sh.nrows):
            row = []
            for c in range(sh.ncols):
                cell = sh.cell(r, c)
                if cell.ctype == xlrd.XL_CELL_DATE:
                    row.append(xlrd.xldate.xldate_as_datetime(cell.value, 0))
                elif cell.ctype == xlrd.XL_CELL_EMPTY:
                    row.append(None)
                else:
                    row.append(cell.value)
            rows.append(row)
        return rows

    if head[:1] == b"\x09":                       # BIFF قديم بدون حاوية OLE
        return _legacy_biff_rows(path)

    if ext in (".csv", ".txt"):
        raw = open(path, "rb").read()
        text = ""
        for enc in ("utf-8-sig", "cp1256", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        return [r for r in csv.reader(text.splitlines())]

    try:
        return _legacy_biff_rows(path)
    except Exception:
        raise ReadError("صيغة الملف غير مدعومة. استخدم xls أو xlsx أو csv")


# ----------------------------------------------------------------- تحويل الوقت
_RE_DMY = re.compile(r"^\s*(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})[ T]+(\d{1,2}):(\d{2})(?::\d{2})?\s*(.*)$")
_RE_YMD = re.compile(r"^\s*(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})[ T]+(\d{1,2}):(\d{2})(?::\d{2})?\s*(.*)$")
_PM = ("PM", "م", "ã")      # ã = بايت 0xE3 (م) عند قراءته بترميز خاطئ
_AM = ("AM", "ص", "Õ")      # Õ = بايت 0xD5 (ص)


def _apply_marker(h, marker):
    mk = (marker or "").strip().upper()
    if mk:
        if any(x in mk for x in _PM):
            return h % 12 + 12
        if any(x in mk for x in _AM):
            return h % 12
    return h


def parse_dt(v):
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.replace(second=0, microsecond=0)
    if isinstance(v, (int, float)):
        if 30000 < v < 80000:
            return (datetime(1899, 12, 30) + timedelta(days=float(v))).replace(second=0, microsecond=0)
        return None
    s = str(v).strip()
    try:
        m = _RE_DMY.match(s)
        if m:
            d, mo, y, h, mi, mk = m.groups()
            return datetime(int(y), int(mo), int(d), _apply_marker(int(h), mk), int(mi))
        m = _RE_YMD.match(s)
        if m:
            y, mo, d, h, mi, mk = m.groups()
            return datetime(int(y), int(mo), int(d), _apply_marker(int(h), mk), int(mi))
    except ValueError:
        return None
    return None


def norm_code(v):
    if v is None:
        return ""
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v).strip()


# ----------------------------------------------------------------- التعرف على الأعمدة
_CODE_HINTS = ("ac-no", "ac no", "acno", "code", "كود", "رقم الموظف", "id")
_NAME_HINTS = ("name", "اسم", "الاسم")


def detect_columns(rows):
    sample = [r for r in rows[:500] if any(x not in (None, "") for x in r)]
    if not sample:
        raise ReadError("الملف فارغ")
    ncol = max(len(r) for r in sample)

    def vals(c):
        return [r[c] for r in sample if c < len(r) and r[c] not in (None, "")]

    best, best_ratio = None, 0.0
    for c in range(ncol):
        ok = sum(1 for r in sample if c < len(r) and parse_dt(r[c]))
        ratio = ok / len(sample)
        if ratio > best_ratio:
            best, best_ratio = c, ratio
    if best is None or best_ratio < 0.5:
        raise ReadError("لم أتمكن من التعرف على عمود التاريخ والوقت في الشيت")
    tcol = best

    header = [str(x).strip().lower() if x is not None else "" for x in sample[0]]
    has_header = parse_dt(sample[0][tcol]) is None

    def hint(c, words):
        return has_header and c < len(header) and any(w in header[c] for w in words)

    cands = []
    for c in range(ncol):
        if c == tcol:
            continue
        v = vals(c)
        if len(v) < 0.6 * len(sample):
            continue
        strs = [norm_code(x) for x in v]
        if sum(len(x) for x in strs) / len(strs) > 12:
            continue
        if len(set(strs)) / len(strs) > 0.7:
            continue
        cands.append(c)
    if not cands:
        raise ReadError("لم أتمكن من التعرف على عمود كود الموظف في الشيت")
    ccol = next((c for c in cands if hint(c, _CODE_HINTS)), cands[0])

    ncands = []
    for c in range(ncol):
        if c in (tcol, ccol):
            continue
        v = [str(x).strip() for x in vals(c)]
        if len(v) < 0.5 * len(sample):
            continue
        texty = [x for x in v if not x.replace(".", "").isdigit()]
        if len(texty) < 0.5 * len(v) or sum(len(x) for x in v) / len(v) < 4:
            continue
        ncands.append(c)
    namecol = next((c for c in ncands if hint(c, _NAME_HINTS)), ncands[0] if ncands else None)
    return ccol, namecol, tcol


def extract_punches(rows):
    """يرجع (قائمة (code, name, datetime), الأعمدة المكتشفة)"""
    ccol, ncol, tcol = detect_columns(rows)
    out, names = [], {}
    for r in rows:
        if tcol >= len(r) or ccol >= len(r):
            continue
        dt = parse_dt(r[tcol])
        code = norm_code(r[ccol])
        if not dt or not code:
            continue
        nm = ""
        if ncol is not None and ncol < len(r) and r[ncol] not in (None, ""):
            nm = str(r[ncol]).strip()
        names.setdefault(code, Counter())[nm] += 1
        out.append((code, nm, dt))
    final = {}
    for code, cnt in names.items():
        good = [n for n, _ in cnt.most_common() if n and not n.isdigit()]
        final[code] = good[0] if good else (cnt.most_common(1)[0][0] or code)
    out = [(c, final[c], d) for c, _, d in out]
    if not out:
        raise ReadError("لم يتم العثور على أي حركات بصمة صالحة")
    return out, (ccol, ncol, tcol)
