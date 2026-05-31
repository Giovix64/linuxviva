#!/usr/bin/env bash
# Disinstallazione di LinuxViva

set -e
PREFIX="$HOME/.local"
APP_ID="io.github.giomarco2107.LinuxViva"
APPDIR="$PREFIX/share/$APP_ID"
BINDIR="$PREFIX/bin"
DESKTOPDIR="$PREFIX/share/applications"
ICONDIR="$PREFIX/share/icons/hicolor/scalable/apps"

echo "==> Rimozione file applicazione..."
rm -rf "$APPDIR"

echo "==> Rimozione launcher..."
rm -f "$BINDIR/linuxviva"

echo "==> Rimozione voce desktop..."
rm -f "$DESKTOPDIR/$APP_ID.desktop"

echo "==> Rimozione icona..."
rm -f "$ICONDIR/$APP_ID.svg"

echo "==> Aggiornamento database icone e applicazioni..."
update-desktop-database "$DESKTOPDIR" 2>/dev/null || true
gtk-update-icon-cache -f -t "$PREFIX/share/icons/hicolor" 2>/dev/null || true

echo ""
echo "✓ LinuxViva disinstallato."
echo ""
echo "  Le credenziali salvate nel portachiavi di sistema non sono state rimosse."
echo "  Per rimuoverle manualmente usa: secret-tool clear service linuxviva"
