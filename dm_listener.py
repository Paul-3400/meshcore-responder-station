#!/usr/bin/env python3
"""
DM-Responder + Paket-Logger: RAK4631 als Daten-Reservoir.
Auto-Reply auf DMs mit Umweltdaten, Channel-Logging.
Erstellt von Paul (Brain Gym) mit Hilfe von Claude (Anthropic, 2025/2026).
Repo: https://github.com/Paul-3400/meshcore-responder-station
Version: 2.2 - Filesystem statt SD-Karte, neue Boot-Sequenz
"""
import asyncio
import time
from datetime import datetime, timezone
from meshcore import MeshCore, EventType
from threading import Thread
from sd_server import flask_app
import env_sensor
import file_store

PORT = "/dev/ttyACM0"
ADVERT_INTERVAL = 12 * 60 * 60  # 12 Stunden

# ============================================================
# Liest env_interval dynamisch aus station.conf (in Minuten)
# Gibt Sekunden zurueck. Fallback: 12 Minuten.
# ============================================================
def get_env_interval():
    """Liest Messintervall aus station.conf, gibt Sekunden zurueck."""
    try:
        with open(STATION_CONF_PATH, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('env_interval'):
                    value = line.split('=', 1)[1].strip()
                    minutes = int(value)
                    if 1 <= minutes <= 60:
                        return minutes * 60
    except (FileNotFoundError, ValueError):
        pass
    return 12 * 60  # Fallback: 12 Minuten


# ============================================================
# STATION-KONFIGURATION LADEN
# ============================================================
STATION_CONF_PATH = "/home/paul-rppi/meshcore-responder/station.conf"

def load_station_conf():
    """Liest station.conf und gibt Dictionary zurueck."""
    config = {}
    try:
        with open(STATION_CONF_PATH, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('#') or line.startswith('[') or '=' not in line:
                    continue
                key, value = line.split('=', 1)
                config[key.strip()] = value.strip()
    except FileNotFoundError:
        print(f"  \u26a0 station.conf nicht gefunden: {STATION_CONF_PATH}")
    return config

station_conf = load_station_conf()

# ============================================================
# ANTWORT-VORLAGE aus station.conf
# ============================================================
REPLY_TEMPLATE = station_conf.get(
    'template',
    '{sender} {qth} {alt}m {date} {time} {temp}C {hum}% {pressure}hPa TP{dewpoint}C 73 de {callsign}'
)
REPLY_MAX_LENGTH = int(station_conf.get('max_length', '150'))

# Station-Parameter
STATION_NAME = station_conf.get('name', 'Responder')
STATION_CALLSIGN = station_conf.get('callsign', 'HE9NOH')
STATION_QTH = station_conf.get('qth', 'JN37TB')
STATION_ALT = station_conf.get('altitude', '554')

# ============================================================
# SCHLEIFEN-SCHUTZ
# ============================================================
REPLY_PREFIX = STATION_QTH
COOLDOWN_SECONDS = 30
last_reply = {}

# ============================================================
# CSV DEFINITIONEN
# ============================================================
CSV_FILENAME = "DMLOG.CSV"
CSV_HEADER = "timestamp,sender_name,sender_key,text,path,hops,status,snr,rssi,noise_floor\n"

CHAN_CSV_FILENAME = "CHANNELS.CSV"
CHAN_CSV_HEADER = "timestamp,channel_idx,sender_name,text,path_len,txt_type\n"

CONTACTS_CSV_FILENAME = "CONTACTS.CSV"
CONTACTS_CSV_HEADER = "tstmp_snapshot,pubkey_prefix,node_name,node_type,lat,lon,path_hops,tstmp_last_advert,tstmp_lastmod\n"

ENV_CSV_FILENAME = "ENVLOG.CSV"
ENV_CSV_HEADER = "Timestamp,Temp_C,Humidity_%,Pressure_QNH_hPa,Dewpoint_C,Pressure_Station_hPa,Temp_BMP_C\n"

# ============================================================
# HILFSFUNKTIONEN
# ============================================================
def unix_to_iso(unix_ts):
    """Wandelt Unix-Timestamp in ISO-Format um (lokal).
    Gibt leeren String zurueck wenn Timestamp ungueltig (0 oder negativ).
    Beispiel: 1781652055 -> '2026-06-14 16:00:55'
    """
    if not unix_ts or unix_ts <= 0:
        return ""
    try:
        dt = datetime.fromtimestamp(unix_ts)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (OSError, ValueError):
        return ""

def parse_channel_sender(text):
    """Extrahiert Sender-Name und Nachricht aus Channel-Text.
    Channel-Messages haben Format: "nickname DeviceName: Nachricht"
    Falls kein ':' gefunden wird, ist sender unbekannt.
    """
    if ": " in text:
        parts = text.split(": ", 1)
        return parts[0].strip(), parts[1]
    else:
        return "unknown", text

def build_env_reply(sender_name, signal_snr=None, signal_rssi=None, signal_noise_floor=None):
    """Baut Auto-Reply mit aktuellen Umweltdaten zusammen."""
    m = env_sensor.get_last_measurement()
    if m is None:
        now = datetime.now()
        return f"{sender_name} {STATION_QTH} {STATION_ALT}m {now.strftime('%d.%m %H:%M')} no sensor 73 de {STATION_CALLSIGN}"

    # Signal-Block bauen
    if signal_snr is not None and signal_rssi is not None:
        signal_block = f"SNR {signal_snr:.1f}dB RSSI {signal_rssi}dBm "
    elif signal_snr is not None:
        signal_block = f"SNR {signal_snr:.1f}dB "
    else:
        signal_block = ""

    reply = REPLY_TEMPLATE.format(
        sender=sender_name,
        qth=STATION_QTH,
        alt=STATION_ALT,
        date=m['date_short'],
        time=m['time_short'],
        signal=signal_block,
        temp=m['temp'],
        hum=m['humidity'],
        pressure=m['pressure_qnh'],
        dewpoint=m['dewpoint'],
        callsign=STATION_CALLSIGN
    )

    if len(reply) > REPLY_MAX_LENGTH:
        reply = reply[:REPLY_MAX_LENGTH]
    return reply

async def send_flood_advert(meshcore):
    """Sendet ein Flood-Advert ins Mesh."""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"\U0001f4e1 [{ts}] Sende Flood-Advert...")
    result = await meshcore.commands.send_advert(flood=True)
    if result.type == EventType.ERROR:
        print(f"  \u274c Fehler: {result.payload}")
    else:
        print(f"  \u2705 Flood-Advert gesendet!")

async def advert_loop(meshcore):
    """Sendet alle 12 Stunden ein Flood-Advert."""
    while True:
        await asyncio.sleep(ADVERT_INTERVAL)
        await send_flood_advert(meshcore)

def get_path_info(contact):
    """Extrahiert Path-Info aus einem Kontakt-Dict."""
    out_path = contact.get("out_path", "")
    out_path_len = contact.get("out_path_len", -1)
    hash_mode = contact.get("out_path_hash_mode", 0)

    if out_path_len <= 0 or out_path == "":
        return "direct", 0
    else:
        hash_size = max(hash_mode + 1, 1)
        path_hex_len = out_path_len * hash_size * 2
        path_display = out_path[:path_hex_len]
        return path_display, out_path_len

# ============================================================
# UMWELTSENSOR-LOOP (Intervall aus station.conf)
# ============================================================
async def env_sensor_loop():
    """Misst alle 12 Minuten Umweltdaten und loggt ins Filesystem."""
    while True:
        try:
            m = env_sensor.update_measurement()
            ts = datetime.now().strftime("%H:%M:%S")
            print(f"\U0001f321 [{ts}] Env: T={m['temp']}\u00b0C H={m['humidity']}% "
                  f"P={m['pressure_qnh']}hPa TP={m['dewpoint']}\u00b0C")

            # Ins Filesystem loggen
            line = (f"{m['timestamp']},{m['temp']},{m['humidity']},"
                    f"{m['pressure_qnh']},{m['dewpoint']},"
                    f"{m['pressure_station']},{m['temp_bmp']}\n")
            try:
                file_store.append_to_file(ENV_CSV_FILENAME, line)
            except Exception as e:
                print(f"  \u26a0 Log Fehler (Env): {e}")

        except Exception as e:
            print(f"  \u274c Sensor-Fehler: {e}")

        await asyncio.sleep(get_env_interval())

# ============================================================
# BOOT: KONTAKTE EXPORTIEREN (einmalig)
# ============================================================
async def export_contacts_on_boot(meshcore):
    """Exportiert alle Kontakte vom RAK einmalig beim Boot in CONTACTS.CSV."""
    ts_label = datetime.now().strftime("%H:%M:%S")
    print(f"\U0001f4cb [{ts_label}] Kontakte exportieren (Boot)...")

    try:
        await meshcore.commands.get_contacts()
        snapshot_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        count = 0

        for key, contact in meshcore.contacts.items():
            name = contact.get("adv_name", "?")
            node_type = contact.get("type", "?")
            lat = contact.get("adv_lat", 0)
            lon = contact.get("adv_lon", 0)
            out_path_len = contact.get("out_path_len", -1)
            hops = out_path_len if out_path_len >= 0 else -1
            last_advert = contact.get("last_advert", 0)
            lastmod = contact.get("lastmod", 0)

            last_advert_iso = unix_to_iso(last_advert)
            lastmod_iso = unix_to_iso(lastmod)

            safe_name = name.replace(",", ";")
            line = (f"{snapshot_ts},{key[:12]},{safe_name},"
                    f"{node_type},{lat},{lon},{hops},"
                    f"{last_advert_iso},{lastmod_iso}\n")
            file_store.append_to_file(CONTACTS_CSV_FILENAME, line)
            count += 1

        print(f"  \u2705 {count} Kontakte exportiert.")
    except Exception as e:
        print(f"  \u274c Export-Fehler: {e}")

# ============================================================
# HAUPTPROGRAMM
# ============================================================
async def main():
    print("\U0001f680 DM-Responder v2.2 startet...")
    print(f"  Port: {PORT}")
    print(f"  Zeit: {datetime.now().strftime('%H:%M:%S')}")
    print(f"  Station: {STATION_NAME} ({STATION_CALLSIGN})")
    print(f"  QTH: {STATION_QTH} / {STATION_ALT}m")
    print(f"  Advert-Intervall: {ADVERT_INTERVAL // 3600}h")
    print(f"  Umweltmessung: alle {get_env_interval() // 60} Min")
    print(f"  Reply-Template: \"{REPLY_TEMPLATE}\"")
    print("-" * 50)

    # ============================================================
    # BOOT-SEQUENZ: Filesystem init, Backup, Reset
    # ============================================================
    print("\U0001f4c1 Filesystem initialisieren...")
    file_store.init_data_dir()

    # Alte CSVs sichern und neue mit Header anlegen
    file_store.backup_and_reset(CSV_FILENAME, CSV_HEADER)
    file_store.backup_and_reset(CHAN_CSV_FILENAME, CHAN_CSV_HEADER)
    file_store.backup_and_reset(CONTACTS_CSV_FILENAME, CONTACTS_CSV_HEADER)
    file_store.backup_and_reset(ENV_CSV_FILENAME, ENV_CSV_HEADER)
    print("  \u2705 CSVs bereit (alte Daten gesichert)")

    # ============================================================
    # MeshCore verbinden
    # ============================================================
    meshcore = await MeshCore.create_serial(PORT)

    # Kontakte vom RAK exportieren (einmalig)
    await export_contacts_on_boot(meshcore)

    # ============================================================
    # Erste Umweltmessung durchfuehren
    # ============================================================
    print("\U0001f321 Erste Umweltmessung...")
    try:
        m = env_sensor.update_measurement()
        print(f"  T={m['temp']}\u00b0C H={m['humidity']}% "
              f"P={m['pressure_qnh']}hPa TP={m['dewpoint']}\u00b0C")
        # Sofort loggen
        line = (f"{m['timestamp']},{m['temp']},{m['humidity']},"
                f"{m['pressure_qnh']},{m['dewpoint']},"
                f"{m['pressure_station']},{m['temp_bmp']}\n")
        file_store.append_to_file(ENV_CSV_FILENAME, line)
    except Exception as e:
        print(f"  \u26a0 Sensor-Fehler: {e}")

    # ============================================================
    # Web-Server starten (eigener Thread)
    # ============================================================
    web_thread = Thread(
        target=lambda: flask_app.run(host="0.0.0.0", port=5000, debug=False),
        daemon=True
    )
    web_thread.start()
    print(f"  Web-Server: http://10.0.1.167:5000")

    print(f"\u2705 Verbunden. {len(meshcore.contacts)} Kontakte auf dem RAK.")

    # ============================================================
    # EVENT-HANDLER als Closures
    # ============================================================
    async def handle_advert(event):
        """Advert empfangen -> Kontaktdaten vom RAK abrufen."""
        ts = datetime.now().strftime("%H:%M:%S")
        pub_key = event.payload.get("public_key", "")
        print(f"\U0001f4e8 [{ts}] Advert empfangen! Key: {pub_key[:16]}...")

        if pub_key:
            result = await meshcore.commands.get_contact_by_key(
                bytes.fromhex(pub_key)
            )
            if result.type == EventType.NEXT_CONTACT:
                contact = result.payload
                name = contact.get("adv_name", "?")
                ctype = contact.get("type", "?")
                lat = contact.get("adv_lat", 0)
                lon = contact.get("adv_lon", 0)
                path, hops = get_path_info(contact)

                print(f"  Name: {name}")
                print(f"  Typ: {ctype}")
                print(f"  Pos: {lat:.4f}, {lon:.4f}")
                print(f"  Path: {path} ({hops} hops)")

                meshcore.contacts[pub_key] = contact
                print(f"  \u2705 Kontakt '{name}' in lokaler Liste aktualisiert.")
            else:
                print(f"  \u26a0 RAK kennt Key nicht: {result.payload}")
        print()

    async def handle_channel_message(event):
        """Channel-Message empfangen -> in CHANNELS.CSV loggen."""
        ts = datetime.now().strftime("%H:%M:%S")
        data = event.payload
        channel_idx = data.get("channel_idx", 0)
        text = data.get("text", "")
        path_len = data.get("path_len", 0)
        txt_type = data.get("txt_type", 0)

        sender_name, message_text = parse_channel_sender(text)

        print(f"\U0001f4ac [{ts}] Channel[{channel_idx}] von: {sender_name}")
        print(f"  Text: {message_text[:60]}")
        print(f"  Path-Len: {path_len}")

        # In CSV loggen
        csv_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        safe_text = text.replace(",", ";")
        safe_sender = sender_name.replace(",", ";")
        line = (f"{csv_ts},{channel_idx},{safe_sender},"
                f"{safe_text},{path_len},{txt_type}\n")
        try:
            file_store.append_to_file(CHAN_CSV_FILENAME, line)
        except Exception as e:
            print(f"  \u26a0 Log Fehler (Channel): {e}")
        print()

    def log_to_file(sender_name, sender_key, text, path, hops, status, snr="", rssi="", noise_floor=""):
        """Schreibt eine Zeile ins DM-CSV."""
        try:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            safe_text = text.replace(",", ";")
            line = (f"{ts},{sender_name},{sender_key[:16]},"
                    f"{safe_text},{path},{hops},{status},{snr},{rssi},{noise_floor}\n")
            file_store.append_to_file(CSV_FILENAME, line)
        except Exception as e:
            print(f"  \u26a0 Log Fehler: {e}")

    async def handle_message(event):
        """Eingehende DM -> Auto-Reply mit Umweltdaten."""
        ts = datetime.now().strftime("%H:%M:%S")
        data = event.payload

        # Signal-Daten abfragen (SNR, RSSI, Noise Floor)
        signal_snr = None
        signal_rssi = None
        signal_noise_floor = None
        try:
            stats = await meshcore.commands.get_stats_radio()
            if stats and hasattr(stats, 'payload') and stats.payload:
                signal_snr = stats.payload.get("last_snr")
                signal_rssi = stats.payload.get("last_rssi")
                signal_noise_floor = stats.payload.get("noise_floor")
                print(f"  \U0001f4f6 Signal: SNR={signal_snr}dB RSSI={signal_rssi}dBm NF={signal_noise_floor}dBm")
        except Exception as e:
            print(f"  \u26a0 Stats-Radio Fehler: {e}")

        sender_key = data.get("pubkey_prefix", "unbekannt")
        text = data.get("text", "")

        # --- SCHLEIFEN-SCHUTZ ---
        if text.startswith(STATION_QTH):
            print(f"\U0001f504 [{ts}] Ignoriert (eigene Antwort): {text[:40]}")
            log_to_file("self", sender_key, text, "n/a", 0, "ignored")
            return

        now = time.time()
        if sender_key in last_reply:
            elapsed = now - last_reply[sender_key]
            if elapsed < COOLDOWN_SECONDS:
                print(f"\u23f3 [{ts}] Cooldown fuer {sender_key[:12]} "
                      f"(noch {int(COOLDOWN_SECONDS - elapsed)}s)")
                log_to_file(sender_key[:12], sender_key, text,
                           "n/a", 0, "cooldown")
                return

        # --- NORMALE VERARBEITUNG ---
        contact = None
        sender_name = sender_key[:12]
        for key, c in meshcore.contacts.items():
            if key.startswith(sender_key):
                contact = c
                sender_name = c.get("adv_name", sender_key[:12])
                break

        if contact:
            path, hops = get_path_info(contact)
        else:
            path, hops = "unknown", 0

        print(f"\U0001f4e9 [{ts}] DM von: {sender_name}")
        print(f"  Text: {text}")
        print(f"  Path: {path} ({hops} hops)")

        reply = build_env_reply(sender_name, signal_snr, signal_rssi, signal_noise_floor)

        print(f"  \U0001f4ac Antwort: {reply}")
        try:
            result = await meshcore.commands.send_msg(
                sender_key, reply
            )
            if result.type == EventType.ERROR:
                print(f"  \u26a0 Senden fehlgeschlagen: {result.payload}")
            else:
                print(f"  \u2705 Antwort gesendet!")
                last_reply[sender_key] = now
                log_to_file(sender_name, sender_key, text, path, hops, "replied", signal_snr or "", signal_rssi or "", signal_noise_floor or "")
        except Exception as e:
            print(f"  \u274c Sende-Fehler: {e}")
        print()

    # ============================================================
    # START: Events subscriben und Loops starten
    # ============================================================
    await send_flood_advert(meshcore)

    meshcore.subscribe(EventType.ADVERTISEMENT, handle_advert)
    meshcore.subscribe(EventType.CONTACT_MSG_RECV, handle_message)
    meshcore.subscribe(EventType.CHANNEL_MSG_RECV, handle_channel_message)

    await meshcore.start_auto_message_fetching()

    # Advert-Loop (alle 12h)
    advert_task = asyncio.create_task(advert_loop(meshcore))

    # Umweltsensor-Loop (alle 12 Min)
    env_task = asyncio.create_task(env_sensor_loop())

    print("\U0001f449 Lausche auf Adverts + DMs + Channels... (Ctrl+C zum Beenden)\n")

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n\U0001f44b Responder gestoppt.")
        advert_task.cancel()
        env_task.cancel()
    finally:
        await meshcore.disconnect()
        print("\u2705 Verbindung getrennt.")


asyncio.run(main())
