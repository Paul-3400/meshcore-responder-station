#!/usr/bin/env python3
"""
file_store.py - Lokaler Dateispeicher fuer CSV-Logs.
Ersetzt sdcard_writer.py (SPI SD-Karte) durch normales Filesystem.
Erstellt von Paul (Brain Gym) mit Hilfe von Claude (Anthropic, 2026).
Repo: https://github.com/Paul-3400/meshcore-responder-station
"""
import os
from datetime import datetime

# ============================================================
# DATENVERZEICHNIS (relativ zum Script)
# ============================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")


def init_data_dir():
    """Erstellt data/-Verzeichnis falls nicht vorhanden."""
    os.makedirs(DATA_DIR, exist_ok=True)


def _filepath(filename):
    """Gibt den vollen Pfad zu einer Datei im data/-Verzeichnis zurueck."""
    return os.path.join(DATA_DIR, filename)


# ============================================================
# BACKUP + RESET (beim Boot)
# ============================================================
def backup_and_reset(filename, header):
    """Benennt alte Datei in JJMMDD_filename_backup um,
    legt neue Datei mit Header an.

    Format Backup-Name: JJMMDD_FILENAME_backup
    Beispiel: 260620_DMLOG.CSV_backup
    """
    path = _filepath(filename)

    # Falls alte Datei existiert → umbenennen
    if os.path.exists(path):
        date_prefix = datetime.now().strftime("%y%m%d")
        backup_name = f"{date_prefix}_{filename}_backup"
        backup_path = _filepath(backup_name)
        # Falls Backup vom selben Tag schon existiert → ueberschreiben
        if os.path.exists(backup_path):
            os.remove(backup_path)
        os.rename(path, backup_path)

    # Neue Datei mit Header anlegen
    with open(path, 'w') as f:
        f.write(header)


# ============================================================
# DATEIZUGRIFF (Lesen, Schreiben, Loeschen)
# ============================================================
def append_to_file(filename, text):
    """Text an Datei anhaengen. Erstellt Datei falls noetig."""
    path = _filepath(filename)
    with open(path, 'a') as f:
        f.write(text)


def read_file(filename):
    """Datei komplett lesen. Returns String oder None."""
    path = _filepath(filename)
    if not os.path.exists(path):
        return None
    with open(path, 'r') as f:
        return f.read()


def delete_file(filename, header=None):
    """Datei loeschen und optional mit Header neu anlegen."""
    path = _filepath(filename)
    if os.path.exists(path):
        os.remove(path)
    # Falls Header angegeben → sofort neue leere Datei mit Header
    if header:
        with open(path, 'w') as f:
            f.write(header)


def file_exists(filename):
    """Prueft ob Datei existiert."""
    return os.path.exists(_filepath(filename))


def get_file_size(filename):
    """Dateigroesse in Bytes. Returns 0 wenn nicht vorhanden."""
    path = _filepath(filename)
    if os.path.exists(path):
        return os.path.getsize(path)
    return 0
