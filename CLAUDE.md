# Classeviva GNOME — Istruzioni per Claude Code

## Obiettivo
App Linux nativa in stile GNOME per il registro elettronico Classeviva (Spaggiari).

## Stack
- Python 3.11+
- GTK4 + libadwaita (AdwApplicationWindow, AdwNavigationView, AdwPreferencesPage, ecc.)
- httpx per le chiamate HTTP
- keyring per il salvataggio sicuro delle credenziali
- Meson come build system
- Flatpak per la distribuzione

## API Reference
- Base URL: https://web.spaggiari.eu/rest/v1
- Headers obbligatori: `User-Agent: zorro/1.0`, `Z-Dev-ApiKey: +zorro+`
- Login: POST /auth/login → restituisce token da usare in Z-Auth-Token
- Voti: GET /students/{id}/grades
- Assenze: GET /students/{id}/absences/details
- Agenda: GET /students/{id}/agenda/all/{YYYYMMDD}/{YYYYMMDD}
- Bacheca: GET /students/{id}/noticeboard
- Didattica: GET /students/{id}/didactics

## Struttura progetto
Segui la struttura src/ con api/, views/, widgets/ separati.
Usa GLib.idle_add() per aggiornare la UI dai thread.
Usa threading.Thread(daemon=True) per le chiamate di rete.

## Stile GNOME
- Segui le GNOME HIG (Human Interface Guidelines)
- Usa AdwToast per i feedback, non i dialoghi
- Lista con css_class "boxed-list"
- Usa AdwStatusPage per stati vuoti/errori/caricamento
- Dark mode automatica tramite AdwStyleManager
