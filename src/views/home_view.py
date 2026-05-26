import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib
import threading
from datetime import datetime

from widgets.grade_badge import GradeBadge, GradeRing, _apply_css

_MONTHS_IT = [
    "", "gen", "feb", "mar", "apr", "mag", "giu",
    "lug", "ago", "set", "ott", "nov", "dic",
]
_AGENDA_META = {
    "AGNT": ("Nota",     "dialog-information-symbolic"),
    "AGHW": ("Compito",  "document-edit-symbolic"),
    "AGVC": ("Verifica", "dialog-warning-symbolic"),
    "AGVS": ("Verifica", "dialog-warning-symbolic"),
}
_DEFAULT_AGENDA = ("Evento", "x-office-calendar-symbolic")


def _parse_dt(s: str) -> datetime:
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:19], fmt)
        except ValueError:
            continue
    return datetime.min


def _fmt_short_date(s: str) -> str:
    try:
        p = s[:10].split("-")
        return f"{p[2]} {_MONTHS_IT[int(p[1])]}"
    except Exception:
        return s[:10]


def _global_avg(grades: list) -> float:
    valid = [
        g for g in grades
        if (g.get("decimalValue") or 0) > 0
        and not g.get("noAverage", False)
        and not g.get("canceled", False)
    ]
    if not valid:
        return 0.0
    return sum(g["decimalValue"] for g in valid) / len(valid)


def _period_avg(grades: list, pos: int) -> float:
    return _global_avg([g for g in grades if g.get("periodPos") == pos])


class HomeView(Adw.Bin):
    def __init__(self, client):
        super().__init__()
        self._client = client
        self._loaded = False
        _apply_css()
        self._build_ui()

    def _build_ui(self) -> None:
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
        lbl = Gtk.Label(label="Caricamento…")
        lbl.add_css_class("dim-label")
        loading_box.append(sp)
        loading_box.append(lbl)
        self._stack.add_named(loading_box, "loading")

        # Error
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

        # Content
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        clamp = Adw.Clamp()
        clamp.set_maximum_size(760)
        clamp.set_margin_top(16)
        clamp.set_margin_bottom(16)
        clamp.set_margin_start(16)
        clamp.set_margin_end(16)
        self._home_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        clamp.set_child(self._home_box)
        scroll.set_child(clamp)
        self._stack.add_named(scroll, "content")

        self._stack.set_visible_child_name("loading")
        self.set_child(self._stack)

    def refresh(self) -> None:
        self._stack.set_visible_child_name("loading")
        self._load()

    def _load(self) -> None:
        results = {}
        errors = []
        lock = threading.Lock()
        remaining = [3]

        def done():
            with lock:
                remaining[0] -= 1
                if remaining[0] > 0:
                    return
            if errors:
                GLib.idle_add(self._show_error, errors[0])
            else:
                GLib.idle_add(self._populate, results)

        def load_grades():
            try:
                results["grades"] = self._client.get_grades()
            except Exception as e:
                with lock:
                    errors.append(str(e))
            done()

        def load_agenda():
            try:
                results["agenda"] = self._client.get_agenda(days_back=0, days_forward=14)
            except Exception as e:
                with lock:
                    errors.append(str(e))
            done()

        def load_notices():
            try:
                results["notices"] = self._client.get_noticeboard()
            except Exception as e:
                with lock:
                    errors.append(str(e))
            done()

        threading.Thread(target=load_grades, daemon=True).start()
        threading.Thread(target=load_agenda, daemon=True).start()
        threading.Thread(target=load_notices, daemon=True).start()

    def _populate(self, results: dict) -> bool:
        child = self._home_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._home_box.remove(child)
            child = nxt

        grades  = results.get("grades", [])
        agenda  = results.get("agenda", [])
        notices = results.get("notices", [])

        # ── Grade stats banner ───────────────────────────────────────
        avg = _global_avg(grades)
        if avg > 0:
            valid_all = [g for g in grades
                         if (g.get("decimalValue") or 0) > 0
                         and not g.get("noAverage") and not g.get("canceled")]

            # Collect periods
            periods: dict = {}
            for g in valid_all:
                pos = g.get("periodPos")
                if pos is not None and pos not in periods:
                    periods[pos] = (g.get("periodDesc") or f"Periodo {pos}").title()

            stats_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

            # Overall card
            overall = self._make_avg_card("Media generale", avg,
                                          len(valid_all))
            stats_box.append(overall)

            # Period cards
            for pos in sorted(periods.keys()):
                pg   = [g for g in valid_all if g.get("periodPos") == pos]
                pavg = _global_avg(pg)
                card = self._make_avg_card(periods[pos], pavg, len(pg))
                stats_box.append(card)

            self._home_box.append(stats_box)

        # ── Recent grades ────────────────────────────────────────────
        recent = sorted(
            [g for g in grades if (g.get("decimalValue") or 0) > 0],
            key=lambda g: g.get("evtDate", ""),
            reverse=True,
        )[:5]

        grades_group = Adw.PreferencesGroup()
        grades_group.set_title("Ultimi voti")
        if recent:
            for g in recent:
                dec     = float(g.get("decimalValue") or 0)
                display = (g.get("displayValue") or "").strip() or f"{dec:.1g}"
                subject = (g.get("subjectDesc") or "—").title()
                date_str = _fmt_short_date(g.get("evtDate", ""))
                period  = (g.get("periodDesc") or "").title()

                row = Adw.ActionRow()
                row.set_title(subject)
                row.set_subtitle(f"{date_str}" + (f"  ·  {period}" if period else ""))
                row.add_suffix(GradeBadge(dec, display))
                grades_group.add(row)
        else:
            row = Adw.ActionRow()
            row.set_title("Nessun voto recente")
            grades_group.add(row)
        self._home_box.append(grades_group)

        # ── Upcoming agenda ───────────────────────────────────────────
        now = datetime.now()
        upcoming = sorted(
            [i for i in agenda if _parse_dt(i.get("evtDatetimeBegin", "")) >= now],
            key=lambda i: i.get("evtDatetimeBegin", ""),
        )[:5]

        agenda_group = Adw.PreferencesGroup()
        agenda_group.set_title("Prossimi impegni")
        if upcoming:
            for item in upcoming:
                code = item.get("evtCode", "")
                label, icon_name = _AGENDA_META.get(code, _DEFAULT_AGENDA)
                subject  = (item.get("subjectDesc") or "").strip()
                notes    = (item.get("notes") or item.get("note") or "").strip()
                dt       = _parse_dt(item.get("evtDatetimeBegin", ""))
                date_str = f"{dt.day} {_MONTHS_IT[dt.month]}"

                title = (subject.title() if subject else label)
                if subject and label != "Nota":
                    title = f"{label} — {subject.title()}"

                subtitle_parts = [date_str]
                if notes:
                    subtitle_parts.append(notes[:60] + ("…" if len(notes) > 60 else ""))

                row = Adw.ActionRow()
                row.set_title(title)
                row.set_subtitle("  ·  ".join(subtitle_parts))
                img = Gtk.Image.new_from_icon_name(icon_name)
                if code in ("AGVC", "AGVS"):
                    img.add_css_class("warning")
                row.add_prefix(img)
                agenda_group.add(row)
        else:
            row = Adw.ActionRow()
            row.set_title("Nessun impegno nei prossimi 14 giorni")
            agenda_group.add(row)
        self._home_box.append(agenda_group)

        # ── Unread notices ────────────────────────────────────────────
        unread = [n for n in notices if not n.get("readStatus", True)]
        if unread:
            notice_group = Adw.PreferencesGroup()
            notice_group.set_title("Bacheca")
            count_row = Adw.ActionRow()
            n = len(unread)
            count_row.set_title(
                f"{n} comunicazion{'e' if n == 1 else 'i'} non lett{'a' if n == 1 else 'e'}"
            )
            count_row.set_subtitle("Apri la sezione Bacheca per visualizzarle")
            badge = Gtk.Label(label=str(n))
            badge.add_css_class("accent")
            badge.add_css_class("heading")
            count_row.add_suffix(badge)
            notice_group.add(count_row)
            self._home_box.append(notice_group)

        self._stack.set_visible_child_name("content")
        return False

    def _make_avg_card(self, label: str, value: float, count: int) -> Gtk.Box:
        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        card.add_css_class("stat-card")
        card.set_hexpand(True)

        ring = GradeRing(value, size=60)
        card.append(ring)

        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        text.set_valign(Gtk.Align.CENTER)

        title_lbl = Gtk.Label(label=label)
        title_lbl.set_halign(Gtk.Align.START)
        title_lbl.add_css_class("heading")
        title_lbl.set_wrap(True)
        title_lbl.set_xalign(0)

        sub_lbl = Gtk.Label(label=f"{count} vot{'o' if count == 1 else 'i'}")
        sub_lbl.set_halign(Gtk.Align.START)
        sub_lbl.add_css_class("dim-label")
        sub_lbl.add_css_class("caption")

        text.append(title_lbl)
        text.append(sub_lbl)
        card.append(text)
        return card

    def _show_error(self, msg: str) -> bool:
        self._error_page.set_description(msg)
        self._stack.set_visible_child_name("error")
        return False
