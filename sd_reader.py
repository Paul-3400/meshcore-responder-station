#!/usr/bin/env python3
"""
sd_reader.py - Liest CSV-Dateien von der Raw-SD-Karte am Mac.

Verwendung:
  python3 sd_reader.py                # Status anzeigen
  python3 sd_reader.py DMLOG.CSV      # Datei auf Konsole ausgeben
  python3 sd_reader.py DMLOG.CSV -o   # Datei lokal speichern
  python3 sd_reader.py --all          # Alle Dateien exportieren

WICHTIG: Muss mit sudo ausgefuehrt werden!
  sudo python3 sd_reader.py
"""

import sys
import os
import struct
import subprocess

# Konstanten (identisch mit sdcard_writer.py)
MAGIC = b"PLOG"
HEADER_SIZE = 16
SLOT_SIZE = 48
NUM_SLOTS = 6
BLOCK_SIZE = 512


def find_sd_device():
    """SD-Karte als Raw-Block-Device finden (macOS)."""
    result = subprocess.run(
        ["diskutil", "list", "external"],
        capture_output=True, text=True
    )

    devices = []
    for line in result.stdout.split("\n"):
        if "/dev/disk" in line:
            dev = line.strip().split()[0]
            devices.append(dev)

    if not devices:
        return None

    # Jedes Device pruefen ob PLOG-Magic vorhanden
    for dev in devices:
        raw_dev = dev.replace("/dev/disk", "/dev/rdisk")
        try:
            with open(raw_dev, "rb") as f:
                block0 = f.read(BLOCK_SIZE)
                if len(block0) >= 4 and block0[:4] == MAGIC:
                    return raw_dev
        except (PermissionError, FileNotFoundError, OSError):
            continue

    # Nichts gefunden - erstes externes Device zurueckgeben
    # (User kann manuell pruefen)
    if devices:
        raw = devices[0].replace("/dev/disk", "/dev/rdisk")
        return raw

    return None


def read_superblock(device):
    """Superblock lesen und Slots parsen."""
    with open(device, "rb") as f:
        block0 = f.read(BLOCK_SIZE)

    if block0[:4] != MAGIC:
        print(f"\nFEHLER: Kein gueltiger PLOG-Superblock auf {device}!")
        print(f"  Erste 4 Bytes: {block0[:4]}")
        print(f"  Erwartet: {MAGIC}")
        print("\n  Ist die richtige Karte eingesteckt?")
        sys.exit(1)

    version = struct.unpack_from("<H", block0, 4)[0]
    num_slots = struct.unpack_from("<H", block0, 6)[0]

    slots = []
    for i in range(num_slots):
        offset = HEADER_SIZE + i * SLOT_SIZE
        name = block0[offset:offset + 16].split(b"\x00")[0].decode("ascii")
        start_block = struct.unpack_from("<I", block0, offset + 16)[0]
        max_blocks = struct.unpack_from("<I", block0, offset + 20)[0]
        current_block = struct.unpack_from("<I", block0, offset + 24)[0]
        byte_offset = struct.unpack_from("<I", block0, offset + 28)[0]
        size_low = struct.unpack_from("<I", block0, offset + 32)[0]
        size_high = struct.unpack_from("<I", block0, offset + 36)[0]
        total_size = (size_high << 32) | size_low

        slots.append({
            "name": name,
            "start_block": start_block,
            "max_blocks": max_blocks,
            "current_block": current_block,
            "byte_offset": byte_offset,
            "total_size": total_size,
        })

    return version, slots


def read_file_from_sd(device, slot):
    """Datei-Inhalt aus Raw-Blocks lesen."""
    if slot["total_size"] == 0:
        return ""

    start = slot["start_block"]
    current = slot["current_block"]
    byte_off = slot["byte_offset"]
    total = slot["total_size"]

    content = bytearray()
    remaining = total

    with open(device, "rb") as f:
        block_num = start
        while remaining > 0 and block_num <= current:
            f.seek(block_num * BLOCK_SIZE)
            data = f.read(BLOCK_SIZE)
            if not data:
                break
            if block_num == current:
                to_read = min(byte_off, remaining)
            else:
                to_read = min(BLOCK_SIZE, remaining)
            content.extend(data[:to_read])
            remaining -= to_read
            block_num += 1

    return content.decode("utf-8", errors="replace")


def format_size(size):
    if size < 1024:
        return f"{size} B"
    elif size < 1048576:
        return f"{size/1024:.1f} KB"
    elif size < 1073741824:
        return f"{size/1048576:.1f} MB"
    else:
        return f"{size/1073741824:.2f} GB"


def show_status(device, version, slots):
    """Status-Tabelle anzeigen."""
    print(f"\n  SD-Karte: {device}")
    print(f"  Format: PLOG v{version}")
    print(f"  {'─' * 56}")
    print(f"  {'Slot':<5}{'Datei':<16}{'Groesse':<12}"
          f"{'Bloecke':<10}{'Voll%'}")
    print(f"  {'─' * 56}")
    for i, slot in enumerate(slots):
        if not slot["name"]:
            print(f"  {i+1:<5}(leer)")
            continue
        blocks_used = slot["current_block"] - slot["start_block"]
        percent = (blocks_used / slot["max_blocks"]) * 100
        print(f"  {i+1:<5}{slot['name']:<16}"
              f"{format_size(slot['total_size']):<12}"
              f"{blocks_used:<10}{percent:.4f}%")
    print()


def main():
    # Root-Check
    if os.geteuid() != 0:
        print("\n  HINWEIS: Zugriff auf Raw-Device braucht Root-Rechte!")
        print("  Bitte mit sudo ausfuehren:")
        print("    sudo python3 ~/Scripts/sd_reader.py\n")
        sys.exit(1)

    # Device finden
    print("\n  Suche SD-Karte...")
    device = find_sd_device()

    if not device:
        print("\n  Keine externe SD-Karte gefunden!")
        print("  Ist die Karte eingesteckt?\n")
        sys.exit(1)

    print(f"  Gefunden: {device}")

    # Superblock lesen
    version, slots = read_superblock(device)

    # Argumente verarbeiten
    if len(sys.argv) < 2 or sys.argv[1] == "--status":
        show_status(device, version, slots)
        return

    if sys.argv[1] == "--all":
        os.makedirs("sd_export", exist_ok=True)
        exported = 0
        for slot in slots:
            if not slot["name"] or slot["total_size"] == 0:
                continue
            content = read_file_from_sd(device, slot)
            outpath = os.path.join("sd_export", slot["name"])
            with open(outpath, "w") as f:
                f.write(content)
            print(f"    {slot['name']} -> sd_export/{slot['name']} "
                  f"({format_size(slot['total_size'])})")
            exported += 1
        print(f"\n  {exported} Datei(en) exportiert nach ./sd_export/\n")
        return

    # Einzelne Datei
    filename = sys.argv[1].upper()
    slot = None
    for s in slots:
        if s["name"] == filename:
            slot = s
            break

    if not slot:
        print(f"\n  Datei '{filename}' nicht gefunden!")
        print("  Vorhandene Dateien:")
        for s in slots:
            if s["name"]:
                print(f"    - {s['name']}")
        print()
        sys.exit(1)

    content = read_file_from_sd(device, slot)

    if "-o" in sys.argv:
        with open(filename, "w") as f:
            f.write(content)
        print(f"\n  Gespeichert: {filename} "
              f"({format_size(slot['total_size'])})\n")
    else:
        print(f"\n  --- {filename} ({format_size(slot['total_size'])}) ---\n")
        print(content)


if __name__ == "__main__":
    main()

