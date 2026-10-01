#!/usr/bin/env bash
# Brillo de la pantalla: --inc | --dec | --set N | --get (por defecto).
# Cada cambio muestra una notificacion con barra de progreso.

PASO=10     # % que sube o baja cada pulsacion
MINIMO=5    # % minimo, para no dejar la pantalla apagada

brillo() { brightnessctl -m | cut -d, -f4 | tr -d '%'; }

avisar() {
    local valor
    valor=$(brillo)
    notify-send -e -u low -i display-brightness-symbolic \
        -h string:x-canonical-private-synchronous:brillo \
        -h int:value:"$valor" "Brillo: $valor%"
}

# fija el brillo en $1 % (entre MINIMO y 100) y avisa
fijar() {
    local destino=$1
    ((destino < MINIMO)) && destino=$MINIMO
    ((destino > 100)) && destino=100
    brightnessctl -q set "$destino%" && avisar
}

case "$1" in
    --inc) fijar $(($(brillo) + PASO)) ;;
    --dec) fijar $(($(brillo) - PASO)) ;;
    --set) fijar "${2:-100}" ;;
    *)     brillo ;;
esac
