#!/usr/bin/env bash
# Muestra fastfetch con el siguiente logo de img/ (rota en cada terminal nueva)
# y ajusta tamaño y posicion segun el ancho de la terminal.

DIR=$(dirname "$(readlink -f "$0")")
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/fastfetch"
STATE_FILE="$STATE_DIR/last_index"

shopt -s nullglob
IMAGES=("$DIR"/img/*.png)
TOTAL=${#IMAGES[@]}

# sin imagenes: fastfetch normal, con el logo de la distro
if ((TOTAL == 0)); then
    exec fastfetch --logo-type auto
fi

# siguiente imagen (0 si no hay estado o no es un numero)
last=$(cat "$STATE_FILE" 2>/dev/null)
[[ "$last" =~ ^[0-9]+$ ]] || last=-1
INDEX=$(((last + 1) % TOTAL))
mkdir -p "$STATE_DIR" && echo "$INDEX" > "$STATE_FILE"

WIDTH=$(tput cols 2>/dev/null || echo 80)

if ((WIDTH < 50)); then
    HEIGHT=8
    POSITION="top"
elif ((WIDTH < 120)); then
    HEIGHT=12
    POSITION="left"
else
    HEIGHT=18
    POSITION="left"
fi

exec fastfetch \
    --logo "${IMAGES[$INDEX]}" \
    --logo-height "$HEIGHT" \
    --logo-position "$POSITION"
