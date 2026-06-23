# MeshCore Responder-Station v2.3

Ein autonomer Field Access Point fuer das MeshCore LoRa-Mesh-Netzwerk.

Empfaengt DMs, antwortet automatisch mit Umweltdaten (Temperatur, Luftfeuchtigkeit,
Luftdruck, Taupunkt), loggt Channel-Nachrichten, exportiert Kontakte und bietet
ein Web-Dashboard mit Login-geschuetzter Konfiguration.

Built as a "brain gym" project - keeping the mind sharp through electronics and code.
by Paul and Claude, Anthropic 2026

---

## Inhaltsverzeichnis

1. Features
2. Hardware
3. Software-Voraussetzungen
4. Installation
5. Konfiguration
6. Services einrichten
7. Web-Dashboard
8. Hotspot-Steuerung
9. Dateistruktur
10. Befehlsverzeichnis
11. Troubleshooting
12. Bekannte Eigenheiten
13. Lizenz

---

## 1. Features

- Auto-Reply: Antwortet auf DMs mit konfigurierbarem Template inkl. Umweltdaten und Signalinfo
- Umweltsensor: BME280 + BMP280 via I2C - Temperatur, Luftfeuchtigkeit, QNH-Druck, Taupunkt
- Channel-Logging: Zeichnet alle Channel-Nachrichten in CSV auf
- Kontakt-Export: Exportiert beim Boot alle bekannten Nodes in CSV
- Web-Dashboard: Flask-basiert mit System-Status, DMs, Channels, Kontakte, Umweltdaten
- Web-Konfiguration: Login-geschuetzte Konfigurationsseite fuer station.conf
- Hotspot-Toggle: GPIO-Taster schaltet WLAN-Hotspot ein (90 Min Timeout)
- Filesystem-Speicher: CSV-Dateien im Dateisystem (kein SD-Karten-Verschleiss)
- Autarker Betrieb: Solarpanel + Akku, kein Netzstrom noetig

---

## 2. Hardware

### Benoetigte Komponenten

- Raspberry Pi Zero W (rev 1.1, 512 MB, armv6l, WLAN onboard)
- MeshCore-Radio: Heltec V3 oder RAK4631 (via USB an Pi)
- Umweltsensor: BME280 + BMP280 (I2C, Adresse 0x76 / 0x77)
- Taster: Momentary Push Button, GPIO17 (Pin 11) nach GND
- Status-LED: Standard-LED mit 330 Ohm Vorwiderstand, GPIO27 (Pin 13)
- Stromversorgung: Solarpanel + LiPo + Laderegler (5V USB-Ausgang)
- USB-Kabel: USB-A auf Micro-USB + USB-C (Pi zu Radio)

### GPIO-Belegung

    Pin 11 (GPIO17) --- Taster --- GND (Pin 9)
    Pin 13 (GPIO27) --- 330 Ohm --- LED --- GND (Pin 14)

### I2C-Sensoren

    Pin 1  (3.3V)  -> VCC (BME280 + BMP280)
    Pin 3  (SDA)   -> SDA
    Pin 5  (SCL)   -> SCL
    Pin 6  (GND)   -> GND

---

## 3. Software-Voraussetzungen

- Raspberry Pi OS 13 (Trixie), Kernel: armv6l
- Python 3.11+
- MeshCore-Radio mit aktueller Firmware

### Python-Pakete installieren

    sudo apt update
    sudo apt install -y python3-pip python3-venv i2c-tools
    pip3 install flask gpiozero bcrypt meshcore_py smbus2

### I2C aktivieren

    sudo raspi-config
    # -> Interface Options -> I2C -> Enable

    # Pruefen ob Sensoren erkannt werden:
    i2cdetect -y 1
    # Erwartete Adressen: 0x76 (BME280) und/oder 0x77 (BMP280)

---

## 4. Installation

### Repository klonen

    cd /home/paul-rppi
    git clone https://github.com/Paul-3400/meshcore-responder-station.git meshcore-responder
    cd meshcore-responder

### Verzeichnisse anlegen

    mkdir -p static
    mkdir -p data

---

## 5. Konfiguration

### station.conf

Die zentrale Konfigurationsdatei. Editierbar manuell oder ueber Web-Dashboard.

    nano -lmi /home/paul-rppi/meshcore-responder/station.conf

Beispielinhalt:

    [station]
    name = MeinCallsign-Station
    callsign = HB9XXX
    qth = JN47AB
    altitude = 554
    lat = 46.9480
    lon = 7.4474

    [reply]
    template = Hallo {sender}! Station {name} ({callsign}) QTH:{qth} {alt}m | {date} {time} | Signal: {signal} | Env: T={temp}C H={hum}% P={pressure}hPa TP={dewpoint}C

    [sensor]
    env_interval = 12

### Template-Variablen

- {sender}    - Name des Absenders
- {name}      - Stationsname
- {callsign}  - Amateurfunk-Rufzeichen
- {qth}       - Maidenhead Locator (6 Zeichen)
- {alt}       - Hoehe in Metern
- {date}      - Aktuelles Datum
- {time}      - Aktuelle Uhrzeit
- {signal}    - SNR/RSSI/Noise Floor der empfangenen DM
- {temp}      - Temperatur (Grad C)
- {hum}       - Luftfeuchtigkeit (%)
- {pressure}  - QNH-Luftdruck (hPa)
- {dewpoint}  - Taupunkt (Grad C)

### auth.conf

Wird beim ersten Start automatisch erstellt.
Standard-Login: admin / admin
Pfad: /home/paul-rppi/meshcore-responder/auth.conf

WICHTIG: Beim ersten Login sofort das Passwort aendern!

---

## 6. Services einrichten

### dm-responder.service (Hauptprogramm)

    sudo nano -lmi /etc/systemd/system/dm-responder.service

Inhalt:

    [Unit]
    Description=MeshCore DM Responder + Web Dashboard
    After=network.target

    [Service]
    Type=simple
    ExecStart=/usr/bin/python3 -u /home/paul-rppi/meshcore-responder/dm_listener.py
    WorkingDirectory=/home/paul-rppi/meshcore-responder
    Restart=on-failure
    RestartSec=10
    StandardOutput=journal
    StandardError=journal

    [Install]
    WantedBy=multi-user.target

### hotspot-toggle.service (Hotspot-Taster)

    sudo nano -lmi /etc/systemd/system/hotspot-toggle.service

Inhalt:

    [Unit]
    Description=Hotspot Toggle Button (GPIO17)
    After=multi-user.target

    [Service]
    Type=simple
    ExecStart=/usr/bin/python3 -u /home/paul-rppi/meshcore-responder/hotspot_button.py
    WorkingDirectory=/home/paul-rppi/meshcore-responder
    Restart=on-failure
    RestartSec=5

    [Install]
    WantedBy=multi-user.target

### Services aktivieren und starten

    sudo systemctl daemon-reload
    sudo systemctl enable dm-responder.service
    sudo systemctl enable hotspot-toggle.service
    sudo systemctl start dm-responder.service
    sudo systemctl start hotspot-toggle.service

---

## 7. Web-Dashboard

Nach dem Start von dm-responder erreichbar unter:

    http://<PI-IP>:5000

Beispiel: http://10.0.1.167:5000

### Seiten (ohne Login)

- /              - Dashboard (System-Status, Radio-Status)
- /messages      - Empfangene DMs (Tabelle + CSV-Download)
- /channels      - Channel-Nachrichten (Tabelle + CSV-Download)
- /contacts      - Kontakte/Nodes (Boot-Export)
- /environment   - Umweltdaten (aktuelle Messung + Historie)
- /login         - Login-Seite

### Seiten (mit Login)

- /config            - Station-Konfiguration bearbeiten
- /change-password   - Passwort aendern
- /restart           - Service neu starten (POST)
- /logout            - Abmelden

### API

- /api/status        - JSON mit System-Status

### Downloads und Loeschen

- /download/DMLOG.CSV       - DM-Log herunterladen
- /download/CHANNELS.CSV    - Channel-Log herunterladen
- /download/CONTACTS.CSV    - Kontakte herunterladen
- /download/ENVLOG.CSV      - Umweltdaten herunterladen
- /delete/<filename> (POST) - CSV loeschen und mit Header neu anlegen

### Validierung (Config-Seite)

- QTH: genau 6 Zeichen (Maidenhead Locator)
- Hoehe: 0 bis 4500 m
- Breitengrad: 45.0 bis 48.0 (Schweiz)
- Laengengrad: 5.5 bis 10.5 (Schweiz)
- Messintervall: 1 bis 60 Minuten

---

## 8. Hotspot-Steuerung

### Funktionsweise

Der Pi Zero W hat nur ein WLAN-Interface (wlan0). Der Hotspot-Modus
unterbricht die regulaere WLAN-Verbindung.

- Taster 1x druecken: Hotspot EIN, LED AN, Timer 90 Min laeuft
- Taster nochmal druecken: Hotspot sofort AUS, LED AUS
- Nach 90 Minuten: Hotspot automatisch AUS, LED AUS

### WLAN-Reconnect nach Hotspot-Abschaltung

Nach Abschaltung des Hotspots wird NetworkManager neu gestartet, um die
Client-WLAN-Verbindung wiederherzustellen. Dies dauert einige Sekunden
(ca. 5-15s). Waehrend dieser Zeit ist der Pi nicht erreichbar.
Die LED erlischt sofort bei Abschaltung, die Netzwerkverbindung folgt
kurz darauf.

### Hotspot-Netzwerk konfigurieren

Die Hotspot-Konfiguration erfolgt ueber hostapd und dnsmasq:

    sudo nano -lmi /etc/hostapd/hostapd.conf
    sudo nano -lmi /etc/dnsmasq.conf

---

## 9. Dateistruktur

    meshcore-responder/
    ├── dm_listener.py          # Hauptprogramm (DM-Responder + Sensor-Loop)
    ├── sd_server.py            # Flask-Webserver (Dashboard + Config)
    ├── hotspot_button.py       # GPIO-Taster fuer Hotspot-Steuerung
    ├── file_store.py           # Filesystem-Abstraktionsschicht
    ├── auth.py                 # Authentifizierung (bcrypt, Sessions)
    ├── station.conf            # Stationskonfiguration
    ├── auth.conf               # Login-Credentials (auto-generiert)
    ├── static/
    │   └── style.css           # CSS fuer Web-Dashboard
    ├── data/
    │   ├── DMLOG.CSV           # Empfangene DMs
    │   ├── CHANNELS.CSV        # Channel-Nachrichten
    │   ├── CONTACTS.CSV        # Kontakt-Export (Boot)
    │   └── ENVLOG.CSV          # Umweltmessungen
    ├── README.md               # Diese Datei
    └── HANDOVER.md             # Session-Uebergabe fuer Weiterarbeit

---

## 10. Befehlsverzeichnis

### Service-Steuerung

    sudo systemctl start dm-responder       # Hauptprogramm starten
    sudo systemctl stop dm-responder        # Hauptprogramm stoppen
    sudo systemctl restart dm-responder     # Hauptprogramm neu starten
    sudo systemctl status dm-responder      # Status anzeigen
    sudo systemctl start hotspot-toggle     # Hotspot-Service starten
    sudo systemctl stop hotspot-toggle      # Hotspot-Service stoppen
    sudo systemctl status hotspot-toggle    # Status anzeigen

### Logs anzeigen

    sudo journalctl -u dm-responder -f              # Live-Log Hauptprogramm
    sudo journalctl -u dm-responder --no-pager -n 50  # Letzte 50 Zeilen
    sudo journalctl -u hotspot-toggle -f            # Live-Log Hotspot

### Konfiguration bearbeiten

    nano -lmi /home/paul-rppi/meshcore-responder/station.conf
    nano -lmi /home/paul-rppi/meshcore-responder/static/style.css

### Hardware-Diagnose

    i2cdetect -y 1                  # I2C-Sensoren erkennen
    vcgencmd measure_temp           # CPU-Temperatur
    hostname -I                     # IP-Adressen anzeigen
    cat /proc/uptime                # Uptime in Sekunden
    ls /dev/ttyACM*                 # USB-Serial (MeshCore Radio)

### WLAN und Netzwerk

    iwconfig wlan0                  # WLAN-Status
    nmcli connection show           # NetworkManager Verbindungen
    sudo systemctl restart NetworkManager  # WLAN neu verbinden
    pgrep -x hostapd                # Hotspot-Prozess pruefen

### GPIO-Diagnose

    pinctrl get 17                  # GPIO17 Status (Taster)
    pinctrl get 27                  # GPIO27 Status (LED)
    python3 -c "from gpiozero import Button; print('OK')"  # gpiozero Test

### Dateien verwalten

    cat /home/paul-rppi/meshcore-responder/data/DMLOG.CSV      # DMs anzeigen
    cat /home/paul-rppi/meshcore-responder/data/ENVLOG.CSV     # Umweltdaten
    wc -l /home/paul-rppi/meshcore-responder/data/*.CSV        # Zeilenanzahl

### Backup und Download (auf Mac)

    scp paul-rppi@10.0.1.167:/home/paul-rppi/meshcore-responder/data/*.CSV ~/Desktop/
    scp paul-rppi@10.0.1.167:/home/paul-rppi/meshcore-responder/station.conf ~/Desktop/

### System

    df -h                           # Speicherplatz
    free -m                         # RAM-Nutzung
    uptime                          # Laufzeit + Load
    sudo reboot                     # Neustart
    sudo shutdown -h now            # Herunterfahren

---

## 11. Troubleshooting

### Radio wird nicht erkannt

    ls /dev/ttyACM*
    # Falls leer: USB-Kabel pruefen, Radio neu starten
    # Falls /dev/ttyACM0 vorhanden: Service neu starten

### Sensoren liefern keine Daten

    i2cdetect -y 1
    # Falls keine Adressen: Verkabelung pruefen (SDA/SCL)
    # Falls 0x76/0x77 sichtbar: Python-Library pruefen

### Web-Dashboard nicht erreichbar

    sudo systemctl status dm-responder
    # Falls "failed": Logs pruefen
    sudo journalctl -u dm-responder --no-pager -n 20
    # Haeufige Ursache: Port 5000 belegt oder Import-Fehler

### GPIO busy (Hotspot-Taster)

    ps aux | grep hotspot
    # Falls alter Prozess laeuft: killen
    sudo kill <PID>
    # Dann neuen Service starten
    sudo systemctl restart hotspot-toggle

### Pi nach Hotspot nicht erreichbar

    # Warten (15-30 Sekunden fuer NetworkManager Reconnect)
    # Falls weiterhin offline: Strom trennen und neu booten

---

## 12. Bekannte Eigenheiten

1. WLAN-Reconnect nach Hotspot: Dauert 5-15 Sekunden. Pi ist in dieser
   Zeit nicht erreichbar. LED erlischt sofort, Netzwerk folgt.

2. Session-Key: Wird bei jedem Service-Restart neu generiert
   (os.urandom). Bestehende Web-Sessions werden dabei ungueltig
   (erneutes Login noetig).

3. CSV-Dateien: Wachsen unbegrenzt. Regelmaessig ueber Dashboard
   herunterladen und loeschen.

4. Sensor-Intervall: Aenderungen ueber Web-Config greifen beim
   naechsten Messzyklus (ohne Service-Restart).

5. Autarker Betrieb: Bei zu wenig Sonne kann der Akku leer werden.
   Das System startet nach Stromrueckkehr automatisch.

---

## 13. Lizenz

Open Source - MIT License
Repo: https://github.com/Paul-3400/meshcore-responder-station
