# HANDOVER – MeshCore Responder Station

Letztes Update: 2026-06-12

## Aktueller Stand

Projekt ist **funktionsfähig und läuft als Service** auf RpPiZeroW-001.

### Was funktioniert

- DM-Responder empfängt MeshCore-Nachrichten via RAK4631 und antwortet automatisch⏎
- SD-Card Logging schreibt CSV auf separate Daten-SD (MH-SD Modul, Raw PLOG-Format)⏎
- Flask Web-Server (Port 5000) läuft im gleichen Prozess (Threading)⏎
- Mac-Auslese-Script liest Raw-SD direkt am Mac⏎
- systemd-Service startet alles automatisch beim Boot

### Offene Punkte / bekannte Einschränkungen
⏎
- CSS im Web-Interface: Inline-Styles (kein externer Stylesheet)
- IP-Adresse hat sich geändert: dokumentiert 10.0.1.165, tatsächlich **10.0.1.191**
- `sd_server.py` hat noch die alte IP im Print-Statement (kosmetisch)
- Service-File im Repo hat User `paul-rppi` hardcoded
- Flood-Advert-Intervall: 12h (anpassbar in dm_listener.py Zeile 13)

## Hardware-Setup

| Komponente | Detail |
|---|---|
| Pi | Raspberry Pi Zero 2 W (RpPiZeroW-001) |
| OS | Raspberry Pi OS 13 (Trixie) |
| IP | 10.0.1.191 (kann sich ändern!) |
| Hostname | RpPiZeroW-001 |
| User | paul-rppi |
| LoRa-Node | RAK4631 via USB → /dev/ttyACM0 |
| SD-Modul | MH-SD Card Module (SPI, CS=GPIO25) |
| RTC | DS1307 (I2C) |
| Strom | Solarpanel + Akku via Steckverbindung |

### SPI-Verkabelung MH-SD

| Pi Pin | GPIO | MH-SD |
|---|---|---|
| 17 | 3.3V | 3V3 |
| 6 | GND | GND |
| 22 | GPIO25 | CS |
| 19 | GPIO10 | MOSI |
| 21 | GPIO9 | MISO |
| 23 | GPIO11 | SCK |

> WICHTIG: Nur 3.3V verwenden! Das "Micro SD Card Adapter"-Modul
> (mit Pegelwandler) funktioniert NICHT zuverlässig an 3.3V.
> Nur das **MH-SD Card Module** verwenden!

## Dateistruktur auf dem Pi

```
/home/paul-rppi/
├── dm_listener.py          # Hauptprogramm (Responder + SD + Web)
├── sdcard_writer.py        # Raw SD-Card Writer Klasse
├── sd_server.py            # Flask (wird von dm_listener importiert)
└── sd_reader.py            # Liegt auch am Mac: ~/Scripts/sd_reader.py
```

## Service

```bash
sudo systemctl status dm-responder.service   # Status
sudo systemctl restart dm-responder.service  # Neustart
sudo systemctl stop dm-responder.service     # Stoppen
journalctl -u dm-responder.service -f        # Live-Log
```

## Zugriff auf Daten

| Weg | Wie |
|---|---|
| Browser | http://10.0.1.191:5000 |
| API | curl http://10.0.1.191:5000/api/file/DMLOG.CSV |
| Mac-Script | sudo python3 ~/Scripts/sd_reader.py --all |

## Wichtige Erkenntnisse aus der Entwicklung

1. **MH-SD Modul** ist Pflicht – Micro SD Card Adapter (Pegelwandler) instabil bei 3.3V
2. **GPIO-Konflikt:** Nur EIN Prozess darf GPIO25 belegen → Flask als Thread im dm_listener
3. **SD Init:** Mit MH-SD Modul reicht 1 Zyklus (kein Retry nötig)
4. **PLOG-Format:** Raw Blocks, kein Dateisystem, 6 Slots à 10 Mio Blöcke
5. **Superblock:** Block 0 + Backup Block 1, Magic "PLOG"

## Kontext für neuen Chat

- Repo: https://github.com/Paul-3400/meshcore-responder-station
- Paul arbeitet via SSH (RemoteShell) auf dem Pi, Editor: nano -lmi
- Mac: MacBook Air M2, macOS 26.4.1
- Weitere Projekte: meshcore-duty-cycle-observer, meshcore-duty-cycle-dashboard,
  meshcore-standort-evaluator
- Infrastruktur-Dok: Separat vorhanden (PDF)

## Mögliche nächste Schritte

- [ ] IP-Adresse dynamisch ermitteln (statt hardcoded in Print)
- [ ] Web-Interface: Auto-Refresh / Live-Counter
- [ ] Zweite CSV-Datei (PACKETS.CSV) für empfangene Adverts
- [ ] SD-Karte "formatieren" Funktion (alle Slots löschen)
- [ ] Infrastruktur-Dok aktualisieren (IP, MH-SD, RAK4631)
