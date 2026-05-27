<div align="center">

# LinuxViva
### Classeviva client for Linux

A native GNOME desktop client for the **Spaggiari Classeviva** electronic register,
built with GTK4 + libadwaita.

![License](https://img.shields.io/github/license/Giovix64/linuxviva)
![Platform](https://img.shields.io/badge/platform-Linux-blue)
![GTK](https://img.shields.io/badge/GTK-4-green)

</div>

---

## Features

| Section | Description |
|---|---|
| **Home** | Dashboard with grade summary rings, upcoming agenda, unread notices |
| **Voti** | Grades grouped by subject with per-period averages and circular ring badges; ↑/↓ trend indicators |
| **Assenze** | Calendar heatmap + statistics (absences / delays / early exits) with justification status |
| **Agenda** | Day-navigation view with colour-coded subject bars; separate homework/lessons sections |
| **Bacheca** | Noticeboard with attachment download (auto read-confirmation before download) |
| **Materiali** | Teacher-uploaded files, grouped by teacher, with one-tap download/open |
| **Pagelle** | Downloadable PDF report cards + **inline web report viewer** (WebKit) with auto-login and PDF export |

### Design
- Fully adaptive (works at any window width)
- Respects system dark/light mode via `AdwStyleManager`
- Circular grade rings drawn with Cairo + Pango
- Credentials stored securely in GNOME Keyring / Secret Service
- Auto-login when credentials are saved

---

## Installation

### Arch Linux / CachyOS / Manjaro — via AUR

```bash
# Using yay
yay -S linuxviva-git

# Using paru
paru -S linuxviva-git
```

### Manual install (any distro)

```bash
git clone https://github.com/Giovix64/linuxviva.git
cd linuxviva
bash install.sh
```

This installs to `~/.local/` (no root required) and registers the app in your application launcher.

### Build with Meson (system-wide)

```bash
git clone https://github.com/Giovix64/linuxviva.git
cd linuxviva
meson setup builddir --prefix=/usr
meson compile -C builddir
sudo meson install -C builddir
```

---

## Dependencies

| Package | Arch name | Fedora name | Debian/Ubuntu name |
|---|---|---|---|
| Python 3.11+ | `python` | `python3` | `python3` |
| PyGObject | `python-gobject` | `python3-gobject` | `python3-gi` |
| GTK 4 | `gtk4` | `gtk4` | `gir1.2-gtk-4.0` |
| libadwaita | `libadwaita` | `libadwaita` | `gir1.2-adw-1` |
| WebKitGTK 6 | `webkitgtk-6.0` | `webkitgtk6.0` | `gir1.2-webkit-6.0` |
| httpx | `python-httpx` | `python3-httpx` | `python3-httpx` |
| keyring | `python-keyring` | `python3-keyring` | `python3-keyring` |

**Quick install (Arch):**
```bash
sudo pacman -S python python-gobject gtk4 libadwaita webkitgtk-6.0 python-httpx python-keyring
```

**Quick install (Fedora):**
```bash
sudo dnf install python3 python3-gobject gtk4 libadwaita webkitgtk6.0 python3-httpx python3-keyring
```

**Quick install (Ubuntu 24.04+):**
```bash
sudo apt install python3 python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-webkit-6.0 python3-httpx python3-keyring
```

---

## Running from source

```bash
git clone https://github.com/Giovix64/linuxviva.git
cd linuxviva
python3 src/main.py
```

---

## Project structure

```
linuxviva/
├── meson.build
├── install.sh          ← quick local install (no root needed)
├── PKGBUILD            ← AUR package
├── data/
│   ├── icons/hicolor/scalable/apps/
│   │   └── io.github.giomarco2107.LinuxViva.svg  ← app icon
│   ├── linuxviva.in    ← launcher wrapper template
│   └── io.github.giomarco2107.LinuxViva.desktop
└── src/
    ├── main.py
    ├── application.py
    ├── api/
    │   └── client.py   ← HTTP client (httpx) for Spaggiari REST API
    ├── views/
    │   ├── login_view.py
    │   ├── main_view.py
    │   ├── home_view.py
    │   ├── grades_view.py
    │   ├── absences_view.py
    │   ├── agenda_view.py
    │   ├── noticeboard_view.py
    │   ├── didactics_view.py
    │   └── scrutini_view.py
    └── widgets/
        └── grade_badge.py   ← GradeBadge (pill) + GradeRing (Cairo arc)
```

---

## Contributing

Pull requests are welcome! Please open an issue first to discuss what you'd like to change.

---

## License

[GPL-3.0](LICENSE) — © 2025 Giovix64
