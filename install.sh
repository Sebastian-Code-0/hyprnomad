#!/usr/bin/env bash
# Instala estos dotfiles: copia config/ a ~/.config (con respaldo de lo que ya exista),
# deja los wallpapers de ejemplo y genera la paleta inicial de pywal.
# No instala paquetes (ver README, seccion Dependencies) ni toca ~/.zshrc salvo con --zshrc.
set -euo pipefail

AQUI=$(cd "$(dirname "$0")" && pwd)
DESTINO="$HOME/.config"       # las rutas de la configuracion asumen ~/.config
SIMULAR=0
ZSHRC=0

# archivos personales: si ya existen en el equipo se conservan, no se pisan
PERSONALES=(hypr/local.conf hypr/hyprlock/assets/avatar.jpg launcher/assets/cover.jpg)

uso() {
    cat <<'EOF'
Uso: ./install.sh [opciones]

  -n, --simular   muestra lo que haria sin cambiar nada
      --zshrc     instala home/zshrc.example como ~/.zshrc (solo si no existe)
  -h, --ayuda     muestra esta ayuda
EOF
}

for arg in "$@"; do
    case $arg in
        -n | --simular) SIMULAR=1 ;;
        --zshrc) ZSHRC=1 ;;
        -h | --ayuda) uso; exit 0 ;;
        *) echo "Opcion desconocida: $arg" >&2; uso >&2; exit 1 ;;
    esac
done

[[ $EUID -ne 0 ]] || { echo "No lo ejecutes como root: instala en tu propio HOME." >&2; exit 1; }
[[ -d $AQUI/config ]] || { echo "No encuentro $AQUI/config: ejecuta el script desde el repositorio." >&2; exit 1; }

hacer() { if ((SIMULAR)); then echo "  [simulacro] $*"; else "$@"; fi; }
paso() { echo; echo "==> $*"; }

# 1) dependencias: solo avisa de lo que falta, no instala nada
paso "Comprobando dependencias"
faltan=()
for cmd in Hyprland uwsm hyprlock hypridle waybar swaync swaync-client awww wal wlogout kitty lf \
           fastfetch cliphist wl-copy wl-paste grim magick jq brightnessctl pamixer notify-send \
           xdg-user-dir python3 lsd bat; do
    command -v "$cmd" >/dev/null 2>&1 || faltan+=("$cmd")
done
python3 - <<'EOF' 2>/dev/null || faltan+=("python-gobject/gtk-layer-shell")
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
gi.require_version("GLibUnix", "2.0")
from gi.repository import Gtk, GtkLayerShell, GLibUnix
EOF
if ((${#faltan[@]})); then
    echo "  Faltan: ${faltan[*]}"
    echo "  Consulta el README, seccion Dependencies (la instalacion continua igualmente)."
else
    echo "  Todo lo esencial esta instalado."
fi

# 2) configuracion: respalda lo existente, copia y restaura los archivos personales
paso "Copiando la configuracion a $DESTINO"
RESPALDO="$HOME/.config-respaldo-$(date +%Y%m%d-%H%M%S)"
hacer mkdir -p "$DESTINO"
for origen in "$AQUI"/config/*/; do
    dir=$(basename "$origen")
    if [[ -e $DESTINO/$dir || -L $DESTINO/$dir ]]; then
        hacer mkdir -p "$RESPALDO"
        hacer chmod 700 "$RESPALDO"   # contiene configs completas: solo el usuario
        hacer mv "$DESTINO/$dir" "$RESPALDO/$dir"
        echo "  respaldada: $dir -> $RESPALDO/$dir"
    fi
    hacer cp -a "$origen" "$DESTINO/$dir"
    echo "  instalada:  $dir"
done

for rel in "${PERSONALES[@]}"; do
    if [[ -f $RESPALDO/$rel ]]; then
        hacer cp -a "$RESPALDO/$rel" "$DESTINO/$rel"
        echo "  conservado: $rel (ya existia, no se pisa)"
    fi
done

# avisa de lo que solo existia en el respaldo (favoritos, estado propio): no se restaura solo
if [[ -d $RESPALDO ]] && ((!SIMULAR)); then
    extras=()
    while IFS= read -r f; do
        rel=${f#"$RESPALDO"/}
        [[ -e $DESTINO/$rel || -L $DESTINO/$rel ]] || extras+=("$rel")
    done < <(find "$RESPALDO" \( -type f -o -type l \))
    if ((${#extras[@]})); then
        echo "  aviso: ${#extras[@]} archivo(s) tuyos solo estan en el respaldo (no se restauraron):"
        printf '    %s\n' "${extras[@]:0:10}"
        ((${#extras[@]} <= 10)) || echo "    ... y $((${#extras[@]} - 10)) mas en $RESPALDO"
    fi
fi

# los scripts deben ser ejecutables (un zip descargado puede perder el permiso)
if ((!SIMULAR)); then
    while IFS= read -r f; do chmod +x "$f"; done < <(grep -rIl --exclude='*.css' --exclude='*.json*' '^#!' "$DESTINO"/{hypr,launcher,clipboard,wallpaper-select,window-select,network-panel,lf,fastfetch,wlogout} 2>/dev/null)
fi

# 3) wallpapers de ejemplo y wallpaper inicial (sin pisar los que ya tengas)
paso "Wallpapers de ejemplo"
. "$AQUI/config/hypr/scripts/wallpaper-paths.sh"
hacer mkdir -p "$WALLPAPER_DIR"
hacer cp -n "$AQUI"/wallpapers/* "$WALLPAPER_DIR"/
echo "  carpeta: $WALLPAPER_DIR"
if [[ ! -e $WALLPAPER_LINK ]]; then
    hacer ln -s "$WALLPAPER_DIR/aurora.jpg" "$WALLPAPER_LINK"
    echo "  wallpaper inicial: aurora.jpg"
fi

# 4) paleta inicial (pywal) y fondo de hyprlock: sin esto las apps no tienen colores al primer inicio
paso "Generando la paleta de colores"
if ((SIMULAR)); then
    echo "  [simulacro] wal -i $WALLPAPER_LINK, fondo de hyprlock y colores del calendario"
elif command -v wal >/dev/null 2>&1 && [[ -e $WALLPAPER_LINK ]]; then
    # pywal usa el comando "convert" de ImageMagick y este avisa que esta obsoleto: solo se muestra si hay error
    if salida=$(wal -i "$(readlink -f "$WALLPAPER_LINK")" -q -n -e 2>&1); then
        if command -v magick >/dev/null 2>&1; then
            mkdir -p "$HOME/.cache/hyprlock"
            magick "$(readlink -f "$WALLPAPER_LINK")[0]" -resize '2560x1440>' "$HOME/.cache/hyprlock/background.png"
        fi
        python3 "$DESTINO/hypr/scripts/update_calendar_colors.py"
        echo "  paleta generada"
    else
        echo "$salida"
        echo "  aviso: pywal fallo; la paleta se genera al elegir un wallpaper"
    fi
else
    echo "  omitido (falta pywal o el wallpaper); se genera al elegir un wallpaper con Super+Shift+A"
fi

# 5) zshrc opcional
if ((ZSHRC)); then
    paso "zshrc"
    if [[ -e $HOME/.zshrc ]]; then
        echo "  ya tienes ~/.zshrc: no se toca (ejemplo en $AQUI/home/zshrc.example)"
    else
        hacer cp "$AQUI/home/zshrc.example" "$HOME/.zshrc"
        echo "  instalado ~/.zshrc"
    fi
fi

paso "Listo"
cat <<EOF
  Siguientes pasos:
   1. Ajusta $DESTINO/hypr/local.conf (monitores, teclas Fn y demas)
   2. Cierra sesion e inicia Hyprland con uwsm
EOF
[[ -d $RESPALDO ]] && echo "   Tu configuracion anterior esta en $RESPALDO"
exit 0
