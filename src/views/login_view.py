import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, GObject
import threading

SERVICE_NAME = "io.github.giomarco2107.LinuxViva"


def _keyring_get(key: str) -> str:
    try:
        import keyring
        return keyring.get_password(SERVICE_NAME, key) or ""
    except Exception:
        return ""


def _keyring_set(key: str, value: str) -> None:
    try:
        import keyring
        keyring.set_password(SERVICE_NAME, key, value)
    except Exception:
        pass


def _keyring_delete(key: str) -> None:
    try:
        import keyring
        keyring.delete_password(SERVICE_NAME, key)
    except Exception:
        pass


class LoginView(Adw.Bin):
    __gsignals__ = {
        "login-success": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
    }

    def __init__(self, client):
        super().__init__()
        self._client = client
        self._build_ui()
        self._restore_credentials()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        toolbar_view = Adw.ToolbarView()

        header = Adw.HeaderBar()
        header.set_show_title(False)
        toolbar_view.add_top_bar(header)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)

        clamp = Adw.Clamp()
        clamp.set_maximum_size(420)
        clamp.set_margin_top(32)
        clamp.set_margin_bottom(32)
        clamp.set_margin_start(12)
        clamp.set_margin_end(12)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=28)

        # ── Hero ──────────────────────────────────────────────────────
        hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        hero.set_halign(Gtk.Align.CENTER)
        hero.set_margin_top(12)

        icon = Gtk.Image.new_from_icon_name("io.github.giomarco2107.LinuxViva")
        icon.set_pixel_size(96)

        title = Gtk.Label(label="ClasseViva")
        title.add_css_class("title-1")

        subtitle = Gtk.Label(label="Registro elettronico Spaggiari")
        subtitle.add_css_class("dim-label")
        subtitle.add_css_class("body")

        hero.append(icon)
        hero.append(title)
        hero.append(subtitle)

        # ── Error banner ───────────────────────────────────────────────
        self._banner = Adw.Banner()
        self._banner.set_use_markup(False)
        self._banner.set_revealed(False)

        # ── Form ──────────────────────────────────────────────────────
        group = Adw.PreferencesGroup()
        group.set_title("Credenziali")

        self._uid_row = Adw.EntryRow()
        self._uid_row.set_title("Email o Codice Utente")
        self._uid_row.set_input_purpose(Gtk.InputPurpose.EMAIL)

        self._pwd_row = Adw.PasswordEntryRow()
        self._pwd_row.set_title("Password")
        self._pwd_row.connect("apply", lambda _r: self._do_login())

        self._remember_row = Adw.SwitchRow()
        self._remember_row.set_title("Ricorda credenziali")
        self._remember_row.set_active(True)

        group.add(self._uid_row)
        group.add(self._pwd_row)
        group.add(self._remember_row)

        # ── Login button ───────────────────────────────────────────────
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        btn_box.set_halign(Gtk.Align.CENTER)

        self._login_btn = Gtk.Button(label="Accedi")
        self._login_btn.add_css_class("suggested-action")
        self._login_btn.add_css_class("pill")
        self._login_btn.connect("clicked", lambda _b: self._do_login())

        self._spinner = Gtk.Spinner()
        self._spinner.set_visible(False)

        btn_box.append(self._spinner)
        btn_box.append(self._login_btn)

        box.append(hero)
        box.append(self._banner)
        box.append(group)
        box.append(btn_box)

        clamp.set_child(box)
        scroll.set_child(clamp)
        toolbar_view.set_content(scroll)
        self.set_child(toolbar_view)

    def _restore_credentials(self) -> None:
        uid = _keyring_get("username")
        pwd = _keyring_get("password")
        if uid:
            self._uid_row.set_text(uid)
        if pwd:
            self._pwd_row.set_text(pwd)
        if uid and pwd:
            GLib.idle_add(self._do_login)

    # ------------------------------------------------------------------
    def _do_login(self) -> None:
        uid = self._uid_row.get_text().strip()
        pwd = self._pwd_row.get_text()

        if not uid or not pwd:
            self._set_error("Inserisci email e password")
            return

        self._set_loading(True)
        self._banner.set_revealed(False)

        def worker():
            try:
                info = self._client.login(uid, pwd)
                GLib.idle_add(self._on_success, uid, pwd, info)
            except Exception as exc:
                GLib.idle_add(self._on_error, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _on_success(self, uid: str, pwd: str, info: dict) -> bool:
        self._set_loading(False)
        if self._remember_row.get_active():
            _keyring_set("username", uid)
            _keyring_set("password", pwd)
        else:
            _keyring_delete("username")
            _keyring_delete("password")
        self.emit("login-success", info)
        return False

    def _on_error(self, message: str) -> bool:
        self._set_loading(False)
        self._set_error(message)
        return False

    def _set_loading(self, loading: bool) -> None:
        self._login_btn.set_sensitive(not loading)
        self._uid_row.set_sensitive(not loading)
        self._pwd_row.set_sensitive(not loading)
        self._spinner.set_visible(loading)
        if loading:
            self._spinner.start()
        else:
            self._spinner.stop()

    def _set_error(self, msg: str) -> None:
        self._banner.set_title(msg)
        self._banner.set_revealed(True)
