#!/usr/bin/env python3
"""
sd_server.py - Webserver zum Auslesen der Daten-SD via WLAN.
Laeuft auf RpPiZeroW-001, liest vom MH-SD Modul via SPI.
"""

from flask import Flask, Response, jsonify
from sdcard_writer import SDCardWriter

app = Flask(__name__)
sd = None


def get_sd():
    global sd
    if sd is None:
        raise RuntimeError("SD nicht initialisiert")
    return sd


@app.route("/")
def index():
    """Startseite mit Status."""
    rows = ""
    try:
        card = get_sd()
        for i in range(6):
            slot = card._read_slot(i)
            if not slot["name"]:
                rows += (f"<tr><td style='border:1px solid #444;padding:8px;'>{i+1}</td>"
                         f"<td style='border:1px solid #444;padding:8px;' colspan='4'>"
                         f"(leer)</td></tr>")
                continue
            total = slot["size_low"] | (slot["size_high"] << 32)
            blocks = slot["current_block"] - slot["start_block"]
            if total < 1024:
                size_str = f"{total} B"
            elif total < 1048576:
                size_str = f"{total/1024:.1f} KB"
            else:
                size_str = f"{total/1048576:.1f} MB"
            name = slot["name"]
            td = "style='border:1px solid #444;padding:8px;'"
            rows += (f"<tr><td {td}>{i+1}</td><td {td}>{name}</td>"
                     f"<td {td}>{size_str}</td><td {td}>{blocks}</td>"
                     f"<td {td}><a style='color:#4fc3f7;' href='/file/{name}'>Anzeigen</a>"
                     f" | <a style='color:#4fc3f7;' href='/download/{name}'>"
                     f"Download</a></td></tr>")
    except Exception as e:
        rows = f"<tr><td colspan='5'>Fehler: {e}</td></tr>"

    page = (
        "<!DOCTYPE html><html><head>"
        "<title>SD-Card Reader - RpPiZeroW-001</title>"
        "<meta charset='utf-8'>"
        "</head>"
        "<body style='font-family:monospace;max-width:800px;"
        "margin:40px auto;padding:0 20px;"
        "background:#1a1a2e;color:#e0e0e0;'>"
        "<h1 style='color:#00d4aa;'>SD-Card Reader</h1>"
        "<p>RpPiZeroW-001 | MH-SD Modul | SPI GPIO25</p>"
        "<h2 style='color:#00d4aa;'>Dateien</h2>"
        "<table style='border-collapse:collapse;width:100%;'>"
        "<tr style='background:#16213e;'>"
        "<th style='border:1px solid #444;padding:8px;color:#00d4aa;'>Slot</th>"
        "<th style='border:1px solid #444;padding:8px;color:#00d4aa;'>Datei</th>"
        "<th style='border:1px solid #444;padding:8px;color:#00d4aa;'>Groesse</th>"
        "<th style='border:1px solid #444;padding:8px;color:#00d4aa;'>Bloecke</th>"
        "<th style='border:1px solid #444;padding:8px;color:#00d4aa;'>Aktion</th></tr>"
        f"{rows}"
        "</table>"
        "<h2 style='color:#00d4aa;'>API</h2>"
        "<ul>"
        "<li><a style='color:#4fc3f7;' href='/api/status'>/api/status</a> - JSON</li>"
        "<li>/api/file/DATEINAME - Text</li>"
        "<li>/download/DATEINAME - CSV Download</li>"
        "</ul>"
        "<p style='color:#666;margin-top:40px;'>Paul's ElektroTech-Lab</p>"
        "</body></html>"
    )
    return page


@app.route("/api/status")
def api_status():
    try:
        card = get_sd()
        slots = []
        for i in range(6):
            slot = card._read_slot(i)
            total = slot["size_low"] | (slot["size_high"] << 32)
            slots.append({
                "slot": i + 1,
                "name": slot["name"],
                "size_bytes": total,
                "blocks_used": slot["current_block"] - slot["start_block"],
            })
        return jsonify({"status": "ok", "slots": slots})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/file/<filename>")
def show_file(filename):
    try:
        card = get_sd()
        content = card.read_file(filename)
        if content is None:
            return f"Datei '{filename}' nicht gefunden", 404
        return f"<pre style='background:#1a1a2e;color:#e0e0e0;padding:20px;'>{content}</pre>"
    except Exception as e:
        return f"Fehler: {e}", 500


@app.route("/api/file/<filename>")
def api_file(filename):
    try:
        card = get_sd()
        content = card.read_file(filename)
        if content is None:
            return f"Datei '{filename}' nicht gefunden", 404
        return Response(content, mimetype="text/plain")
    except Exception as e:
        return f"Fehler: {e}", 500


@app.route("/download/<filename>")
def download_file(filename):
    try:
        card = get_sd()
        content = card.read_file(filename)
        if content is None:
            return f"Datei '{filename}' nicht gefunden", 404
        return Response(
            content,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        return f"Fehler: {e}", 500


if __name__ == "__main__":
    # Standalone-Modus (ohne dm_listener)
    print("SD-Card Server startet (standalone)...")
    print("  http://10.0.1.191:5000")
    try:
        sd = SDCardWriter()
        print("  SD-Karte bereit")
    except Exception as e:
        print(f"  WARNUNG: SD nicht verfuegbar ({e})")
    print("  Ctrl+C zum Stoppen\n")
    app.run(host="0.0.0.0", port=5000, debug=False)
