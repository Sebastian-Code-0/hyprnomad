#!/usr/bin/env bash
# Aplica el tema de pywal del wallpaper actual y refresca lo que usa sus colores.
# Lo cargan con "source" apply_wallpaper.sh y random_wallpaper.sh.

. "$HOME/.config/hypr/scripts/wallpaper-paths.sh"

# fondo estatico para hyprlock (primer cuadro si es GIF)
_fondo_hyprlock() {
    mkdir -p ~/.cache/hyprlock
    magick "$1[0]" -resize '2560x1440>' ~/.cache/hyprlock/background.png 2>/dev/null &
}

# anota el wallpaper en el historial ("Recientes" del selector)
_anotar_historial() {
    mkdir -p ~/.local/share/wallpaper-select
    echo "$(date +%s) $1" >> ~/.local/share/wallpaper-select/history.log
}

# genera la paleta; $XDG_RUNTIME_DIR/theme_variant con "light" pide el tema claro
_generar_paleta() {
    local variante=() archivo="${XDG_RUNTIME_DIR:-/tmp}/theme_variant"
    [[ -s $archivo && $(<"$archivo") == light ]] && variante=(-l)
    wal -i "$1" "${variante[@]}" -q -n -e
}

# recarga las apps que leen los colores
_recargar_apps() {
    python3 "$HOME/.config/hypr/scripts/update_calendar_colors.py"
    pgrep -x waybar >/dev/null && killall waybar
    waybar &
    swaync-client -rs
}

_wall=$(readlink -f "$WALLPAPER_LINK")
_fondo_hyprlock "$_wall"
_anotar_historial "$_wall"
_generar_paleta "$_wall"
_recargar_apps

unset -f _fondo_hyprlock _anotar_historial _generar_paleta _recargar_apps
unset _wall
