#!/usr/bin/env bash
# Datos en español para hyprlock: date | greeting | battery | caps | lock | clock [rise]

# segundos que faltan para que pam_faillock libere la cuenta (vacio si no esta bloqueada)
lock_remaining() {
    local conf=/etc/security/faillock.conf deny unlock interval
    deny=$(sed -n 's/^[[:space:]]*deny[[:space:]]*=[[:space:]]*\([0-9]\+\).*/\1/p' "$conf" 2>/dev/null | tail -1)
    unlock=$(sed -n 's/^[[:space:]]*unlock_time[[:space:]]*=[[:space:]]*\([0-9]\+\).*/\1/p' "$conf" 2>/dev/null | tail -1)
    interval=$(sed -n 's/^[[:space:]]*fail_interval[[:space:]]*=[[:space:]]*\([0-9]\+\).*/\1/p' "$conf" 2>/dev/null | tail -1)
    faillock ${FAILLOCK_DIR:+--dir "$FAILLOCK_DIR"} --user "${USER:-$(id -un)}" 2>/dev/null | awk \
        -v deny="${deny:-3}" -v unlock="${unlock:-600}" -v interval="${interval:-900}" '
        $NF == "V" { cmd = "date -d \"" $1 " " $2 "\" +%s"; cmd | getline t; close(cmd); ts[++n] = t; if (t > last) last = t }
        END {
            for (i = 1; i <= n; i++) if (last - ts[i] <= interval) fails++
            now = systime(); left = last + unlock - now
            if (fails >= deny && left > 0) print left
        }'
}

case "$1" in
date)
    dias=(domingo lunes martes miércoles jueves viernes sábado)
    meses=(enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre)
    echo "${dias[$(date +%w)]}, $(date +%-d) de ${meses[$(date +%-m) - 1]}"
    ;;
greeting)
    h=$(date +%-H)
    if   ((h < 6));  then s="Buenas noches"
    elif ((h < 12)); then s="Buenos días"
    elif ((h < 19)); then s="Buenas tardes"
    else                  s="Buenas noches"
    fi
    echo "$s, ${USER:-$(id -un)}"
    ;;
battery)
    bat=$(ls -d /sys/class/power_supply/BAT* 2>/dev/null | head -1)
    [[ -n "$bat" ]] || exit 0   # sin bateria: no muestra nada
    pct=$(<"$bat/capacity")
    status=$(<"$bat/status")
    if [[ "$status" == "Charging" ]]; then
        icon=$'\U000f0084'
    else
        icons=($'\U000f008e' $'\U000f007a' $'\U000f007b' $'\U000f007c' $'\U000f007d' $'\U000f007e'
               $'\U000f007f' $'\U000f0080' $'\U000f0081' $'\U000f0082' $'\U000f0079')
        icon=${icons[pct / 10]}
    fi
    echo "$icon  $pct%"
    ;;
caps)
    # mayusculas activas: LED del teclado o estado de Hyprland (hyprlock no lo expone)
    [[ -n "$(lock_remaining)" ]] && exit 0
    on=0
    for led in /sys/class/leds/*capslock/brightness; do
        [[ -r "$led" && $(<"$led") -gt 0 ]] && on=1
    done
    ((on)) || { hyprctl devices -j 2>/dev/null | grep -q '"capsLock": true' && on=1; }
    ((on)) && echo $'\u21ea  Mayúsculas activadas'
    ;;
lock)
    left=$(lock_remaining)
    [[ -n "$left" ]] && printf 'Cuenta bloqueada · faltan %02d:%02d\n' $((left / 60)) $((left % 60))
    ;;
clock)
    # hora en formato 12 h con AM/PM pequeño a la derecha; el espacio invisible de la izquierda
    # mantiene los numeros centrados. $2 = elevacion opcional del AM/PM (unidades de 1/1024 pt)
    ap=$(LC_ALL=C date +%p)
    small="font_size=\"22pt\"${2:+ rise=\"$2\"}"
    echo "<span $small alpha=\"1%\"> $ap</span>$(date +%-I:%M)<span $small> $ap</span>"
    ;;
esac
