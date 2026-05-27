import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, Pango, PangoCairo
import math
import cairo

_CSS_APPLIED = False


def _apply_css() -> None:
    global _CSS_APPLIED
    if _CSS_APPLIED:
        return
    css = b"""
    .grade-badge {
        border-radius: 999px;
        padding: 3px 11px;
        font-weight: bold;
        font-size: 0.85em;
        min-width: 34px;
    }
    .grade-badge-large {
        border-radius: 999px;
        padding: 5px 18px;
        font-weight: bold;
        font-size: 1.1em;
        min-width: 52px;
    }
    .grade-pass {
        background-color: alpha(@success_color, 0.18);
        color: @success_color;
        border: 1px solid alpha(@success_color, 0.45);
    }
    .grade-warn {
        background-color: alpha(@warning_color, 0.18);
        color: @warning_color;
        border: 1px solid alpha(@warning_color, 0.45);
    }
    .grade-fail {
        background-color: alpha(@error_color, 0.18);
        color: @error_color;
        border: 1px solid alpha(@error_color, 0.45);
    }
    .grade-neutral {
        background-color: alpha(@view_fg_color, 0.08);
        color: @view_fg_color;
        border: 1px solid alpha(@view_fg_color, 0.18);
    }
    .stat-card {
        border-radius: 14px;
        padding: 16px 20px;
        background-color: @card_bg_color;
        border: 1px solid alpha(@card_shade_color, 0.9);
    }
    .trend-up   { color: @success_color; font-weight: bold; font-size: 1.1em; }
    .trend-down { color: @error_color;   font-weight: bold; font-size: 1.1em; }
    .subject-title { font-weight: bold; }
    .login-hero-icon { color: @accent_color; }
    """
    provider = Gtk.CssProvider()
    provider.load_from_data(css)
    display = Gdk.Display.get_default()
    if display:
        Gtk.StyleContext.add_provider_for_display(
            display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
    _CSS_APPLIED = True


def _grade_css_class(value: float) -> str:
    if value <= 0:
        return "grade-neutral"
    if value >= 6.0:
        return "grade-pass"
    if value >= 5.0:
        return "grade-warn"
    return "grade-fail"


def _grade_rgb(value: float) -> tuple:
    if value <= 0:
        return (0.55, 0.55, 0.55)
    if value >= 6.0:
        return (0.30, 0.82, 0.52)
    if value >= 5.0:
        return (0.95, 0.75, 0.15)
    return (0.92, 0.30, 0.30)


# ---------------------------------------------------------------------------

class GradeBadge(Gtk.Label):
    """Pill-shaped label badge for individual grade rows."""
    def __init__(self, decimal_value: float, display_value: str = "", large: bool = False):
        super().__init__()
        _apply_css()
        label = display_value.strip() if display_value else (
            f"{decimal_value:.1f}" if decimal_value > 0 else "—"
        )
        self.set_label(label)
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.CENTER)
        self.add_css_class("grade-badge-large" if large else "grade-badge")
        self.add_css_class(_grade_css_class(decimal_value))


# ---------------------------------------------------------------------------

class GradeRing(Gtk.DrawingArea):
    """Circular arc-ring grade indicator for stat cards."""

    def __init__(self, value: float, size: int = 72):
        super().__init__()
        _apply_css()
        self._value = max(0.0, min(10.0, value))
        self.set_content_width(size)
        self.set_content_height(size)
        self.set_valign(Gtk.Align.CENTER)
        self.set_halign(Gtk.Align.CENTER)
        self.set_draw_func(self._draw)

    def _draw(self, _area, cr, width, height) -> None:
        r, g, b = _grade_rgb(self._value)
        cx, cy = width / 2, height / 2
        size = min(width, height)
        sw = max(4.5, size * 0.11)
        radius = size / 2 - sw / 2 - 2

        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_width(sw)

        # Dim background ring
        cr.set_source_rgba(r, g, b, 0.15)
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.stroke()

        # Filled progress arc
        if self._value > 0:
            start = -math.pi / 2
            end = start + (self._value / 10.0) * 2 * math.pi
            cr.set_source_rgba(r, g, b, 0.88)
            cr.arc(cx, cy, radius, start, end)
            cr.stroke()

        # Grade label in centre
        display = f"{self._value:.1f}" if self._value > 0 else "—"
        cr.set_source_rgba(r, g, b, 1.0)
        layout = PangoCairo.create_layout(cr)
        desc = Pango.FontDescription.new()
        desc.set_weight(Pango.Weight.BOLD)
        desc.set_size(int(size * 0.26 * Pango.SCALE))
        layout.set_font_description(desc)
        layout.set_text(display, -1)
        pw, ph = layout.get_pixel_size()
        cr.move_to(cx - pw / 2, cy - ph / 2)
        PangoCairo.show_layout(cr, layout)
