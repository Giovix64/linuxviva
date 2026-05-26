import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, GObject

from views.home_view import HomeView
from views.grades_view import GradesView
from views.absences_view import AbsencesView
from views.agenda_view import AgendaView
from views.noticeboard_view import NoticeboardView
from views.didactics_view import DidacticsView
from views.scrutini_view import ScrutiniView


class MainView(Adw.Bin):
    __gsignals__ = {
        "logout": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, client, user_info: dict):
        super().__init__()
        self._client = client
        self._user_info = user_info
        self._build_ui()

    def _build_ui(self) -> None:
        toolbar_view = Adw.ToolbarView()

        # ── Header bar ────────────────────────────────────────────────
        header = Adw.HeaderBar()

        name = (
            f"{self._user_info.get('firstName', '')} "
            f"{self._user_info.get('lastName', '')}"
        ).strip() or "Classeviva"

        # Adaptive title switcher (shows in header on wide screens)
        title_switcher = Adw.ViewSwitcherTitle()
        title_switcher.set_title(name)
        header.set_title_widget(title_switcher)

        # Refresh button
        refresh_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        refresh_btn.set_tooltip_text("Aggiorna")
        refresh_btn.connect("clicked", self._on_refresh)
        header.pack_start(refresh_btn)

        # Logout button
        logout_btn = Gtk.Button.new_from_icon_name("system-log-out-symbolic")
        logout_btn.set_tooltip_text("Esci")
        logout_btn.connect("clicked", lambda _: self.emit("logout"))
        header.pack_end(logout_btn)

        toolbar_view.add_top_bar(header)

        # ── View stack ────────────────────────────────────────────────
        self._stack = Adw.ViewStack()

        self._home_view = HomeView(client=self._client)
        self._home_view._loaded = True
        p = self._stack.add_titled(self._home_view, "home", "Home")
        p.set_icon_name("user-home-symbolic")

        self._grades_view = GradesView(client=self._client)
        p = self._stack.add_titled(self._grades_view, "grades", "Voti")
        p.set_icon_name("starred-symbolic")

        self._absences_view = AbsencesView(client=self._client)
        p = self._stack.add_titled(self._absences_view, "absences", "Assenze")
        p.set_icon_name("alarm-symbolic")

        self._agenda_view = AgendaView(client=self._client)
        p = self._stack.add_titled(self._agenda_view, "agenda", "Agenda")
        p.set_icon_name("office-calendar-symbolic")

        self._noticeboard_view = NoticeboardView(client=self._client)
        p = self._stack.add_titled(self._noticeboard_view, "noticeboard", "Bacheca")
        p.set_icon_name("mail-unread-symbolic")

        self._didactics_view = DidacticsView(client=self._client)
        p = self._stack.add_titled(self._didactics_view, "didactics", "Materiali")
        p.set_icon_name("folder-symbolic")

        self._scrutini_view = ScrutiniView(client=self._client)
        p = self._stack.add_titled(self._scrutini_view, "scrutini", "Pagelle")
        p.set_icon_name("x-office-document-symbolic")

        title_switcher.set_stack(self._stack)
        self._stack.connect("notify::visible-child", self._on_visible_child_changed)

        toolbar_view.set_content(self._stack)

        # ── Bottom switcher bar (narrow screens) ──────────────────────
        bar = Adw.ViewSwitcherBar()
        bar.set_stack(self._stack)
        # Reveal bar only when the title switcher doesn't fit
        title_switcher.bind_property(
            "title-visible", bar, "reveal",
            GObject.BindingFlags.SYNC_CREATE,
        )
        toolbar_view.add_bottom_bar(bar)

        self.set_child(toolbar_view)
        GLib.idle_add(self._home_view._load)

    def _on_visible_child_changed(self, stack, _param) -> None:
        child = stack.get_visible_child()
        if child and hasattr(child, "_loaded") and not child._loaded:
            child._loaded = True
            child._load()

    def _on_refresh(self, _btn) -> None:
        child = self._stack.get_visible_child()
        if child and hasattr(child, "refresh"):
            child.refresh()
