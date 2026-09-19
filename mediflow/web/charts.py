"""Chart geometry for the web dashboard, computed server-side as plain SVG.

Why no chart library
--------------------
MediFlow runs in a clinic with no internet, so a CDN script tag is not an
option, and vendoring a charting bundle would add a megabyte of JavaScript to
maintain for one fourteen-point line. Inline SVG needs neither: the geometry is
arithmetic, the browser renders it, and ``<title>`` gives every mark a native
tooltip with no script at all.

Direction
---------
The plot is LTR — oldest day on the left — inside an RTL page. That is the
convention the codebase already follows for anything numeric: the desktop views
wrap figures and dates in LRM marks (``_ltr``) precisely so a mixed-direction
line does not reorder them. A mirrored time axis beside LTR numerals is the
combination that actually confuses people.
"""
from __future__ import annotations

from dataclasses import dataclass

from mediflow.services.dashboard_service import DayPoint

# A 4:1 plot area. Wider and the fourteen labels crowd; taller and a flat
# fortnight looks like a dramatic climb.
VIEW_WIDTH = 560
VIEW_HEIGHT = 140
PAD_X = 10
PAD_TOP = 14      # room for the peak's direct label
PAD_BOTTOM = 22   # room for the day ticks


@dataclass(slots=True)
class Mark:
    """One day, positioned. ``label`` is only set where a label is wanted."""

    x: float
    y: float
    value: int
    day: str
    label: str = ""


@dataclass(slots=True)
class TrendChart:
    marks: list[Mark]
    line: str          # polyline points
    area: str          # the same line closed to the baseline
    baseline: float
    peak: int
    total: int
    width: int = VIEW_WIDTH
    height: int = VIEW_HEIGHT

    @property
    def is_empty(self) -> bool:
        """Nothing happened in the window — the caller shows a sentence, not a flat line."""
        return self.total == 0


def build_trend(points: list[DayPoint]) -> TrendChart:
    """Lay out the appointment trend.

    The y-scale always starts at zero. Cropping the baseline to the data's own
    minimum is the single most effective way to make a chart lie, and on a
    clinic's daily volumes it would turn 11 vs 13 patients into a cliff.
    """
    if not points:
        return TrendChart(marks=[], line="", area="", baseline=0.0, peak=0, total=0)

    inner_width = VIEW_WIDTH - 2 * PAD_X
    baseline = VIEW_HEIGHT - PAD_BOTTOM
    plot_height = baseline - PAD_TOP
    peak = max(point.appointments for point in points)
    # A flat run of zeros still needs a divisor, and a peak of 1 should not
    # touch the ceiling, so the scale never drops below 1.
    scale = max(peak, 1)
    step = inner_width / (len(points) - 1) if len(points) > 1 else 0

    marks: list[Mark] = []
    for index, point in enumerate(points):
        x = PAD_X + index * step
        y = baseline - (point.appointments / scale) * plot_height
        marks.append(Mark(x=round(x, 1), y=round(y, 1),
                          value=point.appointments, day=point.day.isoformat()))

    # Selective direct labels only: the peak and the last day. A number on every
    # point is the most common way a fourteen-point line becomes unreadable.
    if peak:
        marks[max(range(len(marks)), key=lambda i: marks[i].value)].label = str(peak)
    marks[-1].label = str(marks[-1].value)

    line = " ".join(f"{mark.x},{mark.y}" for mark in marks)
    area = f"{marks[0].x},{baseline} {line} {marks[-1].x},{baseline}"
    return TrendChart(
        marks=marks, line=line, area=area, baseline=baseline,
        peak=peak, total=sum(point.appointments for point in points),
    )
