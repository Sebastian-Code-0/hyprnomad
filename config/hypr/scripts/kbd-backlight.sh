#!/usr/bin/env bash
# Apaga (off) o restaura (on) la luz del teclado. Detecta el dispositivo solo;
# si el equipo no tiene luz de teclado no hace nada.

dispositivo=$(brightnessctl -l -m 2>/dev/null | awk -F, '/kbd_backlight/ {print $1; exit}')
[[ -n $dispositivo ]] || exit 0

case "$1" in
    off) brightnessctl -sd "$dispositivo" set 0 ;;
    on)  brightnessctl -rd "$dispositivo" ;;
esac
