"""
Flask-Webserver fuer die MeshCore Responder-Station.
Dashboard mit System-Status, MeshCore-Daten, Umweltdaten und Web-Konfiguration.
Erstellt von Paul (Brain Gym) mit Hilfe von Claude (Anthropic, 2026).
Repo: https://github.com/Paul-3400/meshcore-responder-station
Version: 2.3 - Web-Konfiguration mit Login-Schutz
"""
from flask import Flask, jsonify, request, session, redirect, url_for
import subprocess
import time
import os
import threading
import file_store
import auth

flask_app = Flask(__name__)

# ============================================================
# FLASK SESSION SECRET KEY
# ============================================================
flask_app.secret_key = os.urandom(24)

# ============================================================
# STATION.CONF PFAD
# ============================================================
STATION_CONF_PATH = "/home/paul-rppi/meshcore-responder/station.conf"

# ============================================================
# CSV HEADER (muessen mit dm_listener.py uebereinstimmen)
# ============================================================
CSV_HEADERS = {
    "DMLOG.CSV": "timestamp,sender_name,sender_key,text,path,hops,status,snr,rssi,noise_floor\n",
    "CHANNELS.CSV": "timestamp,channel_idx,sender_name,text,path_len,txt_type\n",
    "CONTACTS.CSV": "tstmp_snapshot,pubkey_prefix,node_name,node_type,lat,lon,path_hops,tstmp_last_advert,tstmp_lastmod\n",
    "ENVLOG.CSV": "Timestamp,Temp_C,Humidity_%,Pressure_QNH_hPa,Dewpoint_C,Pressure_Station_hPa,Temp_BMP_C\n",
}

# ============================================================
# HILFSFUNKTIONEN – SYSTEM
# ============================================================
def get_uptime():
    with open('/proc/uptime', 'r') as f:
        seconds = float(f.readline().split()[0])
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    return f"{hours}h {minutes}m"

def get_cpu_temp():
    try:
        temp = subprocess.check_output(["vcgencmd", "measure_temp"], text=True)
        return temp.strip().replace("temp=", "")
    except Exception:
        return "n/a"

def get_hostname():
    return subprocess.check_output(["hostname"], text=True).strip()

def is_hotspot_active():
    result = subprocess.run(["pgrep", "-x", "hostapd"], capture_output=True)
    return result.returncode == 0

def read_csv_lines(filename):
    data = file_store.read_file(filename)
    if data is None:
        return []
    lines = data.strip().split('\n')
    return lines

# ============================================================
# HILFSFUNKTIONEN – STATION.CONF LESEN/SCHREIBEN
# ============================================================
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
        pass
    return config

def save_station_conf(config):
    """Schreibt station.conf mit aktuellen Werten zurueck.
    Bewahrt Kommentare und Sektions-Header."""
    lines_out = []
    try:
        with open(STATION_CONF_PATH, 'r') as f:
            original_lines = f.readlines()
    except FileNotFoundError:
        original_lines = []

    written_keys = set()
    for line in original_lines:
        stripped = line.strip()
        # Kommentare und Sektions-Header beibehalten
        if stripped.startswith('#') or stripped.startswith('[') or stripped == '':
            lines_out.append(line)
        elif '=' in stripped:
            key = stripped.split('=', 1)[0].strip()
            if key in config:
                lines_out.append(f"{key} = {config[key]}\n")
                written_keys.add(key)
            else:
                lines_out.append(line)
        else:
            lines_out.append(line)

    # Neue Keys die noch nicht in der Datei waren
    for key, value in config.items():
        if key not in written_keys:
            lines_out.append(f"{key} = {value}\n")

    with open(STATION_CONF_PATH, 'w') as f:
        f.writelines(lines_out)

# ============================================================
# HILFSFUNKTION – NAVIGATION (bedingt je Login-Status)
# ============================================================
def get_nav():
    """Gibt Navigation-HTML zurueck. Config/Logout nur wenn eingeloggt."""
    nav = '<nav>'
    nav += '<a href="/">Dashboard</a> '
    nav += '<a href="/messages">DMs</a> '
    nav += '<a href="/channels">Channels</a> '
    nav += '<a href="/contacts">Kontakte</a> '
    nav += '<a href="/environment">Umwelt</a> '
    if session.get('logged_in'):
        nav += '<a href="/config">Config</a> '
        nav += '<a href="/logout">Logout</a>'
    else:
        nav += '<a href="/login">Login</a>'
    nav += '</nav>'
    return nav

# ============================================================
# HTML BAUSTEINE
# ============================================================
FOOTER = '<footer>Paul3400 Brain Gym - Claude Anthropic 2026</footer>'

CSS = '<link rel="stylesheet" href="/static/style.css">'

# ============================================================
# ROUTEN – AUTHENTIFIZIERUNG
# ============================================================
@flask_app.route('/login', methods=['GET', 'POST'])
def login():
    """Login-Seite mit Formular."""
    msg = ""
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        if auth.verify_login(username, password):
            session['logged_in'] = True
            session['username'] = username
            session['login_time'] = time.time()
            return redirect(url_for('config'))
        else:
            msg = '<p class="msg-err">❌ Benutzername oder Passwort falsch.</p>'

    html = f'''<html><head><title>Login</title>{CSS}</head><body>
<h1>🔐 Login</h1>
{get_nav()}
{msg}
<form method="POST">
  <div class="form-row"><label>Benutzer:</label>
    <input type="text" name="username" required></div>
  <div class="form-row"><label>Passwort:</label>
    <input type="password" name="password" required></div>
  <div class="form-row"><button type="submit" class="btn">Anmelden</button></div>
</form>
{FOOTER}</body></html>'''
    return html

@flask_app.route('/logout')
def logout():
    """Session beenden und auf Dashboard umleiten."""
    session.clear()
    return redirect(url_for('index'))

@flask_app.route('/change-password', methods=['GET', 'POST'])
@auth.login_required
def change_password():
    """Passwort-Aenderung (nur eingeloggt)."""
    msg = ""
    if request.method == 'POST':
        current_pw = request.form.get('current_password', '')
        new_pw = request.form.get('new_password', '')
        confirm_pw = request.form.get('confirm_password', '')

        username = session.get('username', 'admin')

        if not auth.verify_login(username, current_pw):
            msg = '<p class="msg-err">❌ Aktuelles Passwort ist falsch.</p>'
        elif len(new_pw) < 4:
            msg = '<p class="msg-err">❌ Neues Passwort muss mind. 4 Zeichen haben.</p>'
        elif new_pw != confirm_pw:
            msg = '<p class="msg-err">❌ Neue Passwoerter stimmen nicht ueberein.</p>'
        else:
            auth.change_password(new_pw)
            msg = '<p class="msg-ok">✅ Passwort erfolgreich geaendert!</p>'

    html = f'''<html><head><title>Passwort aendern</title>{CSS}</head><body>
<h1>🔑 Passwort aendern</h1>
{get_nav()}
{msg}
<form method="POST">
  <div class="form-row"><label>Aktuelles PW:</label>
    <input type="password" name="current_password" required></div>
  <div class="form-row"><label>Neues PW:</label>
    <input type="password" name="new_password" required></div>
  <div class="form-row"><label>Bestaetigen:</label>
    <input type="password" name="confirm_password" required></div>
  <div class="form-row"><button type="submit" class="btn">Aendern</button></div>
</form>
{FOOTER}</body></html>'''
    return html

# ============================================================
# ROUTEN – KONFIGURATION
# ============================================================
@flask_app.route('/config', methods=['GET', 'POST'])
@auth.login_required
def config():
    """Web-Konfiguration: station.conf lesen und schreiben."""
    msg = ""
    conf = load_station_conf()

    if request.method == 'POST':
        # Formulardaten lesen
        new_conf = {
            'name': request.form.get('name', '').strip(),
            'callsign': request.form.get('callsign', '').strip(),
            'qth': request.form.get('qth', '').strip(),
            'altitude': request.form.get('altitude', '').strip(),
            'lat': request.form.get('lat', '').strip(),
            'lon': request.form.get('lon', '').strip(),
            'template': request.form.get('template', '').strip(),
            'env_interval': request.form.get('env_interval', '').strip(),
        }

        # ---- VALIDIERUNG ----
        errors = []

        # QTH: genau 6 Zeichen
        if len(new_conf['qth']) != 6:
            errors.append("QTH muss genau 6 Zeichen haben (Maidenhead Locator).")

        # Hoehe: 0–4500m
        try:
            alt = int(new_conf['altitude'])
            if alt < 0 or alt > 4500:
                errors.append("Hoehe muss zwischen 0 und 4500m liegen.")
        except ValueError:
            errors.append("Hoehe muss eine Ganzzahl sein.")

        # Latitude: 45–48 (Schweiz)
        try:
            lat = float(new_conf['lat'])
            if lat < 45.0 or lat > 48.0:
                errors.append("Breitengrad muss zwischen 45.0 und 48.0 liegen (Schweiz).")
        except ValueError:
            errors.append("Breitengrad muss eine Zahl sein.")

        # Longitude: 5.5–10.5 (Schweiz)
        try:
            lon = float(new_conf['lon'])
            if lon < 5.5 or lon > 10.5:
                errors.append("Laengengrad muss zwischen 5.5 und 10.5 liegen (Schweiz).")
        except ValueError:
            errors.append("Laengengrad muss eine Zahl sein.")

        # Messintervall: 1–60 Minuten
        try:
            interval = int(new_conf['env_interval'])
            if interval < 1 or interval > 60:
                errors.append("Messintervall muss zwischen 1 und 60 Minuten liegen.")
        except ValueError:
            errors.append("Messintervall muss eine Ganzzahl sein.")

        if errors:
            msg = '<p class="msg-err">❌ ' + '<br>'.join(errors) + '</p>'
        else:
            # Speichern
            save_station_conf(new_conf)
            conf = new_conf
            msg = '<p class="msg-ok">✅ Konfiguration gespeichert! Restart fuer Uebernahme empfohlen.</p>'

    # Aktuelle Werte fuer Formular
    html = f'''<html><head><title>Konfiguration</title>{CSS}</head><body>
<h1>⚙️ Station Konfiguration</h1>
{get_nav()}
{msg}
<form method="POST">
  <h3>Station</h3>
  <div class="form-row"><label>Name:</label>
    <input type="text" name="name" value="{conf.get('name', '')}"></div>
  <div class="form-row"><label>Callsign:</label>
    <input type="text" name="callsign" value="{conf.get('callsign', '')}"></div>
  <div class="form-row"><label>QTH (6 Zeichen):</label>
    <input type="text" name="qth" value="{conf.get('qth', '')}" maxlength="6"></div>
  <div class="form-row"><label>Hoehe (m):</label>
    <input type="number" name="altitude" value="{conf.get('altitude', '554')}" min="0" max="4500"></div>
  <div class="form-row"><label>Breitengrad:</label>
    <input type="text" name="lat" value="{conf.get('lat', '')}"></div>
  <div class="form-row"><label>Laengengrad:</label>
    <input type="text" name="lon" value="{conf.get('lon', '')}"></div>

  <h3>Auto-Reply</h3>
  <div class="form-row"><label>Template:</label>
    <input type="text" name="template" value="{conf.get('template', '')}" style="width:500px;"></div>
  <p style="color:#888; font-size:0.85em;">Variablen: {{sender}}, {{name}}, {{qth}}, {{alt}}, {{date}}, {{time}}, {{signal}}, {{temp}}, {{hum}}, {{pressure}}, {{dewpoint}}, {{callsign}}</p>

  <h3>Sensoren</h3>
  <div class="form-row"><label>Messintervall (Min):</label>
    <input type="number" name="env_interval" value="{conf.get('env_interval', '12')}" min="1" max="60"></div>

  <div class="form-row" style="margin-top:20px;">
    <button type="submit" class="btn">💾 Speichern</button>
  </div>
</form>

<hr style="border-color:#333; margin-top:30px;">
<h3>🔑 Passwort</h3>
<a href="/change-password" class="btn">Passwort aendern</a>

<hr style="border-color:#333; margin-top:30px;">
<h3>🔄 Service Restart</h3>
<p style="color:#888;">Startet den dm-responder Service neu (uebernimmt Config-Aenderungen).</p>
<form method="POST" action="/restart" onsubmit="return confirm('Service wirklich neu starten?');">
  <button type="submit" class="btn btn-danger">⚡ Service neu starten</button>
</form>

{FOOTER}</body></html>'''
    return html

# ============================================================
# ROUTE – SERVICE RESTART
# ============================================================
@flask_app.route('/restart', methods=['POST'])
@auth.login_required
def restart():
    """Startet den dm-responder Service mit 2s Verzoegerung neu."""
    def delayed_restart():
        time.sleep(2)
        subprocess.run(["sudo", "systemctl", "restart", "dm-responder"],
                      capture_output=True)
    threading.Thread(target=delayed_restart, daemon=True).start()

    html = f'''<html><head><title>Restart</title>{CSS}
<meta http-equiv="refresh" content="10;url=/"></head><body>
<h1>🔄 Service wird neu gestartet...</h1>
{get_nav()}
<p>Der dm-responder Service wird neu gestartet.</p>
<p>Weiterleitung zum Dashboard in 10 Sekunden...</p>
<p><a href="/">Manuell zum Dashboard</a></p>
{FOOTER}</body></html>'''
    return html

# ============================================================
# ROUTEN – DASHBOARD (bestehend, mit neuem Nav)
# ============================================================
@flask_app.route('/')
def index():
    hotspot = is_hotspot_active()
    fs_ok = file_store.file_exists("DMLOG.CSV")
    hotspot_class = "badge-green" if hotspot else "badge-orange"
    hotspot_text = "AKTIV" if hotspot else "INAKTIV"
    fs_class = "badge-green" if fs_ok else "badge-orange"
    fs_text = "OK" if fs_ok else "NICHT BEREIT"
    html = f'''<html><head><title>Responder-Station</title>{CSS}</head><body>
<h1>📡 MeshCore Field Access Point v2.3</h1>
{get_nav()}
<h2>System</h2>
<table>
  <tr><td>Hostname</td><td>{get_hostname()}</td></tr>
  <tr><td>Uptime</td><td>{get_uptime()}</td></tr>
  <tr><td>CPU Temp</td><td>{get_cpu_temp()}</td></tr>
  <tr><td>Hotspot</td><td class="{hotspot_class}">{hotspot_text}</td></tr>
  <tr><td>Filesystem</td><td class="{fs_class}">{fs_text}</td></tr>
</table>

<h2>MeshCore Radio</h2>
<table>
  <tr><td>Port</td><td>/dev/ttyACM0</td></tr>
  <tr><td>Status</td><td class="badge-green">VERBUNDEN</td></tr>
</table>

<p><a href="/" class="btn">Aktualisieren</a></p>
{FOOTER}</body></html>'''
    return html

# ============================================================
# ROUTEN – DMs (bestehend, mit neuem Nav)
# ============================================================
@flask_app.route('/messages')
def messages():
    lines = read_csv_lines("DMLOG.CSV")
    rows_html = ""
    if len(lines) > 1:
        for line in reversed(lines[1:]):
            cols = line.split(',')
            if len(cols) >= 7:
                rows_html += (f"<tr><td>{cols[0]}</td><td>{cols[1]}</td>"
                              f"<td>{cols[2]}</td><td>{cols[6]}</td>"
                              f"<td>{cols[7] if len(cols) > 7 else ''}</td>"
                              f"<td>{cols[8] if len(cols) > 8 else ''}</td></tr>\n")
    else:
        rows_html = "<tr><td colspan='6'>Keine Nachrichten</td></tr>"

    html = f'''<html><head><title>Responder-Station</title>{CSS}</head><body>
<h1>📨 Empfangene DMs</h1>
{get_nav()}
<p><a href="/download/DMLOG.CSV">CSV herunterladen</a> |
<a href="#" onclick="fetch('/delete/DMLOG.CSV',{{method:'POST'}}).then(()=>location.reload())">CSV loeschen</a></p>
<p style="color:#888; font-size:0.85em;">Angezeigte Spalten: timestamp, sender_name, sender_key, status, snr, rssi<br>
Weitere Spalten im CSV: text, path, hops, noise_floor</p>
<table>
<tr><th>timestamp</th><th>sender_name</th><th>sender_key</th><th>status</th><th>snr</th><th>rssi</th></tr>
{rows_html}
</table>
{FOOTER}</body></html>'''
    return html

# ============================================================
# ROUTEN – CHANNELS (bestehend, mit neuem Nav)
# ============================================================
@flask_app.route('/channels')
def channels():
    lines = read_csv_lines("CHANNELS.CSV")
    rows_html = ""
    if len(lines) > 1:
        for line in reversed(lines[1:]):
            cols = line.split(',')
            if len(cols) >= 4:
                rows_html += (f"<tr><td>{cols[0]}</td><td>{cols[1]}</td>"
                              f"<td>{cols[2]}</td><td>{cols[3][:60]}</td></tr>\n")
    else:
        rows_html = "<tr><td colspan='4'>Keine Channel-Nachrichten</td></tr>"

    html = f'''<html><head><title>Responder-Station</title>{CSS}</head><body>
<h1>📢 Channel-Nachrichten</h1>
{get_nav()}
<p><a href="/download/CHANNELS.CSV">CSV herunterladen</a> |
<a href="#" onclick="fetch('/delete/CHANNELS.CSV',{{method:'POST'}}).then(()=>location.reload())">CSV loeschen</a></p>
<p style="color:#888; font-size:0.85em;">Angezeigte Spalten: timestamp, channel_idx, sender_name, text<br>
Weitere Spalten im CSV: path_len, txt_type</p>
<table>
<tr><th>timestamp</th><th>channel_idx</th><th>sender_name</th><th>text</th></tr>
{rows_html}
</table>
{FOOTER}</body></html>'''
    return html

# ============================================================
# ROUTEN – KONTAKTE (bestehend, mit neuem Nav)
# ============================================================
@flask_app.route('/contacts')
def contacts():
    lines = read_csv_lines("CONTACTS.CSV")
    rows_html = ""
    if len(lines) > 1:
        for line in reversed(lines[1:]):
            cols = line.split(',')
            if len(cols) >= 4:
                rows_html += (f"<tr><td>{cols[0]}</td><td>{cols[2]}</td>"
                              f"<td>{cols[3]}</td><td>{cols[1]}</td></tr>\n")
    else:
        rows_html = "<tr><td colspan='4'>Keine Kontakte</td></tr>"

    html = f'''<html><head><title>Responder-Station</title>{CSS}</head><body>
<h1>👥 Kontakte (Boot-Export)</h1>
{get_nav()}
<p><a href="/download/CONTACTS.CSV">CSV herunterladen</a> |
<a href="#" onclick="fetch('/delete/CONTACTS.CSV',{{method:'POST'}}).then(()=>location.reload())">CSV loeschen</a></p>
<p style="color:#888; font-size:0.85em;">Angezeigte Spalten: tstmp_snapshot, node_name, node_type, pubkey_prefix<br>
Weitere Spalten im CSV: lat, lon, path_hops, tstmp_last_advert, tstmp_lastmod<br>
node_type: 1 = Client, 2 = Repeater, 3 = Room Server</p>
<table>
<tr><th>tstmp_snapshot</th><th>node_name</th><th>node_type</th><th>pubkey_prefix</th></tr>
{rows_html}
</table>
{FOOTER}</body></html>'''
    return html

# ============================================================
# ROUTEN – UMWELTDATEN (bestehend, mit neuem Nav)
# ============================================================
@flask_app.route('/environment')
def environment():
    lines = read_csv_lines("ENVLOG.CSV")
    rows_html = ""
    current_html = ""

    if len(lines) > 1:
        last_line = lines[-1].split(',')
        if len(last_line) >= 5:
            current_html = f'''<h2>Aktuelle Messung</h2>
<table>
  <tr><td>Timestamp</td><td>{last_line[0]}</td></tr>
  <tr><td>Temp_C</td><td>{last_line[1]} °C</td></tr>
  <tr><td>Humidity_%</td><td>{last_line[2]} %</td></tr>
  <tr><td>Pressure_QNH_hPa</td><td>{last_line[3]} hPa</td></tr>
  <tr><td>Dewpoint_C</td><td>{last_line[4]} °C</td></tr>
</table>'''

        for line in reversed(lines[1:]):
            cols = line.split(',')
            if len(cols) >= 5:
                rows_html += (f"<tr><td>{cols[0]}</td><td>{cols[1]}</td>"
                              f"<td>{cols[2]}</td><td>{cols[3]}</td>"
                              f"<td>{cols[4]}</td></tr>\n")
    else:
        rows_html = "<tr><td colspan='5'>Keine Umweltdaten vorhanden</td></tr>"

    html = f'''<html><head><title>Responder-Station</title>{CSS}</head><body>
<h1>🌡️ Umweltdaten</h1>
{get_nav()}
<p style="color:#888;">Standort: JN37TB / 554 m ue.M. • Messintervall: dynamisch aus station.conf</p>
{current_html}
<p><a href="/download/ENVLOG.CSV">CSV herunterladen</a> |
<a href="#" onclick="fetch('/delete/ENVLOG.CSV',{{method:'POST'}}).then(()=>location.reload())">CSV loeschen</a></p>
<p style="color:#888; font-size:0.85em;">Angezeigte Spalten: Timestamp, Temp_C, Humidity_%, Pressure_QNH_hPa, Dewpoint_C<br>
Weitere Spalten im CSV: Pressure_Station_hPa, Temp_BMP_C</p>
<table>
<tr><th>Timestamp</th><th>Temp_C</th><th>Humidity_%</th><th>Pressure_QNH_hPa</th><th>Dewpoint_C</th></tr>
{rows_html}
</table>
{FOOTER}</body></html>'''
    return html

# ============================================================
# API + DOWNLOADS + DELETE
# ============================================================
@flask_app.route('/api/status')
def api_status():
    return jsonify({
        "hostname": get_hostname(),
        "uptime": get_uptime(),
        "cpu_temp": get_cpu_temp(),
        "hotspot_active": is_hotspot_active(),
        "filesystem": file_store.file_exists("DMLOG.CSV"),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    })

@flask_app.route("/download/<filename>")
def download_file(filename):
    allowed = ["DMLOG.CSV", "CHANNELS.CSV", "CONTACTS.CSV", "ENVLOG.CSV"]
    if filename not in allowed:
        return "Nicht erlaubt", 403
    data = file_store.read_file(filename)
    if not data:
        return "Datei leer oder nicht vorhanden", 404
    return flask_app.response_class(
        data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"})

@flask_app.route("/delete/<filename>", methods=["POST"])
def delete_csv(filename):
    allowed = ["DMLOG.CSV", "CHANNELS.CSV", "CONTACTS.CSV", "ENVLOG.CSV"]
    if filename not in allowed:
        return jsonify({"error": "Nicht erlaubt"}), 403
    header = CSV_HEADERS.get(filename, "")
    file_store.delete_file(filename, header=header)
    return jsonify({"message": f"{filename} geloescht und neu angelegt."})


# ============================================================
# APP-REFERENZ (fuer Import durch dm_listener.py)
# ============================================================
app = flask_app
