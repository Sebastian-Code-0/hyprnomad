#!/usr/bin/env bash
# Menu de aplicaciones favoritas/mas usadas (wlogout con un boton por app)

data_dir="$HOME/.local/share/launcher"
app_dirs=(
    "$HOME/.local/share/applications"
    "/usr/share/applications"
    "/usr/local/share/applications"
)
icon_dirs=(/usr/share/icons /usr/share/pixmaps)
max_items=4

find_desktop_file() {
    local id="$1"
    for dir in "${app_dirs[@]}"; do
        [[ -f "$dir/$id" ]] && { echo "$dir/$id"; return; }
    done
}

resolve_icon() {
    local name="$1"
    if [[ "$name" == /* ]]; then
        echo "$name"
        return
    fi
    local matches best
    matches=$(find "${icon_dirs[@]}" -type f \( -iname "${name}.png" -o -iname "${name}.svg" \) 2>/dev/null)
    best=$(grep -E '/(256x256|128x128|scalable)/' <<< "$matches" | head -1)
    [[ -z "$best" ]] && best=$(head -1 <<< "$matches")
    echo "$best"
}

# favoritos marcados primero, luego mas usadas; formato "<puntaje> <id>"
favorites_ranked() {
    jq -rn --slurpfile fav <(cat "$data_dir/favorites.json" 2>/dev/null || echo '[]') \
           --slurpfile use <(cat "$data_dir/usage.json" 2>/dev/null || echo '{}') '
        ($fav[0]) as $f | ($use[0]) as $u
        | [ $f[] | "1000000 \(.)" ],
          [ $u | to_entries | sort_by(-.value)[] | select(.key as $k | $f | index($k) | not)
            | "\(.value) \(.key)" ]
        | .[]'
}

tmp_dir=$(mktemp -d "${XDG_RUNTIME_DIR:-/tmp}/fav-wlogout.XXXXXX")
trap 'rm -rf "$tmp_dir"' EXIT
layout_file="$tmp_dir/layout"
css_file="$tmp_dir/style.css"

cp ~/.config/wlogout/style.css "$css_file"
sed -i "s#@import \"../../.cache/wal/colors-waybar.css\";#@import \"$HOME/.cache/wal/colors-waybar.css\";#" "$css_file"

: > "$layout_file"
count=0

while read -r num id; do
    [[ -z "$id" || -z "$num" ]] && continue
    [[ "$id" =~ ^[A-Za-z0-9._-]+\.desktop$ ]] || continue   # el id acaba en un comando: solo nombres validos
    (( num <= 0 )) && continue

    file=$(find_desktop_file "$id")
    [[ -z "$file" ]] && continue

    name=$(grep -m1 "^Name=" "$file" | cut -d= -f2-)
    icon_name=$(grep -m1 "^Icon=" "$file" | cut -d= -f2-)
    [[ -z "$name" ]] && name="${id%.desktop}"
    [[ -z "$icon_name" ]] && icon_name="application-x-executable"

    icon_path=$(resolve_icon "$icon_name")
    label="fav$count"

    {
        echo "{"
        echo "    \"label\": \"$label\","
        echo "    \"action\": \"gtk-launch ${id%.desktop}\","
        echo "    \"text\": \"$name\""
        echo "}"
        echo
    } >> "$layout_file"

    if [[ -n "$icon_path" ]]; then
        {
            echo
            echo "#$label {"
            echo "    background-image: url(\"$icon_path\");"
            echo "}"
        } >> "$css_file"
    fi

    count=$((count + 1))
    (( count >= max_items )) && break
done < <(favorites_ranked)

if [[ $count -eq 0 ]]; then
    notify-send "Favoritos" "Todavia no hay historial: abre apps con Super+Espacio o marca favoritos"
    exit 0
fi

wlogout -l "$layout_file" -C "$css_file" -b "$count"
