import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gio
import threading
import os
import subprocess
import json

try:
    gi.require_version("WebKit", "6.0")
    from gi.repository import WebKit
    _WEBKIT_AVAILABLE = True
except (ValueError, ImportError):
    _WEBKIT_AVAILABLE = False

_SERVICE_NAME = "io.github.giomarco2107.LinuxViva"


def _keyring_get(key: str) -> str:
    try:
        import keyring
        return keyring.get_password(_SERVICE_NAME, key) or ""
    except Exception:
        return ""


def _open_url(url: str) -> None:
    try:
        Gio.AppInfo.launch_default_for_uri(url, None)
    except Exception:
        subprocess.Popen(["xdg-open", url])


_DOWNLOAD_DIR = os.path.join(GLib.get_user_cache_dir(), "classeviva", "downloads")
_WEB_DATA_DIR = os.path.join(GLib.get_user_data_dir(), "classeviva", "pagella_web")


def _open_file(path: str) -> None:
    try:
        Gio.AppInfo.launch_default_for_uri(f"file://{path}", None)
    except Exception:
        subprocess.Popen(["xdg-open", path])


# ---------------------------------------------------------------------------
# JavaScript injected to auto-fill Classeviva web login form
# ---------------------------------------------------------------------------

def _autofill_js(username: str, password: str) -> str:
    u = json.dumps(username)
    p = json.dumps(password)
    return f"""
(function() {{
    var u = document.querySelector(
        'input[name="login_username"], input[id*="username"], ' +
        'input[placeholder*="Codice"], input[placeholder*="Email"], ' +
        'input[type="email"], input[type="text"]'
    );
    var pw = document.querySelector(
        'input[name="login_password"], input[type="password"]'
    );
    if (!u || !pw) return false;

    var setVal = function(el, val) {{
        var setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value'
        ).set;
        setter.call(el, val);
        el.dispatchEvent(new Event('input',  {{bubbles: true}}));
        el.dispatchEvent(new Event('change', {{bubbles: true}}));
    }};

    setVal(u,  {u});
    setVal(pw, {p});

    var btn = document.querySelector(
        'button[type="submit"], input[type="submit"], ' +
        'button.pulsante, button[class*="login"], button[class*="entra"]'
    );
    if (!btn) {{
        var form = u.closest('form');
        if (form) {{ btn = form.querySelector('button, input[type="submit"]'); }}
    }}
    if (btn) {{ btn.click(); return true; }}

    var form = u.closest('form');
    if (form) {{ form.submit(); return true; }}

    return false;
}})();
"""


# ---------------------------------------------------------------------------
# In-app WebKit dialog
# ---------------------------------------------------------------------------

class PagellaWebDialog(Adw.Dialog):
    def __init__(self, url: str, title: str, token: str):
        super().__init__()
        self._url = url
        self._token = token
        self._autofill_done = False
        self._username = _keyring_get("username")
        self._password = _keyring_get("password")
        self.set_title(title or "Pagella")
        self.set_content_width(960)
        self.set_content_height(700)
        self._build_ui()

    def _build_ui(self) -> None:
        toolbar_view = Adw.ToolbarView()

        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(True)

        self._back_btn = Gtk.Button.new_from_icon_name("go-previous-symbolic")
        self._back_btn.set_tooltip_text("Indietro")
        self._back_btn.set_sensitive(False)
        self._back_btn.connect("clicked", lambda _: self._webview.go_back())

        self._fwd_btn = Gtk.Button.new_from_icon_name("go-next-symbolic")
        self._fwd_btn.set_tooltip_text("Avanti")
        self._fwd_btn.set_sensitive(False)
        self._fwd_btn.connect("clicked", lambda _: self._webview.go_forward())

        self._reload_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        self._reload_btn.set_tooltip_text("Ricarica")
        self._reload_btn.connect("clicked", self._on_reload)

        pdf_btn = Gtk.Button.new_from_icon_name("document-print-symbolic")
        pdf_btn.set_tooltip_text("Esporta / Stampa PDF")
        pdf_btn.connect("clicked", self._on_print)

        ext_btn = Gtk.Button.new_from_icon_name("external-link-symbolic")
        ext_btn.set_tooltip_text("Apri nel browser")
        ext_btn.connect("clicked", lambda _: _open_url(self._url))

        header.pack_start(self._back_btn)
        header.pack_start(self._fwd_btn)
        header.pack_start(self._reload_btn)
        header.pack_end(ext_btn)
        header.pack_end(pdf_btn)
        toolbar_view.add_top_bar(header)

        self._progress = Gtk.ProgressBar()
        self._progress.set_visible(False)
        toolbar_view.add_top_bar(self._progress)

        # Persistent network session — cookies survive dialog close/reopen
        os.makedirs(_WEB_DATA_DIR, exist_ok=True)
        self._net_session = WebKit.NetworkSession.new(
            _WEB_DATA_DIR,
            os.path.join(_WEB_DATA_DIR, "cache"),
        )

        self._webview = WebKit.WebView(network_session=self._net_session)
        self._webview.set_vexpand(True)
        self._webview.set_hexpand(True)
        self._webview.connect("load-changed", self._on_load_changed)
        self._webview.connect("notify::estimated-load-progress", self._on_progress)
        self._webview.connect("notify::title", self._on_title_changed)

        toolbar_view.set_content(self._webview)
        self.set_child(toolbar_view)

        # First load: send Z-Auth-Token header so the server can recognise
        # the REST session; subsequent navigations use normal cookies.
        req = WebKit.URIRequest.new(self._url)
        hdrs = req.get_http_headers()
        hdrs.replace("Z-Auth-Token", self._token)
        hdrs.replace("Z-Dev-Apikey", "Tg1NWEwNGIgIC0K")
        self._webview.load_request(req)

    # ------------------------------------------------------------------
    def _on_reload(self, _btn) -> None:
        if self._webview.is_loading():
            self._webview.stop_loading()
        else:
            self._autofill_done = False
            self._webview.reload()

    def _on_load_changed(self, wv, event) -> None:
        is_loading = event in (
            WebKit.LoadEvent.STARTED,
            WebKit.LoadEvent.REDIRECTED,
            WebKit.LoadEvent.COMMITTED,
        )
        self._reload_btn.set_icon_name(
            "process-stop-symbolic" if is_loading else "view-refresh-symbolic"
        )
        self._progress.set_visible(is_loading)

        if event == WebKit.LoadEvent.STARTED:
            self._autofill_done = False

        if event == WebKit.LoadEvent.FINISHED:
            self._progress.set_visible(False)
            self._progress.set_fraction(0)
            self._back_btn.set_sensitive(wv.can_go_back())
            self._fwd_btn.set_sensitive(wv.can_go_forward())
            self._maybe_autofill(wv)

    def _maybe_autofill(self, wv) -> None:
        if self._autofill_done:
            return
        if not self._username or not self._password:
            return
        uri = wv.get_uri() or ""
        # Only autofill on obvious login pages
        if not any(k in uri.lower() for k in ("login", "dologin", "accedi", "auth")):
            return
        self._autofill_done = True
        js = _autofill_js(self._username, self._password)
        wv.evaluate_javascript(js, -1, None, None, None, None, None)

    def _on_progress(self, wv, _param) -> None:
        p = wv.get_estimated_load_progress()
        self._progress.set_fraction(p)

    def _on_title_changed(self, wv, _param) -> None:
        t = wv.get_title()
        if t:
            self.set_title(t)

    def _on_print(self, _btn) -> None:
        op = WebKit.PrintOperation.new(self._webview)
        win = self.get_root()
        op.run_dialog(win)


# ---------------------------------------------------------------------------
# Main Pagelle view
# ---------------------------------------------------------------------------

class ScrutiniView(Adw.Bin):
    def __init__(self, client):
        super().__init__()
        self._client = client
        self._loaded = False
        self._build_ui()

    def _build_ui(self) -> None:
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)

        loading_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        loading_box.set_valign(Gtk.Align.CENTER)
        loading_box.set_halign(Gtk.Align.CENTER)
        loading_box.set_vexpand(True)
        sp = Gtk.Spinner()
        sp.set_size_request(48, 48)
        sp.start()
        lbl = Gtk.Label(label="Caricamento pagelle…")
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
        empty.set_icon_name("x-office-document-symbolic")
        empty.set_title("Nessuna pagella disponibile")
        empty.set_description("Le pagelle verranno mostrate qui quando saranno disponibili.")
        self._stack.add_named(empty, "empty")

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        clamp = Adw.Clamp()
        clamp.set_maximum_size(700)
        clamp.set_margin_top(12)
        clamp.set_margin_bottom(12)
        clamp.set_margin_start(12)
        clamp.set_margin_end(12)
        self._box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        clamp.set_child(self._box)
        scroll.set_child(clamp)
        self._stack.add_named(scroll, "content")

        self._stack.set_visible_child_name("loading")
        self.set_child(self._stack)

    def refresh(self) -> None:
        self._stack.set_visible_child_name("loading")
        self._load()

    def _load(self) -> None:
        def worker():
            try:
                docs = self._client.get_documents()
                GLib.idle_add(self._populate, docs)
            except Exception as exc:
                GLib.idle_add(self._show_error, str(exc))
        threading.Thread(target=worker, daemon=True).start()

    def _populate(self, docs: list) -> bool:
        child = self._box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._box.remove(child)
            child = nxt

        if not docs:
            self._stack.set_visible_child_name("empty")
            return False

        download_docs = [d for d in docs if d.get("type") == "download"]
        link_docs     = [d for d in docs if d.get("type") == "link"]

        if download_docs:
            group = Adw.PreferencesGroup()
            group.set_title("Pagelle scaricabili (PDF)")
            for doc in download_docs:
                group.add(self._make_download_row(doc))
            self._box.append(group)

        if link_docs:
            group = Adw.PreferencesGroup()
            group.set_title("Report e pagelle web")
            for doc in link_docs:
                group.add(self._make_link_row(doc))
            self._box.append(group)

        self._stack.set_visible_child_name("content")
        return False

    def _make_download_row(self, doc: dict) -> Adw.ActionRow:
        desc     = (doc.get("desc") or "Pagella").strip()
        doc_hash = doc.get("hash", "")
        sessione = (doc.get("sessione") or "").strip()

        row = Adw.ActionRow()
        row.set_title(desc)
        row.set_subtitle(f"PDF{f'  ·  {sessione}' if sessione else ''}")
        row.add_prefix(Gtk.Image.new_from_icon_name("x-office-document-symbolic"))

        btn = Gtk.Button()
        btn.set_icon_name("folder-download-symbolic")
        btn.set_tooltip_text("Scarica e apri")
        btn.add_css_class("flat")
        btn.set_valign(Gtk.Align.CENTER)
        btn.connect("clicked", lambda _b, h=doc_hash, d=desc, r=row: self._download(h, d, _b, r))
        row.add_suffix(btn)
        return row

    def _make_link_row(self, doc: dict) -> Adw.ActionRow:
        desc     = (doc.get("desc") or "Report").strip()
        url      = doc.get("url", "")
        sessione = (doc.get("sessione") or "").strip()

        row = Adw.ActionRow()
        row.set_title(desc)
        row.set_subtitle(f"Visualizza{f'  ·  {sessione}' if sessione else ''}")
        row.add_prefix(Gtk.Image.new_from_icon_name("web-browser-symbolic"))

        if _WEBKIT_AVAILABLE:
            btn = Gtk.Button()
            btn.set_icon_name("web-browser-symbolic")
            btn.set_tooltip_text("Apri nell'app")
            btn.add_css_class("flat")
            btn.set_valign(Gtk.Align.CENTER)
            btn.connect("clicked", lambda _b, u=url, d=desc: self._open_in_app(u, d))
            row.add_suffix(btn)
        else:
            btn = Gtk.Button()
            btn.set_icon_name("external-link-symbolic")
            btn.set_tooltip_text("Apri nel browser")
            btn.add_css_class("flat")
            btn.set_valign(Gtk.Align.CENTER)
            btn.connect("clicked", lambda _b, u=url: _open_url(u))
            row.add_suffix(btn)

        return row

    def _open_in_app(self, url: str, title: str) -> None:
        win = self.get_root()
        dialog = PagellaWebDialog(url, title, self._client.token)
        dialog.present(win)

    def _download(self, doc_hash: str, desc: str,
                  btn: Gtk.Button, row: Adw.ActionRow) -> None:
        btn.set_sensitive(False)
        sp = Gtk.Spinner()
        sp.start()
        sp.set_valign(Gtk.Align.CENTER)
        btn.set_child(sp)

        def worker():
            try:
                data, name = self._client.download_document(doc_hash, f"{desc}.pdf")
                GLib.idle_add(_on_done, data, name, None)
            except Exception as exc:
                GLib.idle_add(_on_done, None, "", str(exc))

        def _on_done(data, name, error):
            btn.set_icon_name("folder-download-symbolic")
            btn.set_sensitive(True)
            if error:
                if "not available" in error.lower() or "no content" in error.lower():
                    row.set_subtitle("PDF non ancora disponibile — riprova più tardi")
                else:
                    row.set_subtitle(f"Errore: {error}")
                return
            os.makedirs(_DOWNLOAD_DIR, exist_ok=True)
            safe = "".join(c for c in name if c.isalnum() or c in "._- ()").strip() or "pagella.pdf"
            path = os.path.join(_DOWNLOAD_DIR, safe)
            with open(path, "wb") as f:
                f.write(data)
            _open_file(path)

        threading.Thread(target=worker, daemon=True).start()

    def _show_error(self, msg: str) -> bool:
        self._error_page.set_description(msg)
        self._stack.set_visible_child_name("error")
        return False
