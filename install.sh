#!/usr/bin/env bash
# Quick local install for LinuxViva (no root needed)

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="$HOME/.local"
APP_ID="io.github.giomarco2107.LinuxViva"
APPDIR="$PREFIX/share/$APP_ID"
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
cat > "$BINDIR/linuxviva" << LAUNCHER
#!/usr/bin/env bash
APPDIR="$APPDIR"
exec python3 "\$APPDIR/main.py" "\$@"
LAUNCHER
chmod +x "$BINDIR/linuxviva"

echo "==> Installazione icona..."
mkdir -p "$ICONDIR"
cp "$SCRIPT_DIR/data/icons/hicolor/scalable/apps/$APP_ID.svg" "$ICONDIR/$APP_ID.svg"

echo "==> Installazione voce desktop..."
mkdir -p "$DESKTOPDIR"
cp "$SCRIPT_DIR/data/$APP_ID.desktop" "$DESKTOPDIR/$APP_ID.desktop"
# Update Exec path to point to installed launcher
sed -i "s|^Exec=.*|Exec=$BINDIR/linuxviva|" "$DESKTOPDIR/$APP_ID.desktop"

echo "==> Aggiornamento database icone e applicazioni..."
update-desktop-database "$DESKTOPDIR" 2>/dev/null || true
gtk-update-icon-cache -f -t "$PREFIX/share/icons/hicolor" 2>/dev/null || true

echo ""
echo "✓ LinuxViva installato!"
echo "  Avvia con: linuxviva"
echo "  Oppure cerca 'LinuxViva' nel launcher applicazioni."
echo ""
echo "  Per disinstallare:"
echo "    rm -rf $APPDIR"
echo "    rm $BINDIR/linuxviva"
echo "    rm $DESKTOPDIR/$APP_ID.desktop"
echo "    rm $ICONDIR/$APP_ID.svg"
