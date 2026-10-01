#!/usr/bin/env bash
# Previsualizador para el panel de fzf de "restaurar de papelera" (bc y Ctrl-F no usan esto).
# fzf llama: fzf_trash_preview.sh <ruta_del_archivo_en_la_papelera>
#
# Reusa la misma idea de ~/.config/lf/previewer/previewer.sh: imagen real con
# "kitty +kitten icat" si estamos en kitty, texto resaltado con "bat" si no es
# imagen. fzf expone FZF_PREVIEW_COLUMNS/LINES/TOP/LEFT con el tamaño y la
# posición exacta del panel de preview, así que la imagen se recorta siempre
# dentro de esa caja.

file="$1"

# fzf vuelve a llamar a este script cada vez que cambiás de selección. Si la
# anterior era una imagen dibujada con el protocolo de kitty, queda pegada en
# pantalla hasta que alguien la borre explícitamente — así que la borramos acá
# SIEMPRE, sea la nueva selección imagen o no, para que nunca queden dos
# superpuestas.
if [ -n "$KITTY_WINDOW_ID" ]; then
    kitty +kitten icat --clear --transfer-mode file --stdin no < /dev/null > /dev/tty 2>/dev/null
fi

if [ ! -e "$file" ]; then
    echo "   (sin vista previa, el archivo no está en la papelera)"
    exit 0
fi

if [ -d "$file" ]; then
    echo "   carpeta:"
    echo
    ls -la --color=always -- "$file" 2>/dev/null
    exit 0
fi

mime="$(file -Lb --mime-type "$file" 2>/dev/null)"

case "$mime" in
    image/*)
        if [ -n "$KITTY_WINDOW_ID" ]; then
            kitty +kitten icat --silent --stdin no --transfer-mode file \
                --place "${FZF_PREVIEW_COLUMNS}x${FZF_PREVIEW_LINES}@${FZF_PREVIEW_LEFT}x${FZF_PREVIEW_TOP}" \
                "$file" < /dev/null > /dev/tty 2>/dev/null
        else
            chafa --format symbols --size "${FZF_PREVIEW_COLUMNS}x${FZF_PREVIEW_LINES}" "$file" 2>/dev/null
        fi
        ;;
    text/*|application/json|application/xml|application/javascript|application/x-shellscript|inode/x-empty)
        bat --color=always --style=plain --pager=never -- "$file" 2>/dev/null
        ;;
    *)
        echo "   $mime"
        ;;
esac
