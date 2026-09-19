"""Dashboard: what needs attention today, then what happened today.

Alerts lead. A counter reports; an alert asks for an action. Expiring stock,
supplies below their reorder level, lab requests nobody has resulted and
invoices nobody has collected were all already in the database and reachable
only by opening each module and looking. Putting them at the top is the whole
difference between a dashboard and a report.

The trend is painted with QPainter rather than QtCharts. QtCharts would add a
Qt module — and its QML dependencies — to a bundle the spec deliberately keeps
lean, for one fourteen-point line. Two dozen lines of painting cost less and
take their colours straight from the live theme, so the chart follows a theme
switch without a second palette to maintain.
"""
from __future__ import annotations

from typing import ClassVar

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from mediflow.services.dashboard_service import DashboardService, DayPoint
from mediflow.ui import icons, theme
from mediflow.ui.views.base_view import BaseView


def _ltr(text: str) -> str:
    """Wrap a figure in LRM marks so RTL layout cannot reorder it."""
    return f"‎{text}‎" if text else text


class _StatCard(QFrame):
    def __init__(self, icon: str):
        super().__init__(objectName="StatCard")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        self.icon_label = QLabel(objectName="StatIcon")
        self.icon_label.setPixmap(icons.pixmap(icon, 22, "#ffffff"))
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon_label)

        text_box = QVBoxLayout()
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.setSpacing(2)
        self.value_label = QLabel("0", objectName="StatValue")
        self.caption_label = QLabel("", objectName="StatCaption")
        text_box.addWidget(self.value_label)
        text_box.addWidget(self.caption_label)
        layout.addLayout(text_box)
        layout.addStretch(1)

    def set_value(self, value: int) -> None:
        self.value_label.setText(_ltr(str(value)))

    def set_caption(self, caption: str) -> None:
        self.caption_label.setText(caption)


class _AlertCard(QFrame):
    """One thing that is wrong, with its count, its name and what it means.

    The count is never the only signal: the name is always beside it, so the
    card reads the same to someone who cannot distinguish amber from red.
    """

    def __init__(self, level: str):
        super().__init__(objectName="AlertCard")
        self.setProperty("level", level)      # "danger" or "warn", styled in QSS
        self.apply_direction()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        self.count_label = QLabel("0", objectName="AlertCount")
        self.count_label.setMinimumWidth(38)
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.count_label)

        text_box = QVBoxLayout()
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.setSpacing(1)
        self.title_label = QLabel("", objectName="AlertTitle")
        self.meta_label = QLabel("", objectName="AlertMeta")
        text_box.addWidget(self.title_label)
        text_box.addWidget(self.meta_label)
        layout.addLayout(text_box)
        layout.addStretch(1)

    def set_count(self, value: int) -> None:
        self.count_label.setText(_ltr(str(value)))

    def set_text(self, title: str, meta: str) -> None:
        self.title_label.setText(title)
        self.meta_label.setText(meta)

    def apply_direction(self) -> None:
        """Put the coloured bar on the leading edge of the current direction.

        Called again on every language switch, because switching to Dari flips
        the application to RTL and a bar pinned to the physical left would end
        up trailing the text it belongs to.
        """
        rtl = QApplication.layoutDirection() == Qt.LayoutDirection.RightToLeft
        self.setProperty("side", "right" if rtl else "left")
        # A dynamic property already used by a selector needs an explicit
        # repolish; Qt does not re-evaluate the stylesheet on its own.
        self.style().unpolish(self)
        self.style().polish(self)


class _TrendChart(QWidget):
    """A fourteen-day appointment line, painted from the live theme.

    Left-to-right, oldest first, inside an RTL window — the same choice the
    rest of the app makes for figures and dates, which it wraps in LRM marks
    rather than letting the layout reorder them.
    """

    _PAD_X = 10
    _PAD_TOP = 18      # room for the peak's label
    _PAD_BOTTOM = 20   # room for the end ticks

    def __init__(self) -> None:
        super().__init__()
        self._points: list[DayPoint] = []
        self._empty_text = ""
        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_points(self, points: list[DayPoint], empty_text: str) -> None:
        self._points = points
        self._empty_text = empty_text
        self.update()

    def _clamped(self, centre: float, width: int) -> int:
        """Left edge of a text box centred on ``centre``, kept inside the widget.

        The first and last marks sit against the padding, so a box centred on
        them overhangs the edge and Qt clips the glyph rather than moving it.
        """
        return int(max(0, min(centre - width / 2, self.width() - width)))

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt's own name
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = theme.CURRENT
        muted = QColor(palette["text_muted"])

        baseline = self.height() - self._PAD_BOTTOM
        if not self._points or not any(p.appointments for p in self._points):
            painter.setPen(muted)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._empty_text)
            return

        # The y-scale starts at zero. Cropping it to the data's own minimum is
        # the quickest way to make a chart lie, and on a clinic's daily volumes
        # it turns eleven patients against thirteen into a cliff.
        peak = max(p.appointments for p in self._points)
        scale = max(peak, 1)
        inner = self.width() - 2 * self._PAD_X
        span = baseline - self._PAD_TOP
        step = inner / (len(self._points) - 1) if len(self._points) > 1 else 0

        marks = [
            QPointF(self._PAD_X + index * step,
                    baseline - (point.appointments / scale) * span)
            for index, point in enumerate(self._points)
        ]

        primary = QColor(palette["primary"])
        # Recessive baseline: it orients the eye, it is not part of the data.
        painter.setPen(QPen(QColor(palette["border"]), 1))
        painter.drawLine(0, baseline, self.width(), baseline)

        fill = QPainterPath(QPointF(marks[0].x(), baseline))
        for mark in marks:
            fill.lineTo(mark)
        fill.lineTo(marks[-1].x(), baseline)
        fill.closeSubpath()
        translucent = QColor(primary)
        translucent.setAlpha(30)
        painter.fillPath(fill, translucent)

        line = QPainterPath(marks[0])
        for mark in marks[1:]:
            line.lineTo(mark)
        painter.setPen(QPen(primary, 2, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawPath(line)

        # A 2px surface ring keeps a dot readable where the line runs under it.
        painter.setPen(QPen(QColor(palette["surface"]), 2))
        painter.setBrush(primary)
        for mark in marks:
            painter.drawEllipse(mark, 3.5, 3.5)

        # Selective labels only — the peak and the last day. A number on every
        # point is how a fourteen-point line becomes unreadable.
        label_font = QFont(self.font())
        label_font.setBold(True)
        label_font.setPointSize(max(8, label_font.pointSize() - 1))
        painter.setFont(label_font)
        painter.setPen(QColor(palette["text"]))   # values wear text tokens
        peak_index = max(range(len(self._points)),
                         key=lambda i: self._points[i].appointments)
        for index in {peak_index, len(self._points) - 1}:
            mark = marks[index]
            painter.drawText(
                self._clamped(mark.x(), 36), int(mark.y() - 20), 36, 16,
                Qt.AlignmentFlag.AlignCenter,
                _ltr(str(self._points[index].appointments)),
            )

        tick_font = QFont(self.font())
        tick_font.setPointSize(max(7, tick_font.pointSize() - 2))
        painter.setFont(tick_font)
        painter.setPen(muted)
        for index in (0, len(self._points) - 1):
            mark = marks[index]
            painter.drawText(
                self._clamped(mark.x(), 52), baseline + 3, 52, 16,
                Qt.AlignmentFlag.AlignCenter,
                _ltr(self._points[index].day.isoformat()[5:]),
            )


class DashboardView(BaseView):
    required_permission = "dashboard.view"

    # (stats attribute, caption source string, icon name)
    _SPECS: ClassVar[list[tuple[str, str, str]]] = [
        ("total_patients", "Total patients", "patients"),
        ("patients_today", "Registered today", "user-plus"),
        ("appointments_today", "Appointments today", "appointments"),
        ("waiting_now", "Waiting now", "clock"),
        ("completed_today", "Completed today", "check-circle"),
        ("revenue_today", "Collected today", "billing"),
    ]

    # (stats attribute, severity, title source, meaning source)
    _ALERTS: ClassVar[list[tuple[str, str, str, str]]] = [
        ("out_of_stock_medications", "danger", "Out of stock",
         "No quantity left to dispense"),
        ("expiring_batches", "warn", "Expiring batches",
         "Expires within 90 days"),
        ("low_stock_items", "warn", "Low supplies",
         "At or below the reorder level"),
        ("open_lab_requests", "warn", "Lab results pending",
         "Requested but not yet resulted"),
        ("unpaid_invoices", "warn", "Open invoices",
         "Still owing payment"),
    ]

    def build_ui(self) -> None:
        self._service = DashboardService(self.container.database)

        header = QVBoxLayout()
        header.setSpacing(2)
        self._title = QLabel(objectName="PageTitle")
        self._subtitle = QLabel(objectName="Subtitle")
        header.addWidget(self._title)
        header.addWidget(self._subtitle)
        self._root.addLayout(header)
        self._root.addSpacing(6)

        # Alerts above the counters: the page answers "what needs me?" before
        # "what happened?".
        self._alerts_title = QLabel(objectName="SectionTitle")
        self._root.addWidget(self._alerts_title)
        self._alert_grid = QGridLayout()
        self._alert_grid.setSpacing(12)
        self._alert_cards: dict[str, _AlertCard] = {}
        for index, (key, level, _title, _meta) in enumerate(self._ALERTS):
            card = _AlertCard(level)
            self._alert_cards[key] = card
            self._alert_grid.addWidget(card, index // 3, index % 3)
        self._root.addLayout(self._alert_grid)

        self._all_clear = QLabel(objectName="Subtitle")
        self._root.addWidget(self._all_clear)
        self._root.addSpacing(10)

        grid = QGridLayout()
        grid.setSpacing(16)
        self._cards: dict[str, _StatCard] = {}
        for index, (key, _caption, icon) in enumerate(self._SPECS):
            card = _StatCard(icon)
            self._cards[key] = card
            grid.addWidget(card, index // 3, index % 3)
        self._root.addLayout(grid)
        self._root.addSpacing(10)

        self._trend_title = QLabel(objectName="SectionTitle")
        self._root.addWidget(self._trend_title)
        self._chart = _TrendChart()
        self._root.addWidget(self._chart)
        self._root.addStretch(1)

    def on_activated(self) -> None:
        stats = self._service.snapshot()
        for key, card in self._cards.items():
            value = getattr(stats, key)
            card.set_value(f"{value:,.0f}" if isinstance(value, float) else value)

        for key, card in self._alert_cards.items():
            count = getattr(stats, key)
            card.set_count(count)
            # A zero is not an alert. Hiding the card keeps the row honest:
            # five permanent zeroes teach people to stop reading it.
            card.setVisible(bool(count))
        self._all_clear.setVisible(not stats.alert_total)
        self._chart.set_points(stats.trend, self.tr("No appointments in the last 14 days"))
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        if not hasattr(self, "_title"):
            return
        self._title.setText(self.tr("Dashboard"))
        self._subtitle.setText(self.tr("Today at a glance"))
        self._alerts_title.setText(self.tr("Needs attention"))
        self._all_clear.setText(self.tr("Nothing needs attention."))
        self._trend_title.setText(self.tr("Appointments, last 14 days"))
        for key, caption, _icon in self._SPECS:
            self._cards[key].set_caption(self.tr(caption))
        for key, _level, title, meta in self._ALERTS:
            card = self._alert_cards[key]
            card.set_text(self.tr(title), self.tr(meta))
            card.apply_direction()
