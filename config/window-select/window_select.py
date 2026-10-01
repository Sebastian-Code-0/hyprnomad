#!/usr/bin/env python3
"""Selector de ventanas con miniaturas, espacios de trabajo y acciones rapidas."""
import json
import os
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

GLib.set_prgname("window-select")

CSS_PATH = os.path.join(BASE_DIR, "style.css")
DATA_DIR = os.path.join(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")), "window-select")
CACHE_DIR = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "window-select")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
THUMB_DIR = os.path.join(CACHE_DIR, "thumbs")
# capturas que guarda window_thumb_daemon.py al abrirse cada ventana
SRC_THUMB_DIR = os.path.expanduser("~/.cache/hypr-winselect")
PID_FILE = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "window-select.pid")


def private_dir(path):
    """Crea el directorio solo accesible por el usuario (la caché puede contener datos privados)."""
    os.makedirs(path, exist_ok=True)
    os.chmod(path, 0o700)

THUMB_W = 560
PANEL_W, PANEL_H = 1100, 600
SIDEBAR_W, DETAIL_W = 230, 340
PREVIEW_H = 178
GRID_GAP = 12

GLYPH_WINDOWS, GLYPH_HERE, GLYPH_SPACE = chr(0xF2D2), chr(0xF108), chr(0xF2D0)
GLYPH_SPECIAL, GLYPH_GO, GLYPH_BRING = chr(0xF24D), chr(0xF061), chr(0xF0B2)
GLYPH_CLOSE, GLYPH_RES, GLYPH_WS, GLYPH_CURRENT = chr(0xF2D3), chr(0xf065), chr(0xF009), chr(0xF108)

FALLBACK_ICON = "application-x-executable"


def hyprctl(*args):
    """Salida JSON de `hyprctl -j`, o None si falla."""
    try:
        out = subprocess.run(["hyprctl", "-j", *args], capture_output=True, text=True, timeout=3).stdout
        return json.loads(out) if out.strip() else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def dispatch(*args):
    subprocess.run(["hyprctl", "dispatch", *args], capture_output=True)


def fetch_state():
    """(ventanas, id del espacio activo, direccion de la ventana activa)."""
    clients = [c for c in (hyprctl("clients") or []) if c.get("mapped")]
    ws = hyprctl("activeworkspace") or {}
    active = hyprctl("activewindow") or {}
    return clients, ws.get("id"), active.get("address")


def ws_label(ws_id, name):
    if ws_id is not None and ws_id < 0 or str(name).startswith("special"):
        tail = str(name).partition(":")[2]
        return "Scratchpad" if tail in ("", "magic") else tail.capitalize()
    return f"Espacio {ws_id}"


class AppIcons:
    """Busca el icono real de una clase de ventana en los .desktop instalados."""

    def __init__(self):
        self.index = {}
        for app in Gio.AppInfo.get_all():
            keys = {(app.get_id() or "").removesuffix(".desktop").lower(), (app.get_name() or "").lower()}
            wm = app.get_startup_wm_class() if hasattr(app, "get_startup_wm_class") else None
            if wm:
                keys.add(wm.lower())
            for key in keys - {""}:
                self.index.setdefault(key, app)
        self.theme = Gtk.IconTheme.get_default()

    def gicon(self, cls):
        cls = (cls or "").lower()
        for key in (cls, cls.rsplit(".", 1)[-1]):
            app = self.index.get(key)
            if app and app.get_icon():
                return app.get_icon()
        for key in (cls, cls.rsplit(".", 1)[-1]):
            if key and self.theme.has_icon(key):
                return Gio.ThemedIcon.new(key)
        return Gio.ThemedIcon.new(FALLBACK_ICON)


class Win:
    def __init__(self, c, icons):
        self.addr = c["address"]
        self.cls = c.get("class") or ""
        self.title = c.get("title") or "(sin título)"
        self.pid = c.get("pid")
        self.ws_id = c["workspace"]["id"]
        self.ws = ws_label(self.ws_id, c["workspace"]["name"])
        self.size = tuple(c.get("size", (0, 0)))
        self.at = tuple(c.get("at", (0, 0)))
        self.floating = bool(c.get("floating"))
        self.fullscreen = bool(c.get("fullscreen"))
        self.pinned = bool(c.get("pinned"))
        self.xwayland = bool(c.get("xwayland"))
        self.focus = c.get("focusHistoryID", 99)
        self.src = os.path.join(SRC_THUMB_DIR, self.addr.replace("0x", "") + ".png")
        self.gicon = icons.gicon(self.cls)
        self.thumb = None
        self.show = True
        self.search = f"{self.title} {self.cls} {self.ws}".casefold()

    def chips(self, active):
        flags = [(active, "activa"), (self.floating, "flotante"), (self.fullscreen, "pantalla completa"),
                 (self.pinned, "fijada"), (self.xwayland, "XWayland")]
        return [text for on, text in flags if on]


def capture_missing(wins, active_ws, active_addr):
    """Captura la ventana activa (miniatura al dia) y las visibles que aun no tienen una."""
    private_dir(SRC_THUMB_DIR)
    procs = []
    for win in wins:
        has_thumb = os.path.exists(win.src) and os.path.getsize(win.src)
        if win.ws_id == active_ws and (win.addr == active_addr or not has_thumb):
            x, y = win.at
            w, h = win.size
            tmp = win.src + ".tmp.png"
            procs.append((win, subprocess.Popen(["grim", "-g", f"{x},{y} {w}x{h}", tmp],
                                                stderr=subprocess.DEVNULL)))
    for win, proc in procs:
        tmp = win.src + ".tmp.png"
        if proc.wait() == 0 and os.path.exists(tmp):
            os.replace(tmp, win.src)
        elif os.path.exists(tmp):
            os.remove(tmp)


def clean_stale(wins):
    """Borra miniaturas de ventanas que ya no existen."""
    valid = {w.addr.replace("0x", "") for w in wins}
    try:
        for name in os.listdir(SRC_THUMB_DIR):
            if name.endswith(".png") and not name.endswith(".tmp.png") and name[:-4] not in valid:
                os.remove(os.path.join(SRC_THUMB_DIR, name))
    except OSError:
        pass


class WindowSelector(Gtk.Window):
    def __init__(self):
        super().__init__()
        self.view = "todas"
        self.current = None
        self.wins = []
        self.ordered = []
        self.active_ws = None
        self.active_addr = None
        self.after_close = []
        self.building = False
        self.settings = base.load_json(SETTINGS_FILE, {})
        self.columns = 3 if self.settings.get("columns") == 3 else 2
        self.icons = AppIcons()
        self._last_flow_w = 0

        self._setup_layer()
        self._load_css()
        self._build_ui()

    # ---------- ventana ----------
    def _setup_layer(self):
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_namespace(self, "window-select")
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
        self.connect("destroy", lambda *_: Gtk.main_level() and Gtk.main_quit())

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

    # ---------- interfaz ----------
    @staticmethod
    def _label(text, css_class, xalign=0):
        lbl = Gtk.Label(label=text, xalign=xalign)
        if css_class:
            lbl.get_style_context().add_class(css_class)
        return lbl

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
        note = Gtk.Label(label="Selector de ventanas")
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
        self.placeholder = Gtk.Label(label="Buscar ventana...", xalign=0)
        self.placeholder.get_style_context().add_class("placeholder")
        self.placeholder.set_margin_start(2)
        overlay = Gtk.Overlay()
        overlay.add(self.search)
        overlay.add_overlay(self.placeholder)
        overlay.set_overlay_pass_through(self.placeholder, True)
        search.pack_start(overlay, True, True, 0)
        header.set_center_widget(search)
        return header

    def _build_sidebar(self):
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        side.get_style_context().add_class("cats")
        self.side_rows = {}
        self.side_list = Gtk.ListBox()
        self.side_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.side_list.set_can_focus(False)
        self.side_list.connect("row-selected", self.on_side_selected)
        side.pack_start(self.side_list, False, False, 0)

        footer = Gtk.Box(spacing=10)
        footer.set_valign(Gtk.Align.END)
        footer.set_tooltip_text("Ventana donde estás ahora")
        footer.pack_start(base.glyph_label(GLYPH_CURRENT, "cat-glyph"), False, False, 0)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        col.pack_start(self._label("Ventana actual", "hint"), False, False, 0)
        self.current_label = self._label("", None)
        self.current_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.current_label.set_max_width_chars(20)
        col.pack_start(self.current_label, False, False, 0)
        footer.pack_start(col, True, True, 0)
        side.pack_end(footer, True, True, 0)
        return base.Launcher._fixed_column(side, SIDEBAR_W)

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

    def _rebuild_sidebar(self):
        """Filas fijas + un espacio de trabajo por cada uno que tenga ventanas."""
        for row in self.side_list.get_children():
            self.side_list.remove(row)
        self.side_rows = {}
        self.side_list.add(self._sidebar_row("todas", "Ventanas", GLYPH_WINDOWS))
        self.side_list.add(self._sidebar_row("actual", "Este espacio", GLYPH_HERE))

        sep_row = Gtk.ListBoxRow()
        sep_row.set_selectable(False)
        sep_row.set_activatable(False)
        sep_row.get_style_context().add_class("plain-row")
        sep_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        sep_box.pack_start(Gtk.Separator(), False, False, 6)
        sep_box.pack_start(self._label("ESPACIOS DE TRABAJO", "section-title"), False, False, 0)
        sep_row.add(sep_box)
        self.side_list.add(sep_row)

        spaces = {}
        for win in self.wins:
            spaces[win.ws_id] = win.ws
        for ws_id in sorted(spaces, key=lambda i: (i < 0, abs(i))):
            glyph = GLYPH_SPECIAL if ws_id < 0 else GLYPH_SPACE
            self.side_list.add(self._sidebar_row(f"ws:{ws_id}", spaces[ws_id], glyph))
        self.side_list.show_all()

    def _build_middle(self):
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.mid_stack = Gtk.Stack()
        self.mid_stack.add_named(self._build_grid(), "grid")
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
        self.scroller.get_hadjustment().connect("value-changed", lambda a: a.get_value() and a.set_value(0))

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
        self.flow.set_filter_func(lambda child: child.win.show)
        self.flow.set_sort_func(lambda a, b: a.win.focus - b.win.focus)
        self.flow.connect("selected-children-changed", self.on_selection_changed)
        self.flow.connect("child-activated", lambda _fb, child: self.go(child.win))
        self.flow.connect("size-allocate", self._on_flow_allocate)
        self.scroller.add(self.flow)
        return self.scroller

    def _build_detail(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        page.get_style_context().add_class("detail")
        page.set_border_width(16)

        overlay = Gtk.Overlay()
        overlay.set_size_request(-1, PREVIEW_H)
        self.preview = Gtk.Box()
        for cls in ("wthumb", "preview"):
            self.preview.get_style_context().add_class(cls)
        self.preview_css = Gtk.CssProvider()
        self.preview.get_style_context().add_provider(self.preview_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        overlay.add(self.preview)
        self.preview_icon = Gtk.Image()
        self.preview_icon.set_pixel_size(72)
        self.preview_icon.set_halign(Gtk.Align.CENTER)
        self.preview_icon.set_valign(Gtk.Align.CENTER)
        overlay.add_overlay(self.preview_icon)
        overlay.set_overlay_pass_through(self.preview_icon, True)
        page.pack_start(overlay, False, False, 0)

        self.d_name = self._label("", "d-name")
        self.d_name.set_ellipsize(Pango.EllipsizeMode.END)
        page.pack_start(self.d_name, False, False, 2)
        self.d_app = self._label("", "d-generic")
        self.d_app.set_ellipsize(Pango.EllipsizeMode.END)
        page.pack_start(self.d_app, False, False, 0)

        meta = Gtk.Box(spacing=18)
        self.d_ws = self._meta_item(GLYPH_WS, meta)
        self.d_size = self._meta_item(GLYPH_RES, meta)
        page.pack_start(meta, False, False, 0)

        self.d_chips = Gtk.Box(spacing=6)
        page.pack_start(self.d_chips, False, False, 0)

        bottom = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        page.pack_end(bottom, False, False, 0)
        self.btn_go = base.action_button(GLYPH_GO, "Ir a la ventana", "primary", "↵")
        self.btn_go.connect("clicked", lambda *_: self.current and self.go(self.current))
        bottom.pack_start(self.btn_go, False, False, 0)
        row = Gtk.Box(spacing=8, homogeneous=True)
        self.btn_bring = base.action_button(GLYPH_BRING, "Traer aquí")
        self.btn_bring.set_tooltip_text("Ctrl+M · mueve la ventana a este espacio")
        self.btn_bring.connect("clicked", lambda *_: self.current and self.bring(self.current))
        self.btn_close = base.action_button(GLYPH_CLOSE, "Cerrar")
        self.btn_close.set_tooltip_text("Ctrl+W · cierra la ventana")
        self.btn_close.connect("clicked", lambda *_: self.current and self.close_window(self.current))
        row.pack_start(self.btn_bring, True, True, 0)
        row.pack_start(self.btn_close, True, True, 0)
        bottom.pack_start(row, False, False, 0)
        return base.Launcher._fixed_column(page, DETAIL_W)

    def _meta_item(self, glyph, parent):
        box = Gtk.Box(spacing=8)
        box.pack_start(base.glyph_label(glyph, "meta-glyph"), False, False, 0)
        lbl = Gtk.Label(xalign=0)
        box.pack_start(lbl, False, False, 0)
        parent.pack_start(box, False, False, 0)
        return lbl

    # ---------- datos ----------
    def load(self, keep_index=None):
        """Lee las ventanas de Hyprland y reconstruye barra lateral y cuadricula."""
        clients, self.active_ws, self.active_addr = fetch_state()
        self.wins = sorted((Win(c, self.icons) for c in clients), key=lambda w: w.focus)
        capture_missing(self.wins, self.active_ws, self.active_addr)
        clean_stale(self.wins)

        self.building = True
        for child in self.flow.get_children():
            self.flow.remove(child)
        self.current = None
        for win in self.wins:
            self.flow.add(self._build_card(win))
        self.flow.show_all()
        self._rebuild_sidebar()
        self.building = False

        self.update_counts()
        row = self.side_rows.get(self.view) or self.side_rows["todas"]
        self.side_list.select_row(row)
        self.refilter()
        if keep_index is not None and self.ordered:
            self.select_win(self.ordered[min(keep_index, len(self.ordered) - 1)])
        elif len(self.ordered) > 1 and self.view == "todas" and not self.search.get_text():
            # como Alt+Tab: preselecciona la ventana anterior a la actual
            self.select_win(self.ordered[1])
        threading.Thread(target=self._make_thumbs, args=(self.wins,), daemon=True).start()

    def _make_thumbs(self, wins):
        """Reduce las capturas a un tamaño de miniatura (cache por ventana+fecha)."""
        private_dir(CACHE_DIR)
        private_dir(THUMB_DIR)
        keep = set()
        for win in wins:
            try:
                mtime = int(os.path.getmtime(win.src))
                if not os.path.getsize(win.src):
                    continue
            except OSError:
                continue
            path = os.path.join(THUMB_DIR, f"{win.addr.replace('0x', '')}-{mtime}.png")
            keep.add(os.path.basename(path))
            try:
                if not os.path.exists(path):
                    pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(win.src, THUMB_W, -1, True)
                    pb.savev(path + ".tmp", "png", [], [])
                    os.replace(path + ".tmp", path)
                GLib.idle_add(self._set_thumb, wins, win, path)
            except (GLib.Error, OSError):
                continue
        for name in os.listdir(THUMB_DIR):
            if name not in keep and not name.endswith(".tmp"):
                try:
                    os.remove(os.path.join(THUMB_DIR, name))
                except OSError:
                    pass

    def _set_thumb(self, wins, win, path):
        if wins is not self.wins:
            return False
        win.thumb = path
        win.card.css.load_from_data(f'.wthumb {{ background-image: url("{path}"); }}'.encode())
        win.card.big_icon.hide()
        if win is self.current:
            self.update_detail()
        return False

    # ---------- cuadricula ----------
    def _card_size(self):
        avail = self._last_flow_w or 490
        w = (avail - (self.columns - 1) * GRID_GAP) // self.columns - 1
        return w, w * 9 // 16

    def _build_card(self, win):
        child = Gtk.FlowBoxChild()
        child.win = win
        win.card = child
        child.set_can_focus(False)
        child.set_tooltip_text(win.title)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        overlay = Gtk.Overlay()
        thumb = Gtk.Box()
        thumb.get_style_context().add_class("wthumb")
        w, h = self._card_size()
        thumb.set_size_request(w, h)
        child.css = Gtk.CssProvider()
        thumb.get_style_context().add_provider(child.css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        overlay.add(thumb)
        child.thumb = thumb

        child.big_icon = Gtk.Image.new_from_gicon(win.gicon, Gtk.IconSize.DIALOG)
        child.big_icon.set_pixel_size(56)
        child.big_icon.set_halign(Gtk.Align.CENTER)
        child.big_icon.set_valign(Gtk.Align.CENTER)
        overlay.add_overlay(child.big_icon)
        overlay.set_overlay_pass_through(child.big_icon, True)

        space = self._label(win.ws, "card-badge")
        space.set_halign(Gtk.Align.END)
        space.set_valign(Gtk.Align.START)
        overlay.add_overlay(space)
        overlay.set_overlay_pass_through(space, True)
        if win.addr == self.active_addr:
            badge = self._label("en uso", "card-badge")
            badge.set_halign(Gtk.Align.START)
            badge.set_valign(Gtk.Align.START)
            overlay.add_overlay(badge)
            overlay.set_overlay_pass_through(badge, True)
        outer.pack_start(overlay, False, False, 0)

        info = Gtk.Box(spacing=8)
        icon = Gtk.Image.new_from_gicon(win.gicon, Gtk.IconSize.LARGE_TOOLBAR)
        icon.set_pixel_size(24)
        info.pack_start(icon, False, False, 0)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        texts.set_valign(Gtk.Align.CENTER)
        title = self._label(win.title, "app-name")
        title.set_ellipsize(Pango.EllipsizeMode.END)
        title.set_max_width_chars(1)
        sub = self._label(win.cls or "—", "app-sub")
        sub.set_ellipsize(Pango.EllipsizeMode.END)
        sub.set_max_width_chars(1)
        texts.pack_start(title, False, False, 0)
        texts.pack_start(sub, False, False, 0)
        info.pack_start(texts, True, True, 0)
        outer.pack_start(info, False, False, 0)
        child.add(outer)
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
        for win in self.wins:
            win.card.thumb.set_size_request(w, h)
        return False

    def toggle_columns(self):
        self.columns = 2 if self.columns == 3 else 3
        self.settings["columns"] = self.columns
        base.save_json(SETTINGS_FILE, self.settings)
        self.apply_columns()
        if self.current:
            GLib.idle_add(self.scroll_to, self.current.card)

    # ---------- filtrado ----------
    def _view_wins(self):
        query = self.search.get_text().strip().casefold()
        if query:
            return [w for w in self.wins if query in w.search]
        if self.view == "actual":
            return [w for w in self.wins if w.ws_id == self.active_ws]
        if self.view.startswith("ws:"):
            return [w for w in self.wins if w.ws_id == int(self.view[3:])]
        return list(self.wins)

    def _empty_text(self):
        if self.search.get_text().strip():
            return "Sin resultados"
        return "No hay ventanas en este espacio"

    def update_counts(self):
        totals = {"todas": len(self.wins),
                  "actual": sum(1 for w in self.wins if w.ws_id == self.active_ws)}
        for win in self.wins:
            key = f"ws:{win.ws_id}"
            totals[key] = totals.get(key, 0) + 1
        for rid, row in self.side_rows.items():
            row.count_label.set_text(str(totals.get(rid, 0)))
            ctx = row.get_style_context()
            if totals.get(rid, 0) == 0:
                ctx.add_class("empty-cat")
            else:
                ctx.remove_class("empty-cat")
        active = next((w for w in self.wins if w.addr == self.active_addr), None)
        self.current_label.set_text(active.title if active else "—")

    def refilter(self):
        wins = self._view_wins()
        visible = set(wins)
        for win in self.wins:
            win.show = win in visible
        self.ordered = sorted(wins, key=lambda w: w.focus)
        self.flow.invalidate_filter()
        self.flow.invalidate_sort()

        if not self.ordered:
            self.empty_label.set_text(self._empty_text())
            self.mid_stack.set_visible_child_name("empty")
            self.flow.unselect_all()
            self.current = None
            self.update_detail()
            return
        self.mid_stack.set_visible_child_name("grid")
        self.select_win(self.ordered[0])
        self.scroller.get_vadjustment().set_value(0)

    def select_win(self, win):
        self.flow.select_child(win.card)
        GLib.idle_add(self.scroll_to, win.card)

    def scroll_to(self, card):
        adj = self.scroller.get_vadjustment()
        coords = card.translate_coordinates(self.flow, 0, 0)
        if coords is None:
            return False
        top, height = coords[1], card.get_allocated_height()
        if top < adj.get_value():
            adj.set_value(top)
        elif top + height > adj.get_value() + adj.get_page_size():
            adj.set_value(top + height - adj.get_page_size())
        return False

    def update_detail(self):
        win = self.current
        for widget in (self.btn_go, self.btn_bring, self.btn_close):
            widget.set_sensitive(win is not None)
        for chip in self.d_chips.get_children():
            self.d_chips.remove(chip)
        if not win:
            self.d_name.set_text("Selecciona una ventana")
            self.d_name.set_tooltip_text(None)
            self.d_app.set_text("")
            self.d_ws.set_text("—")
            self.d_size.set_text("—")
            self.preview_css.load_from_data(b".wthumb { background-image: none; }")
            self.preview_icon.clear()
            return
        self.d_name.set_text(win.title)
        self.d_name.set_tooltip_text(win.title)
        self.d_app.set_text(f"{win.cls or '—'} · PID {win.pid}")
        self.d_ws.set_text(win.ws)
        self.d_size.set_text(f"{win.size[0]}×{win.size[1]}")
        self.btn_bring.set_sensitive(win.ws_id != self.active_ws)
        if win.thumb:
            self.preview_css.load_from_data(f'.wthumb {{ background-image: url("{win.thumb}"); }}'.encode())
            self.preview_icon.clear()
        else:
            self.preview_css.load_from_data(b".wthumb { background-image: none; }")
            self.preview_icon.set_from_gicon(win.gicon, Gtk.IconSize.DIALOG)
            self.preview_icon.set_pixel_size(72)
        for text in win.chips(win.addr == self.active_addr):
            chip = self._label(text, "chip")
            self.d_chips.pack_start(chip, False, False, 0)
        self.d_chips.show_all()

    # ---------- acciones ----------
    def _finish(self, *commands):
        """Cierra el selector y luego ejecuta los comandos (el foco vuelve solo al cerrar)."""
        self.after_close = list(commands)
        Gtk.main_quit()

    def go(self, win):
        self._finish(["focuswindow", f"address:{win.addr}"])

    def bring(self, win):
        if win.ws_id == self.active_ws or self.active_ws is None:
            return self.go(win)
        self._finish(["movetoworkspacesilent", f"{self.active_ws},address:{win.addr}"],
                     ["focuswindow", f"address:{win.addr}"])

    def close_window(self, win):
        """Pide a la app que cierre la ventana (puede preguntar si hay cambios) y refresca."""
        idx = self.ordered.index(win) if win in self.ordered else 0
        dispatch("closewindow", f"address:{win.addr}")
        GLib.timeout_add(450, self._after_close_window, idx)

    def _after_close_window(self, idx):
        self.load(keep_index=idx)
        if not self.wins:
            Gtk.main_quit()
        return False

    def move_selection(self, dx=0, dy=0):
        if not self.ordered:
            return
        idx = self.ordered.index(self.current) if self.current in self.ordered else -1
        step = dx + dy * self.columns
        target = self.ordered[0] if idx < 0 else self.ordered[max(0, min(len(self.ordered) - 1, idx + step))]
        self.flow.select_child(target.card)
        self.scroll_to(target.card)

    def cycle_side(self, step):
        rows = [r for r in self.side_list.get_children() if r.get_selectable()]
        cur = self.side_list.get_selected_row()
        nxt = rows[((rows.index(cur) if cur in rows else 0) + step) % len(rows)]
        self.side_list.select_row(nxt)

    # ---------- eventos ----------
    def on_search_changed(self, _entry):
        self.placeholder.set_visible(not self.search.get_text())
        if self.search.get_text().strip() and self.view != "todas":
            self.side_list.select_row(self.side_rows["todas"])
        else:
            self.refilter()

    def on_side_selected(self, _lb, row):
        if self.building:
            return
        if row is None:
            # SINGLE deselecciona al pulsar la fila activa: se vuelve a marcar
            target = self.side_rows.get(self.view)
            if target:
                GLib.idle_add(self.side_list.select_row, target)
            return
        self.view = row.side_id
        self.refilter()

    def on_selection_changed(self, flow):
        selected = flow.get_selected_children()
        self.current = selected[0].win if selected else None
        self.update_detail()

    def on_backdrop_click(self, root, event):
        # un widget con ventana propia (tarjeta, boton) implica clic dentro del panel
        if Gtk.get_event_widget(event) is not root:
            return False
        a = self.panel.get_allocation()
        if not (a.x <= event.x <= a.x + a.width and a.y <= event.y <= a.y + a.height):
            Gtk.main_quit()
        return False

    def on_key(self, _win, event):
        key = Gdk.keyval_name(event.keyval)
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
        if key == "Escape":
            Gtk.main_quit()
        elif key in ("Down", "Up"):
            self.move_selection(dy=1 if key == "Down" else -1)
        elif key in ("Left", "Right") and not self.search.get_text():
            self.move_selection(dx=1 if key == "Right" else -1)
        elif key in ("Return", "KP_Enter"):
            if self.current:
                self.go(self.current)
        elif key == "Tab":
            self.cycle_side(1)
        elif key == "ISO_Left_Tab":
            self.cycle_side(-1)
        elif ctrl and key in ("w", "W") and self.current:
            self.close_window(self.current)
        elif ctrl and key in ("m", "M") and self.current:
            self.bring(self.current)
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
            if "window_select.py" in f.read():
                os.kill(pid, signal.SIGTERM)
                return True
    except (OSError, ValueError):
        pass
    return False


def main():
    if toggle_running_instance():
        return
    clients, _, _ = fetch_state()
    if not clients:
        subprocess.run(["notify-send", "Selector de ventanas", "No hay ventanas abiertas"])
        return
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    win = WindowSelector()
    GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, Gtk.main_quit)
    win.load()
    win.show_all()
    win.search.grab_focus()
    Gtk.main()
    commands = win.after_close
    win.destroy()
    Gdk.Display.get_default().flush()
    try:
        os.remove(PID_FILE)
    except OSError:
        pass
    for cmd in commands:
        dispatch(*cmd)


if __name__ == "__main__":
    main()
