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


def _save_and_open(data: bytes, filename: str) -> None:
    os.makedirs(_DOWNLOAD_DIR, exist_ok=True)
    safe = "".join(c for c in filename if c.isalnum() or c in "._- ()").strip() or "allegato"
    path = os.path.join(_DOWNLOAD_DIR, safe)
    with open(path, "wb") as f:
        f.write(data)
    _open_file(path)


class NoticeboardView(Adw.Bin):
    def __init__(self, client):
        super().__init__()
        self._client = client
        self._loaded = False
        self._build_ui()

    def _build_ui(self) -> None:
        self._toast_overlay = Adw.ToastOverlay()

        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)

        loading_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        loading_box.set_valign(Gtk.Align.CENTER)
        loading_box.set_halign(Gtk.Align.CENTER)
        loading_box.set_vexpand(True)
        sp = Gtk.Spinner()
        sp.set_size_request(48, 48)
        sp.start()
        lbl = Gtk.Label(label="Caricamento bacheca…")
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
        empty.set_icon_name("mail-read-symbolic")
        empty.set_title("Bacheca vuota")
        empty.set_description("Non ci sono comunicazioni in bacheca.")
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
        self._toast_overlay.set_child(self._stack)
        self.set_child(self._toast_overlay)

    def _show_toast(self, msg: str) -> None:
        toast = Adw.Toast.new(msg)
        toast.set_timeout(3)
        self._toast_overlay.add_toast(toast)

    def refresh(self) -> None:
        self._stack.set_visible_child_name("loading")
        self._load()

    def _load(self) -> None:
        def worker():
            try:
                items = self._client.get_noticeboard()
                GLib.idle_add(self._populate, items)
            except Exception as exc:
                GLib.idle_add(self._show_error, str(exc))
        threading.Thread(target=worker, daemon=True).start()

    def _populate(self, items: list) -> bool:
        child = self._box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._box.remove(child)
            child = nxt

        if not items:
            self._stack.set_visible_child_name("empty")
            return False

        items_sorted = sorted(items, key=lambda x: x.get("pubDT", ""), reverse=True)
        unread = [i for i in items_sorted if not i.get("readStatus", True)]
        read   = [i for i in items_sorted if i.get("readStatus", True)]

        for label, group_items in [
            (f"Non lette ({len(unread)})", unread),
            (f"Lette ({len(read)})", read),
        ]:
            if not group_items:
                continue
            group = Adw.PreferencesGroup()
            group.set_title(label)
            for item in group_items:
                group.add(self._make_notice_row(item))
            self._box.append(group)

        self._stack.set_visible_child_name("content")
        return False

    def _make_notice_row(self, item: dict):
        title      = (item.get("cntTitle") or "Comunicazione").strip()
        category   = (item.get("cntCategory") or "").strip()
        pub_date   = _fmt_date(item.get("pubDT", ""))
        unread     = not item.get("readStatus", True)
        attachments = item.get("attachments") or []
        needs_join   = bool(item.get("needJoin"))
        needs_action = any([needs_join, item.get("needReply"),
                            item.get("needFile"), item.get("needSign")])

        subtitle_parts = []
        if pub_date:
            subtitle_parts.append(pub_date)
        if category:
            subtitle_parts.append(category)
        if needs_action:
            subtitle_parts.append("azione richiesta")

        # Notices with attachments get an ExpanderRow
        if attachments:
            row = Adw.ExpanderRow()
            row.set_title(title)
            if subtitle_parts:
                row.set_subtitle("  ·  ".join(subtitle_parts))

            for att in attachments:
                fname    = (att.get("fileName") or "allegato").strip()
                att_num  = att.get("attachNum", 1)
                evt_code = item.get("evtCode", "")
                pub_id   = item.get("pubId", 0)
                row.add_row(self._make_attachment_row(fname, evt_code, pub_id, att_num, needs_join))
        else:
            row = Adw.ActionRow()
            row.set_title(title)
            if subtitle_parts:
                row.set_subtitle("  ·  ".join(subtitle_parts))

        # Unread indicator prefix
        if unread:
            dot = Gtk.Label(label="●")
            dot.add_css_class("accent")
            dot.set_valign(Gtk.Align.CENTER)
            row.add_prefix(dot)
        else:
            icon = Gtk.Image.new_from_icon_name("mail-read-symbolic")
            icon.set_opacity(0.4)
            icon.set_valign(Gtk.Align.CENTER)
            row.add_prefix(icon)

        if needs_action:
            badge = Gtk.Image.new_from_icon_name("dialog-warning-symbolic")
            badge.add_css_class("warning")
            badge.set_tooltip_text("Richiede azione (conferma lettura / risposta)")
            badge.set_valign(Gtk.Align.CENTER)
            row.add_suffix(badge)

        return row

    def _make_attachment_row(self, filename: str, evt_code: str,
                             pub_id: int, attach_num: int,
                             needs_join: bool = False) -> Adw.ActionRow:
        row = Adw.ActionRow()
        row.set_title(filename)

        icon = Gtk.Image.new_from_icon_name("mail-attachment-symbolic")
        icon.set_valign(Gtk.Align.CENTER)
        row.add_prefix(icon)

        btn = Gtk.Button()
        btn.set_icon_name("folder-download-symbolic")
        btn.set_tooltip_text("Scarica e apri")
        btn.add_css_class("flat")
        btn.set_valign(Gtk.Align.CENTER)
        btn.connect(
            "clicked",
            lambda _b, fn=filename, ec=evt_code, pid=pub_id, an=attach_num, nj=needs_join, r=row:
                self._download_attachment(fn, ec, pid, an, _b, r, nj),
        )
        row.add_suffix(btn)
        return row

    def _download_attachment(self, filename: str, evt_code: str,
                              pub_id: int, attach_num: int,
                              btn: Gtk.Button, row: Adw.ActionRow,
                              needs_join: bool = False) -> None:
        btn.set_sensitive(False)
        sp = Gtk.Spinner()
        sp.start()
        sp.set_valign(Gtk.Align.CENTER)
        btn.set_child(sp)

        def worker():
            try:
                data, name = self._client.download_noticeboard_attachment(
                    evt_code, pub_id, attach_num, filename, need_join=needs_join
                )
                GLib.idle_add(_on_done, data, name or filename, None)
            except Exception as exc:
                GLib.idle_add(_on_done, None, filename, str(exc))

        def _on_done(data, name, error):
            btn.set_icon_name("folder-download-symbolic")
            btn.set_sensitive(True)
            if error:
                row.set_subtitle(f"⚠ {error[:120]}")
                self._show_toast(f"Errore download: {error[:80]}")
                return
            row.set_subtitle("")
            self._show_toast(f"Aperto: {name}")
            _save_and_open(data, name)

        threading.Thread(target=worker, daemon=True).start()

    def _show_error(self, msg: str) -> bool:
        self._error_page.set_description(msg)
        self._stack.set_visible_child_name("error")
        return False
