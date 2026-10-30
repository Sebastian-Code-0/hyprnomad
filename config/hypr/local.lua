-- Ajustes propios de cada equipo: monitores, teclas Fn/multimedia y demas.
-- hyprland.lua carga este archivo al final. Descomenta y adapta lo que necesites.
-- Para ver el nombre de una tecla: wev (o hyprctl binds); de un monitor: hyprctl monitors.

-- Monitores (nombre, resolucion, posicion, escala)
-- hl.monitor({ output = "HDMI-A-1", mode = "preferred", position = "auto", scale = 1 })

-- Volumen y micrófono
-- hl.bind("XF86AudioRaiseVolume", hl.dsp.exec_cmd("~/.config/hypr/scripts/volume.sh --inc"))
-- hl.bind("XF86AudioLowerVolume", hl.dsp.exec_cmd("~/.config/hypr/scripts/volume.sh --dec"))
-- hl.bind("XF86AudioMute",        hl.dsp.exec_cmd("~/.config/hypr/scripts/volume.sh --toggle"))
-- hl.bind("XF86AudioMicMute",     hl.dsp.exec_cmd("~/.config/hypr/scripts/volume.sh --toggle-mic"))

-- Brillo
-- hl.bind("XF86MonBrightnessUp",   hl.dsp.exec_cmd("~/.config/hypr/scripts/brightness.sh --inc"))
-- hl.bind("XF86MonBrightnessDown", hl.dsp.exec_cmd("~/.config/hypr/scripts/brightness.sh --dec"))

-- Capturas de pantalla (requiere hyprshot)
-- hl.bind("PRINT", hl.dsp.exec_cmd('hyprshot -m output -o "$(xdg-user-dir PICTURES)/Screenshots"'))

-- Multimedia (requiere playerctl)
-- hl.bind("XF86AudioPlay", hl.dsp.exec_cmd("playerctl play-pause"), { locked = true })
-- hl.bind("XF86AudioNext", hl.dsp.exec_cmd("playerctl next"),       { locked = true })
-- hl.bind("XF86AudioPrev", hl.dsp.exec_cmd("playerctl previous"),   { locked = true })

-- Menu de apps favoritas en una tecla libre de tu teclado
-- hl.bind("XF86Favorites", hl.dsp.exec_cmd("~/.config/hypr/scripts/favorites_launcher.sh"))

-- Calculadora (requiere libqalculate)
-- hl.bind("XF86Calculator", hl.dsp.exec_cmd("kitty --title qalc-float -e qalc"))
