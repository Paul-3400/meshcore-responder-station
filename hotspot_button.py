"""
Hotspot-Steuerung per GPIO-Taster mit automatischem Timeout.
Taster GPIO17 (active low, Pull-Up), Status-LED GPIO27.
Druecken = Hotspot EIN (90 Min Timer), nochmal druecken = sofort AUS.
Verwendet gpiozero (kompatibel mit RPi OS Trixie/lgpio).
Erstellt von Paul (Brain Gym) mit Hilfe von Claude (Anthropic, 2026).
Repo: https://github.com/Paul-3400/meshcore-responder-station
Version: 2.3
"""

from gpiozero import Button, LED
from signal import pause
import subprocess
import threading
import time
import signal
import sys

# ============================================================
# KONFIGURATION
# ============================================================
BUTTON_PIN = 17          # GPIO17 (Pin 11) - Taster nach GND
LED_PIN = 27             # GPIO27 (Pin 13) - Status-LED
HOTSPOT_TIMEOUT = 90     # Minuten bis Auto-Abschaltung

# ============================================================
# GLOBALER STATUS
# ============================================================
hotspot_active = False
timer_thread = None

# ============================================================
# GPIO SETUP (gpiozero)
# ============================================================
button = Button(BUTTON_PIN, pull_up=True, bounce_time=0.3)
led = LED(LED_PIN)

# ============================================================
# HOTSPOT EIN/AUS
# ============================================================
def hotspot_start():
    """Stoppt NetworkManager, setzt IP, startet hostapd direkt + dnsmasq."""
    # NM komplett stoppen - gibt wlan0 frei
    subprocess.run(["sudo", "systemctl", "stop", "NetworkManager"], capture_output=True)
    time.sleep(2)
    # Statische IP fuer AP setzen
    subprocess.run(["sudo", "ip", "addr", "flush", "dev", "wlan0"], capture_output=True)
    subprocess.run(["sudo", "ip", "addr", "add", "10.0.50.1/24", "dev", "wlan0"], capture_output=True)
    subprocess.run(["sudo", "ip", "link", "set", "wlan0", "up"], capture_output=True)
    time.sleep(1)
    # hostapd DIREKT starten (nicht via systemctl!)
    subprocess.Popen(["sudo", "hostapd", "/etc/hostapd/hostapd.conf"])
    time.sleep(2)
    # dnsmasq via systemctl (das funktioniert)
    subprocess.run(["sudo", "systemctl", "start", "dnsmasq"], capture_output=True)
    led.on()
    ts = time.strftime("%H:%M:%S")
    print(f"\U0001f4e1 [{ts}] Hotspot EIN - AP: 10.0.50.1 - Timeout {HOTSPOT_TIMEOUT} Min")
    return True

def hotspot_stop():
    """Stoppt hostapd + dnsmasq, startet NetworkManager."""
    led.off()
    subprocess.run(["sudo", "pkill", "hostapd"], capture_output=True)
    subprocess.run(["sudo", "systemctl", "stop", "dnsmasq"], capture_output=True)
    time.sleep(1)
    # NM wieder starten - verbindet automatisch mit RoPa Net
    subprocess.run(["sudo", "systemctl", "start", "NetworkManager"], capture_output=True)
    ts = time.strftime("%H:%M:%S")
    print(f"\U0001f4f4 [{ts}] Hotspot AUS - NetworkManager gestartet")

# ============================================================
# TIMER - Automatische Abschaltung nach 90 Minuten
# ============================================================
def timeout_handler():
    """Wird nach Ablauf des Timers aufgerufen - schaltet Hotspot ab."""
    global hotspot_active, timer_thread
    if hotspot_active:
        ts = time.strftime("%H:%M:%S")
        print(f"\u23f0 [{ts}] Timeout erreicht ({HOTSPOT_TIMEOUT} Min) - schalte ab")
        hotspot_stop()
        hotspot_active = False
        timer_thread = None

def start_timer():
    """Startet den Abschalt-Timer."""
    global timer_thread
    cancel_timer()
    timer_thread = threading.Timer(HOTSPOT_TIMEOUT * 60, timeout_handler)
    timer_thread.daemon = True
    timer_thread.start()

def cancel_timer():
    """Bricht laufenden Timer ab."""
    global timer_thread
    if timer_thread is not None:
        timer_thread.cancel()
        timer_thread = None

# ============================================================
# TASTER-CALLBACK - Toggle Hotspot
# ============================================================
def button_pressed():
    """Wird bei Tastendruck aufgerufen. Toggled den Hotspot."""
    global hotspot_active
    if not hotspot_active:
        # --- Hotspot einschalten + Timer starten ---
        if hotspot_start():
            start_timer()
            hotspot_active = True
        # Falls False: nichts passiert, Pi bleibt im Client-Modus
    else:
        # --- Hotspot sofort ausschalten + Timer abbrechen ---
        cancel_timer()
        hotspot_stop()
        hotspot_active = False

# ============================================================
# SAUBERES BEENDEN (Ctrl+C oder systemd stop)
# ============================================================
def cleanup(signum, frame):
    """Raeumt auf bei Signal (SIGTERM/SIGINT)."""
    ts = time.strftime("%H:%M:%S")
    print(f"\n\U0001f6d1 [{ts}] Beende hotspot_button.py - raeume auf...")
    cancel_timer()
    if hotspot_active:
        hotspot_stop()
    led.off()
    sys.exit(0)

# ============================================================
# HAUPTPROGRAMM
# ============================================================
if __name__ == "__main__":
    ts = time.strftime("%H:%M:%S")
    print(f"\U0001f680 [{ts}] hotspot_button.py gestartet")
    print(f"   Taster: GPIO{BUTTON_PIN} | LED: GPIO{LED_PIN} | Timeout: {HOTSPOT_TIMEOUT} Min")

    # Signal-Handler fuer sauberes Beenden
    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    # Taster-Event registrieren (when_pressed = fallende Flanke)
    button.when_pressed = button_pressed

    # Warte auf Tastendruck
    print(f"   Warte auf Tastendruck...")
    pause()
