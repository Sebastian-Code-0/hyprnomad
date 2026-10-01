#!/usr/bin/env bash

SOUND_DIR="/usr/share/sounds/freedesktop/stereo"

play_sound() {
    paplay "$SOUND_DIR/$1" &disown
}

get_volume() {
    pamixer --get-volume
}

is_muted() {
    pamixer --get-mute
}

notify_volume() {
    volume=$(get_volume)
    muted=$(is_muted)

    if [[ "$muted" == "true" ]]; then
        icon="audio-volume-muted-symbolic"
        text="Volumen: silenciado"
    else
        if (( volume <= 30 )); then
            icon="audio-volume-low-symbolic"
        elif (( volume <= 60 )); then
            icon="audio-volume-medium-symbolic"
        else
            icon="audio-volume-high-symbolic"
        fi
        text="Volumen: ${volume}%"
    fi

    notify-send -e \
    -h int:value:"$volume" \
    -h string:x-canonical-private-synchronous:volume_notif \
    -u low -i "$icon" "$text"
}

inc_volume() {
    pamixer -i 5
    notify_volume
    play_sound audio-volume-change.oga
}

dec_volume() {
    pamixer -d 5
    notify_volume
    play_sound audio-volume-change.oga
}

toggle_volume() {
    pamixer -t
    sleep 0.09
    notify_volume
    play_sound audio-volume-change.oga
}

toggle_mic() {
    pamixer --default-source -t
    sleep 0.09

    if [[ "$(pamixer --default-source --get-mute)" == "true" ]]; then
        notify-send -e \
        -h string:x-canonical-private-synchronous:mic_notif \
        -u low -i "microphone-sensitivity-muted-symbolic" "Micrófono desactivado"
        play_sound device-removed.oga
    else
        notify-send -e \
        -h string:x-canonical-private-synchronous:mic_notif \
        -u low -i "microphone-sensitivity-high-symbolic" "Micrófono activado"
        play_sound device-added.oga
    fi
}

case "$1" in
    --inc) inc_volume ;;
    --dec) dec_volume ;;
    --toggle) toggle_volume ;;
    --toggle-mic) toggle_mic ;;
    --get) get_volume ;;
    *) get_volume ;;
esac