import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from collections import defaultdict
from rmt_hr.excel_reader import read_table, extract_punches
from rmt_hr.attendance import build_days, summarize, detect_mode
from rmt_hr.payroll import calculate

path = sys.argv[1] if len(sys.argv) > 1 else "in-out.xls"
rows = read_table(path)
punches, cols = extract_punches(rows)
print("rows", len(rows), "punches", len(punches), "cols", cols)
by = defaultdict(list)
names = {}
for c, n, d in punches:
    by[c].append(d); names[c] = n
for code in sorted(by, key=lambda x: int(x))[:30]:
    days = build_days(by[code])
    s = summarize(days, "2026-10", 10, 20)
    print(code, names[code][:14].ljust(14), detect_mode(by[code]), "present", s.present, "rest", s.rest,
          "rem", s.remaining, "hrs %.1f" % s.total_hours, "avg %.1f" % s.avg_hours, "ot %.1f" % s.ot_hours)
d = build_days(by["234"], "night")
for k in sorted(d): print(k, d[k].in_dt.strftime("%H:%M"), d[k].out_dt and d[k].out_dt.strftime("%d %H:%M"), d[k].note)
s = summarize(build_days(by["121"]), "2026-10", 10, 20)
print(calculate({"salary": 6200, "allowances": 300, "advance": 500, "insurance": 100, "leave_days": 1}, s))
