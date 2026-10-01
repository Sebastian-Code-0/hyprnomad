# hyprnomad

---

![desktop](img/desktop.png)

<p align="center">
  <img src="img/terminal.png" width="49%" alt="terminal">
  <img src="img/hyprlock.png" width="49%" alt="hyprlock">
</p>

> [!NOTE]
> `install.sh` backs up anything it replaces in `~/.config` automatically, but making your own copy of your current setup first costs nothing.

English (this file) · [Español](README.es.md)

Configuring and customizing the Hyprland desktop with pywal colors. A full Arch Linux +
Hyprland setup — hyprlock, waybar, swaync, wlogout, and a handful of custom GTK3 apps
(launcher, clipboard history, wallpaper picker, window picker, wifi panel) — where the color
palette comes from the current wallpaper and gets applied everywhere.

The configuration, its comments and every app's text are written in Spanish, since the
project is built for Spanish speakers. This README is in English so it's discoverable; using
the setup itself means reading (or translating) Spanish.

## Software

**Base**

| | |
|---|---|
| OS | Arch Linux |
| Compositor | Hyprland |
| Session | uwsm |
| Bar | Waybar |
| Terminal | kitty |
| Shell | Zsh + Oh My Zsh + Powerlevel10k |
| Lock / idle | hyprlock / hypridle |
| Notifications | SwayNC |

**Input & UI**

| | |
|---|---|
| Launcher | custom, GTK3 + gtk-layer-shell |
| Clipboard | cliphist + custom GTK3 UI |
| Wallpaper picker | custom GTK3 UI |
| Window picker | custom GTK3 UI |
| Wifi panel | custom GTK3 UI, NetworkManager |
| Power menu | wlogout |
| Color scheme | pywal |
| Fonts | SpaceMono Nerd Font, JetBrainsMono Nerd Font |

**Utilities**

| | |
|---|---|
| File manager | lf |
| System info | fastfetch |
| Disk automount | udiskie |
| `ls` / `cat` replacement | lsd / bat |
| Wallpaper daemon | awww |

**Multimedia**

| | |
|---|---|
| Volume | pamixer |
| Audio mixer (GUI) | pavucontrol |
| Media keys | playerctl |
| Screenshots | grim, hyprshot |
| Image processing | ImageMagick |

## Apps

Five GTK3 apps built for this setup, replacing rofi/wofi-based launchers and pickers.

<table>
<tr>
<td align="center" width="20%"><img src="img/launcher.png"><br>Launcher</td>
<td align="center" width="20%"><img src="img/clipboard.png"><br>Clipboard history</td>
<td align="center" width="20%"><img src="img/wallpapers.png"><br>Wallpaper picker</td>
<td align="center" width="20%"><img src="img/windows.png"><br>Window picker</td>
<td align="center" width="20%"><img src="img/wifi.png"><br>Wifi panel</td>
</tr>
</table>

## Dependencies

`install.sh` checks these are present and lists what's missing, but doesn't install anything.

```sh
sudo pacman -S hyprland uwsm hyprlock hypridle waybar swaync awww kitty lf fastfetch \
  cliphist wl-clipboard grim imagemagick jq brightnessctl pamixer libnotify \
  xdg-user-dirs ffmpegthumbnailer perl-image-exiftool udisks2 lsd bat zsh \
  gtk-layer-shell python-gobject ttf-jetbrains-mono-nerd ttf-space-mono-nerd ttf-dejavu

yay -S python-pywal wlogout   # AUR
```

Only needed for `./install.sh --zshrc`: [Oh My Zsh](https://ohmyz.sh) with the
[Powerlevel10k](https://github.com/romkatv/powerlevel10k) theme and the `zsh-autosuggestions` /
`zsh-syntax-highlighting` plugins — all installed as git clones into `~/.oh-my-zsh`, not pacman
packages.

## Install

```sh
git clone https://github.com/Sebastian-Code-0/hyprnomad.git
cd hyprnomad
./install.sh --simular   # dry run: shows what it would do
./install.sh
```

Copies `config/` into `~/.config` and generates the initial pywal palette. Doesn't install any
packages.

## Shortcuts

`Super` is the Windows key. Full list, from `config/hypr/hyprland.conf`.

**Programs**

| Shortcut | Action |
|---|---|
| `Super + Enter` | Terminal (kitty) |
| `Super + Shift + Enter` | Floating terminal |
| `Super + Space` | Launcher |
| `Super + E` | File manager (lf, in kitty) |
| `Super + F` | Browser |
| `Super + Shift + V` | Clipboard history |
| `Super + Shift + A` | Wallpaper picker |
| `Super + A` | Random wallpaper |
| `Ctrl + Alt + Tab` | Window picker |
| `Super + N` | Notification center |

**Session**

| Shortcut | Action |
|---|---|
| `Super + L` | Lock screen |
| `Super + Shift + L` | Power menu (lock / suspend / restart / shutdown) |
| `Super + Shift + M` | Log out |

**Windows & workspaces**

| Shortcut | Action |
|---|---|
| `Super + Q` | Close window |
| `Super + V` | Toggle floating |
| `Super + P` | Pseudo mode (dwindle) |
| `Super + J` | Toggle split |
| `Super + arrows` | Move focus |
| `Super + 1..9, 0` | Go to workspace 1..10 |
| `Super + Shift + 1..9, 0` | Move window to workspace 1..10 |
| `Super + mouse wheel` | Cycle workspaces |
| `Super + S` / `Super + Shift + S` | Toggle / move to the special workspace |
| `Super + left/right click` (drag) | Move / resize window |

**Equipment keys** (`hypr/local.conf`, commented out by default): volume, mic, brightness,
screenshot, media keys, favorites menu.

### Inside the apps

Launcher, clipboard, wallpaper picker and window picker share the same base keys: `Esc`
closes, type to search, `↑↓` moves, `Enter` acts, `Tab`/`Shift+Tab` switches
category/section. Extra keys: `Ctrl+F` favorite, `Ctrl+D` details (launcher); `Ctrl+O` open,
`Ctrl+Delete` delete, `Alt+Delete` clear history (clipboard); `Ctrl+T` categories, `Ctrl+G`
columns (wallpaper picker); `Ctrl+W` close, `Ctrl+M` bring here, `Ctrl+G` columns (window
picker).

### lf

`.` hidden files · `Esc` clear · `f` filter · `w` jump (zoxide) · `Ctrl+F` find files (fzf) ·
`bc` search text in files (ripgrep) · `x y p` cut/copy/paste · `bb` trash · `B` delete ·
`br`/`bv` restore/empty trash · `bn`/`bf` rename · `aa` open · `Ctrl+A` select all · `cm`
make executable · `cb` backup · `cn cx ca cd` copy filename/filename+ext/file path/dir path ·
`na nd ns` new file/dir/dir from selection · `zc za ze` zip/encrypted zip/extract · `v4 vv vp
vj vg v3` convert to mp4/mkv/png/jpg/gif/mp3 · `id im iv in iw is` go to
Downloads/Pictures/Videos/Music/Wallpapers/Screenshots · `ii` or `gh` go home · `iu`/`du` USB
mount/unmount · `gg` top of list · `zh zr zn zs zt` hidden/reverse/info/size/date · `sn ss st
se sa sb sc` sort by name/size/mtime/ext/atime/ctime/btime · `rc` reload config.

Full definitions in `config/lf/configs/{keymaps,commands}`.

## Credits

- [hyprstellar](https://github.com/xeji01/hyprstellar) — starting point for the general
  layout; the kitty terminal config, the lf file manager icons and the swaync setup are
  closely based on it.

Licensed under GPL-3.0.

---

<p align="center"><img src="img/nyancat.gif" width="180" alt="nyancat"></p>
