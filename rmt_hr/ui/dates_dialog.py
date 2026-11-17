from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView, QPushButton, QLabel,
                               QAbstractItemView)

from ..constants import DAY_NAMES_AR


class DatesListDialog(QDialog):
    """قائمة تواريخ بند معيّن (إجازة سنوية / بدون أجر / غياب ...) في شهر أو سنة."""

    def __init__(self, title, dates, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(420, 480)
        lay = QVBoxLayout(self)
        head = QLabel("<b>%s</b> — العدد: <b>%d</b> يوم" % (title, len(dates)))
        head.setAlignment(Qt.AlignCenter)
        lay.addWidget(head)
        tbl = QTableWidget(len(dates), 3)
        tbl.setHorizontalHeaderLabels(["#", "التاريخ", "اليوم"])
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        tbl.verticalHeader().setVisible(False)
        tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for i, d in enumerate(dates):
            for c, v in enumerate((str(i + 1), d.strftime("%d/%m/%Y"), DAY_NAMES_AR[d.weekday()])):
                it = QTableWidgetItem(v)
                it.setTextAlignment(Qt.AlignCenter)
                tbl.setItem(i, c, it)
        lay.addWidget(tbl, 1)
        b = QPushButton("إغلاق")
        b.setObjectName("secondary")
        b.clicked.connect(self.accept)
        lay.addWidget(b)
