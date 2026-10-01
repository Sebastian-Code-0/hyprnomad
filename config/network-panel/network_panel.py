#!/usr/bin/env python3
import json
import os
import subprocess
import threading

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk

GLib.set_prgname("network-panel")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSS_PATH = os.path.join(BASE_DIR, "style.css")
CONTRAST_CSS_PATH = os.path.join(BASE_DIR, "contrast.css")
PYWAL_COLORS_JSON = os.path.expanduser("~/.cache/wal/colors.json")


def _hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def _relative_luminance(hex_color):
    def linearize(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (linearize(c) for c in _hex_to_rgb(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(hex_a, hex_b):
    l_a, l_b = _relative_luminance(hex_a), _relative_luminance(hex_b)
    lighter, darker = max(l_a, l_b), min(l_a, l_b)
    return (lighter + 0.05) / (darker + 0.05)


def _write_contrast_css():
    """Fuerza texto blanco o negro puro si el par background/foreground de
    pywal tiene poco contraste real (WCAG); si ya contrasta bien, lo deja tal cual."""
    text_safe = "@foreground"
    shadow_safe = "black"
    try:
        with open(PYWAL_COLORS_JSON) as f:
            colors = json.load(f)
        bg = colors["special"]["background"]
        fg = colors["special"]["foreground"]
        if _contrast_ratio(bg, fg) < 4.5:
            if _relative_luminance(bg) < 0.5:
                text_safe = "#ffffff"
                shadow_safe = "black"
            else:
                text_safe = "#000000"
                shadow_safe = "white"
    except Exception:
        pass

    with open(CONTRAST_CSS_PATH, "w") as f:
        if text_safe == "@foreground":
            f.write("@define-color text_safe @foreground;\n")
        else:
            f.write(f"@define-color text_safe {text_safe};\n")
        f.write(f"@define-color shadow_safe {shadow_safe};\n")


def run(cmd, input=None):
    return subprocess.run(cmd, capture_output=True, text=True, input=input)


def nmcli(*args, input=None):
    return run(["nmcli", *args], input=input)


def connect_wifi(ssid, password=None, saved_profile=None):
    """Conecta a una red. La clave va por la entrada estandar, no por la linea de comandos."""
    if saved_profile:
        return nmcli("connection", "up", saved_profile)
    if password:
        return nmcli("--ask", "device", "wifi", "connect", ssid, input=password + "\n")
    return nmcli("device", "wifi", "connect", ssid)


def set_wifi_password(name, password):
    """Cambia la clave de una conexion guardada (por stdin) y comprueba que quedo guardada."""
    nmcli("connection", "edit", name, input=f"set 802-11-wireless-security.psk {password}\nsave\nquit\n")
    guardada = nmcli("-s", "-g", "802-11-wireless-security.psk", "connection", "show", name).stdout.strip()
    return guardada == password


class NetworkPanel(Gtk.Window):
    def __init__(self):
        super().__init__(title="Red")
        self.set_decorated(False)
        self.set_default_size(760, 520)
        self.get_style_context().add_class("panel-window")

        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)
        self.set_app_paintable(True)

        self.connect("destroy", Gtk.main_quit)
        self.connect("key-press-event", self.on_key)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(root)

        nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        nav.get_style_context().add_class("nav")
        root.pack_start(nav, False, False, 0)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_margin_start(16)
        self.stack.set_margin_end(16)
        self.stack.set_margin_bottom(16)
        root.pack_start(self.stack, True, True, 0)

        pages = [
            ("scan", "Establecer conexion", self.build_scan_page),
            ("saved", "Conexiones guardadas", self.build_saved_page),
            ("hostname", "Nombre del equipo", self.build_hostname_page),
            ("toggle", "Activar / Desactivar", self.build_toggle_page),
        ]
        self.nav_buttons = {}
        for key, label, builder in pages:
            self.stack.add_named(builder(), key)
            btn = Gtk.Button(label=label)
            btn.get_style_context().add_class("nav-btn")
            btn.connect("clicked", lambda b, k=key: self.switch_tab(k))
            nav.pack_start(btn, True, True, 0)
            self.nav_buttons[key] = btn

        self.connect_detail_box = self.build_connect_detail_page()
        self.stack.add_named(self.connect_detail_box, "connect_detail")

        self.switch_tab("scan")
        self.refresh_scan()

    def switch_tab(self, key):
        for k, btn in self.nav_buttons.items():
            ctx = btn.get_style_context()
            if k == key:
                ctx.add_class("nav-btn-active")
            else:
                ctx.remove_class("nav-btn-active")
        self.stack.set_visible_child_name(key)

    def on_key(self, _widget, event):
        if event.keyval == Gdk.KEY_Escape:
            Gtk.main_quit()

    def notify(self, text):
        run(["notify-send", "Red", text])
        return False

    # Pagina: escanear / conectar
    def build_scan_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        refresh_btn = Gtk.Button(label="Actualizar redes")
        refresh_btn.get_style_context().add_class("primary-btn")
        refresh_btn.connect("clicked", lambda b: self.refresh_scan())
        top.pack_start(refresh_btn, False, False, 0)
        self.scan_status = Gtk.Label(label="")
        self.scan_status.get_style_context().add_class("status-label")
        top.pack_start(self.scan_status, False, False, 6)
        box.pack_start(top, False, False, 0)

        self.scan_list = Gtk.ListBox()
        self.scan_list.get_style_context().add_class("list")
        scroller = Gtk.ScrolledWindow()
        scroller.add(self.scan_list)
        box.pack_start(scroller, True, True, 0)

        self.scan_list.connect("row-activated", self.on_scan_activated)
        return box

    def refresh_scan(self):
        self.scan_status.set_text("Buscando...")
        threading.Thread(target=self._do_scan, daemon=True).start()

    def _saved_wifi_ssid_map(self):
        """SSID -> nombre del perfil guardado, para no volver a pedir clave
        de una red que ya tenemos configurada."""
        mapping = {}
        lines = nmcli("-t", "-f", "NAME,TYPE", "connection", "show").stdout.strip().splitlines()
        for line in lines:
            if not line:
                continue
            name, ctype = line.rsplit(":", 1)
            if ctype != "802-11-wireless":
                continue
            ssid = nmcli("-g", "802-11-wireless.ssid", "connection", "show", name).stdout.strip()
            mapping[ssid or name] = name
        return mapping

    def _do_scan(self):
        nmcli("device", "wifi", "rescan")
        result = nmcli(
            "-t", "-f", "SSID,SIGNAL,SECURITY,IN-USE,CHAN,FREQ,RATE",
            "device", "wifi", "list",
        )
        saved_map = self._saved_wifi_ssid_map()
        GLib.idle_add(self._populate_scan, result.stdout, saved_map)

    def _populate_scan(self, output, saved_map):
        for child in self.scan_list.get_children():
            self.scan_list.remove(child)
        seen = set()
        rows = 0
        for line in output.strip().splitlines():
            parts = line.split(":")
            if len(parts) < 7:
                continue
            ssid, signal, security, in_use, chan, freq, rate = parts[:7]
            if not ssid or ssid in seen:
                continue
            seen.add(ssid)
            rows += 1

            row = Gtk.ListBoxRow()
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            marker = "* " if in_use == "*" else ""
            name_lbl = Gtk.Label(label=f"{marker}{ssid}", xalign=0)
            hbox.pack_start(name_lbl, True, True, 0)
            sig_lbl = Gtk.Label(label=f"señal {signal}%")
            sig_lbl.get_style_context().add_class("status-label")
            hbox.pack_start(sig_lbl, False, False, 0)
            lock = Gtk.Label(label="" if security else "")
            lock.get_style_context().add_class("lock-icon")
            hbox.pack_start(lock, False, False, 4)
            row.add(hbox)
            row.ssid = ssid
            row.secured = bool(security)
            row.signal = signal
            row.security = security
            row.chan = chan
            row.freq = freq
            row.rate = rate
            row.saved_profile = saved_map.get(ssid)
            self.scan_list.add(row)
        self.scan_list.show_all()
        self.scan_status.set_text(f"{rows} redes encontradas")
        return False

    def build_connect_detail_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.get_style_context().add_class("detail")
        return box

    def on_scan_activated(self, _listbox, row):
        ssid = row.ssid
        box = self.connect_detail_box
        for child in box.get_children():
            box.remove(child)

        title_lbl = Gtk.Label(label=ssid, xalign=0)
        title_lbl.get_style_context().add_class("detail-title")
        box.pack_start(title_lbl, False, False, 0)

        info_grid = Gtk.Grid(column_spacing=18, row_spacing=6)
        fields = [
            ("Señal", f"{row.signal}%"),
            ("Seguridad", row.security if row.security else "Abierta"),
            ("Canal", row.chan),
            ("Frecuencia", row.freq),
            ("Velocidad maxima", row.rate),
        ]
        for i, (k, v) in enumerate(fields):
            klabel = Gtk.Label(label=f"{k}:", xalign=0)
            klabel.get_style_context().add_class("field-label")
            vlabel = Gtk.Label(label=str(v), xalign=0)
            info_grid.attach(klabel, 0, i, 1, 1)
            info_grid.attach(vlabel, 1, i, 1, 1)
        box.pack_start(info_grid, False, False, 0)

        needs_password = row.secured and not row.saved_profile

        if row.saved_profile:
            note = Gtk.Label(
                label="Ya tienes esta red guardada: se va a conectar con la contraseña que ya tenemos.",
                xalign=0,
            )
            note.set_line_wrap(True)
            note.set_max_width_chars(50)
            note.get_style_context().add_class("helper-text")
            box.pack_start(note, False, False, 0)

        entry = None
        if needs_password:
            pw_label = Gtk.Label(label="Contraseña", xalign=0)
            pw_label.get_style_context().add_class("field-label")
            box.pack_start(pw_label, False, False, 0)

            entry = Gtk.Entry()
            entry.set_visibility(False)
            box.pack_start(entry, False, False, 0)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

        cancel_btn = Gtk.Button(label="Cancelar")
        cancel_btn.connect("clicked", lambda b: self.stack.set_visible_child_name("scan"))
        btn_row.pack_start(cancel_btn, False, False, 0)

        connect_btn = Gtk.Button(label="Conectar")
        connect_btn.get_style_context().add_class("primary-btn")

        def do_connect(_btn):
            password = entry.get_text() if entry is not None else None
            threading.Thread(
                target=self._connect,
                args=(ssid, password, row.saved_profile),
                daemon=True,
            ).start()
            self.stack.set_visible_child_name("scan")

        connect_btn.connect("clicked", do_connect)
        if entry is not None:
            entry.set_activates_default(True)
            entry.connect("activate", do_connect)
        btn_row.pack_start(connect_btn, False, False, 0)

        box.pack_start(btn_row, False, False, 12)
        box.show_all()
        self.stack.set_visible_child_name("connect_detail")

    def _connect(self, ssid, password, saved_profile=None):
        result = connect_wifi(ssid, password, saved_profile)
        ok = result.returncode == 0
        msg = f"Conectado a {ssid}" if ok else f"No se pudo conectar a {ssid}: {result.stderr.strip()}"
        GLib.idle_add(self.notify, msg)

    # Pagina: conexiones guardadas
    def build_saved_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)

        self.saved_list = Gtk.ListBox()
        self.saved_list.get_style_context().add_class("list")
        scroller = Gtk.ScrolledWindow()
        scroller.set_min_content_width(220)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.add(self.saved_list)
        box.pack_start(scroller, False, False, 0)

        detail_scroller = Gtk.ScrolledWindow()
        self.saved_detail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.saved_detail.get_style_context().add_class("detail")
        detail_scroller.add(self.saved_detail)
        box.pack_start(detail_scroller, True, True, 0)

        self.load_saved_connections()
        self.saved_list.connect("row-selected", self.on_saved_selected)
        return box

    def load_saved_connections(self):
        for child in self.saved_list.get_children():
            self.saved_list.remove(child)
        result = nmcli("-t", "-f", "NAME,TYPE", "connection", "show")
        for line in result.stdout.strip().splitlines():
            if not line:
                continue
            name, ctype = line.rsplit(":", 1)
            if ctype != "802-11-wireless":
                continue
            row = Gtk.ListBoxRow()
            lbl = Gtk.Label(label=name, xalign=0)
            row.add(lbl)
            row.connection_name = name
            self.saved_list.add(row)
        self.saved_list.show_all()

    def _info_row(self, label, value):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        l = Gtk.Label(label=f"{label}:", xalign=0)
        l.get_style_context().add_class("field-label")
        v = Gtk.Label(label=str(value), xalign=0)
        box.pack_start(l, False, False, 0)
        box.pack_start(v, False, False, 0)
        return box

    def on_saved_selected(self, _listbox, row):
        for child in self.saved_detail.get_children():
            self.saved_detail.remove(child)
        if row is None:
            return
        name = row.connection_name

        raw = nmcli(
            "-t", "-g",
            "802-11-wireless.mode,802-11-wireless-security.key-mgmt,connection.autoconnect,connection.timestamp",
            "connection", "show", name,
        ).stdout.strip().split("\n")
        mode = raw[0] if len(raw) > 0 and raw[0] else "infrastructure"
        security = raw[1] if len(raw) > 1 and raw[1] else "abierta"
        autoconnect = raw[2] if len(raw) > 2 else "yes"

        psk = nmcli("-s", "-g", "802-11-wireless-security.psk", "connection", "show", name).stdout.strip()

        title = Gtk.Label(label=name, xalign=0)
        title.get_style_context().add_class("detail-title")
        self.saved_detail.pack_start(title, False, False, 0)

        self.saved_detail.pack_start(self._info_row("Modo", mode), False, False, 0)
        self.saved_detail.pack_start(self._info_row("Seguridad", security), False, False, 0)

        auto_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        auto_label = Gtk.Label(label="Conectar automaticamente:", xalign=0)
        auto_label.get_style_context().add_class("field-label")
        auto_row.pack_start(auto_label, False, False, 0)
        auto_switch = Gtk.Switch()
        auto_switch.set_active(autoconnect != "no")

        def on_auto_toggle(_switch, state, cname=name):
            result = nmcli("connection", "modify", cname, "connection.autoconnect", "yes" if state else "no")
            if result.returncode == 0:
                accion = "activada: se conectara sola" if state else "desactivada: no se conectara sola"
                self.notify(f'Conexion automatica {accion} en "{cname}"')
            else:
                self.notify(f"No se pudo cambiar la conexion automatica de {cname}: {result.stderr.strip()}")
            return False

        auto_switch.connect("state-set", on_auto_toggle)
        auto_row.pack_start(auto_switch, False, False, 0)
        self.saved_detail.pack_start(auto_row, False, False, 0)

        pw_label = Gtk.Label(label="Contraseña", xalign=0)
        pw_label.get_style_context().add_class("field-label")
        self.saved_detail.pack_start(pw_label, False, False, 0)

        pw_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        pw_entry = Gtk.Entry()
        pw_entry.set_text(psk)
        pw_entry.set_visibility(False)
        pw_row.pack_start(pw_entry, True, True, 0)

        show_btn = Gtk.ToggleButton(label="Mostrar")
        show_btn.connect("toggled", lambda b: pw_entry.set_visibility(b.get_active()))
        pw_row.pack_start(show_btn, False, False, 0)
        self.saved_detail.pack_start(pw_row, False, False, 0)

        save_btn = Gtk.Button(label="Guardar contraseña")
        save_btn.get_style_context().add_class("primary-btn")

        def save_password(_btn):
            if set_wifi_password(name, pw_entry.get_text()):
                self.notify(f"Contraseña actualizada para {name}")
            else:
                self.notify(f"No se pudo actualizar la contraseña de {name}")

        save_btn.connect("clicked", save_password)
        self.saved_detail.pack_start(save_btn, False, False, 6)

        self.saved_detail.show_all()

    # Pagina: nombre del equipo
    def build_hostname_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.get_style_context().add_class("detail")

        current = run(["hostnamectl", "hostname"]).stdout.strip()

        title = Gtk.Label(label="Nombre del equipo en la red", xalign=0)
        title.get_style_context().add_class("detail-title")
        box.pack_start(title, False, False, 0)

        explain = Gtk.Label(
            label=(
                "Este nombre identifica tu equipo dentro de una red local (por ejemplo, "
                "para verlo al compartir archivos o al listar dispositivos conectados al "
                "mismo router). Lo pueden ver otros equipos de tu misma red wifi o cableada, "
                "pero no alguien fuera de ella."
            ),
            xalign=0,
            wrap=True,
        )
        explain.set_max_width_chars(60)
        explain.get_style_context().add_class("helper-text")
        box.pack_start(explain, False, False, 0)

        self.hostname_entry = Gtk.Entry()
        self.hostname_entry.set_text(current)
        box.pack_start(self.hostname_entry, False, False, 0)

        save_btn = Gtk.Button(label="Guardar")
        save_btn.get_style_context().add_class("primary-btn")
        save_btn.connect("clicked", self.on_save_hostname)
        box.pack_start(save_btn, False, False, 0)

        self.hostname_status = Gtk.Label(label="", xalign=0)
        self.hostname_status.get_style_context().add_class("status-label")
        box.pack_start(self.hostname_status, False, False, 0)
        return box

    def on_save_hostname(self, _btn):
        new_name = self.hostname_entry.get_text().strip()
        if not new_name:
            return
        result = run(["hostnamectl", "set-hostname", new_name])
        if result.returncode == 0:
            self.hostname_status.set_text("Guardado. Puede requerir reiniciar sesion para verse en todos lados.")
        else:
            self.hostname_status.set_text(
                f"No se pudo aplicar. Corre esto en una terminal: sudo hostnamectl set-hostname {new_name}"
            )

    # Pagina: activar/desactivar
    def build_toggle_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.get_style_context().add_class("detail")

        title = Gtk.Label(label="Radio Wi-Fi", xalign=0)
        title.get_style_context().add_class("detail-title")
        box.pack_start(title, False, False, 0)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        label = Gtk.Label(label="Encendido")
        row.pack_start(label, False, False, 0)

        state = nmcli("radio", "wifi").stdout.strip() == "enabled"
        switch = Gtk.Switch()
        switch.set_active(state)
        switch.connect("state-set", self.on_toggle_wifi)
        row.pack_start(switch, False, False, 0)
        box.pack_start(row, False, False, 0)
        return box

    def on_toggle_wifi(self, _switch, state):
        nmcli("radio", "wifi", "on" if state else "off")
        return False


def main():
    settings = Gtk.Settings.get_default()
    settings.set_property("gtk-application-prefer-dark-theme", True)

    _write_contrast_css()
    provider = Gtk.CssProvider()
    provider.load_from_path(CSS_PATH)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(),
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )

    win = NetworkPanel()
    win.show_all()

    # Si se cambia de fondo (pywal regenera sus colores)
    pywal_css = os.path.expanduser("~/.cache/wal/colors-waybar.css")

    def reload_css(*_args):
        _write_contrast_css()
        provider.load_from_path(CSS_PATH)

    pywal_file = Gio.File.new_for_path(pywal_css)
    monitor = pywal_file.monitor_file(Gio.FileMonitorFlags.NONE, None)
    monitor.connect("changed", reload_css)
    win._pywal_monitor = monitor  # evita que el garbage collector lo mate

    Gtk.main()


if __name__ == "__main__":
    main()
