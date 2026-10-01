#!/usr/bin/env python3

import json
import os

COLORS_JSON = os.path.expanduser("~/.cache/wal/colors.json")
MODULES_JSON = os.path.expanduser("~/.config/waybar/modules.json")


def main():
    with open(COLORS_JSON) as f:
        colors = json.load(f)

    accent = colors["colors"]["color1"]
    foreground = colors["special"]["foreground"]

    with open(MODULES_JSON, encoding="utf-8") as f:
        data = json.load(f)

    data["clock"]["calendar"] = {
        "mode": "month",
        "weeks-pos": "",
        "on-scroll": 1,
        "on-click-right": "mode",
        "format": {
            "months": f"<span color='{accent}'><b>{{}}</b></span>",
            "weekdays": f"<span color='{accent}'><b>{{}}</b></span>",
            "days": f"<span color='{foreground}'>{{}}</span>",
            "today": f"<span color='{accent}'><b><u>{{}}</u></b></span>",
        },
    }

    with open(MODULES_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
        f.write("\n")


if __name__ == "__main__":
    main()
