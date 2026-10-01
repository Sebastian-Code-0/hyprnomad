#!/usr/bin/env python3
"""Guarda una miniatura de cada ventana la primera vez que recibe el foco y la borra al cerrarla.
La usa el selector de ventanas (window-select)."""
import json
import os
import socket
import subprocess
import threading
import time

RUNTIME = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
SIG = os.environ["HYPRLAND_INSTANCE_SIGNATURE"]
SOCK_PATH = f"{RUNTIME}/hypr/{SIG}/.socket2.sock"
THUMB_DIR = os.path.expanduser("~/.cache/hypr-winselect")
CAPTURE_DELAY = 1.5

os.makedirs(THUMB_DIR, exist_ok=True)
os.chmod(THUMB_DIR, 0o700)  # las capturas de ventanas son privadas


def hyprctl_json(cmd):
    out = subprocess.run(["hyprctl", "-j", cmd], capture_output=True, text=True).stdout
    return json.loads(out)


def capture(addr):
    time.sleep(CAPTURE_DELAY)
    try:
        clients = hyprctl_json("clients")
        client = next((c for c in clients if c["address"] == f"0x{addr}"), None)
        if not client:
            return
        x, y = client["at"]
        w, h = client["size"]
        thumb = os.path.join(THUMB_DIR, f"{addr}.png")
        subprocess.run(
            ["grim", "-g", f"{x},{y} {w}x{h}", thumb],
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def handle_line(line):
    # activewindowv2 dispara cuando la ventana realmente tiene foco (esta
    # visible de verdad), no apenas se crea -- asi evitamos capturar
    # ventanas que se abren en un workspace que no estamos viendo.
    if line.startswith("activewindowv2>>"):
        addr = line.split(">>", 1)[1].strip()
        if not addr or addr == "0":
            return
        thumb = os.path.join(THUMB_DIR, f"{addr}.png")
        if not os.path.exists(thumb):
            threading.Thread(target=capture, args=(addr,), daemon=True).start()
    elif line.startswith("closewindow>>"):
        addr = line.split(">>", 1)[1].split(",", 1)[0].strip()
        thumb = os.path.join(THUMB_DIR, f"{addr}.png")
        if os.path.exists(thumb):
            os.remove(thumb)


def main():
    while True:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.connect(SOCK_PATH)
                buf = ""
                while True:
                    data = s.recv(4096)
                    if not data:
                        break
                    buf += data.decode(errors="ignore")
                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        handle_line(line)
        except (FileNotFoundError, ConnectionRefusedError, OSError):
            time.sleep(2)


if __name__ == "__main__":
    main()
