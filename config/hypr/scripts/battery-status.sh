#!/usr/bin/env bash
# Avisos de bateria: nivel bajo, carga lista y cambios del cargador.
# Lee la bateria cada 16 s; en equipos sin bateria termina.

BAJO=20          # % que dispara el aviso critico
CARGADO=80       # % recomendado para desconectar el cargador
INTERVALO=${INTERVALO:-16}
DIR=${POWER_SUPPLY_DIR:-/sys/class/power_supply}

bateria=$(ls -d "$DIR"/BAT* 2>/dev/null | head -1)
[[ -n "$bateria" ]] || exit 0

# icono segun el nivel (multiplos de 10, como trae el tema de iconos)
icono() {
    local nivel=$((($1 + 5) / 10 * 10))
    ((nivel > 100)) && nivel=100
    echo "battery-level-$nivel${2:+-charging}-symbolic"
}

aviso() { notify-send -a "Batería" -u "$1" -i "$2" "$3" "$4"; }

bajo_avisado=0
lleno_avisado=0
conectado_antes=""

while true; do
    capacidad=$(<"$bateria/capacity")
    [[ $(<"$bateria/status") == Discharging ]] && conectado=0 || conectado=1

    # nivel bajo: avisa una vez y se vuelve a armar al cargar o subir de nivel
    if ((!conectado && capacidad <= BAJO && !bajo_avisado)); then
        aviso critical battery-low-symbolic "Batería al $capacidad%" "Por favor, enchufe su cargador."
        bajo_avisado=1
    elif ((conectado || capacidad > BAJO + 5)); then
        bajo_avisado=0
    fi

    # carga lista: solo mientras esta conectada
    if ((conectado && capacidad >= CARGADO && !lleno_avisado)); then
        aviso normal battery-level-100-charged-symbolic "Batería al $CARGADO%" \
            "La batería está cargada. Puede desconectar el dispositivo."
        lleno_avisado=1
    elif ((!conectado || capacidad < CARGADO - 5)); then
        lleno_avisado=0
    fi

    # cargador enchufado o desenchufado (no avisa al iniciar la sesion)
    if [[ -n $conectado_antes && $conectado != "$conectado_antes" ]]; then
        if ((conectado)); then
            aviso normal "$(icono "$capacidad" 1)" "Cargando" "El cargador está enchufado."
        else
            aviso normal "$(icono "$capacidad")" "Descargando" "El cargador está desenchufado."
        fi
    fi
    conectado_antes=$conectado

    sleep "$INTERVALO"
done
