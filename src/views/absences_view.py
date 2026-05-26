import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib
import threading
import cairo
import math
from datetime import datetime, date
from collections import defaultdict

# ── Event code classification ──────────────────────────────────────────────
# Real codes returned by the API: "ABA0" (assenza), "ABR0" (ritardo),
# "ABU0" (uscita anticipata).  Older versions used "A", "R", "Rb", "U".
# We normalise to: "absence" | "delay" | "early" | "other"

def _classify(code: str) -> str:
    c = (code or "").strip().upper()
    # New-style codes (ABAx, ABRx, ABUx)
    if c.startswith("ABA"):
        return "absence"
    if c.startswith("ABR"):
        return "delay"
    if c.startswith("ABU"):
        return "early"
    # Old-style single-letter codes
    if c in ("A", "AB", "ASS"):
        return "absence"
    if c in ("R", "RB", "ITR", "RTAR"):
        return "delay"
    if c in ("U", "USO", "US", "UANT"):
        return "early"
    return "other"


_KIND_META = {
    "absence": ("Assenza",           "action-unavailable-symbolic"),
    "delay":   ("Ritardo",           "alarm-symbolic"),
    "early":   ("Uscita anticipata", "go-previous-symbolic"),
    "other":   ("Evento",            "help-browser-symbolic"),
}

_KIND_LABEL = {
    "absence": ("Assenza",           "ore di assenza"),
    "delay":   ("Ritardo",           "ora"),
    "early":   ("Uscita anticipata", "ora"),
    "other":   ("Evento",            ""),
}

_MONTHS_IT = [
    "", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]


def _parse_date(s: str) -> str:
    try:
        p = s[:10].split("-")
        return f"{p[2]}/{p[1]}/{p[0]}"
    except Exception:
        return s


def _evt_date(ev: dict) -> date:
    try:
        return date.fromisoformat(ev.get("evtDate", "")[:10])
    except Exception:
        return date.min


# ── Small stat card (Cairo ring) ──────────────────────────────────────────

def _make_abs_stat_card(label: str, count: int, rgb: tuple) -> Gtk.Box:
    r, g, b = rgb
    card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    card.add_css_class("stat-card")
    card.set_hexpand(True)

    # Coloured circle with number
    da = Gtk.DrawingArea()
    da.set_content_width(52)
    da.set_content_height(52)
    da.set_valign(Gtk.Align.CENTER)

    def draw(area, cr, w, h, _):
        cx, cy = w / 2, h / 2
        rad = min(w, h) / 2 - 3
        cr.set_source_rgba(r, g, b, 0.18)
        cr.arc(cx, cy, rad, 0, 2 * math.pi)
        cr.fill()
        cr.set_source_rgba(r, g, b, 1.0)
        cr.arc(cx, cy, rad, 0, 2 * math.pi)
        cr.set_line_width(2.5)
        cr.stroke()

        from gi.repository import Pango, PangoCairo
        layout = PangoCairo.create_layout(cr)
        desc = Pango.FontDescription.new()
        desc.set_weight(Pango.Weight.BOLD)
        desc.set_size(int(w * 0.32 * Pango.SCALE))
        layout.set_font_description(desc)
        layout.set_text(str(count), -1)
        pw, ph = layout.get_pixel_size()
        cr.set_source_rgba(r, g, b, 1.0)
        cr.move_to(cx - pw / 2, cy - ph / 2)
        PangoCairo.show_layout(cr, layout)

    da.set_draw_func(draw, None)
    card.append(da)

    lbl = Gtk.Label(label=label)
    lbl.add_css_class("heading")
    lbl.set_halign(Gtk.Align.START)
    lbl.set_valign(Gtk.Align.CENTER)
    lbl.set_wrap(True)
    card.append(lbl)
    return card


# ── Main view ──────────────────────────────────────────────────────────────

class AbsencesView(Adw.Bin):
    def __init__(self, client):
        super().__init__()
        self._client = client
        self._loaded = False
        self._all_events: list = []
        self._periods: list = []
        self._selected_period: int | None = None
        self._selected_date: date | None = None
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        toolbar = Adw.ToolbarView()

        # Period filter bar
        self._filter_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self._filter_box.set_halign(Gtk.Align.CENTER)
        self._filter_box.set_margin_top(8)
        self._filter_box.set_margin_bottom(4)
        self._filter_box.add_css_class("linked")
        self._filter_box.set_visible(False)
        toolbar.add_top_bar(self._filter_box)

        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)

        # Loading
        loading_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        loading_box.set_valign(Gtk.Align.CENTER)
        loading_box.set_halign(Gtk.Align.CENTER)
        loading_box.set_vexpand(True)
        sp = Gtk.Spinner()
        sp.set_size_request(48, 48)
        sp.start()
        lbl = Gtk.Label(label="Caricamento assenze…")
        lbl.add_css_class("dim-label")
        loading_box.append(sp)
        loading_box.append(lbl)
        self._stack.add_named(loading_box, "loading")

        self._error_page = Adw.StatusPage()
        self._error_page.set_icon_name("network-error-symbolic")
        self._error_page.set_title("Errore di rete")
        retry = Gtk.Button(label="Riprova")
        retry.add_css_class("pill")
        retry.add_css_class("suggested-action")
        retry.set_halign(Gtk.Align.CENTER)
        retry.connect("clicked", lambda _: self.refresh())
        self._error_page.set_child(retry)
        self._stack.add_named(self._error_page, "error")

        empty = Adw.StatusPage()
        empty.set_icon_name("emblem-ok-symbolic")
        empty.set_title("Nessuna assenza")
        empty.set_description("Non risultano assenze registrate.")
        self._stack.add_named(empty, "empty")

        # Content: scroll with calendar + list
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        clamp = Adw.Clamp()
        clamp.set_maximum_size(760)
        clamp.set_margin_top(12)
        clamp.set_margin_bottom(12)
        clamp.set_margin_start(16)
        clamp.set_margin_end(16)
        self._abs_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        clamp.set_child(self._abs_box)
        scroll.set_child(clamp)
        self._stack.add_named(scroll, "content")

        self._stack.set_visible_child_name("loading")
        toolbar.set_content(self._stack)
        self.set_child(toolbar)

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        self._stack.set_visible_child_name("loading")
        self._selected_period = None
        self._selected_date = None
        self._load()

    def _load(self) -> None:
        results = {}
        errors  = []
        lock    = threading.Lock()
        remaining = [2]

        def done():
            with lock:
                remaining[0] -= 1
                if remaining[0] > 0:
                    return
            if errors:
                GLib.idle_add(self._show_error, errors[0])
            else:
                GLib.idle_add(self._on_loaded, results)

        def load_absences():
            try:
                results["events"] = self._client.get_absences()
            except Exception as e:
                with lock:
                    errors.append(str(e))
            done()

        def load_periods():
            try:
                results["periods"] = self._client.get_periods()
            except Exception:
                results["periods"] = []
            done()

        threading.Thread(target=load_absences, daemon=True).start()
        threading.Thread(target=load_periods, daemon=True).start()

    def _on_loaded(self, results: dict) -> bool:
        self._all_events = results.get("events", [])
        self._periods    = results.get("periods", [])
        self._build_filter_buttons()
        self._render()
        return False

    # ------------------------------------------------------------------
    def _build_filter_buttons(self) -> None:
        child = self._filter_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._filter_box.remove(child)
            child = nxt

        if not self._periods:
            self._filter_box.set_visible(False)
            return

        group_btn = None
        btn_all = Gtk.ToggleButton(label="Tutto l'anno")
        btn_all.set_active(self._selected_period is None)
        btn_all.connect("toggled", self._on_filter_toggled, None)
        self._filter_box.append(btn_all)
        group_btn = btn_all

        for p in sorted(self._periods, key=lambda x: x.get("periodPos", 0)):
            label = (p.get("periodDesc") or p.get("periodLabel") or
                     f"Periodo {p.get('periodPos','')}").title()
            pos = p.get("periodPos")
            btn = Gtk.ToggleButton(label=label)
            btn.set_group(group_btn)
            btn.set_active(self._selected_period == pos)
            btn.connect("toggled", self._on_filter_toggled, pos)
            self._filter_box.append(btn)

        self._filter_box.set_visible(len(self._periods) > 0)

    def _on_filter_toggled(self, btn: Gtk.ToggleButton, period_pos) -> None:
        if not btn.get_active():
            return
        self._selected_period = period_pos
        self._selected_date   = None
        self._render()

    def _events_for_period(self) -> list:
        if self._selected_period is None or not self._periods:
            return self._all_events
        period = next(
            (p for p in self._periods if p.get("periodPos") == self._selected_period), None
        )
        if not period:
            return self._all_events
        try:
            d_start = date.fromisoformat(period.get("dateStart", "")[:10])
            d_end   = date.fromisoformat(period.get("dateEnd",   "")[:10])
        except Exception:
            return self._all_events
        return [ev for ev in self._all_events if d_start <= _evt_date(ev) <= d_end]

    # ------------------------------------------------------------------
    def _render(self) -> None:
        events = self._events_for_period()

        child = self._abs_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._abs_box.remove(child)
            child = nxt

        if not events:
            self._stack.set_visible_child_name("empty")
            return

        # Classify all events
        classified = [(ev, _classify(ev.get("evtCode", ""))) for ev in events]

        n_abs   = sum(1 for _, k in classified if k == "absence")
        n_delay = sum(1 for _, k in classified if k == "delay")
        n_early = sum(1 for _, k in classified if k == "early")

        # ── Stats banner ─────────────────────────────────────────────
        stats_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        stats_box.append(_make_abs_stat_card("Assenze",           n_abs,   (0.92, 0.28, 0.28)))
        stats_box.append(_make_abs_stat_card("Ritardi",           n_delay, (0.95, 0.75, 0.15)))
        stats_box.append(_make_abs_stat_card("Uscite anticipate", n_early, (0.40, 0.68, 1.00)))
        self._abs_box.append(stats_box)

        # ── Calendar ─────────────────────────────────────────────────
        cal_group = Adw.PreferencesGroup()
        cal_group.set_title("Calendario")

        # Reset-day-filter button
        reset_row = Adw.ActionRow()
        reset_row.set_title("Mostra tutti i giorni")
        reset_btn = Gtk.Button.new_from_icon_name("edit-clear-symbolic")
        reset_btn.add_css_class("flat")
        reset_btn.set_valign(Gtk.Align.CENTER)
        reset_btn.set_tooltip_text("Deseleziona giorno")
        reset_btn.connect("clicked", lambda _: self._on_day_reset())
        reset_row.add_suffix(reset_btn)

        cal = Gtk.Calendar()
        cal.set_margin_top(4)
        cal.set_margin_bottom(4)
        cal.set_halign(Gtk.Align.CENTER)

        # Mark event days in the currently displayed month
        event_dates: set[date] = {_evt_date(ev) for ev in events}
        self._event_dates = event_dates
        self._calendar = cal

        today = date.today()
        for d in event_dates:
            if d.year == today.year and d.month == today.month:
                cal.mark_day(d.day)

        cal.connect("day-selected", self._on_day_selected)
        cal.connect("next-month", lambda c: self._refresh_calendar_marks(c))
        cal.connect("prev-month", lambda c: self._refresh_calendar_marks(c))
        cal.connect("next-year",  lambda c: self._refresh_calendar_marks(c))
        cal.connect("prev-year",  lambda c: self._refresh_calendar_marks(c))

        cal_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        cal_box.append(reset_row)
        cal_box.append(cal)
        cal_group.set_header_suffix(Gtk.Box())  # spacer

        self._abs_box.append(cal)

        # ── Events list (filtered by selected day or all) ─────────────
        self._events_group_title_lbl = None
        self._events_group = Adw.PreferencesGroup()
        self._abs_box.append(self._events_group)
        self._fill_events_list(classified)

        self._stack.set_visible_child_name("content")

    def _refresh_calendar_marks(self, cal: Gtk.Calendar) -> None:
        dt = cal.get_date()
        y  = dt.get_year()
        m  = dt.get_month()
        cal.clear_marks()
        for d in self._event_dates:
            if d.year == y and d.month == m:
                cal.mark_day(d.day)

    def _on_day_selected(self, cal: Gtk.Calendar) -> None:
        dt = cal.get_date()
        self._selected_date = date(dt.get_year(), dt.get_month(), dt.get_day())
        events = self._events_for_period()
        classified = [(ev, _classify(ev.get("evtCode", ""))) for ev in events]
        self._fill_events_list(classified)

    def _on_day_reset(self) -> None:
        self._selected_date = None
        events = self._events_for_period()
        classified = [(ev, _classify(ev.get("evtCode", ""))) for ev in events]
        self._fill_events_list(classified)

    def _fill_events_list(self, classified: list) -> None:
        # Remove existing rows from the group
        child = self._events_group.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            # Only remove ActionRow/ExpanderRow children, not the header
            try:
                self._events_group.remove(child)
            except Exception:
                pass
            child = nxt

        if self._selected_date:
            filtered = [(ev, k) for ev, k in classified
                        if _evt_date(ev) == self._selected_date]
            day_str = self._selected_date.strftime("%d/%m/%Y")
            title = f"Evento del {day_str} ({len(filtered)})"
        else:
            filtered = classified
            title = f"Tutti gli eventi ({len(filtered)})"

        self._events_group.set_title(title)

        for ev, kind in sorted(filtered, key=lambda x: x[0].get("evtDate", ""), reverse=True):
            label, icon = _KIND_META[kind]
            date_str  = _parse_date(ev.get("evtDate", ""))
            justified = ev.get("isJustified", False)
            reason    = (ev.get("justifReasonDesc") or "").strip()
            hours     = ev.get("evtHPos")  # hour position (some versions)

            parts = [date_str]
            if hours:
                parts.append(f"Ora {hours}")
            if justified:
                parts.append("✓ Giustificata")
                if reason:
                    parts.append(reason)
            else:
                parts.append("Non giustificata")

            row = Adw.ActionRow()
            row.set_title(label)
            row.set_subtitle("  ·  ".join(parts))
            row.add_prefix(Gtk.Image.new_from_icon_name(icon))
            if not justified:
                dot = Gtk.Label(label="●")
                dot.add_css_class("error")
                row.add_suffix(dot)
            self._events_group.add(row)

    def _show_error(self, msg: str) -> bool:
        self._error_page.set_description(msg)
        self._stack.set_visible_child_name("error")
        return False
