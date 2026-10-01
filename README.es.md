# hyprnomad

---

![escritorio](img/desktop.png)

<p align="center">
  <img src="img/terminal.png" width="49%" alt="terminal">
  <img src="img/hyprlock.png" width="49%" alt="bloqueo de pantalla">
</p>

> [!NOTE]
> `install.sh` respalda automáticamente lo que reemplaza en `~/.config`, pero no cuesta nada
> hacer tú también una copia de tu configuración actual antes de instalar.

[English](README.md) · Español (este archivo)

Configurando y personalizando el escritorio de Hyprland con colores de pywal. Una
configuración completa para Arch Linux + Hyprland — hyprlock, waybar, swaync, wlogout, y unas
cuantas apps propias en GTK3 (lanzador, historial del portapapeles, selector de wallpapers,
selector de ventanas, panel de wifi) — donde la paleta de colores sale del wallpaper actual y
se aplica en todas partes.

## Software

**Base**

| | |
|---|---|
| SO | Arch Linux |
| Compositor | Hyprland |
| Sesión | uwsm |
| Barra | Waybar |
| Terminal | kitty |
| Shell | Zsh + Oh My Zsh + Powerlevel10k |
| Bloqueo / inactividad | hyprlock / hypridle |
| Notificaciones | SwayNC |

**Entrada e interfaz**

| | |
|---|---|
| Lanzador | propio, GTK3 + gtk-layer-shell |
| Portapapeles | cliphist + interfaz propia en GTK3 |
| Selector de wallpapers | interfaz propia en GTK3 |
| Selector de ventanas | interfaz propia en GTK3 |
| Panel de wifi | interfaz propia en GTK3, NetworkManager |
| Menú de apagado | wlogout |
| Esquema de color | pywal |
| Fuentes | SpaceMono Nerd Font, JetBrainsMono Nerd Font |

**Utilidades**

| | |
|---|---|
| Gestor de archivos | lf |
| Información del sistema | fastfetch |
| Automontaje de discos | udiskie |
| Reemplazo de `ls` / `cat` | lsd / bat |
| Demonio de wallpaper | awww |

**Multimedia**

| | |
|---|---|
| Volumen | pamixer |
| Mezclador de audio (GUI) | pavucontrol |
| Teclas multimedia | playerctl |
| Capturas de pantalla | grim, hyprshot |
| Procesamiento de imágenes | ImageMagick |

## Apps

Cinco apps propias en GTK3, hechas para este setup, en lugar de lanzadores/selectores basados en rofi o wofi.

<table>
<tr>
<td align="center" width="20%"><img src="img/launcher.png"><br>Lanzador</td>
<td align="center" width="20%"><img src="img/clipboard.png"><br>Historial del portapapeles</td>
<td align="center" width="20%"><img src="img/wallpapers.png"><br>Selector de wallpapers</td>
<td align="center" width="20%"><img src="img/windows.png"><br>Selector de ventanas</td>
<td align="center" width="20%"><img src="img/wifi.png"><br>Panel de wifi</td>
</tr>
</table>

## Dependencias

`install.sh` revisa que estén instaladas y avisa qué falta, pero no instala nada.

```sh
sudo pacman -S hyprland uwsm hyprlock hypridle waybar swaync awww kitty lf fastfetch \
  cliphist wl-clipboard grim imagemagick jq brightnessctl pamixer libnotify \
  xdg-user-dirs ffmpegthumbnailer perl-image-exiftool udisks2 lsd bat zsh \
  gtk-layer-shell python-gobject ttf-jetbrains-mono-nerd ttf-space-mono-nerd ttf-dejavu

yay -S python-pywal wlogout   # AUR
```

Solo hace falta para `./install.sh --zshrc`: [Oh My Zsh](https://ohmyz.sh) con el tema
[Powerlevel10k](https://github.com/romkatv/powerlevel10k) y los plugins `zsh-autosuggestions` /
`zsh-syntax-highlighting` — se instalan clonando con git en `~/.oh-my-zsh`, no son paquetes de
pacman.

## Instalar

```sh
git clone https://github.com/Sebastian-Code-0/hyprnomad.git
cd hyprnomad
./install.sh --simular   # simulacro: muestra lo que haría
./install.sh
```

Copia `config/` a `~/.config` y genera la paleta inicial de pywal. No instala ningún paquete.

## Atajos

`Super` es la tecla Windows. Lista completa, de `config/hypr/hyprland.conf`.

**Programas**

| Atajo | Acción |
|---|---|
| `Super + Enter` | Terminal (kitty) |
| `Super + Shift + Enter` | Terminal flotante |
| `Super + Espacio` | Lanzador |
| `Super + E` | Gestor de archivos (lf, en kitty) |
| `Super + F` | Navegador |
| `Super + Shift + V` | Historial del portapapeles |
| `Super + Shift + A` | Selector de wallpapers |
| `Super + A` | Wallpaper al azar |
| `Ctrl + Alt + Tab` | Selector de ventanas |
| `Super + N` | Centro de notificaciones |

**Sesión**

| Atajo | Acción |
|---|---|
| `Super + L` | Bloquear pantalla |
| `Super + Shift + L` | Menú de apagado (bloquear / suspender / reiniciar / apagar) |
| `Super + Shift + M` | Cerrar sesión |

**Ventanas y espacios de trabajo**

| Atajo | Acción |
|---|---|
| `Super + Q` | Cerrar ventana |
| `Super + V` | Alternar flotante |
| `Super + P` | Modo pseudo (dwindle) |
| `Super + J` | Alternar la división |
| `Super + flechas` | Mover el foco |
| `Super + 1..9, 0` | Ir al espacio 1..10 |
| `Super + Shift + 1..9, 0` | Mover la ventana al espacio 1..10 |
| `Super + rueda del ratón` | Recorrer los espacios |
| `Super + S` / `Super + Shift + S` | Mostrar / mover al espacio especial |
| `Super + clic izq./der.` (arrastrar) | Mover / redimensionar ventana |

**Teclas de equipo** (`hypr/local.conf`, comentadas por defecto): volumen, micrófono, brillo,
capturas, multimedia, menú de favoritos.

### Dentro de las apps

Lanzador, portapapeles, selector de wallpapers y selector de ventanas comparten las mismas
teclas base: `Esc` cierra, escribe para buscar, `↑↓` mueve, `Enter` actúa,
`Tab`/`Shift+Tab` cambia de categoría/sección. Extra: `Ctrl+F` favorito, `Ctrl+D` detalles
(lanzador); `Ctrl+O` abrir, `Ctrl+Supr` borrar, `Alt+Supr` vaciar historial (portapapeles);
`Ctrl+T` categorías, `Ctrl+G` columnas (wallpapers); `Ctrl+W` cerrar, `Ctrl+M` traer aquí,
`Ctrl+G` columnas (ventanas).

### lf

`.` ocultos · `Esc` limpiar · `f` filtrar · `w` saltar (zoxide) · `Ctrl+F` buscar archivos
(fzf) · `bc` buscar texto en archivos (ripgrep) · `x y p` cortar/copiar/pegar · `bb` papelera
· `B` borrar · `br`/`bv` restaurar/vaciar papelera · `bn`/`bf` renombrar · `aa` abrir ·
`Ctrl+A` seleccionar todo · `cm` hacer ejecutable · `cb` crear respaldo · `cn cx ca cd`
copiar nombre/nombre+ext/ruta archivo/ruta carpeta · `na nd ns` crear archivo/carpeta/carpeta
con selección · `zc za ze` zip/zip cifrado/extraer · `v4 vv vp vj vg v3` convertir a
mp4/mkv/png/jpg/gif/mp3 · `id im iv in iw is` ir a
Descargas/Imágenes/Vídeos/Música/Wallpapers/Capturas · `ii` o `gh` ir al inicio · `iu`/`du`
montar/desmontar USB · `gg` principio de la lista · `zh zr zn zs zt`
ocultos/orden/info/tamaño/fecha · `sn ss st se sa sb sc` ordenar por
nombre/tamaño/modificación/extensión/acceso/creación/cambio · `rc` recargar configuración.

Definiciones completas en `config/lf/configs/{keymaps,commands}`.

## Créditos

- [hyprstellar](https://github.com/xeji01/hyprstellar) — punto de partida de la organización
  general; la configuración de la terminal kitty, los iconos de lf y la configuración de
  swaync están muy basados en él.

Publicado bajo licencia GPL-3.0.

---

<p align="center"><img src="img/nyancat.gif" width="180" alt="nyancat"></p>
