import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib
import threading
import cairo
import math
from datetime import datetime, timedelta, date

_MONTHS_IT = [
    "", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]
_DAYS_IT = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]

_EVT_META = {
    "AGNT": ("Nota",     "dialog-information-symbolic",  False),
    "AGHW": ("Compito",  "document-edit-symbolic",       False),
    "AGVC": ("Verifica", "dialog-warning-symbolic",      True),
    "AGVS": ("Verifica", "dialog-warning-symbolic",      True),
}
_DEFAULT_META = ("Evento", "x-office-calendar-symbolic", False)

# Palette for subject colour bars
_PALETTE = [
    (0.40, 0.68, 1.00),
    (0.30, 0.82, 0.52),
    (1.00, 0.60, 0.20),
    (0.82, 0.42, 0.90),
    (0.95, 0.35, 0.35),
    (0.25, 0.85, 0.85),
    (1.00, 0.85, 0.20),
    (0.55, 0.85, 0.40),
    (1.00, 0.55, 0.75),
    (0.50, 0.65, 0.95),
]


def _subject_rgb(subject: str) -> tuple:
    return _PALETTE[hash(subject.lower()) % len(_PALETTE)]


def _fmt_date(dt: datetime) -> str:
    return f"{_DAYS_IT[dt.weekday()].capitalize()} {dt.day} {_MONTHS_IT[dt.month]}"


def _fmt_date_short(dt: datetime) -> str:
    return f"{dt.day} {_MONTHS_IT[dt.month]}"


def _parse_dt(s: str) -> datetime:
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:19], fmt)
        except ValueError:
            continue
    return datetime.min


# ---------------------------------------------------------------------------
# Small coloured bar drawn via Cairo
# ---------------------------------------------------------------------------

class _SubjectBar(Gtk.DrawingArea):
    def __init__(self, rgb: tuple):
        super().__init__()
        self._rgb = rgb
        self.set_content_width(5)
        self.set_content_height(40)
        self.set_valign(Gtk.Align.FILL)

    def do_draw_func(self, area, cr, w, h):
        r, g, b = self._rgb
        cr.set_source_rgba(r, g, b, 0.90)
        cr.rectangle(0, 4, w, h - 8)
        cr.fill()

    def set_draw_func(self, func, *args):
        super().set_draw_func(func, *args)


# Use a closure-based draw func since we can't subclass DrawingArea's draw_func easily
def _make_subject_bar(rgb: tuple) -> Gtk.DrawingArea:
    bar = Gtk.DrawingArea()
    bar.set_content_width(5)
    bar.set_content_height(36)
    bar.set_valign(Gtk.Align.CENTER)

    def draw(area, cr, w, h, _):
        r, g, b = rgb
        cr.set_source_rgba(r, g, b, 0.88)
        radius = min(w, h) / 2
        cr.arc(w / 2, h / 2, radius, 0, 2 * math.pi)
        cr.fill()

    bar.set_draw_func(draw, None)
    return bar


# ---------------------------------------------------------------------------

class AgendaView(Adw.Bin):
    def __init__(self, client):
        super().__init__()
        self._client = client
        self._loaded = False
        self._all_items: list = []
        self._current_date: date = date.today()
        self._view_mode: str = "future"  # "day" or "future"
        self._build_ui()

    def _build_ui(self) -> None:
        toolbar = Adw.ToolbarView()

        # ── Date navigation bar ───────────────────────────────────────
        nav_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        nav_box.set_halign(Gtk.Align.CENTER)
        nav_box.set_margin_top(6)
        nav_box.set_margin_bottom(6)

        self._prev_btn = Gtk.Button.new_from_icon_name("go-previous-symbolic")
        self._prev_btn.add_css_class("flat")
        self._prev_btn.connect("clicked", lambda _: self._shift_day(-1))

        self._date_lbl = Gtk.Label()
        self._date_lbl.add_css_class("heading")
        self._date_lbl.set_width_chars(26)
        self._date_lbl.set_xalign(0.5)

        self._next_btn = Gtk.Button.new_from_icon_name("go-next-symbolic")
        self._next_btn.add_css_class("flat")
        self._next_btn.connect("clicked", lambda _: self._shift_day(1))

        today_btn = Gtk.Button(label="Oggi")
        today_btn.add_css_class("pill")
        today_btn.connect("clicked", lambda _: self._go_today())

        future_btn = Gtk.Button(label="Prossimi 30 giorni")
        future_btn.add_css_class("pill")
        future_btn.connect("clicked", lambda _: self._go_future())

        nav_box.append(self._prev_btn)
        nav_box.append(self._date_lbl)
        nav_box.append(self._next_btn)
        nav_box.append(today_btn)
        nav_box.append(future_btn)

        toolbar.add_top_bar(nav_box)

        # ── Stack ─────────────────────────────────────────────────────
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)

        loading_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        loading_box.set_valign(Gtk.Align.CENTER)
        loading_box.set_halign(Gtk.Align.CENTER)
        loading_box.set_vexpand(True)
        sp = Gtk.Spinner()
        sp.set_size_request(48, 48)
        sp.start()
        lbl = Gtk.Label(label="Caricamento agenda…")
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

        empty_page = Adw.StatusPage()
        empty_page.set_icon_name("emblem-ok-symbolic")
        empty_page.set_title("Nessun evento")
        empty_page.set_description("Non ci sono eventi per questo periodo.")
        self._stack.add_named(empty_page, "empty")

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        clamp = Adw.Clamp()
        clamp.set_maximum_size(760)
        clamp.set_margin_top(12)
        clamp.set_margin_bottom(12)
        clamp.set_margin_start(16)
        clamp.set_margin_end(16)
        self._agenda_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        clamp.set_child(self._agenda_box)
        scroll.set_child(clamp)
        self._stack.add_named(scroll, "content")

        self._stack.set_visible_child_name("loading")
        toolbar.set_content(self._stack)
        self.set_child(toolbar)

        self._update_date_label()

    # ------------------------------------------------------------------
    def _update_date_label(self) -> None:
        if self._view_mode == "future":
            self._date_lbl.set_text("Prossimi 30 giorni")
            self._prev_btn.set_sensitive(False)
            self._next_btn.set_sensitive(False)
        else:
            dt = datetime.combine(self._current_date, datetime.min.time())
            self._date_lbl.set_text(_fmt_date(dt))
            self._prev_btn.set_sensitive(True)
            self._next_btn.set_sensitive(True)

    def _shift_day(self, delta: int) -> None:
        self._view_mode = "day"
        self._current_date += timedelta(days=delta)
        self._update_date_label()
        self._render()

    def _go_today(self) -> None:
        self._view_mode = "day"
        self._current_date = date.today()
        self._update_date_label()
        self._render()

    def _go_future(self) -> None:
        self._view_mode = "future"
        self._update_date_label()
        self._render()

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        self._stack.set_visible_child_name("loading")
        self._load()

    def _load(self) -> None:
        def worker():
            try:
                items = self._client.get_agenda(days_back=7, days_forward=60)
                GLib.idle_add(self._on_loaded, items)
            except Exception as exc:
                GLib.idle_add(self._show_error, str(exc))
        threading.Thread(target=worker, daemon=True).start()

    def _on_loaded(self, items: list) -> bool:
        self._all_items = items
        self._render()
        return False

    # ------------------------------------------------------------------
    def _render(self) -> None:
        child = self._agenda_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._agenda_box.remove(child)
            child = nxt

        now = datetime.now()

        if self._view_mode == "future":
            items = [i for i in self._all_items
                     if _parse_dt(i.get("evtDatetimeBegin", "")) >= now]
            items.sort(key=lambda i: i.get("evtDatetimeBegin", ""))
        else:
            items = [i for i in self._all_items
                     if _parse_dt(i.get("evtDatetimeBegin", "")).date() == self._current_date]
            items.sort(key=lambda i: i.get("evtDatetimeBegin", ""))

        if not items:
            self._stack.set_visible_child_name("empty")
            return

        # Group by date
        by_date: dict = {}
        for item in items:
            dt = _parse_dt(item.get("evtDatetimeBegin", ""))
            key = dt.date()
            by_date.setdefault(key, []).append(item)

        for date_key in sorted(by_date.keys()):
            day_items = by_date[date_key]
            dt = datetime.combine(date_key, datetime.min.time())

            # ── Day section header ─────────────────────────────────────
            date_hdr = Gtk.Label(label=_fmt_date(dt).upper())
            date_hdr.set_halign(Gtk.Align.START)
            date_hdr.add_css_class("caption-heading")
            date_hdr.add_css_class("dim-label")
            date_hdr.set_margin_top(8)
            date_hdr.set_margin_bottom(4)
            self._agenda_box.append(date_hdr)

            # Separate lessons/notes from homework/tests
            lessons  = [i for i in day_items if i.get("evtCode") == "AGNT"]
            homework = [i for i in day_items if i.get("evtCode") in ("AGHW", "AGVC", "AGVS")]
            other    = [i for i in day_items
                        if i.get("evtCode") not in ("AGNT", "AGHW", "AGVC", "AGVS")]

            # ── Compiti/Verifiche group ───────────────────────────────
            hw_items = homework + other
            if hw_items:
                hw_group = Adw.PreferencesGroup()
                hw_group.set_title("Compiti e verifiche" if homework else "Eventi")
                for item in hw_items:
                    hw_group.add(self._make_event_row(item))
                self._agenda_box.append(hw_group)

            # ── Lezioni/Note group ─────────────────────────────────────
            if lessons:
                note_group = Adw.PreferencesGroup()
                note_group.set_title("Note e comunicazioni")
                for item in lessons:
                    note_group.add(self._make_event_row(item))
                self._agenda_box.append(note_group)

        self._stack.set_visible_child_name("content")

    def _make_event_row(self, item: dict) -> Adw.ActionRow:
        code = item.get("evtCode", "")
        label, icon, is_warn = _EVT_META.get(code, _DEFAULT_META)
        subject  = (item.get("subjectDesc") or "").strip()
        notes    = (item.get("notes") or item.get("note") or "").strip()
        author   = (item.get("authorName") or "").strip()
        begin    = item.get("evtDatetimeBegin", "")
        end      = item.get("evtDatetimeEnd", "")

        row = Adw.ActionRow()
        title = (subject.title() if subject else label)
        row.set_title(title)

        # Time range
        parts = []
        try:
            t0 = _parse_dt(begin)
            t1 = _parse_dt(end)
            if t0 != datetime.min and t0.hour + t0.minute > 0:
                parts.append(f"{t0.strftime('%H:%M')} – {t1.strftime('%H:%M')}")
        except Exception:
            pass
        if notes:
            parts.append(notes[:80] + ("…" if len(notes) > 80 else ""))
        if author and not subject:
            parts.append(author)
        if parts:
            row.set_subtitle("  ·  ".join(parts))

        # Coloured subject bar as prefix
        if subject:
            rgb = _subject_rgb(subject)
            bar = _make_subject_bar(rgb)
            row.add_prefix(bar)
        else:
            img = Gtk.Image.new_from_icon_name(icon)
            if is_warn:
                img.add_css_class("warning")
            row.add_prefix(img)

        # Warning icon suffix for tests
        if is_warn:
            warn_img = Gtk.Image.new_from_icon_name("dialog-warning-symbolic")
            warn_img.add_css_class("warning")
            warn_img.set_valign(Gtk.Align.CENTER)
            row.add_suffix(warn_img)

        return row

    def _show_error(self, message: str) -> bool:
        self._error_page.set_description(message)
        self._stack.set_visible_child_name("error")
        return False
