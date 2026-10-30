-- Copyright (C) 2026 Sebastian-Code-0
-- SPDX-License-Identifier: GPL-3.0-or-later
-- Configuración de Hyprland en Lua (Hyprland 0.55 o superior).
-- Referencia: https://wiki.hypr.land/configuring/

-----------------
--- MONITORES ---
-----------------

-- ver https://wiki.hypr.land/configuring/core/monitors/
hl.monitor({
    output   = "",
    mode     = "preferred",
    position = "auto",
    scale    = "auto",
})

---------------------
--- MIS PROGRAMAS ---
---------------------

-- Programas que uso
local terminal    = "kitty"
local fileManager = "dolphin"
local menu        = "~/.config/launcher/launcher.py"
local navegador   = "firefox"

------------------
--- AUTOINICIO ---
------------------

-- se ejecuta una sola vez al iniciar Hyprland
hl.on("hyprland.start", function()
    hl.exec_cmd("waybar")
    hl.exec_cmd("hypridle")
    hl.exec_cmd("swaync")
    hl.exec_cmd("awww-daemon")
    hl.exec_cmd("udiskie")

    hl.exec_cmd("~/.config/hypr/scripts/set_wallpaper.sh")
    hl.exec_cmd("~/.config/hypr/scripts/battery-status.sh")
    hl.exec_cmd("python3 ~/.config/hypr/scripts/window_thumb_daemon.py")

    hl.exec_cmd("wl-paste --type text --watch ~/.config/clipboard/store.sh")
    hl.exec_cmd("wl-paste --type image --watch ~/.config/clipboard/store.sh")

    hl.exec_cmd("dbus-update-activation-environment --systemd WAYLAND_DISPLAY XDG_CURRENT_DESKTOP")

    hl.exec_cmd("/usr/lib/polkit-kde-authentication-agent-1")
end)

----------------------------
--- VARIABLES DE ENTORNO ---
----------------------------

hl.env("XCURSOR_SIZE", "24")
hl.env("HYPRCURSOR_SIZE", "24")
hl.env("XDG_SESSION_TYPE", "wayland")
hl.env("XDG_CURRENT_DESKTOP", "Hyprland")
hl.env("XDG_SESSION_DESKTOP", "Hyprland")
hl.env("GDK_SCALE", "1")
hl.env("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

----------------
--- PERMISOS ---
----------------

-- hl.config({
--     ecosystem = {
--         enforce_permissions = true,
--     },
-- })

-- hl.permission({ binary = "/usr/(bin|local/bin)/grim", type = "screencopy", mode = "allow" })
-- hl.permission({ binary = "/usr/(lib|libexec|lib64)/xdg-desktop-portal-hyprland", type = "screencopy", mode = "allow" })
-- hl.permission({ binary = "/usr/(bin|local/bin)/hyprpm", type = "plugin", mode = "allow" })

------------------
--- APARIENCIA ---
------------------

hl.config({
    general = {
        gaps_in  = 2,
        gaps_out = 6,

        border_size = 1,

        col = {
            active_border   = "rgba(262626aa)",
            inactive_border = "rgba(111111aa)",
        },

        resize_on_border = true,

        allow_tearing = false,

        layout = "dwindle",
    },

    decoration = {
        rounding       = 6,
        rounding_power = 2,

        -- transparencia de las ventanas
        active_opacity   = 0.8,
        inactive_opacity = 0.6,

        shadow = {
            enabled      = true,
            range        = 20,
            render_power = 4,
            color        = "rgba(000000b3)",
        },

        blur = {
            enabled           = true,
            size              = 5,
            passes            = 3,
            popups            = true,
            new_optimizations = true,
            noise             = 0.0200,
            contrast          = 1,
            brightness        = 0.8172,

            vibrancy = 0.1696,
        },
    },
})

-- blur de fondo para wlogout
hl.layer_rule({
    name         = "wlogout_blur",
    match        = { namespace = "logout_dialog" },
    blur         = true,
    ignore_alpha = 0.5,
})

hl.layer_rule({
    name         = "launcher_blur",
    match        = { namespace = "launcher" },
    blur         = true,
    ignore_alpha = 0.4,
})

hl.layer_rule({
    name         = "clipboard_blur",
    match        = { namespace = "clipboard" },
    blur         = true,
    ignore_alpha = 0.4,
})

hl.layer_rule({
    name         = "wallpaper_blur",
    match        = { namespace = "wallpaper-select" },
    blur         = true,
    ignore_alpha = 0.4,
})

hl.layer_rule({
    name         = "window_blur",
    match        = { namespace = "window-select" },
    blur         = true,
    ignore_alpha = 0.4,
})

hl.config({
    animations = {
        enabled = true,
    },
})

--                  NOMBRE,           X0,   Y0,   X1,   Y1
hl.curve("easeOutQuint",   { type = "bezier", points = { {0.23, 1},    {0.32, 1}    } })
hl.curve("easeInOutCubic", { type = "bezier", points = { {0.65, 0.05}, {0.36, 1}    } })
hl.curve("linear",         { type = "bezier", points = { {0, 0},       {1, 1}       } })
hl.curve("almostLinear",   { type = "bezier", points = { {0.5, 0.5},   {0.75, 1}    } })
hl.curve("quick",          { type = "bezier", points = { {0.15, 0},    {0.1, 1}     } })

hl.animation({ leaf = "global",        enabled = true, speed = 10,   bezier = "default" })
hl.animation({ leaf = "border",        enabled = true, speed = 5.39, bezier = "easeOutQuint" })
hl.animation({ leaf = "windows",       enabled = true, speed = 4.79, bezier = "easeOutQuint" })
hl.animation({ leaf = "windowsIn",     enabled = true, speed = 4.1,  bezier = "easeOutQuint", style = "popin 87%" })
hl.animation({ leaf = "windowsOut",    enabled = true, speed = 1.49, bezier = "linear",       style = "popin 87%" })
hl.animation({ leaf = "fadeIn",        enabled = true, speed = 1.73, bezier = "almostLinear" })
hl.animation({ leaf = "fadeOut",       enabled = true, speed = 1.46, bezier = "almostLinear" })
hl.animation({ leaf = "fade",          enabled = true, speed = 3.03, bezier = "quick" })
hl.animation({ leaf = "layers",        enabled = true, speed = 3.81, bezier = "easeOutQuint" })
hl.animation({ leaf = "layersIn",      enabled = true, speed = 4,    bezier = "easeOutQuint", style = "fade" })
hl.animation({ leaf = "layersOut",     enabled = true, speed = 1.5,  bezier = "linear",       style = "fade" })
hl.animation({ leaf = "fadeLayersIn",  enabled = true, speed = 1.79, bezier = "almostLinear" })
hl.animation({ leaf = "fadeLayersOut", enabled = true, speed = 1.39, bezier = "almostLinear" })
hl.animation({ leaf = "workspaces",    enabled = true, speed = 1.94, bezier = "almostLinear", style = "fade" })
hl.animation({ leaf = "workspacesIn",  enabled = true, speed = 1.21, bezier = "almostLinear", style = "fade" })
hl.animation({ leaf = "workspacesOut", enabled = true, speed = 1.94, bezier = "almostLinear", style = "fade" })
hl.animation({ leaf = "zoomFactor",    enabled = true, speed = 7,    bezier = "quick" })

-- Ref https://wiki.hypr.land/configuring/core/rules/workspace-rules/
-- "Smart gaps" / sin espacios cuando hay una sola ventana
-- descomenta todo para activarlo.
-- hl.workspace_rule({ workspace = "w[tv1]", gaps_out = 0, gaps_in = 0 })
-- hl.workspace_rule({ workspace = "f[1]",   gaps_out = 0, gaps_in = 0 })
-- hl.window_rule({
--     name  = "no-gaps-wtv1",
--     match = { float = false, workspace = "w[tv1]" },
--     border_size = 0,
--     rounding    = 0,
-- })
-- hl.window_rule({
--     name  = "no-gaps-f1",
--     match = { float = false, workspace = "f[1]" },
--     border_size = 0,
--     rounding    = 0,
-- })

-- Más información: https://wiki.hypr.land/configuring/layouts/dwindle-layout/
hl.config({
    dwindle = {
        preserve_split = true,
    },
})

-- Más información: https://wiki.hypr.land/configuring/layouts/master-layout/
hl.config({
    master = {
        new_status = "master",
    },
})

-- https://wiki.hypr.land/configuring/core/config-options/#misc
hl.config({
    misc = {
        force_default_wallpaper = -1,    -- 0 o 1 desactivan los fondos de mascotas anime
        disable_hyprland_logo   = false, -- true desactiva el logo/fondo aleatorio de Hyprland
    },
})

-- XWayland sin escalado (evita apps X11 borrosas con GDK_SCALE fijo)
hl.config({
    xwayland = {
        force_zero_scaling = true,
    },
})

---------------
--- ENTRADA ---
---------------

hl.config({
    input = {
        kb_layout  = "latam",
        kb_variant = "",
        kb_model   = "",
        kb_options = "",
        kb_rules   = "",

        follow_mouse = 1,

        sensitivity = 0, -- -1.0 - 1.0, 0 significa sin modificación

        touchpad = {
            natural_scroll = true,
        },
    },
})

-- Más información: https://wiki.hypr.land/configuring/core/binds/gestures/
hl.gesture({ fingers = 3, direction = "horizontal", action = "workspace" })

-- Ejemplo de configuración por dispositivo (descomenta y pon el nombre de tu mouse)
-- Más información: https://wiki.hypr.land/configuring/core/devices/
-- hl.device({
--     name        = "epic-mouse-v1",
--     sensitivity = -0.5,
-- })

-------------------------
--- ATAJOS DE TECLADO ---
-------------------------

-- Más información: https://wiki.hypr.land/configuring/core/binds/
local mainMod = "SUPER" -- tecla Windows como modificador principal

hl.bind(mainMod .. " + RETURN", hl.dsp.exec_cmd(terminal))
hl.bind(mainMod .. " + SHIFT + RETURN", hl.dsp.exec_cmd(terminal, { float = true, size = "1000 500", center = true }))

hl.bind(mainMod .. " + A", hl.dsp.exec_cmd("~/.config/hypr/scripts/random_wallpaper.sh"))
hl.bind(mainMod .. " + SHIFT + A", hl.dsp.exec_cmd("~/.config/wallpaper-select/wallpaper_select.py"))
hl.bind(mainMod .. " + SHIFT + L", hl.dsp.exec_cmd("wlogout -b 4 -m 260px"))
hl.bind(mainMod .. " + SHIFT + V", hl.dsp.exec_cmd("~/.config/clipboard/clipboard.py"))

-- Selector de ventanas
hl.bind("CTRL + ALT + Tab", hl.dsp.exec_cmd("~/.config/window-select/window_select.py"))

hl.bind(mainMod .. " + Q", hl.dsp.window.close())
hl.bind(mainMod .. " + SHIFT + M", hl.dsp.exec_cmd("command -v hyprshutdown >/dev/null 2>&1 && hyprshutdown || hyprctl dispatch 'hl.dsp.exit()'"))
hl.bind(mainMod .. " + E", hl.dsp.exec_cmd(terminal .. " -e lf"))
hl.bind(mainMod .. " + V", hl.dsp.window.float({ action = "toggle" }))
hl.bind(mainMod .. " + SPACE", hl.dsp.exec_cmd(menu))
hl.bind(mainMod .. " + P", hl.dsp.window.pseudo())              -- dwindle
hl.bind(mainMod .. " + J", hl.dsp.layout("togglesplit"))
hl.bind(mainMod .. " + L", hl.dsp.exec_cmd("hyprlock"))
hl.bind(mainMod .. " + F", hl.dsp.exec_cmd(navegador))
hl.bind(mainMod .. " + N", hl.dsp.exec_cmd("swaync-client -t")) -- panel de swayNC

-- Mover el foco con mainMod + flechas
hl.bind(mainMod .. " + left",  hl.dsp.focus({ direction = "left" }))
hl.bind(mainMod .. " + right", hl.dsp.focus({ direction = "right" }))
hl.bind(mainMod .. " + up",    hl.dsp.focus({ direction = "up" }))
hl.bind(mainMod .. " + down",  hl.dsp.focus({ direction = "down" }))

-- Cambiar de espacio de trabajo con mainMod + [0-9]
-- Mover la ventana activa a un espacio con mainMod + SHIFT + [0-9]
for i = 1, 10 do
    local key = i % 10 -- 10 corresponde a la tecla 0
    hl.bind(mainMod .. " + " .. key,         hl.dsp.focus({ workspace = i }))
    hl.bind(mainMod .. " + SHIFT + " .. key, hl.dsp.window.move({ workspace = i }))
end

-- Espacio de trabajo especial de ejemplo (scratchpad)
hl.bind(mainMod .. " + S",         hl.dsp.workspace.toggle_special("magic"))
hl.bind(mainMod .. " + SHIFT + S", hl.dsp.window.move({ workspace = "special:magic" }))

-- Recorrer los espacios existentes con mainMod + rueda del ratón
hl.bind(mainMod .. " + mouse_down", hl.dsp.focus({ workspace = "e+1" }))
hl.bind(mainMod .. " + mouse_up",   hl.dsp.focus({ workspace = "e-1" }))

-- Mover/redimensionar ventanas con mainMod + clic izquierdo/derecho y arrastrar
hl.bind(mainMod .. " + mouse:272", hl.dsp.window.drag(),   { mouse = true })
hl.bind(mainMod .. " + mouse:273", hl.dsp.window.resize(), { mouse = true })

--------------------------------------
--- VENTANAS Y ESPACIOS DE TRABAJO ---
--------------------------------------

-- Más información: https://wiki.hypr.land/configuring/core/rules/

-- Ignorar las peticiones de maximizar de todas las apps.
hl.window_rule({
    name  = "suppress-maximize-events",
    match = { class = ".*" },

    suppress_event = "maximize",
})

-- Corrige problemas al arrastrar con XWayland
hl.window_rule({
    name  = "fix-xwayland-drags",
    match = {
        class      = "^$",
        title      = "^$",
        xwayland   = true,
        float      = true,
        fullscreen = false,
        pin        = false,
    },

    no_focus = true,
})

-- Regla para ventanas lanzadas con hyprland-run
hl.window_rule({
    name  = "move-hyprland-run",
    match = { class = "hyprland-run" },

    move  = "20 monitor_h-120",
    float = true,
})

hl.window_rule({
    name  = "nmtui-float",
    match = { title = "^(nmtui)$" },

    float  = true,
    size   = "850 400",
    center = true,
})

hl.window_rule({
    name  = "qalc-float",
    match = { title = "^(qalc-float)$" },

    float  = true,
    size   = "500 300",
    center = true,
})

hl.window_rule({
    name  = "network-panel-float",
    match = { class = "^(network-panel)$" },

    float  = true,
    size   = "760 520",
    center = true,
})

hl.window_rule({
    name  = "nyancat-float",
    match = { title = "^(nyancat)$" },

    float  = true,
    size   = "700 420",
    center = true,
})

-------------------------
--- AJUSTES DE EQUIPO ---
-------------------------

-- monitores, teclas Fn/multimedia y demás ajustes propios de cada equipo
-- (ver README); se carga desde local.lua.
-- pcall: si local.lua no existe, el resto de la configuración sigue cargando.
pcall(require, "local")
