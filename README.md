# MeshCore Responder Station

Eine autonome MeshCore-Station, die auf Direktnachrichten antwortet,
alle Kommunikation auf einer separaten SD-Karte protokolliert und
die Daten via Web-Interface oder physisch am Mac auslesbar macht.

## Features

- **Auto-Reply:** Beantwortet eingehende MeshCore-DMs automatisch
- **SD-Card Logging:** Schreibt CSV-Logs auf separate Daten-SD (Raw-Format, kein Dateisystem)
- **Web-Interface:** Flask-Server zum Auslesen via Browser (WLAN)
- **Mac-Auslese:** Python-Script liest die Raw-SD direkt am Mac
- **Schleifen-Schutz:** Erkennt eigene Antworten, Cooldown pro Kontakt
- **RTC-gestützt:** Korrekte Zeitstempel auch ohne Internet (DS1307)
- **Solar-autark:** Betrieb mit Solarpanel + Akku möglich
- **6 Datei-Slots:** Bis zu 6 CSV-Dateien à ~5 GB auf 32 GB SD-Karte

## Hardware

### Stückliste

| Komponente | Typ | Funktion |
|---|---|---|
| Einplatinencomputer | Raspberry Pi Zero 2 W | Hauptrechner |
| LoRa-Node | z.B. RAK 4631 | MeshCore-Radio via USB |
| SD-Karten-Modul | MH-SD Card Module | Daten-Speicher (SPI) |
| Echtzeituhr | DS1307 RTC Modul | Zeitstempel ohne Internet |
| SD-Karte (OS) | Micro-SD im Pi | Betriebssystem + Software |
| SD-Karte (Daten) | Micro-SD im MH-SD Modul | CSV-Logging |
| Stromversorgung | Solarpanel + Akku + Laderegler | Autarker Betrieb |

### Verkabelung MH-SD Card Module

| Pi Pin | GPIO | Funktion | MH-SD Pin |
|---|---|---|---|
| Pin 17 | 3.3V | Stromversorgung | 3V3 |
| Pin 6 | GND | Masse | GND |
| Pin 22 | GPIO25 | Chip Select (CS) | CS |
| Pin 19 | GPIO10 | MOSI | MOSI / DI |
| Pin 21 | GPIO9 | MISO | MISO / DO |
| Pin 23 | GPIO11 | SCK | SCK / CLK |

> **Wichtig:** Nur den 3.3V-Pin am MH-SD Modul verwenden, NICHT 5V!
> Das häufig verwendete "Micro SD Card Adapter"-Modul (mit Pegelwandler)
> funktioniert NICHT zuverlässig an 3.3V-Systemen.

### Verkabelung DS1307 RTC

| Pi Pin | GPIO | Funktion | RTC Pin |
|---|---|---|---|
| Pin 1 | 3.3V | Stromversorgung | VCC |
| Pin 9 | GND | Masse | GND |
| Pin 3 | GPIO2 | I2C SDA | SDA |
| Pin 5 | GPIO3 | I2C SCL | SCL |

### Verkabelung RAK 4631

Direkt via USB-C an den Pi angeschlossen (erscheint als `/dev/ttyACM0`).

### Gehäuse-Aufbau

```
┌─────────────────────────────────────┐
│  Gehäuse                            │
│                                     │
│  ┌─────────────┐  ┌─────────┐       │
│  │ Pi Zero 2W  │  │  RTC    │       │
│  │ (OS + Apps) │  │ DS1307  │       │
│  └──────┬──────┘  └────-────┘       │
│     USB │          I2C / SPI        │
│  ┌──────┴──┐      ┌────-────┐       │
│  │ RAK4631 │      │  MH-SD  │       │
│  │         │      │ (Daten) │       │
│  └─────────┘      └─────────┘       │
│                                     │
│  ═══════╤═══════  Steckverbindung   │
└─────────┼───────────────────────────┘
          │
    ┌─────┴─────┐
    │ Solarpanel│
    │  + Akku   │
    └───────────┘
```

## Software-Setup

### Voraussetzungen

- Raspberry Pi OS 13 (Trixie) oder neuer
- Python 3.13+
- SPI aktiviert (`sudo raspi-config` → Interface Options → SPI → Enable)
- I2C aktiviert (für RTC)
- MeshCore-Firmware auf RAK 4631  (868 MHz EU/Narrow)

### 1. Repository klonen

```bash
cd ~
git clone https://github.com/Paul-3400/meshcore-responder-station.git
cd meshcore-responder-station
```

### 2. Abhängigkeiten installieren

```bash
pip install -r requirements.txt
```

### 3. Symlinks erstellen (damit Scripts direkt im Home liegen)

```bash
ln -sf ~/meshcore-responder-station/dm_listener.py ~/dm_listener.py
ln -sf ~/meshcore-responder-station/sdcard_writer.py ~/sdcard_writer.py
ln -sf ~/meshcore-responder-station/sd_server.py ~/sd_server.py
```

### 4. Service installieren

```bash
sudo cp dm-responder.service /etc/systemd/system/⏎
sudo systemctl daemon-reload⏎
sudo systemctl enable dm-responder.service⏎
sudo systemctl start dm-responder.service⏎
```

### 5. Status prüfen

```bash
sudo systemctl status dm-responder.service
```

## Konfiguration

Alle Parameter stehen am Anfang von `dm_listener.py`:

| Parameter | Default | Beschreibung |
|---|---|---|
| `PORT` | `/dev/ttyACM0` | Serieller Port zum RAK4631 |
| `ADVERT_INTERVAL` | `12 * 60 * 60` | Flood-Advert alle 12 Stunden |
| `REPLY_TEMPLATE` | `"RX OK: {nachricht} [via {path}, {hops} hops]"` | Antwort-Format |
| `REPLY_PREFIX` | `"RX OK:"` | Eigene Antworten erkennen |
| `COOLDOWN_SECONDS` | `30` | Min. Sekunden zwischen Antworten pro Kontakt |
| `CSV_FILENAME` | `"DMLOG.CSV"` | Dateiname auf der Daten-SD |

## Betrieb

### Service starten/stoppen

```bash
sudo systemctl start dm-responder.service
sudo systemctl stop dm-responder.service
sudo systemctl restart dm-responder.service
```

### Logs anzeigen

```bash
journalctl -u dm-responder.service -f
```

### Manuell starten (zum Debuggen)⏎

```bash
sudo systemctl stop dm-responder.service
python3 ~/dm_listener.py
```

## Daten auslesen

### Variante 1: Web-Interface (via WLAN)

Der Flask-Server startet autotatisch mit dem dm_listener.

```
http://<PI-IP>:5000
```

Funktionen:
- Status-Übersicht aller Dateien
- Dateiinhalt im Browser anzeigen
- CSV-Download
- JSON-API (`/api/status`, `/api/file/DATEINAME`)

### Variante 2: SD-Karte am Mac auslesen

1. Service stoppen: `sudo systemctl stop dm-responder.service`
2. Daten-SD aus dem MH-SD Modul entnehmen⏎
3. Am Mac einstecken
4. Script ausführen:

```bash
# Status anzeigen
sudo python3 sd_reader.py

# Einzelne Datei ausgeben
sudo python3 sd_reader.py DMLOG.CSV

# Datei lokal speichern⏎
sudo python3 sd_reader.py DMLOG.CSV -o⏎

# Alle Dateien exportieren
sudo python3 sd_reader.py --all
```

> **Hinweis:** `sudo` ist nötig, da die SD-Karte kein Dateisystem hat
> und als Raw-Block-Device gelesen wird.

### Variante 3: Flask standalone (ohne dm_listener)

Falls nur der Web-Server gebraucht wird:

```bash
python3 ~/sd_server.py
```

## SD-Karten-Format (PLOG)

Die Daten-SD verwendet ein eigenes Raw-Block-Format ohne Dateisystem:

### Superblock (Block 0 + Backup Block 1)

```
Offset  Länge  Inhalt
0       4      Magic "PLOG"
4       2      Version (1)
6       2      Anzahl Slots (6)
8       8      Reserved
16+     48     Slot 0 Descriptor
64+     48     Slot 1 Descriptor
...
```
⏎
### Slot Descriptor (48 Bytes)

```
Offset  Länge  Inhalt
0       16     Dateiname (ASCII, null-terminiert)
16      4      Start-Block
20      4      Max-Blöcke
24      4      Aktueller Block (Schreibposition)
28      4      Byte-Offset im aktuellen Block
32      4      Dateigrösse (Low 32-Bit)
36      4      Dateigrösse (High 32-Bit)
40      8      Reserved
```

### Speicheraufteilung (32 GB Karte)

| Bereich | Blöcke | Start-Block | Grösse |
|---|---|---|---|
| Admin | 0-99 | 0 | ~50 KB |
| Slot 0 | 100 - 10.000.099 | 100 | ~5 GB |
| Slot 1 | 10.000.100 - 20.000.099 | 10.000.100 | ~5 GB |
| Slot 2 | 20.000.100 - 30.000.099 | 20.000.100 | ~5 GB |
| Slot 3 | 30.000.100 - 40.000.099 | 30.000.100 | ~5 GB |
| Slot 4 | 40.000.100 - 50.000.099 | 40.000.100 | ~5 GB |
| Slot 5 | 50.000.100 - 60.000.099 | 50.000.100 | ~5 GB |

## CSV-Format

### DMLOG.CSV

```csv
timestamp,sender_name,sender_key,text,path,hops,status
2026-06-11 10:00:15,TestUser,abc123def456,Hallo Welt,direct,0,replied
2026-06-11 10:01:22,Paul,789abc012def,Test Nachricht,via_xy,1,replied
```

| Feld | Beschreibung |
|---|---|
| timestamp | Zeitpunkt des Empfangs (RTC) |
| sender_name | Name des Absenders |
| sender_key | Public Key (hex, erste 16 Zeichen) |
| text | Nachrichteninhalt |
| path | Routing-Pfad (hex) oder "direct" |
| hops | Anzahl Hops |
| status | "replied" oder "skipped" |

## Architektur

```
┌────────────────────────────────────────────────────┐
│  dm_listener.py (Hauptprozess)                     │
│                                                    │
│  ┌──────────────┐  ┌────────────┐   ┌───────────┐  │
│  │ MeshCore     │  │ SDCard     │   │ Flask     │  │
│  │ Event-Loop   │  │ Writer     │   │ Web-Server│  │
│  │ (asyncio)    │  │ (SPI/GPIO) │   │ (Thread)  │  │
│  └──────┬───────┘  └──────┬─────┘   └─────┬─────┘  │
│         │                 │               │        │
│         │  ┌──────────────┴───────────────┘        │
│         │  │  Gemeinsame SD-Instanz                │
│         │  │                                       │
└─────────┼──┼───────────────────────────────────────┘
          │  │
    ┌─────┴──┴─────┐         ┌─────────────┐
    │ RAK4631      │         │ MH-SD Modul │
    │ (USB serial) │         │ (SPI GPIO25)│
    └──────────────┘         └─────────────┘
```

## Troubleshooting

### "GPIO busy" Fehler

Ein anderer Prozess belegt GPIO25:

```bash
sudo killall python3
sleep 2
sudo systemctl start dm-responder.service
```

### SD-Karte wird nicht erkannt

- Karte rausnehmen, 5 Sekunden warten, wieder einstecken
- Prüfen ob SPI aktiviert ist: `ls /dev/spidev0.0`
- Verkabelung prüfen (3.3V, nicht 5V!)

### Web-Interface nicht erreichbar

- Ist der Service aktiv? `sudo systemctl status dm-responder.service`
- Korrekte IP? `hostname -I`
- Port 5000 frei? `ss -tlnp | grep 5000`

### RAK4631 nicht erkannt

- USB-Kabel prüfen (muss Datenkabel sein, nicht nur Ladekabel)
- `ls /dev/ttyACM*` – erscheint ein Device?
- MeshCore-Firmware geflasht? https://flasher.meshcore.io/

### Mac: "Permission denied" beim SD-Lesen

```bash
sudo python3 sd_reader.py
```

Raw-Device-Zugriff braucht Root-Rechte.

## Lizenz

MIT License – siehe [LICENSE](LICENSE)

## Autor

Paul – [GitHub](https://github.com/Paul-3400) und myAI (Claude)

## Ressourcen

- MeshCore Home: https://meshcore.io/
- MeshCore Docs: https://docs.meshcore.io/
- MeshCore Flasher: https://flasher.meshcore.io/
