# Funciones para los comandos de lf. Envian mensajes y rutas a lf sin que el texto
# (por ejemplo un nombre de archivo con comillas o saltos de linea) pueda inyectar
# comandos. Se cargan con:  . ~/.config/lf/scripts/utils.sh   ($id lo define lf)

# escapa un texto para ponerlo entre comillas dobles de lf (sin saltos de linea)
lf_escapar() {
    local t=${1//$'\n'/ }
    t=${t//$'\r'/ }
    t=${t//\\/\\\\}
    printf '%s' "${t//\"/\\\"}"
}

# aviso "texto": lo muestra en la barra de lf
aviso() { lf -remote "send $id echo \"$(lf_escapar "$1")\""; }

# ir_a "ruta": cambia de carpeta en lf
ir_a() { lf -remote "send $id cd \"$(lf_escapar "$1")\""; }

# seleccionar "ruta": deja el cursor sobre ese archivo
seleccionar() { lf -remote "send $id select \"$(lf_escapar "$1")\""; }
