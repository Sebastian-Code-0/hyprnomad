#!/usr/bin/env bash
# Deja el cursor de lf sobre un archivo. Uso: seleccionar.sh <id de lf> <ruta>
id=$1
. ~/.config/lf/scripts/utils.sh
seleccionar "$2"
