#!/usr/bin/env bash
# Copyright (C) 2026 Sebastian-Code-0
# SPDX-License-Identifier: GPL-3.0-or-later
# Genera los iconos de wlogout (glifos Nerd Font blancos, 512x512) en icons/.
# Requiere ImageMagick y SpaceMono Nerd Font.
cd "$(dirname "$0")" && mkdir -p icons || exit 1
FONT=$(fc-match -f '%{file}' "SpaceMono Nerd Font")

# make nombre codigo-unicode (glifos Material Design Icons)
make() {
    magick -background none -fill white -font "$FONT" -pointsize 380 "label:$(printf "\\U$2")" \
        -trim +repage -resize 480x480 -gravity center -extent 512x512 "icons/$1.png"
}

make lock    000f0341   # candado
make sleep   000f0594   # luna con estrellas
make restart 000f0709   # flecha circular
make power   000f0425   # encendido
