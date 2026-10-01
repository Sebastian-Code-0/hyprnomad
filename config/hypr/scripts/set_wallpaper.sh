#!/bin/bash

. "$HOME/.config/hypr/scripts/wallpaper-paths.sh"
wallpaper_path=$WALLPAPER_LINK

if [ ! -f "$wallpaper_path" ]; then
	notify-send -a "awww" "No se encontró el wallpaper" "$wallpaper_path"
	exit 1
fi

awww img "$wallpaper_path" \
	--transition-bezier .43,1.19,1,.4 \
	--transition-fps 60 \
    --transition-step 90 \
	--transition-type "grow" \
	--transition-duration 0.7 \
	--invert-y \
	--transition-pos "$(hyprctl cursorpos)"
