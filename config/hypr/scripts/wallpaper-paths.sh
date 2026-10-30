# Copyright (C) 2026 Sebastian-Code-0
# SPDX-License-Identifier: GPL-3.0-or-later
# Rutas del wallpaper: carpeta de imagenes del usuario (XDG) + Wallpapers.
# Se pueden sobrescribir con las variables WALLPAPER_DIR y WALLPAPER_LINK.
: "${WALLPAPER_DIR:=$(xdg-user-dir PICTURES 2>/dev/null || echo "$HOME/Pictures")/Wallpapers}"
: "${WALLPAPER_LINK:=$WALLPAPER_DIR/wallpaper.png}"
