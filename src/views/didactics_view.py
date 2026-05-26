import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gio
import threading
import os
import subprocess
from datetime import datetime

_MONTHS_IT = [
    "", "gen", "feb", "mar", "apr", "mag", "giu",
    "lug", "ago", "set", "ott", "nov", "dic",
]
_DOWNLOAD_DIR = os.path.join(GLib.get_user_cache_dir(), "classeviva", "downloads")

_MIME_ICONS = {
    "application/pdf":                  "x-office-document-symbolic",
    "application/msword":               "x-office-document-symbolic",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "x-office-document-symbolic",
    "application/vnd.ms-excel":         "x-office-spreadsheet-symbolic",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":       "x-office-spreadsheet-symbolic",
    "application/vnd.ms-powerpoint":    "x-office-presentation-symbolic",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "x-office-presentation-symbolic",
    "image/jpeg":   "image-x-generic-symbolic",
    "image/png":    "image-x-generic-symbolic",
    "video/mp4":    "video-x-generic-symbolic",
    "audio/mpeg":   "audio-x-generic-symbolic",
    "text/plain":   "text-x-generic-symbolic",
}
_DEFAULT_ICON = "text-x-generic-symbolic"
_LINK_ICON    = "web-browser-symbolic"


def _fmt_date(s: str) -> str:
    try:
        dt = datetime.fromisoformat(s[:19])
        return f"{dt.day} {_MONTHS_IT[dt.month]} {dt.year}"
    except Exception:
        return s[:10] if s else ""


def _open_file(path: str) -> None:
    try:
        Gio.AppInfo.launch_default_for_uri(f"file://{path}", None)
    except Exception:
        subprocess.Popen(["xdg-open", path])


def _open_url(url: str) -> None:
    try:
        Gio.AppInfo.launch_default_for_uri(url, None)
    except Exception:
        subprocess.Popen(["xdg-open", url])


def _save_and_open(data: bytes, filename: str) -> None:
    os.makedirs(_DOWNLOAD_DIR, exist_ok=True)
    safe = "".join(c for c in filename if c.isalnum() or c in "._- ()").strip() or "file"
    path = os.path.join(_DOWNLOAD_DIR, safe)
    with open(path, "wb") as f:
        f.write(data)
    _open_file(path)


class DidacticsView(Adw.Bin):
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
        lbl = Gtk.Label(label="Caricamento materiali…")
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
        empty.set_icon_name("folder-symbolic")
        empty.set_title("Nessun materiale")
        empty.set_description("I professori non hanno ancora condiviso materiali.")
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
                items = self._client.get_didactics()
                GLib.idle_add(self._populate, items)
            except Exception as exc:
                GLib.idle_add(self._show_error, str(exc))
        threading.Thread(target=worker, daemon=True).start()

    def _populate(self, teachers: list) -> bool:
        child = self._box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._box.remove(child)
            child = nxt

        has_content = False

        for teacher in teachers:
            teacher_name = (teacher.get("teacherName") or "Professore").title()
            folders = teacher.get("folders") or []
            if not folders:
                continue

            teacher_group = Adw.PreferencesGroup()
            teacher_group.set_title(teacher_name)

            for folder in folders:
                folder_name = (folder.get("folderName") or "Cartella").strip()
                contents    = folder.get("contents") or []
                last_share  = _fmt_date(folder.get("lastShareDT", ""))
                if not contents:
                    continue

                expander = Adw.ExpanderRow()
                expander.set_title(folder_name)
                expander.set_subtitle(
                    f"{len(contents)} element{'o' if len(contents)==1 else 'i'}"
                    + (f"  ·  {last_share}" if last_share else "")
                )
                folder_icon = Gtk.Image.new_from_icon_name("folder-symbolic")
                folder_icon.set_valign(Gtk.Align.CENTER)
                expander.add_prefix(folder_icon)

                for item in sorted(contents, key=lambda x: x.get("shareDT", ""), reverse=True):
                    expander.add_row(self._make_content_row(item))
                    has_content = True

                teacher_group.add(expander)

            self._box.append(teacher_group)

        if not has_content:
            self._stack.set_visible_child_name("empty")
        else:
            self._stack.set_visible_child_name("content")
        return False

    def _make_content_row(self, item: dict) -> Adw.ActionRow:
        name       = (item.get("contentName") or "File senza nome").strip()
        mime       = (item.get("mimeType") or "").strip()
        ctype      = (item.get("contentType") or "").lower()
        share_date = _fmt_date(item.get("shareDT", ""))
        content_id = item.get("contentId")
        object_id  = item.get("objectId") or ""
        is_link    = ctype == "link"

        icon_name = _LINK_ICON if is_link else _MIME_ICONS.get(mime, _DEFAULT_ICON)

        row = Adw.ActionRow()
        row.set_title(name)
        if share_date:
            row.set_subtitle(share_date)

        file_icon = Gtk.Image.new_from_icon_name(icon_name)
        file_icon.set_valign(Gtk.Align.CENTER)
        row.add_prefix(file_icon)

        # Action button: open link vs download file
        btn = Gtk.Button()
        btn.set_valign(Gtk.Align.CENTER)
        btn.add_css_class("flat")

        if is_link:
            btn.set_icon_name("web-browser-symbolic")
            btn.set_tooltip_text("Apri nel browser")
            url = object_id if object_id.startswith("http") else f"https://{object_id}"
            btn.connect("clicked", lambda _b, u=url: _open_url(u))
        else:
            btn.set_icon_name("folder-download-symbolic")
            btn.set_tooltip_text("Scarica e apri")
            btn.connect(
                "clicked",
                lambda _b, n=name, cid=content_id, r=row:
                    self._download_file(n, cid, _b, r),
            )

        row.add_suffix(btn)
        return row

    def _download_file(self, filename: str, content_id,
                       btn: Gtk.Button, row: Adw.ActionRow) -> None:
        if content_id is None:
            row.set_subtitle("ID file non disponibile")
            return

        btn.set_sensitive(False)
        sp = Gtk.Spinner()
        sp.start()
        sp.set_valign(Gtk.Align.CENTER)
        btn.set_child(sp)

        def worker():
            try:
                data, name = self._client.download_didactics_file(content_id, filename)
                GLib.idle_add(_on_done, data, name or filename, None)
            except Exception as exc:
                GLib.idle_add(_on_done, None, filename, str(exc))

        def _on_done(data, name, error):
            btn.set_icon_name("folder-download-symbolic")
            btn.set_sensitive(True)
            if error:
                row.set_subtitle(f"Errore: {error}")
                return
            _save_and_open(data, name)

        threading.Thread(target=worker, daemon=True).start()

    def _show_error(self, msg: str) -> bool:
        self._error_page.set_description(msg)
        self._stack.set_visible_child_name("error")
        return False
