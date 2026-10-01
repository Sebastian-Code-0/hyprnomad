#!/usr/bin/env bash
# Previsualizador de lf. Uso: previewer.sh <archivo> <ancho> <alto> <columna_x> <fila_y>
# En kitty dibuja la imagen a resolucion real con "kitty +kitten icat --place"
# (siempre dentro de la caja indicada); en otro terminal usa chafa en modo texto.

file="$1"
w="$2"
h="$3"
x="$4"
y="$5"

CACHE_DIR="$HOME/.cache/lf-previewer"
mkdir -p "$CACHE_DIR"
cache_key=$(printf '%s' "$file" | md5sum | cut -d' ' -f1)
cache_f="$CACHE_DIR/$cache_key"

# Dibuja la imagen y termina el script. El código de salida depende del
# método: icat dibuja directo en la terminal -> exit 1 (lf no toca nada
# más). chafa en modo texto -> exit 0 (lf muestra la salida como texto).
#
# $2 (offset) = líneas de metadata ya impresas arriba, para que la imagen
# empiece justo debajo del texto en vez de dibujarse encima.
show_image() {
    img="$1"
    off="${2:-0}"
    yy=$((y + off))
    hh=$((h - off))
    [ "$hh" -lt 1 ] && hh=1
    if [ -n "$KITTY_WINDOW_ID" ]; then
        kitty +kitten icat --silent --stdin no --transfer-mode file \
            --place "${w}x${hh}@${x}x${yy}" "$img" < /dev/null > /dev/tty 2>/dev/null
        exit 1
    else
        chafa --format symbols --size "${w}x${hh}" "$img" 2>/dev/null
        exit 0
    fi
}

mime="$(file -Lb --mime-type "$file" 2>/dev/null)"

case "$file" in
    *.zip) zipinfo "$file" 2>/dev/null; exit 0 ;;
    *.7z) 7z l "$file" 2>/dev/null; exit 0 ;;
    *.rar) unrar l "$file" 2>/dev/null; exit 0 ;;
    *.tar.gz|*.tgz) tar -ztvf "$file" 2>/dev/null; exit 0 ;;
    *.tar.bz2) tar -jtvf "$file" 2>/dev/null; exit 0 ;;
    *.tar.xz) tar -Jtvf "$file" 2>/dev/null; exit 0 ;;
    *.tar.zst) tar --zstd -tvf "$file" 2>/dev/null; exit 0 ;;
    *.tar) tar -tvf "$file" 2>/dev/null; exit 0 ;;
    *.apk|*.jar) unzip -l "$file" 2>/dev/null; exit 0 ;;
    *.ttf|*.otf|*.woff|*.woff2)
        meta=$(exiftool -S -FontName -FileType -FontFamily -FontSubfamily "$file" 2>/dev/null)
        printf '%s\n\n' "$meta"
        if magick -size 400x150 xc:white -font "$file" -pointsize 28 -fill black \
            -gravity center -annotate 0 "AaBbCc 123" "$cache_f.png" 2>/dev/null; then
            show_image "$cache_f.png" "$(printf '%s\n\n' "$meta" | wc -l)"
        fi
        exit 0
        ;;
esac

case "$mime" in
    image/*)
        show_image "$file"
        exit 0
        ;;
    video/*)
        meta=$(exiftool -S -ImageSize -FileType -Duration -AudioChannel -CompressorName "$file" 2>/dev/null)
        printf '%s\n\n' "$meta"
        if ffmpegthumbnailer -i "$file" -o "$cache_f.jpg" -c jpeg -s 0 -q 8 -t 50% 2>/dev/null \
            && [ -s "$cache_f.jpg" ]; then
            show_image "$cache_f.jpg" "$(printf '%s\n\n' "$meta" | wc -l)"
        fi
        exit 0
        ;;
    audio/*)
        meta=$(exiftool -S -Title -Artist -Album -Duration -FileSize -AudioBitrate -SampleRate "$file" 2>/dev/null)
        printf '%s\n\n' "$meta"
        if ffmpegthumbnailer -i "$file" -o "$cache_f.jpg" -s 256 -c jpeg -q 8 2>/dev/null \
            && [ -s "$cache_f.jpg" ]; then
            show_image "$cache_f.jpg" "$(printf '%s\n\n' "$meta" | wc -l)"
        fi
        exit 0
        ;;
    application/vnd.openxmlformats-officedocument.wordprocessingml.document| \
    application/vnd.openxmlformats-officedocument.spreadsheetml.sheet| \
    application/vnd.openxmlformats-officedocument.presentationml.presentation| \
    application/vnd.oasis.opendocument.text| \
    application/vnd.oasis.opendocument.spreadsheet| \
    application/vnd.oasis.opendocument.presentation| \
    application/msword|application/vnd.ms-excel|application/vnd.ms-powerpoint)
        echo "   documento de oficina — ábrelo con 'aa' (OnlyOffice)"
        exit 0
        ;;
    application/pdf)
        meta=$(pdfinfo "$file" 2>/dev/null)
        printf '%s\n\n' "$meta"
        if pdftoppm -f 1 -l 1 -r 100 -png "$file" "$cache_f" 2>/dev/null; then
            img=$(ls "$cache_f"*.png 2>/dev/null | head -1)
            [ -n "$img" ] && show_image "$img" "$(printf '%s\n\n' "$meta" | wc -l)"
        fi
        exit 0
        ;;
    text/*|application/json|application/xml|application/javascript|application/x-shellscript|inode/x-empty)
        bat --color=always --style=plain --pager=never "$file" 2>/dev/null
        exit 0
        ;;
    *)
        bat --color=always --style=plain --pager=never "$file" 2>/dev/null || file -Lb "$file"
        exit 0
        ;;
esac
