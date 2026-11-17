"""مولدات HTML للسندات والتقارير + تصدير Excel."""
import base64
import os
from html import escape

from . import APP_NAME, DEVELOPER
from .constants import MONTH_NAMES_AR


def month_label(ym):
    return "%s %s" % (MONTH_NAMES_AR[int(ym[5:7]) - 1], ym[:4])


def money(x):
    return "{:,.2f}".format(float(x or 0))


def hrs(x):
    x = float(x or 0)
    h = int(x)
    m = int(round((x - h) * 60))
    if m == 60:
        h, m = h + 1, 0
    return "%d:%02d" % (h, m)


_CSS = """
<style>
body { font-family: 'Segoe UI', Tahoma, Arial; font-size: 11pt; }
table { border-collapse: collapse; }
td, th { border: 1px solid #777; padding: 4px 8px; }
th { background-color: #e6f4ea; }
.title { font-size: 18pt; color: #1b9e4b; font-weight: bold; }
.sec { background-color: #1b9e4b; color: white; font-weight: bold; }
.net { background-color: #fff3cd; font-size: 14pt; font-weight: bold; }
.small { color: #666; font-size: 9pt; }
</style>
"""


def _css(f=1.0):
    """نفس التنسيق لكن بكل المقاسات مضروبة في f (للتصغير التلقائي عند الطباعة)."""
    pt = lambda v: "%.2fpt" % (v * f)
    px = lambda v: "%dpx" % max(1, round(v * f))
    return ("<style>body { font-family: 'Segoe UI', Tahoma, Arial; font-size: %s; }"
            "table { border-collapse: collapse; }"
            "td, th { border: 1px solid #777; padding: %s %s; }"
            "th { background-color: #e6f4ea; }"
            ".title { font-size: %s; color: #1b9e4b; font-weight: bold; }"
            ".sec { background-color: #1b9e4b; color: white; font-weight: bold; }"
            ".net { background-color: #fff3cd; font-size: %s; font-weight: bold; }"
            ".small { color: #666; font-size: %s; }</style>"
            % (pt(11), px(4), px(8), pt(18), pt(14), pt(9)))


def _row(label, value, bold=False):
    v = "<b>%s</b>" % value if bold else value
    return "<tr><td width='60%%'>%s</td><td align='center'>%s</td></tr>" % (label, v)


def _gap(f=1.0):
    return "<p style='margin:0; font-size:%.1fpt'>&nbsp;</p>" % (6 * f)


def voucher_html(branch, ym, emp, s, pay, logo_name="logo", scale=1.0, show_logo=True):
    """scale: معامل تصغير/تكبير كل المقاسات. show_logo=False لتوفير مساحة."""
    f = scale
    e = lambda x: escape(str(x))
    pad = max(1, round(4 * f))
    earn = [("المرتب الأساسي", money(pay["salary"])), ("البدلات", money(pay["allowances"])),
            ("الوقت الإضافي (%s ساعة)" % hrs(pay["ot_hours"]), money(pay["ot_pay"]))]
    ded = [("خصم أيام الغياب (%d يوم)" % pay["absent"], money(pay["absence_ded"])),
           ("الجزاءات", money(pay["penalties"])), ("خصم التأمينات", money(pay["insurance"])),
           ("السلف", money(pay["advance"]))]
    if pay["fp_count"] or pay["fp_amount"]:
        lbl = "جزاء نسيان البصمة (%d بصمة منسية" % pay["fp_count"]
        lbl += " = %s يوم)" % ("%g" % pay["fp_days"]) if not pay["fp_edited"] else ") — معدّل يدوياً"
        ded.insert(2, (lbl, money(pay["fp_amount"])))
    if pay["leave_ded"]:
        ded.append(("خصم الإجازة بدون أجر (%d يوم)" % pay["leave"], money(pay["leave_ded"])))
    if pay["short_ded"]:
        ded.append(("خصم نقص ساعات العمل", money(pay["short_ded"])))
    tbl = "<table width='100%%' border='1' cellspacing='0' cellpadding='%d'>" % pad
    logo = ("<img src='%s' width='%d' height='%d'>" % (logo_name, round(90 * f), round(90 * f))) if show_logo else ""
    html = ["<html><head>", _css(f), "</head><body dir='rtl'>"]
    html.append("<table width='100%%' style='border:none'><tr>"
                "<td style='border:none' width='20%%'>%s</td>"
                "<td style='border:none' align='center'><span class='title'>%s</span><br>"
                "<span style='font-size:%.1fpt'><b>سند مرتب</b> — %s</span></td>"
                "<td style='border:none' width='20%%'></td></tr></table>%s" % (logo, e(APP_NAME), 14 * f, month_label(ym), _gap(f)))
    html.append(tbl + "<tr><th>الكود</th><td>%s</td><th>الاسم</th><td>%s</td><th>الفرع</th><td>%s</td></tr></table>%s"
                % (e(emp["code"]), e(emp["name"]), e(branch), _gap(f)))
    html.append(tbl + "<tr><td colspan='2' class='sec' align='center'>بيانات الحضور</td></tr>")
    html.append(_row("نظام الشيفت", s.shift_label or "—"))
    html.append(_row("أيام الحضور", s.present))
    html.append(_row("عدد بصمات الدخول", s.in_punches))
    html.append(_row("عدد بصمات الخروج", s.out_punches))
    html.append(_row("عدد البصمات الناقصة", s.missing_punches))
    html.append(_row("أيام الراحة الأسبوعية المستحقة", s.rest))
    html.append(_row("إجازة بإذن", pay["leave"]))
    html.append(_row("أيام الغياب", pay["absent"]))
    html.append(_row("إجمالي أيام الشهر", s.month_days))
    html.append(_row("إجمالي ساعات العمل", hrs(s.total_hours)))
    html.append(_row("متوسط ساعات العمل اليومي", hrs(s.avg_hours)))
    html.append("</table>" + _gap(f))
    html.append(tbl + "<tr><td colspan='2' class='sec' align='center'>المستحقات</td></tr>")
    html.extend(_row(a, b) for a, b in earn)
    html.append(_row("إجمالي المستحقات", money(pay["gross"]), True))
    html.append("<tr><td colspan='2' class='sec' align='center'>الاستقطاعات</td></tr>")
    html.extend(_row(a, b) for a, b in ded)
    html.append(_row("إجمالي الاستقطاعات", money(pay["total_ded"]), True))
    html.append("<tr><td class='net'>صافي المرتب</td><td align='center' class='net'>%s جنيه</td></tr></table>%s" % (money(pay["net"]), _gap(f)))
    html.append("<table width='100%' style='border:none'><tr>"
                "<td style='border:none' align='center'>توقيع المحاسب<br>.....................</td>"
                "<td style='border:none' align='center'>توقيع المدير<br>.....................</td>"
                "<td style='border:none' align='center'>توقيع المستلم<br>.....................</td></tr></table>")
    if (emp.get("notes") or "").strip():
        html.append(_gap(f) + tbl + "<tr><th width='15%%'>ملاحظات</th><td>%s</td></tr></table>" % e(emp["notes"]))
    html.append("<p class='small' align='center'>%s — %s</p></body></html>" % (e(APP_NAME), e(DEVELOPER)))
    return "".join(html)


def punches_html(branch, ym, emp, days, s, scale=1.0, show_logo=True, logo_name="logo"):
    """صفحة بصمات الموظف: جدول كل أيام الشهر بالدخول والخروج والشيفت وعلامات التحوّل والبصمات اليتيمة."""
    import calendar
    from datetime import date
    from .constants import DAY_NAMES_AR, SHIFT_LABELS
    f = scale
    e = lambda x: escape(str(x))
    pad = max(1, round(3 * f))
    y, m = int(ym[:4]), int(ym[5:7])
    nd = calendar.monthrange(y, m)[1]
    logo = ("<img src='%s' width='%d' height='%d'>" % (logo_name, round(60 * f), round(60 * f))) if show_logo else ""
    h = ["<html><head>", _css(f), "</head><body dir='rtl'>",
         "<table width='100%%' style='border:none'><tr><td style='border:none' width='12%%'>%s</td>"
         "<td style='border:none' align='center'><span class='title'>كشف البصمات</span><br>"
         "<b>%s</b> — كود %s — الفرع: %s — %s — الشيفت: %s</td></tr></table>%s"
         % (logo, e(emp["name"]), e(emp["code"]), e(branch), month_label(ym), e(s.shift_label or "—"), _gap(f)),
         "<table width='100%%' border='1' cellspacing='0' cellpadding='%d'>"
         "<tr><th>التاريخ</th><th>اليوم</th><th>الشيفت</th><th>الدخول</th><th>الخروج</th><th>الساعات</th><th>ملاحظات</th></tr>" % pad]
    orph_map = getattr(days, "orphans", {})
    for d in range(1, nd + 1):
        dt = date(y, m, d)
        rec = days.get(dt)
        orph = orph_map.get(dt)
        onote = ("بصمة خروج %s بدون دخول — اعتُبر راحة" % "، ".join(t.strftime("%H:%M") for t in orph)) if orph else ""
        if rec:
            tin = rec.in_dt.strftime("%H:%M" if rec.in_dt.date() == dt else "%H:%M (%d/%m)") if rec.in_dt else ""
            tout = rec.out_dt.strftime("%H:%M" if rec.out_dt.date() == dt else "%H:%M (%d/%m)") if rec.out_dt else ""
            note = " - ".join(x for x in (rec.note, onote) if x)
            bg = "#fff3cd" if not rec.complete else ("#d6eaf8" if rec.change else "")
            cells = [SHIFT_LABELS[rec.shift], tin, tout, hrs(rec.hours) if rec.complete else "", note]
        else:
            bg = "#ffe8cc" if onote else "#fdecea"
            cells = ["", "", "", "", onote or "لا توجد بصمة"]
        st = " style='background-color:%s'" % bg if bg else ""
        h.append("<tr%s><td align='center'>%02d/%02d/%d</td><td align='center'>%s</td>%s</tr>" % (
            st, d, m, y, DAY_NAMES_AR[dt.weekday()], "".join("<td align='center'>%s</td>" % e(c) for c in cells)))
    h.append("</table>" + _gap(f))
    h.append("<table width='100%%' border='1' cellspacing='0' cellpadding='%d'><tr>"
             "<th>أيام الحضور</th><td align='center'>%s</td><th>بصمات الدخول</th><td align='center'>%s</td>"
             "<th>بصمات الخروج</th><td align='center'>%s</td><th>بصمات ناقصة</th><td align='center'>%s</td>"
             "<th>إجمالي الساعات</th><td align='center'>%s</td></tr></table>"
             % (pad, s.present, s.in_punches, s.out_punches, s.missing_punches, hrs(s.total_hours)))
    h.append("<p class='small' align='center'>%s — %s</p></body></html>" % (e(APP_NAME), e(DEVELOPER)))
    return "".join(h)


def employees_table_html(branch, ym, items, scale=1.0, logo_name="logo"):
    """كشف الموظفين الظاهر في الشاشة الرئيسية (للطباعة)."""
    f = scale
    e = lambda x: escape(str(x))
    pad = max(1, round(3 * f))
    h = ["<html><head>", _css(f), "</head><body dir='rtl'>",
         "<p align='center'><span class='title'>%s</span><br><b>كشف الموظفين</b> — الفرع: %s — %s</p>"
         % (e(APP_NAME), e(branch), month_label(ym)),
         "<table width='100%%' border='1' cellspacing='0' cellpadding='%d'><tr>" % pad]
    cols = ["الكود", "الاسم", "الشيفت", "أيام الحضور", "بصمات الدخول", "بصمات الخروج", "ناقصة", "الراحة", "إجازة", "غياب",
            "إجمالي الساعات", "صافي المرتب"]
    h.append("".join("<th>%s</th>" % c for c in cols) + "</tr>")
    for emp, days, s, pay in items:
        vals = [emp["code"], emp["name"], s.shift_label, s.present, s.in_punches, s.out_punches, s.missing_punches,
                s.rest, pay["leave"], pay["absent"], hrs(s.total_hours), money(pay["net"])]
        bg = " style='background-color:#fff3cd'" if s.missing_punches else ""
        h.append("<tr%s>%s</tr>" % (bg, "".join("<td align='center'>%s</td>" % e(v) for v in vals)))
    h.append("</table><p class='small' align='center'>%s — %s</p></body></html>" % (e(APP_NAME), e(DEVELOPER)))
    return "".join(h)


def vouchers_html(branch, ym, items, logo_name="logo"):
    parts = []
    for i, (emp, days, s, pay) in enumerate(items):
        h = voucher_html(branch, ym, emp, s, pay, logo_name)
        body = h.split("<body dir='rtl'>", 1)[1].rsplit("</body>", 1)[0]
        style = " style='page-break-after:always'" if i < len(items) - 1 else ""
        parts.append("<div%s>%s</div>" % (style, body))
    return "<html><head>%s</head><body dir='rtl'>%s</body></html>" % (_CSS, "".join(parts))


SUMMARY_COLS = [("الكود", None), ("الاسم", None), ("الأساسي", "salary"), ("البدلات", "allowances"),
                ("الإضافي", "ot_pay"), ("خصم الغياب", "absence_ded"), ("الجزاءات", "penalties_total"),
                ("التأمينات", "insurance"), ("السلف", "advance"), ("الصافي", "net")]


def totals_of(items):
    keys = ["salary", "allowances", "ot_pay", "absence_ded", "leave_ded", "short_ded", "penalties", "fp_amount", "penalties_total",
            "insurance", "advance", "gross", "total_ded", "net"]
    t = {k: 0.0 for k in keys}
    for _, _, _, pay in items:
        for k in keys:
            t[k] += pay[k]
    t["net_before_advance"] = t["net"] + t["advance"]
    return {k: round(v, 2) for k, v in t.items()}


def summary_html(branch, ym, items, logo_name="logo"):
    t = totals_of(items)
    h = ["<html><head>", _CSS, "</head><body dir='rtl'>"]
    h.append("<table width='100%%' style='border:none'><tr><td style='border:none' width='15%%'><img src='%s' width='70' height='70'></td>"
             "<td style='border:none' align='center'><span class='title'>%s</span><br><b>كشف إجمالي المرتبات — %s — %s</b></td>"
             "<td style='border:none' width='15%%'></td></tr></table><br>" % (logo_name, escape(APP_NAME), escape(branch), month_label(ym)))
    h.append("<table width='100%' border='1' cellspacing='0' cellpadding='4'><tr>" + "".join("<th>%s</th>" % c for c, _ in SUMMARY_COLS) + "</tr>")
    for emp, _, _, pay in items:
        cells = ["<td align='center'>%s</td>" % escape(emp["code"]), "<td>%s</td>" % escape(emp["name"])]
        cells += ["<td align='center'>%s</td>" % money(pay[k]) for _, k in SUMMARY_COLS[2:]]
        h.append("<tr>" + "".join(cells) + "</tr>")
    tot = ["<td colspan='2' align='center'><b>الإجمالي</b></td>"]
    tot += ["<td align='center'><b>%s</b></td>" % money(t[k]) for _, k in SUMMARY_COLS[2:]]
    h.append("<tr style='background-color:#fff3cd'>" + "".join(tot) + "</tr></table><br>")
    h.append("<table width='60%' border='1' cellspacing='0' cellpadding='4'>")
    h.append(_row("إجمالي المرتبات قبل خصم السلف", money(t["net_before_advance"])))
    h.append(_row("إجمالي مبلغ السلف", money(t["advance"])))
    h.append("<tr><td class='net'>المبلغ المطلوب بعد خصم السلف</td><td align='center' class='net'>%s</td></tr>" % money(t["net"]))
    h.append(_row("إجمالي التأمينات", money(t["insurance"])))
    h.append(_row("إجمالي البدلات", money(t["allowances"])))
    h.append(_row("إجمالي الوقت الإضافي", money(t["ot_pay"])))
    h.append(_row("إجمالي الجزاءات", money(t["penalties_total"])))
    h.append(_row("إجمالي خصم الغياب والإجازات", money(t["absence_ded"] + t["leave_ded"] + t["short_ded"])))
    h.append("</table><p class='small' align='center'>%s</p></body></html>" % escape(DEVELOPER))
    return "".join(h)


def export_summary_xlsx(path, branch, ym, items):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    wb = Workbook()
    ws = wb.active
    ws.title = "المرتبات"
    ws.sheet_view.rightToLeft = True
    ws.append([APP_NAME, branch, month_label(ym)])
    ws["A1"].font = Font(bold=True, size=14)
    head = ["الكود", "الاسم", "أيام الحضور", "الراحة", "إجازة", "غياب", "ساعات العمل", "متوسط الساعات",
            "الأساسي", "البدلات", "الإضافي", "خصم الغياب", "الجزاءات", "التأمينات", "السلف", "الصافي"]
    ws.append(head)
    for c in ws[2]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1B9E4B")
        c.alignment = Alignment(horizontal="center")
    for emp, _, s, p in items:
        ws.append([emp["code"], emp["name"], s.present, s.rest, p["leave"], p["absent"],
                   round(s.total_hours, 2), round(s.avg_hours, 2), p["salary"], p["allowances"], p["ot_pay"],
                   p["absence_ded"] + p["leave_ded"] + p["short_ded"], p["penalties_total"], p["insurance"],
                   p["advance"], p["net"]])
    n = len(items) + 2
    ws.append(["", "الإجمالي"] + [""] * 6 + ["=SUM(%s3:%s%d)" % (c, c, n) for c in "IJKLMNOP"])
    for c in ws[n + 1]:
        c.font = Font(bold=True)
    t = totals_of(items)
    ws.append([])
    ws.append(["", "إجمالي المرتبات قبل خصم السلف", t["net_before_advance"]])
    ws.append(["", "إجمالي السلف", t["advance"]])
    ws.append(["", "المطلوب بعد خصم السلف", t["net"]])
    for col, w in zip("ABCDEFGHIJKLMNOP", [8, 28] + [12] * 14):
        ws.column_dimensions[col].width = w
    wb.save(path)
