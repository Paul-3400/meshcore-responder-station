# HANDOVER – MeshCore Responder-Station v2.3

Built as a "brain gym" project – keeping the mind sharp through electronics and code. 🧠💪
by Paul and Claude, Anthropic 2026

## Session: 26. Juni 2026

### Behobene Bugs

| # | Problem | Ursache | Fix |
|---|---------|---------|-----|
| 1 | Hotspot startet beim Boot | hostapd.service enabled | `sudo systemctl disable hostapd` |
| 2 | Pi verbindet nicht mit Home-WLAN | WLAN-Profil "RoPa Net" fehlte | `RoPaNet.nmconnection` manuell erstellt |
| 3 | hostapd via systemctl funktioniert nicht | Trixie-Bug, DAEMON_CONF leer | hostapd direkt via subprocess.Popen starten |
| 4 | /change-password → 500 Error | Argument-Mismatch in sd_server.py | `auth.change_password(new_pw)` statt 2 Argumente |

### Geänderte Dateien

| Datei | Änderung |
|-------|----------|
| `hotspot_button.py` | hostapd via Popen starten, pkill zum Stoppen, NM stop/start |
| `sd_server.py` | Zeile 204: `auth.change_password(new_pw)` (username entfernt) |
| `/etc/NetworkManager/system-connections/RoPaNet.nmconnection` | NEU erstellt |
| `/etc/default/hostapd` | DAEMON_CONF gesetzt (dokumentiert) |

### Aktueller Zustand

- ✅ Boot → verbindet automatisch mit RoPa Net (10.0.1.167)
- ✅ Taster → Hotspot EIN (SSID: Responder-Station, 10.0.50.1)
- ✅ Taster → Hotspot AUS → zurück zu RoPa Net
- ✅ 90-Min-Timeout funktioniert
- ✅ Dashboard erreichbar (beide Netzwerke)
- ✅ MeshCore Radio verbunden (/dev/ttyACM0)
- ✅ /change-password funktioniert
- ✅ hostapd.service disabled
- ✅ GitHub Repo aktualisiert

### Keine offenen Punkte 🎉

### Netzwerk-Zugang

| Modus | IP | Zugang |
|-------|-----|--------|
| Lokal (RoPa Net) | 10.0.1.167 | SSH, Dashboard :5000 |
| Field (Hotspot) | 10.0.50.1 | SSH, Dashboard :5000 |

### Hotspot-Zugangsdaten

- SSID: Responder-Station
- Passwort: MeshField2026 (WPA2-PSK)

### Wichtiger Hinweis (Trixie-Bug)

Der hostapd systemd-Service funktioniert unter Raspberry Pi OS 13 (Trixie)
nicht korrekt. hostapd wird daher direkt als Prozess gestartet/gestoppt
(subprocess.Popen / pkill). Dies ist ein dokumentierter Workaround.

### Services

| Service | Funktion |
|---------|----------|
| `dm-responder.service` | Flask Dashboard + MeshCore Radio |
| `hotspot-toggle.service` | Taster-Steuerung für Hotspot |
| `NetworkManager` | WLAN-Client (RoPa Net) |
