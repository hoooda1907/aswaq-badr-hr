"""اختبار منطق ضمان الصفحة الواحدة بمحاكاة Qt (يُتخطى لو PySide متاح فعلاً)."""
import os, sys, types, unittest, importlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    import PySide6  # noqa
    HAVE_QT = True
except ImportError:
    try:
        import PySide2  # noqa
        HAVE_QT = True
    except ImportError:
        HAVE_QT = False


class Rect:
    def __init__(self, x=0, y=0, w=0, h=0): self.x, self.y, self._w, self._h = x, y, w, h
    def width(self): return self._w
    def height(self): return self._h


class Anything:
    def __init__(self, *a, **k): pass
    def __getattr__(self, n):
        if n.startswith("__"): raise AttributeError(n)
        return Anything()
    def __call__(self, *a, **k): return Anything()


class FakePrinter:
    HighResolution, DevicePixel, PdfFormat = 1, 2, 3
    def __init__(self, *a): self.pages, self.dpi = 1, 600
    def resolution(self): return self.dpi
    def pageRect(self, unit): return Rect(0, 0, 8.27 * self.dpi, 11.69 * self.dpi)   # A4 بالبكسل
    def newPage(self): self.pages += 1
    def setPageSize(self, *a): pass
    def setPageOrientation(self, *a): pass


class FakePainter:
    log = []
    def begin(self, p): FakePainter.log = []; return True
    def end(self): pass
    def save(self): pass
    def restore(self): pass
    def translate(self, x, y): FakePainter.log.append(("translate", x, y))
    def setClipRect(self, r): FakePainter.log.append(("clip", r.width(), r.height()))
    def setPen(self, p): pass
    def drawLine(self, *a): FakePainter.log.append(("line",) + a)


class FakeDoc:
    def __init__(self, html): self.k = float(html)
    def setDocumentMargin(self, m): pass
    def documentLayout(self): return Anything()
    def setTextWidth(self, w): self.w = w
    def size(self): return Rect(0, 0, self.w, self.k * 9000)      # الارتفاع يتناسب مع معامل التصغير
    def drawContents(self, painter, rect): FakePainter.log.append(("draw", self.k, rect.height()))


@unittest.skipIf(HAVE_QT, "PySide متاح: اختبار المنطق بالمحاكاة غير مطلوب")
class FitLogic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        mods = {}
        for name in ("QtCore", "QtGui", "QtWidgets", "QtPrintSupport"):
            m = types.ModuleType("PySide6." + name)
            m.__getattr__ = lambda n: type(n, (Anything,), {})
            mods[name] = m
        mods["QtCore"].QRectF = Rect
        mods["QtCore"].Qt = Anything()
        mods["QtPrintSupport"].QPrinter = FakePrinter
        mods["QtGui"].QPainter = FakePainter
        sys.modules["PySide6"] = types.ModuleType("PySide6")
        for n, m in mods.items():
            sys.modules["PySide6." + n] = m
        for k in [k for k in sys.modules if k.startswith("rmt_hr.ui")]:
            del sys.modules[k]
        cls.P = importlib.import_module("rmt_hr.ui.printing")
        cls.P.make_doc = FakeDoc

    @classmethod
    def tearDownClass(cls):
        for k in [k for k in sys.modules if k.startswith("PySide6") or k.startswith("rmt_hr.ui")]:
            del sys.modules[k]

    def _run(self, n, layout, scale=100, landscape=False):
        pr = FakePrinter()
        st = {"layout": layout, "margin": 6, "scale": scale, "logo": True}
        builders = [lambda f: "%f" % f for _ in range(n)]
        self.assertTrue(self.P.paint_pages(pr, builders, st, landscape))
        return pr, FakePainter.log

    def test_single_fits_one_page_each(self):
        pr, log = self._run(3, "single")
        self.assertEqual(pr.pages, 3)
        clip_h = [e[2] for e in log if e[0] == "clip"][0]
        for e in [e for e in log if e[0] == "draw"]:
            self.assertLessEqual(e[1] * 9000, clip_h + 1e-6)             # ارتفاع السند ≤ الصفحة
            self.assertLess(e[1], 1.0)                                    # اتصغّر فعلاً (كان أطول من الصفحة)

    def test_double_two_per_page_and_cut_line(self):
        pr, log = self._run(5, "double")
        self.assertEqual(pr.pages, 3)                                     # 5 سندات = 3 أوراق
        heights = {e[2] for e in log if e[0] == "clip"}
        self.assertEqual(len(heights), 1)
        slot_h = heights.pop()
        page_h = 11.69 * 600 - 2 * 6 * 600 / 25.4
        self.assertLess(slot_h, page_h / 2)                                # كل سند في أقل من نصف الورقة
        for e in [e for e in log if e[0] == "draw"]:
            self.assertLessEqual(e[1] * 9000, slot_h + 1e-6)
        self.assertEqual(len([e for e in log if e[0] == "line"]), 3)       # خط قص لكل ورقة

    def test_double_second_slot_is_below_first(self):
        pr, log = self._run(2, "double")
        ys = [e[2] for e in log if e[0] == "translate"]
        self.assertEqual(len(ys), 2)
        self.assertGreater(ys[1], ys[0])

    def test_small_content_is_not_enlarged(self):
        pr = FakePrinter()
        st = {"layout": "single", "margin": 6, "scale": 40, "logo": True}
        self.P.paint_pages(pr, [lambda f: "%f" % f], st)
        self.assertLessEqual([e[1] for e in FakePainter.log if e[0] == "draw"][0], 0.4 + 1e-9)

    def test_extreme_content_never_runs_forever_and_is_clipped(self):
        class Huge(FakeDoc):
            def size(self): return Rect(0, 0, self.w, 1e9)
        self.P.make_doc = Huge
        try:
            pr, log = self._run(1, "single")
        finally:
            self.P.make_doc = FakeDoc
        self.assertTrue(any(e[0] == "clip" for e in log))
        self.assertEqual(pr.pages, 1)


if __name__ == "__main__":
    unittest.main()
