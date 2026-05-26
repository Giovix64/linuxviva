import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib
import threading
from collections import defaultdict

from widgets.grade_badge import GradeBadge, GradeRing, _apply_css


def _fmt_date(s: str) -> str:
    try:
        p = s[:10].split("-")
        return f"{p[2]}/{p[1]}/{p[0]}"
    except Exception:
        return s


def _avg(grades: list) -> float:
    valid = [
        g for g in grades
        if (g.get("decimalValue") or 0) > 0
        and not g.get("noAverage", False)
        and not g.get("canceled", False)
    ]
    if not valid:
        return 0.0
    return sum(g["decimalValue"] for g in valid) / len(valid)


def _valid_count(grades: list) -> int:
    return len([g for g in grades
                if (g.get("decimalValue") or 0) > 0
                and not g.get("noAverage", False)
                and not g.get("canceled", False)])


# ---------------------------------------------------------------------------
# Stats banner widget
# ---------------------------------------------------------------------------

def _make_stat_card(label: str, value: float, count: int) -> Gtk.Box:
    """A card with a GradeRing + title + count."""
    _apply_css()
    card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    card.add_css_class("stat-card")
    card.set_hexpand(True)

    ring = GradeRing(value, size=68)
    card.append(ring)

    text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    text.set_valign(Gtk.Align.CENTER)

    title_lbl = Gtk.Label(label=label)
    title_lbl.set_halign(Gtk.Align.START)
    title_lbl.add_css_class("heading")
    title_lbl.set_wrap(True)
    title_lbl.set_xalign(0)

    sub_lbl = Gtk.Label(label=f"{count} valutazion{'e' if count == 1 else 'i'}")
    sub_lbl.set_halign(Gtk.Align.START)
    sub_lbl.add_css_class("dim-label")
    sub_lbl.add_css_class("caption")

    text.append(title_lbl)
    text.append(sub_lbl)
    card.append(text)
    return card


# ---------------------------------------------------------------------------

class GradesView(Adw.Bin):
    def __init__(self, client):
        super().__init__()
        self._client = client
        self._loaded = False
        self._all_grades: list = []
        self._selected_period: int | None = None
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
        lbl = Gtk.Label(label="Caricamento voti…")
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

        # Empty
        empty = Adw.StatusPage()
        empty.set_icon_name("emblem-documents-symbolic")
        empty.set_title("Nessun voto")
        empty.set_description("Non ci sono ancora valutazioni registrate.")
        self._stack.add_named(empty, "empty")

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
        self._box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        clamp.set_child(self._box)
        scroll.set_child(clamp)
        self._stack.add_named(scroll, "content")

        self._stack.set_visible_child_name("loading")
        self.set_child(self._stack)

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        self._stack.set_visible_child_name("loading")
        self._selected_period = None
        self._load()

    def _load(self) -> None:
        def worker():
            try:
                grades = self._client.get_grades()
                GLib.idle_add(self._on_loaded, grades)
            except Exception as exc:
                GLib.idle_add(self._show_error, str(exc))
        threading.Thread(target=worker, daemon=True).start()

    def _on_loaded(self, grades: list) -> bool:
        self._all_grades = grades
        self._build_content()
        return False

    # ------------------------------------------------------------------
    def _build_content(self) -> None:
        # Clear
        child = self._box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._box.remove(child)
            child = nxt

        valid_grades = [g for g in self._all_grades if (g.get("decimalValue") or 0) > 0]
        if not valid_grades:
            self._stack.set_visible_child_name("empty")
            return

        # ── Collect period data ──────────────────────────────────────
        periods: dict = {}
        for g in valid_grades:
            pos = g.get("periodPos")
            if pos is not None and pos not in periods:
                desc = (g.get("periodDesc") or f"Periodo {pos}").title()
                periods[pos] = desc

        global_avg   = _avg(valid_grades)
        global_count = _valid_count(valid_grades)

        # ── Stats banner ─────────────────────────────────────────────
        stats_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        overall_card = _make_stat_card("Media totale", global_avg, global_count)
        stats_box.append(overall_card)

        period_avgs: dict = {}
        for pos in sorted(periods.keys()):
            pg = [g for g in valid_grades if g.get("periodPos") == pos]
            period_avgs[pos] = (_avg(pg), _valid_count(pg))
            card = _make_stat_card(periods[pos], period_avgs[pos][0], period_avgs[pos][1])
            stats_box.append(card)

        self._box.append(stats_box)

        # ── Period filter ─────────────────────────────────────────────
        if len(periods) >= 2:
            filter_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
            filter_box.set_halign(Gtk.Align.CENTER)
            filter_box.add_css_class("linked")

            group_btn = None
            btn_all = Gtk.ToggleButton(label="Tutti i periodi")
            btn_all.set_active(self._selected_period is None)
            btn_all.connect("toggled", self._on_filter_toggled, None)
            filter_box.append(btn_all)
            group_btn = btn_all

            for pos in sorted(periods.keys()):
                btn = Gtk.ToggleButton(label=periods[pos])
                btn.set_group(group_btn)
                btn.set_active(self._selected_period == pos)
                btn.connect("toggled", self._on_filter_toggled, pos)
                filter_box.append(btn)

            self._box.append(filter_box)

        # ── Subject list ──────────────────────────────────────────────
        self._populate()

    def _on_filter_toggled(self, btn: Gtk.ToggleButton, period_pos) -> None:
        if not btn.get_active():
            return
        self._selected_period = period_pos
        # Remove everything below stats_box and filter_box (2 items)
        children = []
        child = self._box.get_first_child()
        while child:
            children.append(child)
            child = child.get_next_sibling()
        for c in children[2:]:
            self._box.remove(c)
        self._populate()

    def _populate(self) -> None:
        grades = self._all_grades if self._selected_period is None else [
            g for g in self._all_grades if g.get("periodPos") == self._selected_period
        ]
        valid_grades = [g for g in grades if (g.get("decimalValue") or 0) > 0]
        if not valid_grades:
            return

        global_avg = _avg(valid_grades)

        # Group by period
        by_period: dict = defaultdict(list)
        for g in valid_grades:
            pos = g.get("periodPos") or 0
            by_period[pos].append(g)

        for pos in sorted(by_period.keys()):
            period_grades = by_period[pos]
            period_desc = (period_grades[0].get("periodDesc") or f"Periodo {pos}").title()
            period_avg  = _avg(period_grades)

            period_group = Adw.PreferencesGroup()
            period_group.set_title(period_desc)

            # Period average header row
            pavg_row = Adw.ActionRow()
            pavg_row.set_title(f"Media {period_desc}")
            cnt = _valid_count(period_grades)
            pavg_row.set_subtitle(f"{cnt} vot{'o' if cnt == 1 else 'i'} validi")
            pavg_row.add_suffix(GradeRing(period_avg, size=48))
            period_group.add(pavg_row)

            # Group by subject
            by_subject: dict = defaultdict(list)
            for g in period_grades:
                by_subject[g.get("subjectDesc") or "—"].append(g)

            for subj in sorted(by_subject.keys()):
                subj_grades = sorted(
                    by_subject[subj],
                    key=lambda x: x.get("evtDate", ""),
                    reverse=True,
                )
                subj_avg = _avg(subj_grades)
                valid_subj = [g for g in subj_grades
                              if (g.get("decimalValue") or 0) > 0
                              and not g.get("noAverage") and not g.get("canceled")]

                expander = Adw.ExpanderRow()
                expander.set_title(subj.title())
                if subj_avg > 0:
                    teacher = (subj_grades[0].get("subjectTeacherName") or "").strip()
                    n = len(valid_subj)
                    expander.set_subtitle(
                        f"{teacher}  ·  " if teacher else ""
                        + f"Media: {subj_avg:.2f}  ·  {n} vot{'o' if n == 1 else 'i'}"
                    )

                    # Trend arrow vs global average
                    diff = subj_avg - global_avg
                    if diff > 0.15:
                        arrow = Gtk.Label(label="↑")
                        arrow.add_css_class("trend-up")
                    elif diff < -0.15:
                        arrow = Gtk.Label(label="↓")
                        arrow.add_css_class("trend-down")
                    else:
                        arrow = Gtk.Label(label="→")
                        arrow.add_css_class("dim-label")
                    arrow.set_valign(Gtk.Align.CENTER)
                    expander.add_prefix(arrow)
                    expander.add_suffix(GradeRing(subj_avg, size=40))

                for g in subj_grades:
                    dec     = g.get("decimalValue") or 0.0
                    display = (g.get("displayValue") or f"{dec:.1g}").strip()
                    date_str = _fmt_date(g.get("evtDate", ""))
                    notes    = (g.get("notesForFamily") or "").strip()
                    canceled = g.get("canceled", False)
                    no_avg   = g.get("noAverage", False)
                    component = (g.get("componentDesc") or "").strip()

                    parts = [date_str]
                    if component:
                        parts.append(component)
                    if no_avg:
                        parts.append("non fa media")
                    if notes:
                        parts.append(notes[:80] + ("…" if len(notes) > 80 else ""))

                    row = Adw.ActionRow()
                    if canceled:
                        row.set_title(f"<s>{display}</s>")
                        row.set_use_markup(True)
                    else:
                        row.set_title(display)
                    row.set_subtitle("  ·  ".join(parts))

                    if not canceled:
                        badge = GradeBadge(dec if not no_avg else 0, display)
                        row.add_suffix(badge)

                    expander.add_row(row)

                period_group.add(expander)
            self._box.append(period_group)

        self._stack.set_visible_child_name("content")

    def _show_error(self, msg: str) -> bool:
        self._error_page.set_description(msg)
        self._stack.set_visible_child_name("error")
        return False
