#!/usr/bin/env python3
"""DM-Responder: RAK4631 als Daten-Reservoir, Auto-Reply auf DMs."""

import asyncio
import time
from datetime import datetime
from meshcore import MeshCore, EventType
from sdcard_writer import SDCardWriter
from threading import Thread
from sd_server import app as flask_app

PORT = "/dev/ttyACM0"
ADVERT_INTERVAL = 12 * 60 * 60  # 12 Stunden

# ============================================================
# ANTWORT-VORLAGE (hier anpassen!)
# Platzhalter:
#   {nachricht}  = Empfangene Nachricht
#   {path}       = Routing-Pfad (hex) oder "direct"
#   {hops}       = Anzahl Hops
#   {sender}     = Name des Absenders
# ============================================================
REPLY_TEMPLATE = "RX OK: {nachricht} [via {path}, {hops} hops]"

# ============================================================
# SCHLEIFEN-SCHUTZ
# ============================================================
REPLY_PREFIX = "RX OK:"           # Eigene Antworten erkennen
COOLDOWN_SECONDS = 30             # Min. Sekunden zwischen Antworten pro Kontakt
last_reply = {}                   # Dict: pubkey_prefix → timestamp letzte Antwort

# ============================================================
# SD-CARD LOGGING
# ============================================================
CSV_FILENAME = "DMLOG.CSV"
CSV_HEADER = "timestamp,sender_name,sender_key,text,path,hops,status\n"

async def send_flood_advert(meshcore):
    """Sendet ein Flood-Advert ins Mesh."""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"📡 [{ts}] Sende Flood-Advert...")
    result = await meshcore.commands.send_advert(flood=True)
    if result.type == EventType.ERROR:
        print(f"   ❌ Fehler: {result.payload}")
    else:
        print(f"   ✅ Flood-Advert gesendet!")


async def advert_loop(meshcore):
    """Sendet alle 12 Stunden ein Flood-Advert."""
    while True:
        await asyncio.sleep(ADVERT_INTERVAL)
        await send_flood_advert(meshcore)


def get_path_info(contact):
    """Extrahiert Path-Info aus einem Kontakt-Dict."""
    out_path = contact.get("out_path", "")
    out_path_len = contact.get("out_path_len", 0)
    hash_mode = contact.get("out_path_hash_mode", 0)

    if out_path_len <= 0 or out_path == "":
        return "direct", 0
    else:
        hash_size = max(hash_mode + 1, 1)
        path_hex_len = out_path_len * hash_size * 2
        path_display = out_path[:path_hex_len]
        return path_display, out_path_len


async def main():
    print("🚀 DM-Responder startet...")
    print(f"   Port: {PORT}")
    print(f"   Zeit: {datetime.now().strftime('%H:%M:%S')}")
    print(f"   Advert-Intervall: {ADVERT_INTERVAL // 3600}h")
    print(f"   Reply: \"{REPLY_TEMPLATE}\"")
    print("-" * 50)

    meshcore = await MeshCore.create_serial(PORT)
        # SD-Karte oeffnen
    print("💾 SD-Karte initialisieren...")
    try:
        sd = SDCardWriter()
        # Header schreiben falls neue Datei
        existing = sd.read_file(CSV_FILENAME)
        if existing is None:
            sd.append_to_file(CSV_FILENAME, CSV_HEADER)
            print(f"   ✅ {CSV_FILENAME} erstellt (mit Header)")
        else:
            lines = existing.strip().split('\n')
            print(f"   ✅ {CSV_FILENAME} existiert ({len(lines)} Zeilen)")
    except Exception as e:
        print(f"   ⚠️  SD-Karte Fehler: {e}")
        sd = None

    # Web-Server starten (eigener Thread)
    import sd_server
    sd_server.sd = sd
    web_thread = Thread(
        target=lambda: flask_app.run(host="0.0.0.0", port=5000, debug=False),
        daemon=True
    )
    web_thread.start()
    print(f"    Web-Server: http://10.0.1.191:5000")

    # Kontakte vom RAK laden
    await meshcore.commands.get_contacts()
    print(f"✅ Verbunden. {len(meshcore.contacts)} Kontakte auf dem RAK.")

    # --- Handler als Closure ---

    async def handle_advert(event):
        """Advert empfangen → Kontaktdaten vom RAK abrufen."""
        ts = datetime.now().strftime("%H:%M:%S")
        pub_key = event.payload.get("public_key", "")

        print(f"📢 [{ts}] Advert empfangen! Key: {pub_key[:16]}...")

        if pub_key:
            # RAK nach vollstaendigen Kontaktdaten fragen
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

                print(f"   Name:  {name}")
                print(f"   Typ:   {ctype}")
                print(f"   Pos:   {lat:.4f}, {lon:.4f}")
                print(f"   Path:  {path} ({hops} hops)")

                # Lokale Kontaktliste aktualisieren
                meshcore.contacts[pub_key] = contact
                print(f"   ✅ Kontakt '{name}' in lokaler Liste aktualisiert.")
            else:
                print(f"   ⚠️  RAK kennt Key nicht: {result.payload}")
        print()
    def log_to_sd(sender_name, sender_key, text, path, hops, status):
        """Schreibt eine Zeile ins CSV auf der SD-Karte."""
        if sd is None:
            return
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Kommas in Text escapen
        safe_text = text.replace(",", ";")
        line = f"{ts},{sender_name},{sender_key[:16]},{safe_text},{path},{hops},{status}\n"
        try:
            sd.append_to_file(CSV_FILENAME, line)
        except Exception as e:
            print(f"   ⚠️  SD-Log Fehler: {e}")


    async def handle_message(event):
        """Eingehende DM → Auto-Reply mit Schleifen-Schutz."""
        ts = datetime.now().strftime("%H:%M:%S")
        data = event.payload
        sender_key = data.get("pubkey_prefix", "unbekannt")
        text = data.get("text", "")

        # --- SCHLEIFEN-SCHUTZ ---

        # 1) Eigene Antworten ignorieren (von anderen Bots)
        if text.startswith(REPLY_PREFIX):
            print(f"🔁 [{ts}] Ignoriert (Bot-Antwort): {text[:40]}")
            log_to_sd("bot", sender_key, text, "n/a", 0, "ignored")
            return

        # 2) Cooldown pro Kontakt
        now = time.time()
        if sender_key in last_reply:
            elapsed = now - last_reply[sender_key]
            if elapsed < COOLDOWN_SECONDS:
                print(f"⏳ [{ts}] Cooldown fuer {sender_key[:12]} "
                      f"(noch {int(COOLDOWN_SECONDS - elapsed)}s)")
                log_to_sd(sender_key[:12], sender_key, text, "n/a", 0, "cooldown")
                return

        # --- NORMALE VERARBEITUNG ---

        # Kontakt aus lokaler Liste suchen
        contact = None
        sender_name = sender_key[:12]
        for key, c in meshcore.contacts.items():
            if key.startswith(sender_key):
                contact = c
                sender_name = c.get("adv_name", sender_key[:12])
                break

        # Path-Info
        if contact:
            path, hops = get_path_info(contact)
        else:
            path, hops = "unknown", 0

        print(f"📨 [{ts}] DM von: {sender_name}")
        print(f"   Text: {text}")
        print(f"   Path: {path} ({hops} hops)")

        # Auto-Reply zusammenbauen
        reply = REPLY_TEMPLATE.format(
            nachricht=text,
            path=path,
            hops=hops,
            sender=sender_name,
        )

        # Antwort senden
        print(f"   📤 Antwort: {reply}")
        try:
            result = await meshcore.commands.send_msg(
                sender_key, reply
            )
            if result.type == EventType.ERROR:
                print(f"   ⚠️  Senden fehlgeschlagen: {result.payload}")
            else:
                print(f"   ✅ Antwort gesendet!")
                last_reply[sender_key] = now  # Cooldown starten
                log_to_sd(sender_name, sender_key, text, path, hops, "replied")
        except Exception as e:
            print(f"   ❌ Sende-Fehler: {e}")
        print()

    # --- Start ---

    # 1) Flood-Advert sofort senden
    await send_flood_advert(meshcore)

    # 2) Events subscriben
    meshcore.subscribe(EventType.ADVERTISEMENT, handle_advert)
    meshcore.subscribe(EventType.CONTACT_MSG_RECV, handle_message)

    # 3) Auto-Fetch starten
    await meshcore.start_auto_message_fetching()

    # 4) Advert-Loop (alle 12h)
    advert_task = asyncio.create_task(advert_loop(meshcore))

    print("👂 Lausche auf Adverts + DMs... (Ctrl+C zum Beenden)\n")

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n⏹️  Responder gestoppt.")
        advert_task.cancel()
    finally:
        await meshcore.disconnect()
        if sd:
            sd.close()
        print("✅ Verbindun + SD-Karte getrennt.")


asyncio.run(main())
