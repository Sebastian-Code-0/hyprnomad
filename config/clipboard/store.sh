#!/usr/bin/env bash
# Guarda el portapapeles en cliphist, anota la hora y aplica el limite
CONF=~/.config/clipboard/clipboard.conf
MAX_ITEMS=500
[ -f "$CONF" ] && . "$CONF"
DATA=${XDG_DATA_HOME:-$HOME/.local/share}/clipboard
mkdir -p "$DATA" && chmod 700 "$DATA"

ch() { cliphist ${CLIPHIST_DB:+-db-path "$CLIPHIST_DB"} -max-items 1000000 "$@"; }

# los gestores de contraseñas marcan lo que copian: no se guarda en el historial
if wl-paste --list-types 2>/dev/null | grep -qx 'x-kde-passwordManagerHint'; then
    cat > /dev/null
    exit 0
fi

before=$(ch list | head -n1 | cut -f1)
ch store || exit 0
list=$(ch list)
id=$(head -n1 <<<"$list" | cut -f1)
[ -n "$id" ] && [ "$id" != "$before" ] && echo "$id $(date +%s)" >> "$DATA/times.log"

# sobre el limite: borra los mas antiguos y avisa
total=$(wc -l <<<"$list")
if (( total > MAX_ITEMS )); then
    extra=$((total - MAX_ITEMS))
    tail -n "$extra" <<<"$list" | ch delete
    if (( extra == 1 )); then msg="Se eliminó 1 elemento antiguo"; else msg="Se eliminaron $extra elementos antiguos"; fi
    notify-send -a Portapapeles -i edit-delete -h string:x-canonical-private-synchronous:clipboard \
        "Límite superado" "$msg (máximo: $MAX_ITEMS)."
fi
