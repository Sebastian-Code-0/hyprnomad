#!/usr/bin/env python3
"""Historial del portapapeles con filtros por tipo, vista previa y acciones rapidas."""
import os
import re
import signal
import subprocess
import sys
import threading
import time
from urllib.parse import unquote, urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# reutiliza helpers, glifos y constantes de pywal del launcher
sys.path.insert(0, os.path.join(BASE_DIR, "..", "launcher"))
import launcher as base  # noqa: E402

import gi  # noqa: E402

gi.require_version("GdkPixbuf", "2.0")
gi.require_version("GLibUnix", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, GLibUnix, Gtk, GtkLayerShell, Pango  # noqa: E402

GLib.set_prgname("clipboard")

CSS_PATH = os.path.join(BASE_DIR, "style.css")
CONF_PATH = os.path.join(BASE_DIR, "clipboard.conf")
DATA_DIR = os.path.join(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")), "clipboard")
TIMES_FILE = os.path.join(DATA_DIR, "times.log")
CACHE_DIR = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "clipboard")
IMG_DIR = os.path.join(CACHE_DIR, "img")
THUMB_DIR = os.path.join(CACHE_DIR, "thumbs")
PID_FILE = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "clipboard.pid")


def private_dir(path):
    """Crea el directorio solo accesible por el usuario (la caché puede contener datos privados)."""
    os.makedirs(path, exist_ok=True)
    os.chmod(path, 0o700)
CLIPHIST_DB = os.environ.get("CLIPHIST_DB")

PREVIEW_W, PREVIEW_H = 316, 164
THUMB_SIZE = 36
DEFAULT_MAX = 500

# id, etiqueta, icono (Nerd Font)
CATEGORIES = [
    ("todos", "Todos", ""),
    ("texto", "Texto", ""),
    ("imagen", "Imágenes", ""),
    ("archivo", "Archivos", ""),
    ("url", "URL's", ""),
]
KIND_LABEL = {"texto": "Texto", "imagen": "Imagen", "archivo": "Archivo", "url": "URL"}
COPY_TITLE = {"texto": "Texto copiado", "imagen": "Imagen copiada",
              "archivo": "Ruta copiada", "url": "URL copiada"}
KIND_GLYPH = {"texto": "", "imagen": "", "archivo": "", "url": ""}

GLYPH_COPY = ""
GLYPH_OPEN = ""
GLYPH_CLEAR = ""
GLYPH_TRASH = ""
GLYPH_DB = ""

# icono por dominio / tipo de archivo
DOMAIN_GLYPH = {
    "github.com": "", "youtube.com": "", "youtu.be": "",
    "twitter.com": "", "x.com": "", "reddit.com": "",
    "stackoverflow.com": "", "linkedin.com": "", "wikipedia.org": "",
}
MIME_GLYPH = [
    ("inode/directory", ""), ("image/", ""), ("audio/", ""),
    ("video/", ""), ("application/pdf", ""), ("application/zip", ""),
    ("application/x-tar", ""), ("application/gzip", ""), ("text/x-", ""),
    ("text/", ""),
]

# documentos que se abren con OnlyOffice
OFFICE_MIMES = [
    "application/vnd.ms-excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.oasis.opendocument.spreadsheet", "text/csv", "text/tab-separated-values",
    "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.oasis.opendocument.text", "application/rtf",
    "application/vnd.ms-powerpoint", "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.oasis.opendocument.presentation",
]

IMG_RE = re.compile(r"^\[\[ binary data (.+?) (\w+) (\d+)x(\d+) \]\]$")
URL_RE = re.compile(r"^(https?|ftp)://\S+$")


def human_size(n):
    if n < 1024:
        return f"{n} B"
    for unit in ("KB", "MB", "GB", "TB"):
        n /= 1024
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}"


def ago(ts):
    if not ts:
        return "—"
    d = int(time.time() - ts)
    if d < 45:
        return "ahora mismo"
    if d < 3600:
        return f"hace {max(1, d // 60)} min"
    if d < 86400:
        return f"hace {d // 3600} h"
    return f"hace {d // 86400} d"


def read_max_items():
    try:
        with open(CONF_PATH) as f:
            m = re.search(r"^MAX_ITEMS=(\d+)", f.read(), re.M)
            return int(m.group(1)) if m else DEFAULT_MAX
    except OSError:
        return DEFAULT_MAX


def cliphist(*args, data=None):
    cmd = ["cliphist"]
    if CLIPHIST_DB:
        cmd += ["-db-path", CLIPHIST_DB]
    cmd += ["-preview-width", "200", *args]
    out = subprocess.run(cmd, input=data, capture_output=True, timeout=15)
    return out.stdout if out.returncode == 0 else b""


def read_times():
    times = {}
    try:
        with open(TIMES_FILE) as f:
            for line in f:
                cid, _, ts = line.partition(" ")
                if cid.isdigit() and ts.strip().isdigit():
                    times[int(cid)] = int(ts)
    except OSError:
        pass
    return times


def write_times(times):
    private_dir(DATA_DIR)
    tmp = TIMES_FILE + ".tmp"
    with open(tmp, "w") as f:
        f.writelines(f"{cid} {ts}\n" for cid, ts in times.items())
    os.replace(tmp, TIMES_FILE)


def mime_glyph(mime):
    for prefix, glyph in MIME_GLYPH:
        if mime.startswith(prefix):
            return glyph
    return KIND_GLYPH["archivo"]


class Clip:
    def __init__(self, cid, preview, ts):
        self.id, self.preview, self.ts = cid, preview, ts
        self.show = True
        self.path = None
        self.glyph = ""
        img = IMG_RE.match(preview)
        if img:
            self.kind = "imagen"
            self.size_text, self.fmt = img.group(1), img.group(2)
            self.w, self.h = int(img.group(3)), int(img.group(4))
            self.name = f"imagen-{cid}.{self.fmt}"
            self.sub = f"{self.w}×{self.h} · {self.size_text}"
            self.search = f"imagen {self.fmt} {self.w}x{self.h}"
        elif URL_RE.match(preview):
            self.kind = "url"
            host = urlparse(preview).netloc.removeprefix("www.")
            self.name = host or preview
            self.sub = preview
            self.glyph = next((g for d, g in DOMAIN_GLYPH.items()
                               if host == d or host.endswith("." + d)), "")
            self.search = preview
        elif self._file_path():
            self.kind = "archivo"
            self.name = os.path.basename(self.path.rstrip("/")) or self.path
            self.sub = self.path
            self.search = self.path
            mime = ("inode/directory" if os.path.isdir(self.path)
                    else Gio.content_type_guess(self.path, None)[0])
            self.glyph = mime_glyph(mime) if os.path.exists(self.path) else ""
        else:
            self.kind = "texto"
            self.name = preview
            more = "+" if preview.endswith("…") else ""
            self.sub = f"Texto · {len(preview.rstrip('…'))}{more} caracteres"
            self.search = preview
        self.glyph = self.glyph or KIND_GLYPH[self.kind]
        self.search = self.search.casefold()

    def _file_path(self):
        p = self.preview
        if p.startswith("file://"):
            self.path = unquote(urlparse(p.split(" file://")[0]).path)
            return True
        if p.startswith(("/", "~/")):
            path = os.path.expanduser(p)
            if os.path.exists(path):
                self.path = path
                return True
        return False


class ClipboardWindow(Gtk.Window):
    def __init__(self):
        super().__init__()
        self.category = "todos"
        self.current = None
        self.max_items = read_max_items()
        self.info_cache = {}
        self.detail_timer = 0
        self.confirm_timer = 0
        self.clips = self._load_clips()

        self._setup_layer()
        self._load_css()
        self._build_ui()
        self._populate()
        GLib.timeout_add_seconds(30, self._tick_times)
        threading.Thread(target=self._housekeeping, daemon=True).start()

    # ---------- datos ----------
    def _load_clips(self):
        times = read_times()
        clips = []
        for line in cliphist("list").decode("utf-8", "replace").splitlines():
            cid, _, preview = line.partition("\t")
            if cid.isdigit():
                clips.append(Clip(int(cid), preview.strip(), times.get(int(cid))))
        # tiempos de elementos que ya no existen fuera del log
        alive = {c.id for c in clips}
        if any(cid not in alive for cid in times):
            write_times({cid: ts for cid, ts in times.items() if cid in alive})
        return clips

    def _housekeeping(self):
        """Borra miniaturas e imagenes en cache de elementos que ya no existen."""
        alive = {c.id for c in self.clips}
        for folder in (IMG_DIR, THUMB_DIR, CACHE_DIR):
            try:
                for name in os.listdir(folder):
                    head = re.match(r"(?:texto-)?(\d+)", name)
                    if head and os.path.isfile(os.path.join(folder, name)) \
                            and int(head.group(1)) not in alive:
                        os.remove(os.path.join(folder, name))
            except OSError:
                pass

    # ---------- ventana ----------
    def _setup_layer(self):
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_namespace(self, "clipboard")
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.EXCLUSIVE)
        GtkLayerShell.set_exclusive_zone(self, -1)
        for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM,
                     GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
            GtkLayerShell.set_anchor(self, edge, True)
        self.set_app_paintable(True)
        visual = self.get_screen().get_rgba_visual()
        if visual:
            self.set_visual(visual)
        self.connect("key-press-event", self.on_key)
        self.connect("destroy", lambda *_: Gtk.main_quit())

    def _load_css(self):
        screen = Gdk.Screen.get_default()
        Gtk.Settings.get_default().set_property("gtk-application-prefer-dark-theme", True)
        self.safe_provider = Gtk.CssProvider()
        self.safe_provider.load_from_data(
            f"@define-color text_safe {base.text_safe_color()};".encode())
        Gtk.StyleContext.add_provider_for_screen(
            screen, self.safe_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.main_provider = Gtk.CssProvider()
        self.main_provider.load_from_path(CSS_PATH)
        Gtk.StyleContext.add_provider_for_screen(
            screen, self.main_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self._reload_id = 0
        # referencia fuerte: si se pierde, el monitor deja de avisar
        self._pywal_monitor = Gio.File.new_for_path(base.PYWAL_DIR).monitor_directory(
            Gio.FileMonitorFlags.NONE, None)
        self._pywal_monitor.connect("changed", self._on_pywal_changed)

    def _on_pywal_changed(self, _mon, gfile, _other, _event):
        if gfile.get_basename() not in base.PYWAL_FILES:
            return
        if self._reload_id:
            GLib.source_remove(self._reload_id)
        self._reload_id = GLib.timeout_add(400, self._reload_css)

    def _reload_css(self):
        self._reload_id = 0
        self.safe_provider.load_from_data(
            f"@define-color text_safe {base.text_safe_color()};".encode())
        self.main_provider.load_from_path(CSS_PATH)
        return False

    # ---------- interfaz ----------
    def _build_ui(self):
        root = Gtk.EventBox()
        root.connect("button-press-event", self.on_backdrop_click)
        self.add(root)

        self.panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.panel.get_style_context().add_class("panel")
        self.panel.set_size_request(1030, 560)
        self.panel.set_hexpand(False)
        self.panel.set_vexpand(False)
        self.panel.set_halign(Gtk.Align.CENTER)
        self.panel.set_valign(Gtk.Align.CENTER)
        root.add(self.panel)

        self.panel.pack_start(self._build_header(), False, False, 0)
        self.panel.pack_start(Gtk.Separator(), False, False, 0)
        body = Gtk.Box()
        body.pack_start(self._build_sidebar(), False, False, 0)
        body.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 0)
        body.pack_start(self._build_list(), True, True, 0)
        body.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 0)
        body.pack_start(self._build_detail(), False, False, 0)
        self.panel.pack_start(body, True, True, 0)

    def _build_header(self):
        header = Gtk.Box()
        header.get_style_context().add_class("top-bar")
        header.pack_start(base.glyph_label(base.GLYPH_ARCH, "logo"), False, False, 0)

        note = Gtk.Label(label="Historial de portapapeles")
        note.get_style_context().add_class("header-note")
        header.pack_end(note, False, False, 0)

        search = Gtk.Box(spacing=8)
        search.get_style_context().add_class("search-box")
        search.set_size_request(420, -1)
        search.pack_start(base.glyph_label(base.GLYPH_SEARCH, "search-glyph"), False, False, 0)
        self.search = Gtk.Entry()
        self.search.set_has_frame(False)
        self.search.connect("changed", self.on_search_changed)
        # placeholder propio: GTK3 oculta el nativo al tener foco
        self.placeholder = Gtk.Label(label="Buscar en el historial...", xalign=0)
        self.placeholder.get_style_context().add_class("placeholder")
        self.placeholder.set_margin_start(2)
        overlay = Gtk.Overlay()
        overlay.add(self.search)
        overlay.add_overlay(self.placeholder)
        overlay.set_overlay_pass_through(self.placeholder, True)
        search.pack_start(overlay, True, True, 0)
        header.set_center_widget(search)
        return header

    @staticmethod
    def _two_line_button(glyph, text, hint):
        btn = Gtk.Button()
        btn.set_relief(Gtk.ReliefStyle.NONE)
        btn.get_style_context().add_class("action-btn")
        box = Gtk.Box(spacing=12)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        col.set_valign(Gtk.Align.CENTER)
        btn.label = Gtk.Label(label=text, xalign=0)
        btn.hint = Gtk.Label(label=hint, xalign=0)
        btn.hint.get_style_context().add_class("hint")
        for lbl in (btn.label, btn.hint):
            lbl.set_ellipsize(Pango.EllipsizeMode.END)
        col.pack_start(btn.label, False, False, 0)
        col.pack_start(btn.hint, False, False, 0)
        box.pack_start(base.glyph_label(glyph, "btn-glyph"), False, False, 0)
        box.pack_start(col, True, True, 0)
        btn.add(box)
        return btn

    def _build_sidebar(self):
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        side.get_style_context().add_class("cats")

        self.cat_list = Gtk.ListBox()
        self.cat_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.cat_rows = {}
        for cid, label, glyph in CATEGORIES:
            row = Gtk.ListBoxRow()
            row.cat_id = cid
            box = Gtk.Box(spacing=12)
            box.pack_start(base.glyph_label(glyph, "cat-glyph"), False, False, 0)
            box.pack_start(Gtk.Label(label=label, xalign=0), True, True, 0)
            count = Gtk.Label(label="0")
            count.get_style_context().add_class("cat-count")
            box.pack_end(count, False, False, 0)
            row.add(box)
            row.count_label = count
            self.cat_rows[cid] = row
            self.cat_list.add(row)
        self.cat_list.connect("row-selected", self.on_category_selected)
        side.pack_start(self.cat_list, False, False, 0)

        side.pack_start(Gtk.Separator(), False, False, 12)
        title = Gtk.Label(label="ACCIONES RÁPIDAS", xalign=0)
        title.get_style_context().add_class("section-title")
        side.pack_start(title, False, False, 4)

        actions = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.btn_clear = self._two_line_button(GLYPH_CLEAR, "Limpiar historial", "Alt + Supr")
        self.btn_clear.connect("clicked", lambda *_: self.clear_history())
        self.btn_delete = self._two_line_button(GLYPH_TRASH, "Eliminar seleccionado", "Ctrl + Supr")
        self.btn_delete.connect("clicked", lambda *_: self.delete_selected())
        actions.pack_start(self.btn_clear, False, False, 0)
        actions.pack_start(self.btn_delete, False, False, 0)
        side.pack_start(actions, False, False, 0)

        footer = Gtk.Box(spacing=10)
        footer.set_valign(Gtk.Align.END)
        footer.set_tooltip_text("Al superar el límite se eliminan los elementos más antiguos")
        footer.pack_start(base.glyph_label(GLYPH_DB, "cat-glyph"), False, False, 0)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.total_label = Gtk.Label(xalign=0)
        self.limit_label = Gtk.Label(xalign=0)
        self.limit_label.get_style_context().add_class("hint")
        col.pack_start(self.total_label, False, False, 0)
        col.pack_start(self.limit_label, False, False, 0)
        footer.pack_start(col, True, True, 0)
        side.pack_end(footer, True, True, 0)
        self.footer = footer
        return base.Launcher._fixed_column(side, 262)

    def _build_list(self):
        self.scroller = Gtk.ScrolledWindow()
        self.scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroller.set_overlay_scrolling(False)
        self.scroller.get_style_context().add_class("list-area")

        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.set_activate_on_single_click(False)
        self.listbox.set_margin_end(8)
        self.listbox.set_filter_func(lambda row: row.clip.show)
        self.listbox.connect("row-selected", self.on_row_selected)
        self.listbox.connect("row-activated", lambda _lb, row: self.copy(row.clip))
        self.empty_label = Gtk.Label()
        self.empty_label.get_style_context().add_class("empty")
        self.empty_label.set_justify(Gtk.Justification.CENTER)
        self.empty_label.show()
        self.listbox.set_placeholder(self.empty_label)
        self.scroller.add(self.listbox)
        return self.scroller

    def _build_detail(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        page.get_style_context().add_class("detail")
        page.set_border_width(16)

        # marco de tamaño fijo: la vista previa nunca lo agranda ni lo encoge
        frame = Gtk.ScrolledWindow()
        frame.set_policy(Gtk.PolicyType.EXTERNAL, Gtk.PolicyType.EXTERNAL)
        base.lock_scroll(frame)
        frame.set_size_request(-1, PREVIEW_H)
        frame.get_style_context().add_class("preview-frame")
        self.pv_stack = Gtk.Stack()
        self.pv_image = Gtk.Image()
        self.pv_text = Gtk.Label(xalign=0, yalign=0)
        self.pv_text.get_style_context().add_class("preview-text")
        self.pv_text.set_line_wrap(True)
        self.pv_text.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.pv_text.set_max_width_chars(36)
        self.pv_text.set_lines(9)
        self.pv_text.set_ellipsize(Pango.EllipsizeMode.END)
        self.pv_text.set_margin_start(14)
        self.pv_text.set_margin_end(14)
        self.pv_text.set_margin_top(12)
        glyph_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        glyph_page.set_valign(Gtk.Align.CENTER)
        self.pv_glyph = base.glyph_label("", "big-glyph")
        self.pv_caption = Gtk.Label()
        self.pv_caption.get_style_context().add_class("d-desc")
        self.pv_caption.set_line_wrap(True)
        self.pv_caption.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.pv_caption.set_max_width_chars(34)
        self.pv_caption.set_lines(3)
        self.pv_caption.set_ellipsize(Pango.EllipsizeMode.END)
        self.pv_caption.set_justify(Gtk.Justification.CENTER)
        glyph_page.pack_start(self.pv_glyph, False, False, 0)
        glyph_page.pack_start(self.pv_caption, False, False, 0)
        self.pv_stack.add_named(self.pv_image, "image")
        # la altura del texto no debe agrandar el marco fijo
        text_page = Gtk.ScrolledWindow()
        text_page.set_policy(Gtk.PolicyType.EXTERNAL, Gtk.PolicyType.EXTERNAL)
        base.lock_scroll(text_page)
        text_page.add(self.pv_text)
        self.pv_stack.add_named(text_page, "text")
        self.pv_stack.add_named(glyph_page, "glyph")
        frame.add(self.pv_stack)
        page.pack_start(frame, False, False, 0)

        kind = Gtk.Box(spacing=8)
        self.kind_glyph = base.glyph_label("", "cat-glyph")
        self.kind_label = Gtk.Label(xalign=0)
        self.kind_label.get_style_context().add_class("kind-title")
        kind.pack_start(self.kind_glyph, False, False, 0)
        kind.pack_start(self.kind_label, False, False, 0)
        page.pack_start(kind, False, False, 0)

        self.meta_label = Gtk.Label(xalign=0)
        self.meta_label.get_style_context().add_class("d-generic")
        self.meta_label.set_ellipsize(Pango.EllipsizeMode.END)
        page.pack_start(self.meta_label, False, False, 0)
        self.name_label = Gtk.Label(xalign=0)
        self.name_label.get_style_context().add_class("d-name")
        self.name_label.set_ellipsize(Pango.EllipsizeMode.END)
        page.pack_start(self.name_label, False, False, 0)

        buttons = Gtk.Box(spacing=8, homogeneous=True)
        self.btn_copy = base.action_button(GLYPH_COPY, "Copiar", "primary", "↵")
        self.btn_copy.connect("clicked", lambda *_: self.current and self.copy(self.current))
        self.btn_open = base.action_button(GLYPH_OPEN, "Abrir", hint="Ctrl+O")
        self.btn_open.connect("clicked", lambda *_: self.current and self.open_clip(self.current))
        buttons.pack_start(self.btn_copy, True, True, 0)
        buttons.pack_start(self.btn_open, True, True, 0)
        page.pack_start(buttons, False, False, 4)

        bottom = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        page.pack_end(bottom, False, False, 0)
        bottom.pack_start(Gtk.Separator(), False, False, 4)
        title = Gtk.Label(label="DETALLES", xalign=0)
        title.get_style_context().add_class("section-title")
        bottom.pack_start(title, False, False, 0)
        self.det_path = self._detail_field("Ruta", bottom, lines=2)
        pair = Gtk.Box(spacing=12, homogeneous=True)
        self.det_type = self._detail_field("Tipo", pair)
        self.det_size = self._detail_field("Tamaño", pair)
        bottom.pack_start(pair, False, False, 0)
        return base.Launcher._fixed_column(page, 340)

    @staticmethod
    def _detail_field(key, parent, lines=1):
        item = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        k = Gtk.Label(label=key, xalign=0)
        k.get_style_context().add_class("det-key")
        v = Gtk.Label(xalign=0, yalign=0)
        v.get_style_context().add_class("det-val")
        v.set_line_wrap(True)
        v.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        v.set_max_width_chars(34 if lines > 1 else 16)
        v.set_lines(lines)
        v.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        item.pack_start(k, False, False, 0)
        item.pack_start(v, False, False, 0)
        parent.pack_start(item, True, True, 0)
        return v

    # ---------- lista ----------
    def _populate(self):
        for clip in self.clips:
            self.listbox.add(self._build_row(clip))
        self.update_counts()
        self.show_all()
        self.cat_list.select_row(self.cat_rows["todos"])
        self.search.grab_focus()
        threading.Thread(target=self._make_thumbs, daemon=True).start()

    def _build_row(self, clip):
        row = Gtk.ListBoxRow()
        row.clip = clip
        clip.row = row
        box = Gtk.Box(spacing=12)
        row.icon_box = Gtk.Box()
        row.icon_box.set_size_request(THUMB_SIZE, THUMB_SIZE)
        row.icon_box.pack_start(base.glyph_label(clip.glyph, "row-glyph"), True, True, 0)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        texts.set_valign(Gtk.Align.CENTER)
        name = Gtk.Label(label=clip.name, xalign=0)
        name.get_style_context().add_class("app-name")
        name.set_ellipsize(Pango.EllipsizeMode.END)
        sub = Gtk.Label(label=clip.sub, xalign=0)
        sub.get_style_context().add_class("app-sub")
        sub.set_ellipsize(Pango.EllipsizeMode.MIDDLE if clip.kind in ("archivo", "url")
                          else Pango.EllipsizeMode.END)
        texts.pack_start(name, False, False, 0)
        texts.pack_start(sub, False, False, 0)
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        side.set_valign(Gtk.Align.CENTER)
        chip = Gtk.Label(label=KIND_LABEL[clip.kind].lower())
        chip.get_style_context().add_class("chip")
        chip.get_style_context().add_class(f"chip-{clip.kind}")
        chip.set_halign(Gtk.Align.END)
        row.time_label = Gtk.Label(label=ago(clip.ts))
        row.time_label.get_style_context().add_class("time")
        row.time_label.set_halign(Gtk.Align.END)
        side.pack_start(chip, False, False, 0)
        side.pack_start(row.time_label, False, False, 0)
        box.pack_start(row.icon_box, False, False, 0)
        box.pack_start(texts, True, True, 0)
        box.pack_end(side, False, False, 0)
        row.add(box)
        return row

    def _tick_times(self):
        for clip in self.clips:
            clip.row.time_label.set_text(ago(clip.ts))
        return True

    def _make_thumbs(self):
        """Miniaturas de imagenes en segundo plano (cache en disco)."""
        private_dir(CACHE_DIR)
        private_dir(THUMB_DIR)
        for clip in self.clips:
            if clip.kind != "imagen":
                continue
            path = os.path.join(THUMB_DIR, f"{clip.id}_{clip.w}x{clip.h}.png")
            try:
                if not os.path.exists(path):
                    loader = GdkPixbuf.PixbufLoader()
                    loader.write(cliphist("decode", data=f"{clip.id}\t".encode()))
                    loader.close()
                    pb = loader.get_pixbuf()
                    side = min(pb.get_width(), pb.get_height())
                    pb = pb.new_subpixbuf((pb.get_width() - side) // 2,
                                          (pb.get_height() - side) // 2, side, side)
                    pb.scale_simple(THUMB_SIZE, THUMB_SIZE, GdkPixbuf.InterpType.BILINEAR) \
                        .savev(path, "png", [], [])
                GLib.idle_add(self._set_thumb, clip, path)
            except Exception:
                continue

    @staticmethod
    def _set_thumb(clip, path):
        box = clip.row.icon_box
        for child in box.get_children():
            box.remove(child)
        box.pack_start(Gtk.Image.new_from_file(path), True, True, 0)
        box.show_all()
        return False

    def update_counts(self):
        totals = {cid: 0 for cid, _, _ in CATEGORIES}
        for clip in self.clips:
            totals["todos"] += 1
            totals[clip.kind] += 1
        for cid, row in self.cat_rows.items():
            row.count_label.set_text(str(totals[cid]))
            ctx = row.get_style_context()
            if totals[cid] == 0:
                ctx.add_class("empty-cat")
            else:
                ctx.remove_class("empty-cat")
        total = totals["todos"]
        self.total_label.set_text(f"{total} elemento{'s' if total != 1 else ''} en total")
        self.limit_label.set_text(f"Límite máximo: {self.max_items}")
        ctx = self.footer.get_style_context()
        if total >= self.max_items * 0.9:
            ctx.add_class("warn")
        else:
            ctx.remove_class("warn")
        self.btn_clear.set_sensitive(total > 0)

    def refilter(self, keep_selection=False):
        query = self.search.get_text().strip().casefold()
        if not self.clips:
            self.empty_label.set_text("El historial está vacío\nCopia algo para empezar")
        elif query:
            self.empty_label.set_text("Sin resultados")
        else:
            self.empty_label.set_text("No hay elementos de este tipo")
        visible = []
        for clip in self.clips:
            clip.show = ((self.category == "todos" or clip.kind == self.category)
                         and (not query or query in clip.search))
            if clip.show:
                visible.append(clip)
        self.ordered = visible
        self.listbox.invalidate_filter()
        keep = keep_selection and self.current in visible
        target = self.current if keep else (visible[0] if visible else None)
        if target:
            self.listbox.select_row(target.row)
            GLib.idle_add(self.scroll_to, target.row)
        else:
            self.listbox.unselect_all()
            self.current = None
            self.update_detail()
        if not keep_selection:
            self.scroller.get_vadjustment().set_value(0)

    def scroll_to(self, row):
        adj = self.scroller.get_vadjustment()
        coords = row.translate_coordinates(self.listbox, 0, 0)
        if coords is None:
            return False
        y, h = coords[1], row.get_allocated_height()
        if y < adj.get_value():
            adj.set_value(y)
        elif y + h > adj.get_value() + adj.get_page_size():
            adj.set_value(y + h - adj.get_page_size())
        return False

    # ---------- panel de detalle ----------
    def update_detail(self):
        clip = self.current
        for btn in (self.btn_copy, self.btn_open, self.btn_delete):
            btn.set_sensitive(clip is not None)
        if self.detail_timer:
            GLib.source_remove(self.detail_timer)
            self.detail_timer = 0
        if not clip:
            self.kind_glyph.set_text("")
            self.kind_label.set_text("")
            self.meta_label.set_text("")
            self.name_label.set_text("")
            for lbl in (self.det_path, self.det_type, self.det_size):
                lbl.set_text("—")
            self._show_glyph("", "Selecciona un elemento")
            return
        self.kind_glyph.set_text(KIND_GLYPH[clip.kind])
        self.kind_label.set_text("Imagen" if clip.kind == "imagen" else KIND_LABEL[clip.kind])
        self.meta_label.set_text(clip.sub if clip.kind == "imagen" else "Cargando...")
        self.name_label.set_text(clip.name)
        info = self.info_cache.get(clip.id)
        if info:
            self._apply_info(clip, info)
            return
        for lbl in (self.det_path, self.det_type, self.det_size):
            lbl.set_text("…")
        self._show_glyph(clip.glyph, "")
        # pequeña espera: al mantener flecha no se decodifica cada elemento
        self.detail_timer = GLib.timeout_add(70, self._start_load, clip)

    def _start_load(self, clip):
        self.detail_timer = 0
        threading.Thread(target=self._load_info, args=(clip,), daemon=True).start()
        return False

    def _load_info(self, clip):
        try:
            info = self._materialize(clip)
        except Exception as err:
            info = {"meta": "No se pudo cargar", "path": "—", "mime": "—",
                    "size": "—", "glyph": clip.glyph, "caption": str(err)}
        self.info_cache[clip.id] = info
        if len(self.info_cache) > 40:
            self.info_cache.pop(next(iter(self.info_cache)))
        GLib.idle_add(self._apply_if_current, clip, info)

    def _apply_if_current(self, clip, info):
        if clip is self.current:
            self._apply_info(clip, info)
        return False

    def _apply_info(self, clip, info):
        self.meta_label.set_text(info["meta"])
        self.det_path.set_text(info["path"])
        self.det_path.set_tooltip_text(info["path"])
        self.det_type.set_text(info["mime"])
        self.det_size.set_text(info["size"])
        if info.get("pixbuf"):
            self.pv_image.set_from_pixbuf(info["pixbuf"])
            self.pv_stack.set_visible_child_name("image")
        elif info.get("text") is not None:
            self.pv_text.set_text(info["text"])
            self.pv_stack.set_visible_child_name("text")
        else:
            self._show_glyph(info["glyph"], info.get("caption", ""))

    def _show_glyph(self, glyph, caption):
        self.pv_glyph.set_text(glyph)
        self.pv_caption.set_text(caption)
        self.pv_stack.set_visible_child_name("glyph")

    def _decode(self, clip):
        return cliphist("decode", data=f"{clip.id}\t".encode())

    def image_path(self, clip):
        """Extrae la imagen del historial a un archivo (cache) y devuelve su ruta."""
        private_dir(CACHE_DIR)
        private_dir(IMG_DIR)
        path = os.path.join(IMG_DIR, f"{clip.id}-{clip.w}x{clip.h}.{clip.fmt}")
        if not os.path.exists(path):
            with open(path, "wb") as f:
                f.write(self._decode(clip))
        return path

    def _materialize(self, clip):
        """Datos de la vista previa y los detalles (corre en un hilo)."""
        if clip.kind == "imagen":
            path = self.image_path(clip)
            with open(path, "rb") as f:
                mime = Gio.content_type_guess(None, f.read(4096))[0]
            return {
                "pixbuf": GdkPixbuf.Pixbuf.new_from_file_at_scale(path, PREVIEW_W, PREVIEW_H, True),
                "meta": f"{clip.w}×{clip.h} · {human_size(os.path.getsize(path))}",
                "path": path, "mime": mime, "size": human_size(os.path.getsize(path)),
            }
        data = self._decode(clip)
        text = data.decode("utf-8", "replace")
        if clip.kind == "url":
            url = text.strip()
            return {
                "meta": f"Enlace · {urlparse(url).scheme.upper() or 'URL'}", "path": url,
                "mime": "text/uri-list", "size": human_size(len(data)),
                "glyph": clip.glyph, "caption": url,
            }
        if clip.kind == "archivo":
            return self._file_info(clip)
        lines = text.count("\n") + 1
        return {
            "text": text[:800],
            "meta": f"{len(text)} caracteres · {lines} línea{'s' if lines != 1 else ''}",
            "path": f"Portapapeles (entrada #{clip.id})", "mime": "text/plain",
            "size": human_size(len(data)),
        }

    def _file_info(self, clip):
        path = clip.path
        if not os.path.exists(path):
            return {"meta": "El archivo ya no existe", "path": path, "mime": "—",
                    "size": "—", "glyph": clip.glyph, "caption": clip.name}
        isdir = os.path.isdir(path)
        mime = "inode/directory" if isdir else Gio.content_type_guess(path, None)[0]
        size = "—" if isdir else human_size(os.path.getsize(path))
        info = {"meta": "Carpeta" if isdir else size, "path": path, "mime": mime,
                "size": size, "glyph": mime_glyph(mime), "caption": clip.name}
        if mime.startswith("image/"):
            try:
                info["pixbuf"] = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    path, PREVIEW_W, PREVIEW_H, True)
                w, h = GdkPixbuf.Pixbuf.get_file_info(path)[1:]
                info["meta"] = f"{w}×{h} · {size}"
            except GLib.Error:
                pass
        elif Gio.content_type_is_a(mime, "text/plain") and not isdir:
            with open(path, "rb") as f:
                info["text"] = f.read(800).decode("utf-8", "replace")
        return info

    # ---------- acciones ----------
    def copy(self, clip):
        data = self._decode(clip)
        cmd = ["wl-copy"]
        if clip.kind == "imagen":
            cmd += ["--type", "image/jpeg" if clip.fmt in ("jpg", "jpeg") else f"image/{clip.fmt}"]
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, start_new_session=True)
            proc.stdin.write(data)
            proc.stdin.close()
            ok = proc.wait(timeout=3) == 0 and bool(data)
        except (OSError, subprocess.TimeoutExpired):
            ok = False
        if ok:
            self.notify(COPY_TITLE[clip.kind], (clip.sub if clip.kind == "imagen" else clip.name)[:80],
                        "edit-copy")
        else:
            self.notify("No se pudo copiar", clip.name[:80], "dialog-error")
        self.hide()
        GLib.timeout_add(150, Gtk.main_quit)

    @staticmethod
    def _open_command(target, name):
        """Texto -> nvim en kitty, documentos -> OnlyOffice, el resto -> xdg-open."""
        if target.startswith(("http://", "https://", "ftp://")) or os.path.isdir(target):
            return ["xdg-open", target]
        mime = Gio.content_type_guess(target, None)[0]
        if any(Gio.content_type_is_a(mime, m) for m in OFFICE_MIMES):
            return ["onlyoffice-desktopeditors", target]
        if Gio.content_type_is_a(mime, "text/plain"):
            return [base.TERMINAL, "--title", name, "nvim", target]
        return ["xdg-open", target]

    def open_clip(self, clip):
        try:
            if clip.kind == "imagen":
                argv = ["xdg-open", self.image_path(clip)]
            elif clip.kind == "archivo":
                if not os.path.exists(clip.path):
                    self.notify("El archivo ya no existe", clip.path, "dialog-warning")
                    return
                argv = self._open_command(clip.path, clip.name)
            elif clip.kind == "url":
                argv = ["xdg-open", self._decode(clip).decode("utf-8", "replace").strip()]
            else:
                private_dir(CACHE_DIR)
                target = os.path.join(CACHE_DIR, f"texto-{clip.id}.txt")
                with open(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb") as f:
                    f.write(self._decode(clip))
                argv = [base.TERMINAL, "--title", "Portapapeles", "nvim", target]
            subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
        except Exception as err:
            self.notify("No se pudo abrir", str(err), "dialog-error")
            return
        self.hide()
        GLib.timeout_add(150, Gtk.main_quit)

    @staticmethod
    def notify(title, body, icon="edit-paste"):
        subprocess.Popen(["notify-send", "-a", "Portapapeles", "-i", icon,
                          "-h", "string:x-canonical-private-synchronous:clipboard",
                          title, body])

    def delete_selected(self):
        clip = self.current
        if not clip:
            return
        idx = self.ordered.index(clip)
        cliphist("delete", data=f"{clip.id}\t".encode())
        self.notify("Elemento eliminado", f"{KIND_LABEL[clip.kind]}: {clip.name[:80]}", "edit-delete")
        self._forget(clip)
        self.listbox.remove(clip.row)
        self.clips.remove(clip)
        self.ordered.remove(clip)
        self.update_counts()
        if self.ordered:
            target = self.ordered[min(idx, len(self.ordered) - 1)]
            self.listbox.select_row(target.row)
            self.scroll_to(target.row)
        else:
            self.current = None
            self.update_detail()
            self.refilter()

    def _forget(self, clip):
        """Quita hora y archivos en cache de un elemento borrado."""
        self.info_cache.pop(clip.id, None)
        for folder in (IMG_DIR, THUMB_DIR, CACHE_DIR):
            try:
                for name in os.listdir(folder):
                    if re.match(rf"(texto-)?{clip.id}[-_.]", name):
                        os.remove(os.path.join(folder, name))
            except OSError:
                pass
        times = read_times()
        if times.pop(clip.id, None) is not None:
            write_times(times)

    def clear_history(self):
        """Primer uso pide confirmar (3 s); el segundo borra todo."""
        if not self.clips:
            return
        if not self.confirm_timer:
            self.btn_clear.label.set_text("¿Borrar todo?")
            self.btn_clear.hint.set_text("Pulsa de nuevo")
            self.btn_clear.get_style_context().add_class("danger")
            self.confirm_timer = GLib.timeout_add_seconds(3, self._cancel_confirm)
            return
        self._cancel_confirm()
        count = len(self.clips)
        cliphist("wipe")
        for clip in list(self.clips):
            self.listbox.remove(clip.row)
        self.clips.clear()
        self.ordered = []
        self.info_cache.clear()
        write_times({})
        for folder in (IMG_DIR, THUMB_DIR, CACHE_DIR):
            try:
                for name in os.listdir(folder):
                    if os.path.isfile(os.path.join(folder, name)):
                        os.remove(os.path.join(folder, name))
            except OSError:
                pass
        self.current = None
        self.update_counts()
        self.refilter()
        self.notify("Historial borrado", f"Se eliminaron {count} elementos", "edit-clear")

    def _cancel_confirm(self):
        if self.confirm_timer:
            GLib.source_remove(self.confirm_timer)
        self.confirm_timer = 0
        self.btn_clear.label.set_text("Limpiar historial")
        self.btn_clear.hint.set_text("Alt + Supr")
        self.btn_clear.get_style_context().remove_class("danger")
        return False

    def move_selection(self, step):
        if not self.ordered:
            return
        idx = self.ordered.index(self.current) if self.current in self.ordered else -1
        target = self.ordered[max(0, min(len(self.ordered) - 1, idx + step))]
        self.listbox.select_row(target.row)
        self.scroll_to(target.row)

    def cycle_category(self, step):
        ids = [cid for cid, _, _ in CATEGORIES]
        nxt = ids[(ids.index(self.category) + step) % len(ids)]
        self.cat_list.select_row(self.cat_rows[nxt])

    # ---------- eventos ----------
    def on_search_changed(self, _entry):
        self.placeholder.set_visible(not self.search.get_text())
        if self.search.get_text().strip() and self.category != "todos":
            self.cat_list.select_row(self.cat_rows["todos"])
        else:
            self.refilter()

    def on_category_selected(self, _lb, row):
        if row is None:
            return
        self.category = row.cat_id
        self.refilter()

    def on_row_selected(self, _lb, row):
        self.current = row.clip if row else None
        self.update_detail()

    def on_backdrop_click(self, root, event):
        # un widget con ventana propia (fila, boton) implica clic dentro del panel
        if Gtk.get_event_widget(event) is not root:
            return False
        a = self.panel.get_allocation()
        if not (a.x <= event.x <= a.x + a.width and a.y <= event.y <= a.y + a.height):
            Gtk.main_quit()
        return False

    def on_key(self, _win, event):
        key = Gdk.keyval_name(event.keyval)
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
        alt = event.state & Gdk.ModifierType.MOD1_MASK
        if key == "Escape":
            Gtk.main_quit()
        elif key in ("Down", "Up"):
            self.move_selection(1 if key == "Down" else -1)
        elif key in ("Return", "KP_Enter") and self.current:
            self.copy(self.current)
        elif key == "Tab":
            self.cycle_category(1)
        elif key == "ISO_Left_Tab":
            self.cycle_category(-1)
        elif key == "Delete" and alt:
            self.clear_history()
        elif key == "Delete" and ctrl:
            self.delete_selected()
        elif ctrl and key in ("o", "O") and self.current:
            self.open_clip(self.current)
        else:
            return False
        return True


def toggle_running_instance():
    """Si ya hay una instancia abierta la cierra y devuelve True."""
    try:
        with open(PID_FILE) as f:
            pid = int(f.read())
        with open(f"/proc/{pid}/cmdline") as f:
            if "clipboard.py" in f.read():
                os.kill(pid, signal.SIGTERM)
                return True
    except (OSError, ValueError):
        pass
    return False


def main():
    if toggle_running_instance():
        return
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    win = ClipboardWindow()
    GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, Gtk.main_quit)
    win.show_all()
    Gtk.main()
    try:
        os.remove(PID_FILE)
    except OSError:
        pass


if __name__ == "__main__":
    main()
