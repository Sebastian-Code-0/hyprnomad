#!/usr/bin/env python3
"""Selector de wallpapers con categorias, favoritos, recientes y paleta de pywal."""
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# reutiliza helpers, glifos y constantes de pywal del launcher
sys.path.insert(0, os.path.join(BASE_DIR, "..", "launcher"))
import launcher as base  # noqa: E402

import gi  # noqa: E402

gi.require_version("GdkPixbuf", "2.0")
gi.require_version("GLibUnix", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, GLibUnix, Gtk, GtkLayerShell, Pango  # noqa: E402

GLib.set_prgname("wallpaper-select")

CSS_PATH = os.path.join(BASE_DIR, "style.css")
DATA_DIR = os.path.join(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")), "wallpaper-select")
CACHE_DIR = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "wallpaper-select")
FAV_FILE = os.path.join(DATA_DIR, "favorites.json")
TAGS_FILE = os.path.join(DATA_DIR, "tags.json")
HISTORY_FILE = os.path.join(DATA_DIR, "history.log")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
THUMB_DIR = os.path.join(CACHE_DIR, "thumbs")
PAL_DIR = os.path.join(CACHE_DIR, "palettes")
DIMS_FILE = os.path.join(CACHE_DIR, "dimensions.json")
PID_FILE = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "wallpaper-select.pid")
APPLY_SCRIPT = os.environ.get("WALLSEL_APPLY", os.path.expanduser("~/.config/hypr/scripts/apply_wallpaper.sh"))
THEME_FILE = "/tmp/theme_variant"

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
THUMB_W = 480
PANEL_W, PANEL_H = 1100, 600
SIDEBAR_W, DETAIL_W = 230, 340
PREVIEW_H = 178
GRID_GAP = 10
MAX_RECENT = 30

# id, etiqueta, icono (Nerd Font)
VIEWS = [
    ("todos", "Wallpapers", ""),
    ("favoritos", "Favoritos", ""),
    ("recientes", "Recientes", ""),
    ("carpetas", "Carpetas", ""),
]
TAGS = [
    ("anime", "Anime", ""),
    ("ciudad", "Ciudad", ""),
    ("minimalista", "Minimalista", ""),
    ("naturaleza", "Naturaleza", ""),
    ("juegos", "Juegos", ""),
    ("tecnologia", "Tecnología", ""),
]
TAG_LABEL = {tid: label for tid, label, _ in TAGS}

GLYPH_STAR, GLYPH_STAR_O = "", ""
GLYPH_TAG, GLYPH_CHECK, GLYPH_UNCHECK = "", "", ""
GLYPH_APPLY, GLYPH_BACK, GLYPH_FOLDER = "", "", ""
GLYPH_CLEAR, GLYPH_UP, GLYPH_OPEN = "", "", ""
GLYPH_RES, GLYPH_SIZE, GLYPH_CURRENT = "", "", ""

# calcula la paleta con el mismo motor que pywal (sin tocar ~/.cache/wal)
PALETTE_CODE = r"""
import json, logging, sys
logging.disable(logging.CRITICAL)
import pywal
try:
    c = pywal.colors.get(sys.argv[1], light=sys.argv[3] == "1", cache_dir=sys.argv[2])
    print(json.dumps([c["special"]["background"], *[c["colors"][f"color{i}"] for i in range(1, 7)],
                      c["special"]["foreground"]]))
except SystemExit:
    sys.exit(2)
"""


def human_size(n):
    if n < 1024:
        return f"{n} B"
    for unit in ("KB", "MB", "GB"):
        n /= 1024
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}"


def natural_key(text):
    return [int(t) if t.isdigit() else t.casefold() for t in re.split(r"(\d+)", text)]


def xdg_pictures():
    """Carpeta de imagenes del usuario segun XDG (puede no existir)."""
    try:
        out = subprocess.run(["xdg-user-dir", "PICTURES"], capture_output=True, text=True, timeout=2).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        out = ""
    return out or os.path.expanduser("~/Pictures")


def default_root():
    """Carpeta de imagenes si existe; si no, el home."""
    out = xdg_pictures()
    return out if os.path.isdir(out) else os.path.expanduser("~")


WALL_LINK = os.environ.get("WALLPAPER_LINK") or os.path.join(
    os.environ.get("WALLPAPER_DIR") or os.path.join(xdg_pictures(), "Wallpapers"), "wallpaper.png")


def load_root(settings):
    root = os.path.realpath(os.path.expanduser(settings.get("root", "")))
    return root if settings.get("root") and os.path.isdir(root) else default_root()


def short_path(path):
    return path.replace(os.path.expanduser("~"), "~", 1)


def subdirs(path):
    """Subcarpetas visibles, en orden natural."""
    try:
        with os.scandir(path) as it:
            names = [e.name for e in it if e.is_dir() and not e.name.startswith(".")]
    except OSError:
        return []
    return sorted(names, key=natural_key)


def read_history():
    """Rutas aplicadas, la mas reciente primero (sin repetir)."""
    entries = {}
    try:
        with open(HISTORY_FILE) as f:
            for line in f:
                ts, _, path = line.rstrip("\n").partition(" ")
                if ts.isdigit() and path:
                    entries[path] = int(ts)
    except OSError:
        pass
    return [p for p, _ in sorted(entries.items(), key=lambda kv: -kv[1])]


MAGIC = ((b"\x89PNG", "PNG"), (b"\xff\xd8", "JPEG"), (b"GIF8", "GIF"), (b"BM", "BMP"))


def sniff(path):
    """Formato de imagen por los primeros bytes (rapido); None si no es imagen."""
    try:
        with open(path, "rb") as f:
            head = f.read(12)
    except OSError:
        return None
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "WEBP"
    return next((name for magic, name in MAGIC if head.startswith(magic)), None)


class Wall:
    def __init__(self, path, fmt, dims_cache):
        st = os.stat(path)
        self.path, self.fmt = path, fmt
        self.order = 0
        self.name = os.path.basename(path)
        self.folder = os.path.dirname(path)
        self.size, self.mtime = st.st_size, st.st_mtime
        self.animated = fmt == "GIF"
        self.key = hashlib.md5(f"{path}|{self.mtime}|{self.size}".encode()).hexdigest()
        self.w, self.h = dims_cache.get(self.key, (0, 0))
        self.search = f"{self.name} {os.path.basename(self.folder)}".casefold()
        self.thumb = None
        self.show = True

    def load_dims(self):
        """Lee el tamaño en pixeles (lento, ~50 ms): solo cuando hace falta."""
        if not self.w:
            info = GdkPixbuf.Pixbuf.get_file_info(self.path)
            self.w, self.h = info[1], info[2]
        return self.w, self.h


def scan_walls(root):
    """Imagenes bajo la carpeta madre (recursivo, sin enlaces duplicados)."""
    dims_cache = {k: tuple(v) for k, v in base.load_json(DIMS_FILE, {}).items()}
    found = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        if dirpath[len(root):].count(os.sep) >= 3:
            dirs[:] = []
        for name in files:
            path = os.path.join(dirpath, name)
            ext = os.path.splitext(name)[1].lower()
            if name.startswith(".") or (ext and ext not in IMAGE_EXT):
                continue
            if os.path.islink(path) and os.path.realpath(path).startswith(root + os.sep):
                continue
            found.append(path)
    walls, seen = [], set()
    for path in found:
        real = os.path.realpath(path)
        fmt = sniff(path) if real not in seen and os.path.isfile(path) else None
        if fmt:
            walls.append(Wall(path, fmt, dims_cache))
            seen.add(real)
    walls.sort(key=lambda w: natural_key(os.path.relpath(w.path, root)))
    for i, w in enumerate(walls):
        w.order = i
    return walls


class WallpaperWindow(Gtk.Window):
    def __init__(self):
        super().__init__()
        self.view = "todos"
        self.folder = None
        self.current = None
        self.ordered = []
        self.confirm_id = 0
        self.pal_seq = 0
        self.pal_timer = 0
        self.pal_cache = {}
        self.settings = base.load_json(SETTINGS_FILE, {})
        self.columns = 2 if self.settings.get("columns") == 2 else 3
        self.favorites = set(base.load_json(FAV_FILE, []))
        self.tags = base.load_json(TAGS_FILE, {})
        self.recent = read_history()
        self.root = load_root(self.settings)
        self.walls, self.by_path = [], {}
        self.picking = False
        self.picker_dir = self.root
        self.current_path = os.path.realpath(WALL_LINK)

        self._setup_layer()
        self._load_css()
        self._build_ui()
        self._populate()

    # ---------- ventana ----------
    def _setup_layer(self):
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_namespace(self, "wallpaper-select")
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
        self.safe_provider.load_from_data(f"@define-color text_safe {base.text_safe_color()};".encode())
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
        self.safe_provider.load_from_data(f"@define-color text_safe {base.text_safe_color()};".encode())
        self.main_provider.load_from_path(CSS_PATH)
        return False

    @staticmethod
    def _lock_horizontal(scrolled):
        """Evita que el dedo (pantalla tactil) mueva el contenido de lado."""
        scrolled.get_hadjustment().connect("value-changed", lambda a: a.get_value() and a.set_value(0))

    # ---------- interfaz ----------
    def _build_ui(self):
        root = Gtk.EventBox()
        root.connect("button-press-event", self.on_backdrop_click)
        self.add(root)

        self.panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.panel.get_style_context().add_class("panel")
        self.panel.set_size_request(PANEL_W, PANEL_H)
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
        body.pack_start(self._build_middle(), True, True, 0)
        body.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 0)
        body.pack_start(self._build_detail(), False, False, 0)
        self.panel.pack_start(body, True, True, 0)

    def _build_header(self):
        header = Gtk.Box()
        header.get_style_context().add_class("top-bar")
        header.pack_start(base.glyph_label(base.GLYPH_ARCH, "logo"), False, False, 0)
        note = Gtk.Label(label="Selector de wallpapers")
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
        self.placeholder = Gtk.Label(label="Buscar wallpaper...", xalign=0)
        self.placeholder.get_style_context().add_class("placeholder")
        self.placeholder.set_margin_start(2)
        overlay = Gtk.Overlay()
        overlay.add(self.search)
        overlay.add_overlay(self.placeholder)
        overlay.set_overlay_pass_through(self.placeholder, True)
        search.pack_start(overlay, True, True, 0)
        header.set_center_widget(search)
        return header

    def _sidebar_row(self, rid, label, glyph):
        row = Gtk.ListBoxRow()
        row.side_id = rid
        row.set_can_focus(False)
        box = Gtk.Box(spacing=12)
        box.pack_start(base.glyph_label(glyph, "cat-glyph"), False, False, 0)
        box.pack_start(Gtk.Label(label=label, xalign=0), True, True, 0)
        count = Gtk.Label(label="0")
        count.get_style_context().add_class("cat-count")
        box.pack_end(count, False, False, 0)
        row.add(box)
        row.count_label = count
        self.side_rows[rid] = row
        return row

    def _build_sidebar(self):
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        side.get_style_context().add_class("cats")
        self.side_rows = {}
        self.side_list = Gtk.ListBox()
        self.side_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.side_list.set_can_focus(False)
        for rid, label, glyph in VIEWS:
            self.side_list.add(self._sidebar_row(rid, label, glyph))
        # separador y titulo no seleccionables
        sep_row = Gtk.ListBoxRow()
        sep_row.set_selectable(False)
        sep_row.set_activatable(False)
        sep_row.get_style_context().add_class("plain-row")
        sep_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        sep_box.pack_start(Gtk.Separator(), False, False, 6)
        title = Gtk.Label(label="CATEGORÍAS", xalign=0)
        title.get_style_context().add_class("section-title")
        sep_box.pack_start(title, False, False, 0)
        sep_row.add(sep_box)
        self.side_list.add(sep_row)
        for tid, label, glyph in TAGS:
            self.side_list.add(self._sidebar_row(tid, label, glyph))
        self.side_list.connect("row-selected", self.on_side_selected)
        self.side_list.connect("row-activated", self.on_side_activated)
        side.pack_start(self.side_list, False, False, 0)

        footer = Gtk.Box(spacing=10)
        footer.set_valign(Gtk.Align.END)
        footer.set_tooltip_text("Wallpaper en uso ahora")
        footer.pack_start(base.glyph_label(GLYPH_CURRENT, "cat-glyph"), False, False, 0)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        col.pack_start(self._label("Wallpaper actual", "hint"), False, False, 0)
        self.current_label = self._label("", None)
        self.current_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.current_label.set_max_width_chars(20)
        col.pack_start(self.current_label, False, False, 0)
        footer.pack_start(col, True, True, 0)
        side.pack_end(footer, True, True, 0)
        return base.Launcher._fixed_column(side, SIDEBAR_W)

    @staticmethod
    def _label(text, css_class, xalign=0):
        lbl = Gtk.Label(label=text, xalign=xalign)
        if css_class:
            lbl.get_style_context().add_class(css_class)
        return lbl

    def _build_middle(self):
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # barra del filtro de carpeta activo
        self.crumb = Gtk.Box(spacing=10)
        self.crumb.get_style_context().add_class("crumb")
        self.crumb.set_no_show_all(True)
        self.crumb.pack_start(base.glyph_label(GLYPH_FOLDER, "row-glyph"), False, False, 0)
        self.crumb_label = self._label("", "d-name")
        self.crumb_label.set_ellipsize(Pango.EllipsizeMode.END)
        clear = base.action_button(GLYPH_CLEAR, "Quitar filtro")
        clear.connect("clicked", lambda *_: self.choose_folder(None))
        self.crumb.pack_start(self.crumb_label, True, True, 0)
        self.crumb.pack_end(clear, False, False, 0)
        for child in self.crumb.get_children():
            child.show_all()
        col.pack_start(self.crumb, False, False, 0)

        self.mid_stack = Gtk.Stack()
        self.mid_stack.add_named(self._build_grid(), "grid")
        self.mid_stack.add_named(self._build_folders(), "folders")
        self.mid_stack.add_named(self._build_picker(), "picker")
        self.empty_label = Gtk.Label()
        self.empty_label.get_style_context().add_class("empty")
        self.empty_label.set_justify(Gtk.Justification.CENTER)
        self.mid_stack.add_named(self.empty_label, "empty")
        col.pack_start(self.mid_stack, True, True, 0)
        return col

    def _build_grid(self):
        self.scroller = Gtk.ScrolledWindow()
        # EXTERNAL horizontal: la cuadricula nunca ensancha el panel
        self.scroller.set_policy(Gtk.PolicyType.EXTERNAL, Gtk.PolicyType.AUTOMATIC)
        self.scroller.set_overlay_scrolling(False)
        self.scroller.get_style_context().add_class("list-area")
        self._lock_horizontal(self.scroller)

        self.flow = Gtk.FlowBox()
        self.flow.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.flow.set_activate_on_single_click(False)
        self.flow.set_homogeneous(True)
        self.flow.set_can_focus(False)
        self.flow.set_column_spacing(GRID_GAP)
        self.flow.set_row_spacing(GRID_GAP)
        self.flow.set_halign(Gtk.Align.FILL)
        self.flow.set_valign(Gtk.Align.START)
        self.flow.set_margin_start(2)
        self.flow.set_margin_end(10)
        self.flow.set_filter_func(lambda child: child.wall.show)
        self.flow.set_sort_func(self._sort_cards)
        self.flow.connect("selected-children-changed", self.on_selection_changed)
        self.flow.connect("child-activated", lambda _fb, child: self.apply(child.wall))
        self.flow.connect("size-allocate", self._on_flow_allocate)
        self._last_flow_w = 0
        self.scroller.add(self.flow)
        return self.scroller

    def _list_scroller(self, listbox, on_activate):
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_overlay_scrolling(False)
        scroller.get_style_context().add_class("list-area")
        listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        listbox.set_activate_on_single_click(True)
        listbox.set_can_focus(False)
        listbox.set_margin_end(8)
        listbox.connect("row-activated", lambda _lb, row: on_activate(row))
        scroller.add(listbox)
        listbox.scroller = scroller
        return scroller

    def _root_bar(self, title, subtitle_label, button):
        """Cabecera con titulo, ruta y un boton (carpeta madre / selector)."""
        bar = Gtk.Box(spacing=12)
        bar.get_style_context().add_class("crumb")
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        texts.set_valign(Gtk.Align.CENTER)
        texts.pack_start(self._label(title, "section-title"), False, False, 0)
        subtitle_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        texts.pack_start(subtitle_label, False, False, 0)
        bar.pack_start(texts, True, True, 0)
        bar.pack_end(button, False, False, 0)
        return bar

    def _build_folders(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.root_label = self._label("", "d-name")
        change = base.action_button(GLYPH_OPEN, "Cambiar")
        change.connect("clicked", lambda *_: self.open_picker())
        page.pack_start(self._root_bar("CARPETA MADRE", self.root_label, change), False, False, 0)
        self.folder_list = Gtk.ListBox()
        page.pack_start(self._list_scroller(self.folder_list, self.on_folder_row), True, True, 0)
        return page

    def _build_picker(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.picker_label = self._label("", "d-name")
        use = base.action_button(GLYPH_APPLY, "Usar esta carpeta", hint="Ctrl+↵")
        use.connect("clicked", lambda *_: self.picker_use())
        page.pack_start(self._root_bar("ELEGIR CARPETA MADRE", self.picker_label, use), False, False, 0)
        self.picker_list = Gtk.ListBox()
        page.pack_start(self._list_scroller(self.picker_list, self.on_picker_row), True, True, 0)
        return page

    def _build_detail(self):
        self.detail_stack = Gtk.Stack()
        self.detail_stack.get_style_context().add_class("detail")
        self.detail_stack.add_named(self._build_info_page(), "info")
        self.detail_stack.add_named(self._build_tags_page(), "tags")
        return base.Launcher._fixed_column(self.detail_stack, DETAIL_W)

    def _build_info_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        page.set_border_width(16)

        # marco de tamaño fijo: 16:9 como la pantalla, recorte igual que al aplicarlo
        frame = Gtk.ScrolledWindow()
        frame.set_policy(Gtk.PolicyType.EXTERNAL, Gtk.PolicyType.EXTERNAL)
        base.lock_scroll(frame)
        frame.set_size_request(-1, PREVIEW_H)
        self.preview = Gtk.Box()
        self.preview.get_style_context().add_class("thumb")
        self.preview.get_style_context().add_class("preview")
        self.preview_css = Gtk.CssProvider()
        self.preview.get_style_context().add_provider(self.preview_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        frame.add(self.preview)
        page.pack_start(frame, False, False, 0)

        self.d_name = self._label("", "d-name")
        self.d_name.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        page.pack_start(self.d_name, False, False, 2)

        meta = Gtk.Box(spacing=18)
        self.d_res = self._meta_item(GLYPH_RES, meta)
        self.d_size = self._meta_item(GLYPH_SIZE, meta)
        page.pack_start(meta, False, False, 0)

        self.d_chips = Gtk.Box(spacing=6)
        page.pack_start(self.d_chips, False, False, 0)

        bottom = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        page.pack_end(bottom, False, False, 0)
        bottom.pack_start(Gtk.Separator(), False, False, 4)
        bottom.pack_start(self._label("PALETA", "section-title"), False, False, 0)
        self.swatch_box = Gtk.Box(spacing=8)
        self.swatches = []
        for _ in range(8):
            sw = Gtk.Box()
            sw.get_style_context().add_class("swatch")
            sw.set_no_show_all(True)
            prov = Gtk.CssProvider()
            sw.get_style_context().add_provider(prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            sw.prov = prov
            self.swatch_box.pack_start(sw, False, False, 0)
            self.swatches.append(sw)
        bottom.pack_start(self.swatch_box, False, False, 0)
        self.pal_note = self._label("", "hint")
        self.pal_note.set_line_wrap(True)
        self.pal_note.set_max_width_chars(38)
        self.pal_note.set_size_request(-1, 30)
        bottom.pack_start(self.pal_note, False, False, 0)

        self.btn_apply = base.action_button(GLYPH_APPLY, "Aplicar wallpaper", "primary", "↵")
        self.btn_apply.connect("clicked", lambda *_: self.current and self.apply(self.current))
        bottom.pack_start(self.btn_apply, False, False, 0)
        row = Gtk.Box(spacing=8, homogeneous=True)
        self.btn_fav = base.action_button(GLYPH_STAR_O, "Favorito")
        self.btn_fav.set_tooltip_text("Ctrl+F")
        self.btn_fav.connect("clicked", lambda *_: self.toggle_favorite())
        self.btn_tags = base.action_button(GLYPH_TAG, "Categoría")
        self.btn_tags.set_tooltip_text("Ctrl+T")
        self.btn_tags.connect("clicked", lambda *_: self.show_tags())
        row.pack_start(self.btn_fav, True, True, 0)
        row.pack_start(self.btn_tags, True, True, 0)
        bottom.pack_start(row, False, False, 0)
        return page

    def _meta_item(self, glyph, parent):
        box = Gtk.Box(spacing=8)
        box.pack_start(base.glyph_label(glyph, "meta-glyph"), False, False, 0)
        lbl = Gtk.Label(xalign=0)
        box.pack_start(lbl, False, False, 0)
        parent.pack_start(box, False, False, 0)
        return lbl

    def _build_tags_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        page.set_border_width(16)
        back = base.action_button(GLYPH_BACK, "Volver", hint="Esc")
        back.connect("clicked", lambda *_: self.hide_tags())
        page.pack_start(back, False, False, 0)
        self.tags_title = self._label("", "d-name")
        self.tags_title.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        page.pack_start(self.tags_title, False, False, 0)
        page.pack_start(self._label("Marca las categorías de este wallpaper", "d-generic"), False, False, 0)
        self.tag_list = Gtk.ListBox()
        self.tag_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.tag_list.set_can_focus(False)
        self.tag_list.connect("row-activated", lambda _lb, row: self.toggle_tag(row.tag_id))
        for tid, label, glyph in TAGS:
            row = Gtk.ListBoxRow()
            row.tag_id = tid
            box = Gtk.Box(spacing=12)
            box.pack_start(base.glyph_label(glyph, "cat-glyph"), False, False, 0)
            box.pack_start(Gtk.Label(label=label, xalign=0), True, True, 0)
            row.check = base.glyph_label(GLYPH_UNCHECK, "check-glyph")
            box.pack_end(row.check, False, False, 0)
            row.add(box)
            self.tag_list.add(row)
        page.pack_start(self.tag_list, False, False, 0)
        return page

    # ---------- cuadricula ----------
    def _populate(self):
        self._load_walls()
        self.show_all()
        self.side_list.select_row(self.side_rows["todos"])
        self.search.grab_focus()

    def _load_walls(self):
        """Escanea la carpeta madre y reconstruye la cuadricula y las carpetas."""
        for child in self.flow.get_children():
            self.flow.remove(child)
        self.current = None
        self.walls = scan_walls(self.root)
        self.by_path = {w.path: w for w in self.walls}
        for wall in self.walls:
            self.flow.add(self._build_card(wall))
        self.flow.show_all()
        self._build_folder_rows()
        self.update_counts()
        threading.Thread(target=self._make_thumbs, args=(self.walls,), daemon=True).start()
        threading.Thread(target=self._fill_dims, args=(self.walls,), daemon=True).start()

    def _fill_dims(self, walls):
        """Completa y guarda las resoluciones que faltan (para la proxima vez)."""
        missing = [w for w in walls if not w.w]
        if not missing:
            return
        for wall in missing:
            try:
                wall.load_dims()
            except GLib.Error:
                continue
        os.makedirs(CACHE_DIR, exist_ok=True)
        cache = base.load_json(DIMS_FILE, {})
        cache.update({w.key: [w.w, w.h] for w in walls if w.w})
        base.save_json(DIMS_FILE, cache)

    def _card_size(self):
        avail = self._last_flow_w or 490
        w = (avail - (self.columns - 1) * GRID_GAP) // self.columns - 1
        return w, w * 9 // 16

    def _build_card(self, wall):
        child = Gtk.FlowBoxChild()
        child.wall = wall
        wall.card = child
        child.set_can_focus(False)
        child.set_tooltip_text(wall.path.replace(os.path.expanduser("~"), "~"))
        overlay = Gtk.Overlay()
        thumb = Gtk.Box()
        thumb.get_style_context().add_class("thumb")
        w, h = self._card_size()
        thumb.set_size_request(w, h)
        child.css = Gtk.CssProvider()
        thumb.get_style_context().add_provider(child.css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        overlay.add(thumb)
        child.thumb = thumb

        child.star = base.glyph_label(GLYPH_STAR, "card-star")
        child.star.set_halign(Gtk.Align.END)
        child.star.set_valign(Gtk.Align.START)
        child.star.set_no_show_all(True)
        child.star.set_visible(wall.path in self.favorites)
        child.badge = self._label("en uso", "card-badge")
        child.badge.set_halign(Gtk.Align.START)
        child.badge.set_valign(Gtk.Align.START)
        child.badge.set_no_show_all(True)
        child.badge.set_visible(wall.path == self.current_path)
        for widget in (child.star, child.badge):
            overlay.add_overlay(widget)
            overlay.set_overlay_pass_through(widget, True)
        if wall.animated:
            gif = self._label("GIF", "card-badge")
            gif.set_halign(Gtk.Align.START)
            gif.set_valign(Gtk.Align.END)
            overlay.add_overlay(gif)
            overlay.set_overlay_pass_through(gif, True)
        child.add(overlay)
        return child

    def _on_flow_allocate(self, flow, alloc):
        # ajusta el tamaño de las tarjetas al ancho real disponible
        if abs(alloc.width - self._last_flow_w) > 2:
            self._last_flow_w = alloc.width
            GLib.idle_add(self.apply_columns)

    def apply_columns(self):
        self.flow.set_min_children_per_line(self.columns)
        self.flow.set_max_children_per_line(self.columns)
        w, h = self._card_size()
        for wall in self.walls:
            wall.card.thumb.set_size_request(w, h)
        return False

    def toggle_columns(self):
        self.columns = 2 if self.columns == 3 else 3
        self.settings["columns"] = self.columns
        base.save_json(SETTINGS_FILE, self.settings)
        self.apply_columns()
        if self.current:
            GLib.idle_add(self.scroll_to, self.current.card)

    def _sort_cards(self, a, b):
        ka, kb = self._rank(a.wall), self._rank(b.wall)
        return (ka > kb) - (ka < kb)

    def _rank(self, wall):
        if self.view == "recientes" and wall.path in self.recent:
            return self.recent.index(wall.path)
        return wall.order

    def _make_thumbs(self, walls):
        """Miniaturas en segundo plano (cache en disco por ruta+fecha+tamaño)."""
        os.makedirs(THUMB_DIR, exist_ok=True)
        for wall in walls:
            if walls is not self.walls:
                return
            path = os.path.join(THUMB_DIR, wall.key + ".jpg")
            try:
                if not os.path.exists(path):
                    pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(wall.path, THUMB_W, -1, True)
                    if pb.get_has_alpha():
                        # el codificador JPEG no admite alfa: aplana sobre negro
                        flat = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8,
                                                    pb.get_width(), pb.get_height())
                        flat.fill(0x000000FF)
                        pb.composite(flat, 0, 0, pb.get_width(), pb.get_height(), 0, 0, 1, 1,
                                     GdkPixbuf.InterpType.NEAREST, 255)
                        pb = flat
                    pb.savev(path + ".tmp", "jpeg", ["quality"], ["88"])
                    os.replace(path + ".tmp", path)
                GLib.idle_add(self._set_thumb, wall, path)
            except (GLib.Error, OSError):
                continue

    def _set_thumb(self, wall, path):
        wall.thumb = path
        wall.card.css.load_from_data(f'.thumb {{ background-image: url("{path}"); }}'.encode())
        if wall is self.current:
            self.preview_css.load_from_data(f'.thumb {{ background-image: url("{path}"); }}'.encode())
        return False

    # ---------- carpetas ----------
    def _folder_row(self, glyph, name, sub, count=None):
        row = Gtk.ListBoxRow()
        row.set_can_focus(False)
        box = Gtk.Box(spacing=12)
        box.pack_start(base.glyph_label(glyph, "row-glyph"), False, False, 0)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        texts.set_valign(Gtk.Align.CENTER)
        texts.pack_start(self._label(name, "app-name"), False, False, 0)
        if sub:
            path = self._label(sub, "app-sub")
            path.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
            texts.pack_start(path, False, False, 0)
        box.pack_start(texts, True, True, 0)
        if count is not None:
            box.pack_end(self._label(str(count), "cat-count"), False, False, 0)
        row.add(box)
        return row

    def _build_folder_rows(self):
        """Subcarpetas de la carpeta madre (con imagenes) y una fila para ver todo."""
        counts = {}
        for wall in self.walls:
            parts = os.path.relpath(wall.path, self.root).split(os.sep)
            if len(parts) > 1:
                top = os.path.join(self.root, parts[0])
                counts[top] = counts.get(top, 0) + 1
        self.folder_counts = counts
        self.root_label.set_text(short_path(self.root))
        for row in self.folder_list.get_children():
            self.folder_list.remove(row)
        rows = [(None, self._folder_row(GLYPH_FOLDER, "Todas las carpetas", short_path(self.root), len(self.walls)))]
        for folder in sorted(counts, key=lambda f: natural_key(os.path.basename(f))):
            rows.append((folder, self._folder_row(GLYPH_FOLDER, os.path.basename(folder), None, counts[folder])))
        for folder, row in rows:
            row.folder = folder
            self.folder_list.add(row)
        self.folder_list.show_all()

    def select_folder_row(self):
        for row in self.folder_list.get_children():
            if row.folder == self.folder:
                self.folder_list.select_row(row)

    def on_folder_row(self, row):
        self.choose_folder(row.folder)

    def choose_folder(self, folder):
        """Filtra los wallpapers por carpeta (None = todas) y muestra Wallpapers."""
        self.folder = folder
        if self.view == "todos":
            self.refilter()
        else:
            self.side_list.select_row(self.side_rows["todos"])

    # ---------- selector de carpeta madre ----------
    def open_picker(self):
        self.picking = True
        self.picker_dir = self.root
        self._fill_picker()
        self.refilter()

    def close_picker(self):
        self.picking = False
        self.refilter()

    def _fill_picker(self):
        self.picker_label.set_text(short_path(self.picker_dir))
        for row in self.picker_list.get_children():
            self.picker_list.remove(row)
        parent = os.path.dirname(self.picker_dir)
        if parent != self.picker_dir:
            row = self._folder_row(GLYPH_UP, "..", "Subir un nivel")
            row.dir = parent
            self.picker_list.add(row)
        for name in subdirs(self.picker_dir):
            row = self._folder_row(GLYPH_FOLDER, name, None)
            row.dir = os.path.join(self.picker_dir, name)
            self.picker_list.add(row)
        self.picker_list.show_all()
        rows = self.picker_list.get_children()
        if rows:
            self.picker_list.select_row(rows[0])
        self.picker_list.scroller.get_vadjustment().set_value(0)

    def on_picker_row(self, row):
        self.picker_dir = row.dir
        self._fill_picker()

    def picker_use(self):
        """Fija la carpeta madre elegida y vuelve a escanear."""
        self.root = self.picker_dir
        self.settings["root"] = self.root
        base.save_json(SETTINGS_FILE, self.settings)
        self.picking = False
        self.folder = None
        self._load_walls()
        self.refilter()

    # ---------- filtrado ----------
    def _view_walls(self):
        query = self.search.get_text().strip().casefold()
        scoped = [w for w in self.walls if w.path.startswith(self.folder + os.sep)] if self.folder else self.walls
        if query:
            return [w for w in scoped
                    if query in w.search or query in " ".join(self.tags.get(w.path, []))]
        if self.view == "todos":
            return list(scoped)
        if self.view == "favoritos":
            return [w for w in self.walls if w.path in self.favorites]
        if self.view == "recientes":
            return [self.by_path[p] for p in self.recent[:MAX_RECENT] if p in self.by_path]
        if self.view == "carpetas":
            return []
        return [w for w in self.walls if self.view in self.tags.get(w.path, [])]

    def _empty_text(self):
        if self.search.get_text().strip():
            return "Sin resultados"
        return {
            "favoritos": "Aún no tienes favoritos\nUsa Ctrl+F sobre un wallpaper",
            "recientes": "Aún no has aplicado wallpapers",
            "todos": f"No se encontraron imágenes en\n{short_path(self.root)}",
        }.get(self.view, "No hay wallpapers en esta categoría\nUsa Ctrl+T para etiquetarlos")

    def update_counts(self):
        tag_counts = {tid: 0 for tid, _, _ in TAGS}
        for wall in self.walls:
            for tid in self.tags.get(wall.path, []):
                if tid in tag_counts:
                    tag_counts[tid] += 1
        totals = {
            "todos": len(self.walls),
            "favoritos": sum(1 for w in self.walls if w.path in self.favorites),
            "recientes": min(MAX_RECENT, sum(1 for p in self.recent if p in self.by_path)),
            "carpetas": len(self.folder_counts),
            **tag_counts,
        }
        for rid, row in self.side_rows.items():
            row.count_label.set_text(str(totals[rid]))
            ctx = row.get_style_context()
            if totals[rid] == 0:
                ctx.add_class("empty-cat")
            else:
                ctx.remove_class("empty-cat")
        name = os.path.basename(self.current_path) if self.current_path else "—"
        self.current_label.set_text(name)

    def refilter(self, keep_selection=False):
        walls = self._view_walls()
        visible = set(walls)
        for wall in self.walls:
            wall.show = wall in visible
        self.ordered = sorted(walls, key=self._rank)
        self.flow.invalidate_filter()
        self.flow.invalidate_sort()

        in_folders = self.view == "carpetas" and not self.search.get_text().strip()
        show_bar = bool(self.folder) and not in_folders and self.view in ("todos", "carpetas")
        self.crumb.set_visible(show_bar)
        if self.folder:
            self.crumb_label.set_text(f"Carpeta: {os.path.basename(self.folder)}")
        if in_folders:
            self.mid_stack.set_visible_child_name("picker" if self.picking else "folders")
            if not self.picking:
                self.select_folder_row()
        elif not self.ordered:
            self.empty_label.set_text(self._empty_text())
            self.mid_stack.set_visible_child_name("empty")
        else:
            self.mid_stack.set_visible_child_name("grid")

        keep = keep_selection and self.current in self.ordered
        target = self.current if keep else (self.ordered[0] if self.ordered else None)
        if target:
            self.flow.select_child(target.card)
            GLib.idle_add(self.scroll_to, target.card)
        else:
            self.flow.unselect_all()
            self.current = None
            self.update_detail()
        if not keep_selection:
            self.scroller.get_vadjustment().set_value(0)

    def scroll_to(self, card):
        adj = self.scroller.get_vadjustment()
        coords = card.translate_coordinates(self.flow, 0, 0)
        if coords is None:
            return False
        y, h = coords[1], card.get_allocated_height()
        if y < adj.get_value():
            adj.set_value(max(0, y - GRID_GAP))
        elif y + h > adj.get_value() + adj.get_page_size():
            adj.set_value(y + h - adj.get_page_size() + GRID_GAP)
        return False

    # ---------- panel de detalle ----------
    def update_detail(self):
        wall = self.current
        for btn in (self.btn_apply, self.btn_fav, self.btn_tags):
            btn.set_sensitive(wall is not None)
        for chip in self.d_chips.get_children():
            self.d_chips.remove(chip)
        if self.pal_timer:
            GLib.source_remove(self.pal_timer)
            self.pal_timer = 0
        if not wall:
            self.d_name.set_text("Selecciona un wallpaper")
            self.d_res.set_text("—")
            self.d_size.set_text("—")
            self.preview_css.load_from_data(b".thumb { background-image: none; }")
            self._set_palette([], "")
            return
        self.d_name.set_text(wall.name)
        self.d_name.set_tooltip_text(wall.path)
        self.d_res.set_text("{}×{}".format(*wall.load_dims()))
        self.d_size.set_text(human_size(wall.size))
        if wall.thumb:
            self.preview_css.load_from_data(f'.thumb {{ background-image: url("{wall.thumb}"); }}'.encode())
        else:
            self.preview_css.load_from_data(b".thumb { background-image: none; }")
        chips = []
        if wall.path == self.current_path:
            chips.append("en uso")
        if wall.animated:
            chips.append("animado")
        chips += [TAG_LABEL[t].lower() for t in self.tags.get(wall.path, []) if t in TAG_LABEL]
        shown, extra = chips[:3], len(chips) - 3
        if extra > 0:
            shown.append(f"+{extra}")
        for text in shown:
            chip = self._label(text, "chip", 0.5)
            self.d_chips.pack_start(chip, False, False, 0)
        self.d_chips.show_all()
        self.refresh_fav_button()
        # pequeña espera: al mantener una flecha no se calcula la paleta de cada wallpaper
        self._set_palette([], "Calculando paleta...")
        self.pal_seq += 1
        self.pal_timer = GLib.timeout_add(120, self._start_palette, wall, self.pal_seq)

    def refresh_fav_button(self):
        fav = self.current is not None and self.current.path in self.favorites
        self.btn_fav.glyph.set_text(GLYPH_STAR if fav else GLYPH_STAR_O)
        self.btn_fav.label.set_text("Quitar favorito" if fav else "Favorito")

    # ---------- paleta ----------
    def _set_palette(self, colors, note):
        for i, sw in enumerate(self.swatches):
            if i < len(colors):
                sw.prov.load_from_data(f".swatch {{ background-color: {colors[i]}; }}".encode())
                sw.set_tooltip_text(colors[i].upper())
                sw.set_visible(True)
            else:
                sw.set_visible(False)
        self.pal_note.set_text(note)

    def _start_palette(self, wall, seq):
        self.pal_timer = 0
        threading.Thread(target=self._compute_palette, args=(wall, seq), daemon=True).start()
        return False

    @staticmethod
    def _light_flag():
        try:
            with open(THEME_FILE) as f:
                return "1" if f.read().strip() == "light" else "0"
        except OSError:
            return "0"

    def _compute_palette(self, wall, seq):
        light = self._light_flag()
        key = (wall.key, light)
        result = self.pal_cache.get(key)
        cache_file = os.path.join(PAL_DIR, f"{wall.key}-{light}.json")
        if result is None:
            result = base.load_json(cache_file, None)
        if result is None:
            result = self._pywal_palette(wall, light) or self._approx_palette(wall)
            os.makedirs(PAL_DIR, exist_ok=True)
            base.save_json(cache_file, result)
        self.pal_cache[key] = result
        GLib.idle_add(self._apply_palette, wall, seq, result)

    @staticmethod
    def _pywal_palette(wall, light):
        try:
            out = subprocess.run([sys.executable, "-c", PALETTE_CODE, wall.path, PAL_DIR, light],
                                 capture_output=True, text=True, timeout=40)
            if out.returncode == 0:
                return {"colors": json.loads(out.stdout), "exact": True}
        except (OSError, subprocess.TimeoutExpired, ValueError):
            pass
        return None

    @staticmethod
    def _approx_palette(wall):
        """Colores dominantes con ImageMagick cuando pywal no puede generar tema."""
        try:
            out = subprocess.run(
                ["magick", f"{wall.path}[0]", "-resize", "128x128", "-colors", "8", "-unique-colors", "txt:-"],
                capture_output=True, text=True, timeout=20)
            colors = re.findall(r"#[0-9A-Fa-f]{6}", out.stdout)
            return {"colors": colors[:8], "exact": False}
        except (OSError, subprocess.TimeoutExpired):
            return {"colors": [], "exact": False}

    def _apply_palette(self, wall, seq, result):
        if wall is self.current and seq == self.pal_seq:
            if result["exact"]:
                self._set_palette(result["colors"], "Colores que pywal aplicará al tema")
            elif result["colors"]:
                self._set_palette(result["colors"], "Aproximada: pywal no puede generar un tema con esta imagen")
            else:
                self._set_palette([], "No se pudo calcular la paleta")
        return False

    # ---------- acciones ----------
    def apply(self, wall):
        try:
            subprocess.Popen([APPLY_SCRIPT, wall.path], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
        except OSError as err:
            subprocess.Popen(["notify-send", "-a", "Wallpaper", "No se pudo aplicar", str(err)])
            return
        self.hide()
        GLib.timeout_add(150, Gtk.main_quit)

    def toggle_favorite(self):
        wall = self.current
        if not wall:
            return
        if wall.path in self.favorites:
            self.favorites.discard(wall.path)
        else:
            self.favorites.add(wall.path)
        base.save_json(FAV_FILE, sorted(self.favorites))
        wall.card.star.set_visible(wall.path in self.favorites)
        self.refresh_fav_button()
        self.update_counts()
        if self.view == "favoritos":
            self.refilter(keep_selection=True)

    def show_tags(self):
        wall = self.current
        if not wall:
            return
        self.tags_title.set_text(wall.name)
        self._refresh_tag_checks()
        self.tag_list.select_row(self.tag_list.get_row_at_index(0))
        self.detail_stack.set_visible_child_name("tags")

    def hide_tags(self):
        self.detail_stack.set_visible_child_name("info")
        self.refilter(keep_selection=True)
        self.update_detail()

    def _refresh_tag_checks(self):
        marked = self.tags.get(self.current.path, [])
        for row in self.tag_list.get_children():
            row.check.set_text(GLYPH_CHECK if row.tag_id in marked else GLYPH_UNCHECK)

    def toggle_tag(self, tag_id):
        wall = self.current
        marked = list(self.tags.get(wall.path, []))
        if tag_id in marked:
            marked.remove(tag_id)
        else:
            marked.append(tag_id)
        if marked:
            self.tags[wall.path] = marked
        else:
            self.tags.pop(wall.path, None)
        base.save_json(TAGS_FILE, self.tags)
        self._refresh_tag_checks()
        self.update_counts()

    def move_selection(self, dx=0, dy=0):
        page = self.mid_stack.get_visible_child_name()
        if page in ("folders", "picker"):
            lb = self.folder_list if page == "folders" else self.picker_list
            rows = lb.get_children()
            cur = lb.get_selected_row()
            idx = rows.index(cur) if cur in rows else -1
            row = rows[max(0, min(len(rows) - 1, idx + dx + dy))]
            lb.select_row(row)
            self._scroll_row(lb, row)
            return
        if not self.ordered:
            return
        idx = self.ordered.index(self.current) if self.current in self.ordered else -1
        step = dx + dy * self.columns
        target = self.ordered[0] if idx < 0 else self.ordered[max(0, min(len(self.ordered) - 1, idx + step))]
        self.flow.select_child(target.card)
        self.scroll_to(target.card)

    @staticmethod
    def _scroll_row(listbox, row):
        adj = listbox.scroller.get_vadjustment()
        alloc = row.get_allocation()
        if alloc.y < adj.get_value():
            adj.set_value(alloc.y)
        elif alloc.y + alloc.height > adj.get_value() + adj.get_page_size():
            adj.set_value(alloc.y + alloc.height - adj.get_page_size())

    def cycle_side(self, step):
        rows = [r for r in self.side_list.get_children() if r.get_selectable()]
        cur = self.side_list.get_selected_row()
        nxt = rows[((rows.index(cur) if cur in rows else 0) + step) % len(rows)]
        self.side_list.select_row(nxt)

    # ---------- eventos ----------
    def on_search_changed(self, _entry):
        self.placeholder.set_visible(not self.search.get_text())
        if self.search.get_text().strip() and self.view != "todos":
            self.side_list.select_row(self.side_rows["todos"])
        else:
            self.refilter()

    def on_side_selected(self, _lb, row):
        if row is None:
            # SINGLE deselecciona al pulsar la fila activa: se vuelve a marcar
            GLib.idle_add(self.side_list.select_row, self.side_rows[self.view])
            return
        self.view = row.side_id
        self.picking = False
        self.refilter()

    def on_side_activated(self, _lb, row):
        # clic en Carpetas estando ya ahi: vuelve a la lista (cierra el selector)
        if row.side_id == self.view == "carpetas" and self.picking:
            self.close_picker()

    def on_selection_changed(self, flow):
        selected = flow.get_selected_children()
        self.current = selected[0].wall if selected else None
        self.update_detail()

    def on_backdrop_click(self, root, event):
        # un widget con ventana propia (tarjeta, boton) implica clic dentro del panel
        if Gtk.get_event_widget(event) is not root:
            return False
        a = self.panel.get_allocation()
        if not (a.x <= event.x <= a.x + a.width and a.y <= event.y <= a.y + a.height):
            Gtk.main_quit()
        return False

    def on_escape(self):
        if self.detail_stack.get_visible_child_name() == "tags":
            self.hide_tags()
        elif self.picking:
            self.close_picker()
        else:
            Gtk.main_quit()

    def on_key(self, _win, event):
        key = Gdk.keyval_name(event.keyval)
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
        in_tags = self.detail_stack.get_visible_child_name() == "tags"
        if key == "Escape":
            self.on_escape()
        elif in_tags and key in ("Up", "Down"):
            rows = self.tag_list.get_children()
            cur = self.tag_list.get_selected_row()
            idx = rows.index(cur) if cur in rows else 0
            self.tag_list.select_row(rows[max(0, min(len(rows) - 1, idx + (1 if key == "Down" else -1)))])
        elif in_tags and key in ("Return", "KP_Enter", "space"):
            row = self.tag_list.get_selected_row()
            if row:
                self.toggle_tag(row.tag_id)
        elif in_tags:
            return False
        elif key in ("Down", "Up"):
            self.move_selection(dy=1 if key == "Down" else -1)
        elif key in ("Left", "Right") and not self.search.get_text():
            self.move_selection(dx=1 if key == "Right" else -1)
        elif key in ("Return", "KP_Enter"):
            page = self.mid_stack.get_visible_child_name()
            row = (self.folder_list if page == "folders" else self.picker_list).get_selected_row()
            if page == "picker" and ctrl:
                self.picker_use()
            elif page == "folders" and row:
                self.on_folder_row(row)
            elif page == "picker" and row:
                self.on_picker_row(row)
            elif page not in ("folders", "picker") and self.current:
                self.apply(self.current)
        elif key == "Tab":
            self.cycle_side(1)
        elif key == "ISO_Left_Tab":
            self.cycle_side(-1)
        elif ctrl and key in ("f", "F"):
            self.toggle_favorite()
        elif ctrl and key in ("t", "T") and self.current:
            self.show_tags()
        elif ctrl and key in ("g", "G"):
            self.toggle_columns()
        else:
            return False
        return True


def toggle_running_instance():
    """Si ya hay una instancia abierta la cierra y devuelve True."""
    try:
        with open(PID_FILE) as f:
            pid = int(f.read())
        with open(f"/proc/{pid}/cmdline") as f:
            if "wallpaper_select.py" in f.read():
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
    win = WallpaperWindow()
    GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, Gtk.main_quit)
    win.show_all()
    Gtk.main()
    try:
        os.remove(PID_FILE)
    except OSError:
        pass


if __name__ == "__main__":
    main()
