#!/usr/bin/env bash
# Cambia a un wallpaper al azar de la carpeta de wallpapers (distinto del actual).

. "$HOME/.config/hypr/scripts/wallpaper-paths.sh"

NOMBRE="Wallpaper aleatorio"
PONER_FONDO="$HOME/.config/hypr/scripts/set_wallpaper.sh"
APLICAR_TEMA="$HOME/.config/hypr/scripts/apply_wal_theme.sh"

avisar() { notify-send -a "$NOMBRE" "$@"; }

[[ -d $WALLPAPER_DIR ]] || { avisar "La carpeta de imágenes no existe" "$WALLPAPER_DIR"; exit 1; }

# solo imagenes; se excluye la que ya esta puesta y su enlace (wallpaper.png)
candidatas=()
for f in "$WALLPAPER_DIR"/*; do
    case "${f,,}" in *.png | *.jpg | *.jpeg | *.webp | *.gif | *.bmp) ;; *) continue ;; esac
    [[ $f -ef $WALLPAPER_LINK ]] && continue
    candidatas+=("$f")
done

if ((${#candidatas[@]} == 0)); then
    avisar "No hay otra imagen para cambiar" "$WALLPAPER_DIR"
    exit 1
fi

elegida=${candidatas[RANDOM % ${#candidatas[@]}]}
ln -sf "$elegida" "$WALLPAPER_LINK"
. "$PONER_FONDO"
avisar "Wallpaper cambiado" "$(basename "$elegida")" -i "$WALLPAPER_LINK"
. "$APLICAR_TEMA"
