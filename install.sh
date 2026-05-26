#!/usr/bin/env bash
# Quick local install for Classeviva GNOME
# Installs to ~/.local so no root needed.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="$HOME/.local"
APPDIR="$PREFIX/share/classeviva"
BINDIR="$PREFIX/bin"
DESKTOPDIR="$PREFIX/share/applications"
ICONDIR="$PREFIX/share/icons/hicolor/scalable/apps"

echo "==> Installazione dipendenze Python..."
pip install --user httpx keyring 2>/dev/null || true

echo "==> Copia file applicazione..."
mkdir -p "$APPDIR"
cp -r "$SCRIPT_DIR/src/"* "$APPDIR/"

echo "==> Creazione launcher..."
mkdir -p "$BINDIR"
cat > "$BINDIR/classeviva" << 'LAUNCHER'
#!/usr/bin/env bash
APPDIR="$HOME/.local/share/classeviva"
exec python3 "$APPDIR/main.py" "$@"
LAUNCHER
chmod +x "$BINDIR/classeviva"

echo "==> Installazione icona..."
mkdir -p "$ICONDIR"
# Create a simple SVG icon if none exists
cat > "$ICONDIR/it.example.Classeviva.svg" << 'SVGEOF'
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
  <rect width="64" height="64" rx="12" fill="#3584e4"/>
  <text x="32" y="44" font-family="sans-serif" font-weight="bold" font-size="32"
        text-anchor="middle" fill="white">C</text>
</svg>
SVGEOF

echo "==> Installazione voce desktop..."
mkdir -p "$DESKTOPDIR"
cat > "$DESKTOPDIR/it.example.Classeviva.desktop" << DESKTOPEOF
[Desktop Entry]
Name=Classeviva
GenericName=Registro Elettronico
Comment=Accedi al registro elettronico Spaggiari Classeviva
Exec=$BINDIR/classeviva
Icon=it.example.Classeviva
Terminal=false
Type=Application
Categories=Education;Network;
StartupNotify=true
StartupWMClass=classeviva
Keywords=scuola;registro;voti;assenze;
DESKTOPEOF

echo "==> Aggiornamento database icone e applicazioni..."
update-desktop-database "$DESKTOPDIR" 2>/dev/null || true
gtk-update-icon-cache -f -t "$PREFIX/share/icons/hicolor" 2>/dev/null || true

echo ""
echo "✓ Classeviva installato!"
echo "  Avvia con: classeviva"
echo "  Oppure cerca 'Classeviva' nel launcher applicazioni."
echo ""
echo "  Per disinstallare:"
echo "    rm -rf ~/.local/share/classeviva"
echo "    rm ~/.local/bin/classeviva"
echo "    rm ~/.local/share/applications/it.example.Classeviva.desktop"
echo "    rm ~/.local/share/icons/hicolor/scalable/apps/it.example.Classeviva.svg"
