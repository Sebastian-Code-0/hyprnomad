#!/bin/bash
# Aplica un wallpaper: enlace actual, transicion awww, aviso y tema pywal

img=$(realpath "$1") || exit 1
[ -f "$img" ] || { notify-send -a "Wallpaper" "No existe" "$1"; exit 1; }

. "$HOME/.config/hypr/scripts/wallpaper-paths.sh"
mkdir -p "$(dirname "$WALLPAPER_LINK")"
ln -sf "$img" "$WALLPAPER_LINK"
. ~/.config/hypr/scripts/set_wallpaper.sh

notify-send -a "Wallpaper" "Wallpaper aplicado" "$(basename "$img")" -i "$img"
. ~/.config/hypr/scripts/apply_wal_theme.sh
