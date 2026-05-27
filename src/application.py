import gi
import os
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gdk

from api.client import ClassevivaClient
from views.login_view import LoginView
from views.main_view import MainView

APP_ID = "io.github.giomarco2107.LinuxViva"
SERVICE_NAME = "io.github.giomarco2107.LinuxViva"

# Path to the local icons folder (works when running from source)
_SRC_DIR   = os.path.dirname(os.path.abspath(__file__))
_ICONS_DIR = os.path.join(os.path.dirname(_SRC_DIR), "data", "icons")


class ClassevivaApplication(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)
        self._client = ClassevivaClient()
        self._window = None

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        # Add local icon search path so the SVG icon is found without meson install
        if os.path.isdir(_ICONS_DIR):
            display = Gdk.Display.get_default()
            if display:
                Gtk.IconTheme.get_for_display(display).add_search_path(_ICONS_DIR)

    def do_activate(self) -> None:
        if self._window is None:
            self._window = ClassevivaWindow(application=self, client=self._client)
        self._window.present()


# ---------------------------------------------------------------------------

class ClassevivaWindow(Adw.ApplicationWindow):
    def __init__(self, client: ClassevivaClient, **kwargs):
        super().__init__(**kwargs)
        self._client = client

        self.set_title("Classeviva")
        self.set_default_size(420, 720)

        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._stack.set_transition_duration(250)

        self._login_view = LoginView(client=client)
        self._login_view.connect("login-success", self._on_login_success)
        self._stack.add_named(self._login_view, "login")

        self.set_content(self._stack)
        self._stack.set_visible_child_name("login")

    # ------------------------------------------------------------------
    def _on_login_success(self, _view, user_info: dict) -> None:
        old_main = self._stack.get_child_by_name("main")
        if old_main:
            self._stack.remove(old_main)

        main_view = MainView(client=self._client, user_info=user_info)
        main_view.connect("logout", self._on_logout)
        self._stack.add_named(main_view, "main")
        self._stack.set_visible_child_name("main")

    def _on_logout(self, _view) -> None:
        self._client.logout()

        try:
            import keyring
            keyring.delete_password(SERVICE_NAME, "password")
        except Exception:
            pass

        old_main = self._stack.get_child_by_name("main")
        if old_main:
            self._stack.remove(old_main)

        self._stack.set_visible_child_name("login")
