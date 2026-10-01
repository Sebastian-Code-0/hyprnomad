#!/usr/bin/env python3
"""Lanzador de aplicaciones con categorias, detalle y favoritos."""
import json
import os
import re
import shlex
import signal
import subprocess
import threading

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
gi.require_version("GLibUnix", "2.0")
from gi.repository import Gdk, Gio, GLib, GLibUnix, Gtk, GtkLayerShell

GLib.set_prgname("launcher")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSS_PATH = os.path.join(BASE_DIR, "style.css")
COVER_PATH = os.path.join(BASE_DIR, "assets", "cover.jpg")
DATA_DIR = os.path.expanduser("~/.local/share/launcher")
FAV_FILE = os.path.join(DATA_DIR, "favorites.json")
USAGE_FILE = os.path.join(DATA_DIR, "usage.json")
PID_FILE = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "launcher.pid")
PYWAL_DIR = os.path.expanduser("~/.cache/wal")
PYWAL_COLORS_JSON = os.path.join(PYWAL_DIR, "colors.json")
PYWAL_FILES = ("colors-waybar.css", "colors.json")
TERMINAL = "kitty"
PHRASE = "Маленькие шаги — большие перемены"
PHRASE_ES = "Pequeños pasos, grandes cambios"

# id, etiqueta, icono (Nerd Font)
CATEGORIES = [
    ("todas", "Todas", ""),
    ("favoritos", "Favoritos", ""),
    ("internet", "Internet", ""),
    ("terminal", "Terminal", ""),
    ("desarrollo", "Desarrollo", ""),
    ("oficina", "Oficina", ""),
    ("multimedia", "Multimedia", ""),
    ("graficos", "Gráficos", ""),
    ("juegos", "Juegos", ""),
    ("sistema", "Sistema", ""),
    ("otros", "Otros", ""),
]
CAT_LABEL = {cid: label for cid, label, _ in CATEGORIES}

# categorias .desktop por grupo; gana el primero que coincida
CATEGORY_MAP = [
    ("juegos", {"Game"}),
    ("terminal", {"TerminalEmulator"}),
    ("desarrollo", {"Development", "IDE", "TextEditor"}),
    ("internet", {"Network", "WebBrowser", "Email", "InstantMessaging", "Chat", "FileTransfer"}),
    ("oficina", {"Office", "Calendar", "ContactManagement", "Dictionary", "Spreadsheet",
                 "WordProcessor", "Presentation", "Finance"}),
    ("graficos", {"Graphics"}),
    ("multimedia", {"AudioVideo", "Audio", "Video", "Player", "Recorder", "Music", "Mixer", "TV"}),
    ("sistema", {"System", "Settings", "DesktopSettings", "HardwareSettings", "Monitor",
                 "PackageManager", "FileManager", "FileTools", "Utility", "Accessibility"}),
]

GLYPH_ARCH = ""
GLYPH_SEARCH = ""
GLYPH_STAR = ""
GLYPH_STAR_O = ""
GLYPH_OPEN = ""
GLYPH_INFO = ""
GLYPH_BACK = ""


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, path)


def _luminance(hex_color):
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    h = hex_color.lstrip("#")
    r, g, b = (lin(int(h[i:i + 2], 16)) for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def text_safe_color():
    """Texto blanco/negro puro si el par fondo/texto de pywal contrasta poco (WCAG)."""
    try:
        special = load_json(PYWAL_COLORS_JSON, {})["special"]
        la, lb = _luminance(special["background"]), _luminance(special["foreground"])
        if (max(la, lb) + 0.05) / (min(la, lb) + 0.05) < 4.5:
            return "#ffffff" if la < 0.5 else "#000000"
    except Exception:
        pass
    return "@foreground"


def classify(app):
    if app.get_boolean("Terminal"):
        return "terminal"
    cats = set((app.get_categories() or "").split(";"))
    for key, group in CATEGORY_MAP:
        if cats & group:
            return key
    return "otros"


def strip_field_codes(cmd):
    return re.sub(r"%[a-zA-Z]", "", cmd.replace("%%", "\0")).replace("\0", "%").strip()


class AppEntry:
    def __init__(self, app):
        self.app = app
        self.id = app.get_id()
        self.name = app.get_name() or self.id
        self.generic = app.get_generic_name() or ""
        self.comment = app.get_description() or ""
        self.keywords = [k.strip() for k in (app.get_keywords() or []) if k.strip()]
        self.cat = classify(app)
        self.name_l = self.name.casefold()
        self.extra_l = " ".join(
            [self.generic, self.comment, self.id, *self.keywords]
        ).casefold()
        self.score = 0
        self.show = True

    @property
    def subtitle(self):
        return self.generic or self.comment or CAT_LABEL[self.cat]

    def stickers(self):
        seen, tags = set(), []
        for tag in [*self.keywords, CAT_LABEL[self.cat]]:
            t = tag.casefold()
            if t not in seen and len(t) <= 10:
                seen.add(t)
                tags.append(t)
        return tags[:3]


def lock_scroll(scrolled):
    """Impide mover el contenido con el dedo o la rueda (pantalla tactil)."""
    scrolled.set_kinetic_scrolling(False)
    for adj in (scrolled.get_hadjustment(), scrolled.get_vadjustment()):
        adj.connect("value-changed", lambda a: a.get_value() and a.set_value(0))


def glyph_label(glyph, css_class="glyph"):
    lbl = Gtk.Label(label=glyph)
    lbl.get_style_context().add_class(css_class)
    return lbl


def action_button(glyph, text, css_class=None, hint=None):
    btn = Gtk.Button()
    btn.set_relief(Gtk.ReliefStyle.NONE)
    btn.get_style_context().add_class("action-btn")
    if css_class:
        btn.get_style_context().add_class(css_class)
    box = Gtk.Box(spacing=12)
    icon = glyph_label(glyph, "btn-glyph")
    label = Gtk.Label(label=text, xalign=0)
    box.pack_start(icon, False, False, 0)
    box.pack_start(label, True, True, 0)
    if hint:
        h = Gtk.Label(label=hint)
        h.get_style_context().add_class("hint")
        box.pack_end(h, False, False, 0)
    btn.add(box)
    btn.glyph, btn.label = icon, label
    return btn


class Launcher(Gtk.Window):
    def __init__(self):
        super().__init__()
        self.category = "todas"
        self.current = None
        self.ordered = []
        self.favorites = load_json(FAV_FILE, [])
        self.usage = load_json(USAGE_FILE, {})
        self.details_cache = {}

        self._setup_layer()
        self._load_css()
        self.entries = self._scan_apps()
        self._build_ui()
        self._populate()

    # ---------- ventana ----------
    def _setup_layer(self):
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_namespace(self, "launcher")
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
        self.safe_provider = safe = Gtk.CssProvider()
        safe.load_from_data(f"@define-color text_safe {text_safe_color()};".encode())
        Gtk.StyleContext.add_provider_for_screen(screen, safe, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        cover = Gtk.CssProvider()
        cover.load_from_data(
            f'.cover {{ background-image: url("{COVER_PATH}"); }}'.encode()
        )
        Gtk.StyleContext.add_provider_for_screen(screen, cover, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.main_provider = main = Gtk.CssProvider()
        main.load_from_path(CSS_PATH)
        Gtk.StyleContext.add_provider_for_screen(screen, main, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self._reload_id = 0
        # referencia fuerte: si se pierde, el monitor deja de avisar
        self._pywal_monitor = Gio.File.new_for_path(PYWAL_DIR).monitor_directory(
            Gio.FileMonitorFlags.NONE, None)
        self._pywal_monitor.connect("changed", self._on_pywal_changed)

    def _on_pywal_changed(self, _mon, gfile, _other, _event):
        if gfile.get_basename() not in PYWAL_FILES:
            return
        if self._reload_id:
            GLib.source_remove(self._reload_id)
        self._reload_id = GLib.timeout_add(400, self._reload_css)

    def _reload_css(self):
        self._reload_id = 0
        self.safe_provider.load_from_data(f"@define-color text_safe {text_safe_color()};".encode())
        self.main_provider.load_from_path(CSS_PATH)
        return False

    def _scan_apps(self):
        seen, entries = set(), []
        for app in Gio.AppInfo.get_all():
            if not app.should_show() or app.get_id() in seen:
                continue
            seen.add(app.get_id())
            entries.append(AppEntry(app))
        return entries

    # ---------- construccion de la interfaz ----------
    def _build_ui(self):
        root = Gtk.EventBox()
        root.connect("button-press-event", self.on_backdrop_click)
        self.add(root)

        self.panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.panel.get_style_context().add_class("panel")
        self.panel.set_size_request(920, 540)
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
        header.pack_start(glyph_label(GLYPH_ARCH, "logo"), False, False, 0)

        search = Gtk.Box(spacing=8)
        search.get_style_context().add_class("search-box")
        search.set_size_request(420, -1)
        search.pack_start(glyph_label(GLYPH_SEARCH, "search-glyph"), False, False, 0)
        self.search = Gtk.Entry()
        self.search.set_has_frame(False)
        self.search.connect("changed", self.on_search_changed)
        # placeholder propio: GTK3 oculta el nativo al tener foco
        self.placeholder = Gtk.Label(label="Buscar aplicación...", xalign=0)
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

        self.cat_list = Gtk.ListBox()
        self.cat_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.cat_rows = {}
        for cid, label, glyph in CATEGORIES:
            row = Gtk.ListBoxRow()
            row.cat_id = cid
            box = Gtk.Box(spacing=12)
            box.pack_start(glyph_label(glyph, "cat-glyph"), False, False, 0)
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

        footer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        footer.set_valign(Gtk.Align.END)
        phrase = Gtk.Label(label=PHRASE)
        phrase.get_style_context().add_class("phrase")
        phrase.set_line_wrap(True)
        phrase.set_justify(Gtk.Justification.CENTER)
        phrase.set_max_width_chars(22)
        phrase.set_tooltip_text(PHRASE_ES)
        footer.pack_start(phrase, False, False, 0)
        side.pack_end(footer, True, True, 0)
        return self._fixed_column(side, 210)

    @staticmethod
    def _fixed_column(child, width):
        """Ancho fijo: el contenido nunca ensancha ni encoge la columna."""
        box = Gtk.ScrolledWindow()
        # EXTERNAL: sin barras y sin propagar el tamaño del contenido
        box.set_policy(Gtk.PolicyType.EXTERNAL, Gtk.PolicyType.EXTERNAL)
        lock_scroll(box)
        box.set_size_request(width, -1)
        box.add(child)
        return box

    def _build_list(self):
        self.scroller = Gtk.ScrolledWindow()
        self.scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroller.set_overlay_scrolling(False)
        self.scroller.get_style_context().add_class("list-area")

        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.set_activate_on_single_click(False)
        self.listbox.set_margin_end(8)
        self.listbox.set_filter_func(lambda row: row.entry.show)
        self.listbox.set_sort_func(self._sort_rows)
        self.listbox.connect("row-selected", self.on_row_selected)
        self.listbox.connect("row-activated", lambda _lb, row: self.launch(row.entry))
        self.empty_label = Gtk.Label(label="Sin resultados")
        self.empty_label.get_style_context().add_class("empty")
        self.empty_label.set_justify(Gtk.Justification.CENTER)
        self.empty_label.show()
        self.listbox.set_placeholder(self.empty_label)
        self.scroller.add(self.listbox)
        return self.scroller

    def _build_detail(self):
        self.stack = Gtk.Stack()
        self.stack.get_style_context().add_class("detail")
        self.stack.add_named(self._build_info_page(), "info")
        self.stack.add_named(self._build_details_page(), "details")
        return self._fixed_column(self.stack, 350)

    def _build_info_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        page.set_border_width(16)

        cover = Gtk.Box()
        cover.get_style_context().add_class("cover")
        cover.set_size_request(-1, 170)
        page.pack_start(cover, False, False, 0)

        head = Gtk.Box(spacing=12)
        self.d_icon = Gtk.Image()
        self.d_icon.set_pixel_size(56)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        titles.set_valign(Gtk.Align.CENTER)
        self.d_name = Gtk.Label(xalign=0)
        self.d_name.get_style_context().add_class("d-name")
        self.d_name.set_ellipsize(3)
        self.d_generic = Gtk.Label(xalign=0)
        self.d_generic.get_style_context().add_class("d-generic")
        self.d_generic.set_ellipsize(3)
        titles.pack_start(self.d_name, False, False, 0)
        titles.pack_start(self.d_generic, False, False, 0)
        head.pack_start(self.d_icon, False, False, 0)
        head.pack_start(titles, True, True, 0)
        page.pack_start(head, False, False, 0)

        self.d_desc = Gtk.Label(xalign=0, yalign=0)
        self.d_desc.set_line_wrap(True)
        self.d_desc.set_lines(2)
        self.d_desc.set_ellipsize(3)
        self.d_desc.set_max_width_chars(34)
        self.d_desc.get_style_context().add_class("d-desc")
        page.pack_start(self.d_desc, False, False, 0)

        self.d_chips = Gtk.Box(spacing=6)
        page.pack_start(self.d_chips, False, False, 0)

        bottom = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        page.pack_end(bottom, False, False, 0)
        bottom.pack_start(Gtk.Separator(), False, False, 4)

        self.btn_open = action_button(GLYPH_OPEN, "Abrir", "primary", "↵")
        self.btn_open.connect("clicked", lambda *_: self.current and self.launch(self.current))
        self.btn_fav = action_button(GLYPH_STAR_O, "Agregar a favoritos", hint="Ctrl+F")
        self.btn_fav.connect("clicked", lambda *_: self.toggle_favorite())
        self.btn_details = action_button(GLYPH_INFO, "Ver detalles", hint="Ctrl+D")
        self.btn_details.connect("clicked", lambda *_: self.show_details())
        for btn in (self.btn_open, self.btn_fav, self.btn_details):
            bottom.pack_start(btn, False, False, 0)
        return page

    def _build_details_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        page.set_border_width(16)
        back = action_button(GLYPH_BACK, "Volver", hint="Esc")
        back.connect("clicked", lambda *_: self.stack.set_visible_child_name("info"))
        page.pack_start(back, False, False, 0)
        self.det_title = Gtk.Label(xalign=0)
        self.det_title.get_style_context().add_class("d-name")
        page.pack_start(self.det_title, False, False, 0)
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_overlay_scrolling(False)
        self.det_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        scroller.add(self.det_box)
        page.pack_start(scroller, True, True, 0)
        return page

    # ---------- datos / filtrado ----------
    def _populate(self):
        for entry in self.entries:
            row = Gtk.ListBoxRow()
            row.entry = entry
            box = Gtk.Box(spacing=12)
            icon = Gtk.Image.new_from_gicon(
                entry.app.get_icon() or Gio.ThemedIcon.new("application-x-executable"),
                Gtk.IconSize.DIALOG,
            )
            icon.set_pixel_size(36)
            texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            texts.set_valign(Gtk.Align.CENTER)
            name = Gtk.Label(label=entry.name, xalign=0)
            name.get_style_context().add_class("app-name")
            name.set_ellipsize(3)
            sub = Gtk.Label(label=entry.subtitle, xalign=0)
            sub.get_style_context().add_class("app-sub")
            sub.set_ellipsize(3)
            texts.pack_start(name, False, False, 0)
            texts.pack_start(sub, False, False, 0)
            star = glyph_label(GLYPH_STAR, "star")
            star.set_no_show_all(True)
            box.pack_start(icon, False, False, 0)
            box.pack_start(texts, True, True, 0)
            box.pack_end(star, False, False, 0)
            row.add(box)
            row.star = star
            entry.row = row
            star.set_visible(entry.id in self.favorites)
            self.listbox.add(row)

        self.update_counts()
        self.show_all()
        self.cat_list.select_row(self.cat_rows["todas"])
        self.search.grab_focus()

    def _key(self, entry):
        return (entry.score, entry.id not in self.favorites,
                -self.usage.get(entry.id, 0), entry.name_l)

    def _sort_rows(self, a, b):
        ka, kb = self._key(a.entry), self._key(b.entry)
        return (ka > kb) - (ka < kb)

    @staticmethod
    def _score(entry, query):
        if not query:
            return 0
        if entry.name_l.startswith(query):
            return 0
        if any(w.startswith(query) for w in re.split(r"[\s\-_.]+", entry.name_l)):
            return 1
        if query in entry.name_l:
            return 2
        if query in entry.extra_l:
            return 3
        return None

    def _in_category(self, entry):
        if self.category == "todas":
            return True
        if self.category == "favoritos":
            return entry.id in self.favorites
        return entry.cat == self.category

    def update_counts(self):
        totals = {cid: 0 for cid, _, _ in CATEGORIES}
        for entry in self.entries:
            totals["todas"] += 1
            totals[entry.cat] += 1
            totals["favoritos"] += entry.id in self.favorites
        for cid, row in self.cat_rows.items():
            row.count_label.set_text(str(totals[cid]))
            ctx = row.get_style_context()
            if totals[cid] == 0:
                ctx.add_class("empty-cat")
            else:
                ctx.remove_class("empty-cat")

    def refilter(self, keep_selection=False):
        query = self.search.get_text().strip().casefold()
        self.empty_label.set_text(
            "Aún no tienes favoritos\nUsa Ctrl+F sobre una app"
            if self.category == "favoritos" and not query else "Sin resultados")
        for entry in self.entries:
            score = self._score(entry, query)
            entry.show = score is not None and (bool(query) or self._in_category(entry))
            entry.score = score if score is not None else 9
        self.ordered = sorted((e for e in self.entries if e.show), key=self._key)
        self.listbox.invalidate_filter()
        self.listbox.invalidate_sort()
        keep = keep_selection and self.current in self.ordered
        target = self.current if keep else (self.ordered[0] if self.ordered else None)
        if target:
            self.listbox.select_row(target.row)
            if self.current is not target:
                self.current = target
                self.update_detail()
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
            return
        y, h = coords[1], row.get_allocated_height()
        if y < adj.get_value():
            adj.set_value(y)
        elif y + h > adj.get_value() + adj.get_page_size():
            adj.set_value(y + h - adj.get_page_size())

    # ---------- panel de detalle ----------
    def update_detail(self):
        entry = self.current
        self.stack.set_visible_child_name("info")
        sensitive = entry is not None
        for btn in (self.btn_open, self.btn_fav, self.btn_details):
            btn.set_sensitive(sensitive)
        for chip in self.d_chips.get_children():
            self.d_chips.remove(chip)
        if not entry:
            self.d_icon.clear()
            self.d_name.set_text("")
            self.d_generic.set_text("")
            self.d_desc.set_text("Selecciona una aplicación")
            return
        self.d_icon.set_from_gicon(
            entry.app.get_icon() or Gio.ThemedIcon.new("application-x-executable"),
            Gtk.IconSize.DIALOG,
        )
        self.d_icon.set_pixel_size(56)
        self.d_name.set_text(entry.name)
        self.d_generic.set_text(entry.generic or CAT_LABEL[entry.cat])
        self.d_desc.set_text(entry.comment or "Sin descripción disponible.")
        for tag in entry.stickers():
            chip = Gtk.Label(label=tag)
            chip.get_style_context().add_class("chip")
            self.d_chips.pack_start(chip, False, False, 0)
        self.d_chips.show_all()
        self.refresh_fav_button()

    def refresh_fav_button(self):
        fav = self.current is not None and self.current.id in self.favorites
        self.btn_fav.glyph.set_text(GLYPH_STAR if fav else GLYPH_STAR_O)
        self.btn_fav.label.set_text("Quitar de favoritos" if fav else "Agregar a favoritos")

    def toggle_favorite(self):
        entry = self.current
        if not entry:
            return
        if entry.id in self.favorites:
            self.favorites.remove(entry.id)
        else:
            self.favorites.append(entry.id)
        save_json(FAV_FILE, self.favorites)
        entry.row.star.set_visible(entry.id in self.favorites)
        self.refresh_fav_button()
        self.update_counts()
        self.refilter(keep_selection=True)

    def show_details(self):
        entry = self.current
        if not entry:
            return
        self.det_title.set_text(entry.name)
        self._fill_details([("Estado", "Cargando...")])
        self.stack.set_visible_child_name("details")

        def work():
            info = self.details_cache.get(entry.id) or self._collect_details(entry)
            self.details_cache[entry.id] = info
            GLib.idle_add(self._fill_details_if_current, entry, info)

        threading.Thread(target=work, daemon=True).start()

    def _fill_details_if_current(self, entry, info):
        if entry is self.current and self.stack.get_visible_child_name() == "details":
            self._fill_details(info)
        return False

    def _fill_details(self, rows):
        for child in self.det_box.get_children():
            self.det_box.remove(child)
        for key, value in rows:
            item = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            k = Gtk.Label(label=key, xalign=0)
            k.get_style_context().add_class("det-key")
            v = Gtk.Label(label=value, xalign=0)
            v.set_line_wrap(True)
            v.set_max_width_chars(36)
            v.set_selectable(True)
            v.get_style_context().add_class("det-val")
            item.pack_start(k, False, False, 0)
            item.pack_start(v, False, False, 0)
            self.det_box.pack_start(item, False, False, 0)
        self.det_box.show_all()

    @staticmethod
    def _pacman(*args):
        try:
            out = subprocess.run(
                ["pacman", *args], capture_output=True, text=True, timeout=5,
                env={**os.environ, "LC_ALL": "C"},
            )
            return out.stdout.strip() if out.returncode == 0 else ""
        except Exception:
            return ""

    def _collect_details(self, entry):
        path = entry.app.get_filename() or ""
        pkg = self._pacman("-Qoq", path) if path else ""
        rows = []
        if pkg:
            fields = {}
            for line in self._pacman("-Qi", pkg).splitlines():
                key, sep, val = line.partition(" : ")
                if sep:
                    fields[key.strip()] = val.strip()
            rows.append(("Paquete", f"{pkg} {fields.get('Version', '')}".strip()))
            for label, key in (("Descripción del paquete", "Description"),
                               ("Tamaño instalado", "Installed Size"),
                               ("Licencia", "Licenses"), ("Sitio web", "URL")):
                if fields.get(key):
                    rows.append((label, fields[key]))
        else:
            rows.append(("Paquete", "No pertenece a un paquete de pacman"))
        rows.append(("Comando", strip_field_codes(entry.app.get_commandline() or "")))
        rows.append(("Archivo .desktop", path or "—"))
        rows.append(("Categorías", ", ".join(c for c in (entry.app.get_categories() or "").split(";") if c) or "—"))
        rows.append(("Se abre en terminal", "Sí" if entry.app.get_boolean("Terminal") else "No"))
        rows.append(("Veces abierta desde aquí", str(self.usage.get(entry.id, 0))))
        return rows

    # ---------- acciones ----------
    def launch(self, entry):
        self.usage[entry.id] = self.usage.get(entry.id, 0) + 1
        save_json(USAGE_FILE, self.usage)
        self.hide()
        try:
            if entry.app.get_boolean("Terminal"):
                argv = shlex.split(strip_field_codes(entry.app.get_commandline() or ""))
                subprocess.Popen([TERMINAL, "--title", entry.name, "-e", *argv],
                                 start_new_session=True)
            else:
                ctx = Gdk.Display.get_default().get_app_launch_context()
                entry.app.launch([], ctx)
        except Exception as err:
            subprocess.Popen(["notify-send", "Lanzador", f"No se pudo abrir {entry.name}: {err}"])
        GLib.timeout_add(150, Gtk.main_quit)

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
        if self.search.get_text().strip() and self.category != "todas":
            self.cat_list.select_row(self.cat_rows["todas"])
        else:
            self.refilter()

    def on_category_selected(self, _lb, row):
        if row is None:
            return
        self.category = row.cat_id
        self.refilter()

    def on_row_selected(self, _lb, row):
        self.current = row.entry if row else None
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
        if key == "Escape":
            if self.stack.get_visible_child_name() == "details":
                self.stack.set_visible_child_name("info")
            else:
                Gtk.main_quit()
        elif key in ("Down", "Up"):
            self.move_selection(1 if key == "Down" else -1)
        elif key in ("Return", "KP_Enter") and self.current:
            self.launch(self.current)
        elif key == "Tab":
            self.cycle_category(1)
        elif key == "ISO_Left_Tab":
            self.cycle_category(-1)
        elif ctrl and key in ("f", "F"):
            self.toggle_favorite()
        elif ctrl and key in ("d", "D"):
            self.show_details()
        else:
            return False
        return True


def toggle_running_instance():
    """Si ya hay una instancia abierta la cierra y devuelve True."""
    try:
        with open(PID_FILE) as f:
            pid = int(f.read())
        with open(f"/proc/{pid}/cmdline") as f:
            if "launcher.py" in f.read():
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
    win = Launcher()
    GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, Gtk.main_quit)
    win.show_all()
    Gtk.main()
    try:
        os.remove(PID_FILE)
    except OSError:
        pass


if __name__ == "__main__":
    main()
