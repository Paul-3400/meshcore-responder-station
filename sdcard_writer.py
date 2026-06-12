"""
sdcard_writer.py - Raw Multi-File SD-Card Writer
6 Bereiche a ~5GB auf 32GB Karte.
CS auf GPIO25 (Pin 22), manuell via lgpio.
Superblock auf Block 0 + Backup auf Block 1.

Hardware: MH-SD Card Module an RPi Zero 2W (3.3V)
"""

import spidev
import lgpio
import time
import struct

# ============================================================
# KONSTANTEN
# ============================================================

MAGIC = b"PLOG"
VERSION = 1
NUM_SLOTS = 6
SLOT_SIZE = 48
HEADER_SIZE = 16
BLOCKS_PER_AREA = 10000000
ADMIN_BLOCKS = 100
SUPERBLOCK_PRIMARY = 0
SUPERBLOCK_BACKUP = 1

AREA_STARTS = [
    ADMIN_BLOCKS + i * BLOCKS_PER_AREA for i in range(NUM_SLOTS)
]


# ============================================================
# KLASSE
# ============================================================

class SDCardWriter:
    """Raw Multi-File SD-Card Writer mit 6 Bereichen."""

    CS_PIN = 25
    SPI_BUS = 0
    SPI_DEV = 0
    SPI_SPEED = 400000

    def __init__(self):
        """SD-Karte init, Superblock laden oder erstellen."""
        self.h = None
        self.spi = None
        self.superblock = None
        self._init_hardware()
        self._init_sd()

    # --------------------------------------------------------
    # Hardware / SPI
    # --------------------------------------------------------

    def _init_hardware(self):
        self.h = lgpio.gpiochip_open(0)
        try:
            lgpio.gpio_free(self.h, self.CS_PIN)
        except Exception:
            pass
        try:
            lgpio.gpio_claim_output(self.h, self.CS_PIN, 1)
        except Exception:
            lgpio.gpiochip_close(self.h)
            time.sleep(0.1)
            self.h = lgpio.gpiochip_open(0)
            lgpio.gpio_claim_output(self.h, self.CS_PIN, 1)
        self.spi = spidev.SpiDev()
        self.spi.open(self.SPI_BUS, self.SPI_DEV)
        self.spi.max_speed_hz = self.SPI_SPEED
        self.spi.mode = 0
        self.spi.no_cs = True

    def _cs_low(self):
        lgpio.gpio_write(self.h, self.CS_PIN, 0)

    def _cs_high(self):
        lgpio.gpio_write(self.h, self.CS_PIN, 1)
        self.spi.xfer2([0xFF])

    def _send_cmd(self, cmd, arg=0, crc=0xFF):
        self.spi.xfer2([0xFF])
        self.spi.xfer2([
            0x40 | cmd,
            (arg >> 24) & 0xFF,
            (arg >> 16) & 0xFF,
            (arg >> 8) & 0xFF,
            arg & 0xFF,
            crc
        ])
        for _ in range(16):
            r = self.spi.xfer2([0xFF])[0]
            if r != 0xFF:
                return r
        return 0xFF

    def _wait_not_busy(self, timeout=10000):
        for _ in range(timeout):
            if self.spi.xfer2([0xFF])[0] == 0xFF:
                return True
            time.sleep(0.001)
        return False

    # --------------------------------------------------------
    # SD Init
    # --------------------------------------------------------

    def _init_sd(self):
        """SD-Karte initialisieren + Superblock laden/erstellen."""
        # Aufwaermen
        self._cs_high()
        self.spi.xfer2([0xFF] * 10)
        time.sleep(0.1)

        # CMD0
        self._cs_low()
        self._send_cmd(0, 0, 0x95)
        self._cs_high()
        time.sleep(0.01)

        # CMD8
        self._cs_low()
        r = self._send_cmd(8, 0x1AA, 0x87)
        if r <= 1:
            self.spi.xfer2([0xFF] * 4)
        self._cs_high()
        time.sleep(0.01)

        # ACMD41
        for attempt in range(200):
            self._cs_low()
            self._send_cmd(55, 0, 0xFF)
            self._cs_high()
            time.sleep(0.001)
            self._cs_low()
            r = self._send_cmd(41, 0x40000000, 0xFF)
            self._cs_high()
            if r == 0:
                break
            time.sleep(0.05)
        else:
            raise RuntimeError("SD Init TIMEOUT")

        time.sleep(0.2)

        # CMD58 (informativ)
        self._cs_low()
        r = self._send_cmd(58)
        if r == 0:
            self.spi.xfer2([0xFF] * 4)
        self._cs_high()

        # Superblock laden oder erstellen
        self._load_or_create_superblock()

    # --------------------------------------------------------
    # Block-Level I/O
    # --------------------------------------------------------

    def _read_block(self, block):
        """512 Bytes lesen. Returns list oder None."""
        self._cs_low()
        r = self._send_cmd(17, block)
        if r != 0:
            self._cs_high()
            return None
        for _ in range(1000):
            if self.spi.xfer2([0xFF])[0] == 0xFE:
                data = self.spi.xfer2([0xFF] * 512)
                self.spi.xfer2([0xFF, 0xFF])
                self._cs_high()
                return data
        self._cs_high()
        return None

    def _write_block(self, block, data):
        """512 Bytes schreiben. Returns True/False."""
        if len(data) < 512:
            data = list(data) + [0x00] * (512 - len(data))
        self._cs_low()
        r = self._send_cmd(24, block)
        if r != 0:
            self._cs_high()
            return False
        self.spi.xfer2([0xFF])
        self.spi.xfer2([0xFE])
        self.spi.xfer2(list(data))
        self.spi.xfer2([0xFF, 0xFF])
        dr = self.spi.xfer2([0xFF])[0]
        if dr == 0x00:
            pass  # Busy = akzeptiert
        elif (dr & 0x1F) != 0x05:
            self._cs_high()
            return False
        ok = self._wait_not_busy()
        self._cs_high()
        return ok

    # --------------------------------------------------------
    # Superblock Management
    # --------------------------------------------------------

    def _create_superblock(self):
        """Neuen leeren Superblock erstellen."""
        sb = bytearray(512)
        sb[0:4] = MAGIC
        struct.pack_into("<H", sb, 4, VERSION)
        struct.pack_into("<H", sb, 6, NUM_SLOTS)
        for i in range(NUM_SLOTS):
            offset = HEADER_SIZE + i * SLOT_SIZE
            struct.pack_into("<I", sb, offset + 16, AREA_STARTS[i])
            struct.pack_into("<I", sb, offset + 20, BLOCKS_PER_AREA)
            struct.pack_into("<I", sb, offset + 24, AREA_STARTS[i])
            struct.pack_into("<I", sb, offset + 28, 0)
            struct.pack_into("<I", sb, offset + 32, 0)
            struct.pack_into("<I", sb, offset + 36, 0)
        self.superblock = sb
        self._save_superblock()

    def _load_or_create_superblock(self):
        """Superblock laden oder neu erstellen."""
        data = self._read_block(SUPERBLOCK_PRIMARY)
        if data and bytes(data[0:4]) == MAGIC:
            self.superblock = bytearray(data)
            return

        # Backup versuchen
        data = self._read_block(SUPERBLOCK_BACKUP)
        if data and bytes(data[0:4]) == MAGIC:
            self.superblock = bytearray(data)
            self._write_block(SUPERBLOCK_PRIMARY, list(self.superblock))
            return

        # Neu erstellen
        self._create_superblock()

    def _save_superblock(self):
        """Superblock auf Block 0 + Backup Block 1 schreiben."""
        data = list(self.superblock)
        self._write_block(SUPERBLOCK_PRIMARY, data)
        time.sleep(0.01)
        self._write_block(SUPERBLOCK_BACKUP, data)

    # --------------------------------------------------------
    # Slot-Verwaltung
    # --------------------------------------------------------

    def _get_slot(self, filename):
        """Slot-Index fuer Dateiname. Returns 0-5 oder None."""
        name_bytes = filename.upper().encode("ascii")[:15]
        for i in range(NUM_SLOTS):
            offset = HEADER_SIZE + i * SLOT_SIZE
            slot_name = bytes(self.superblock[offset:offset + 16])
            slot_name = slot_name.split(b"\x00")[0]
            if slot_name == name_bytes:
                return i
        return None

    def _get_free_slot(self):
        """Naechsten freien Slot. Returns 0-5 oder None."""
        for i in range(NUM_SLOTS):
            offset = HEADER_SIZE + i * SLOT_SIZE
            if self.superblock[offset] == 0x00:
                return i
        return None

    def _read_slot(self, slot_idx):
        """Slot-Daten als dict."""
        offset = HEADER_SIZE + slot_idx * SLOT_SIZE
        sb = self.superblock
        name = bytes(sb[offset:offset + 16]).split(b"\x00")[0]
        return {
            "name": name.decode("ascii"),
            "start_block": struct.unpack_from("<I", sb, offset + 16)[0],
            "max_blocks": struct.unpack_from("<I", sb, offset + 20)[0],
            "current_block": struct.unpack_from("<I", sb, offset + 24)[0],
            "byte_offset": struct.unpack_from("<I", sb, offset + 28)[0],
            "size_low": struct.unpack_from("<I", sb, offset + 32)[0],
            "size_high": struct.unpack_from("<I", sb, offset + 36)[0],
        }

    def _update_slot(self, slot_idx, current_block, byte_offset, added):
        """Slot im RAM-Superblock aktualisieren."""
        offset = HEADER_SIZE + slot_idx * SLOT_SIZE
        sb = self.superblock
        struct.pack_into("<I", sb, offset + 24, current_block)
        struct.pack_into("<I", sb, offset + 28, byte_offset)
        size_low = struct.unpack_from("<I", sb, offset + 32)[0]
        size_high = struct.unpack_from("<I", sb, offset + 36)[0]
        total = (size_high << 32) | size_low
        total += added
        struct.pack_into("<I", sb, offset + 32, total & 0xFFFFFFFF)
        struct.pack_into("<I", sb, offset + 36, (total >> 32) & 0xFFFFFFFF)

    # --------------------------------------------------------
    # Public API
    # --------------------------------------------------------

    def register_file(self, filename):
        """Datei registrieren. Macht nichts falls schon vorhanden."""
        if self._get_slot(filename) is not None:
            return True

        slot_idx = self._get_free_slot()
        if slot_idx is None:
            return False

        offset = HEADER_SIZE + slot_idx * SLOT_SIZE
        name_bytes = filename.upper().encode("ascii")[:15]
        for i, b in enumerate(name_bytes):
            self.superblock[offset + i] = b

        self._save_superblock()
        return True

    def append_to_file(self, filename, text):
        """Text an Datei anhaengen. Registriert automatisch."""
        slot_idx = self._get_slot(filename)
        if slot_idx is None:
            if not self.register_file(filename):
                return False
            slot_idx = self._get_slot(filename)

        slot = self._read_slot(slot_idx)
        current_block = slot["current_block"]
        byte_offset = slot["byte_offset"]
        start_block = slot["start_block"]
        max_blocks = slot["max_blocks"]

        text_bytes = text.encode("utf-8")
        written = 0

        while written < len(text_bytes):
            if current_block >= start_block + max_blocks:
                return False  # Bereich voll

            if byte_offset == 0:
                block = [0x00] * 512
            else:
                block = self._read_block(current_block)
                if not block:
                    block = [0x00] * 512
                else:
                    block = list(block)

            space = 512 - byte_offset
            chunk = text_bytes[written:written + space]
            for i, b in enumerate(chunk):
                block[byte_offset + i] = b

            if not self._write_block(current_block, block):
                return False

            written += len(chunk)
            byte_offset += len(chunk)

            if byte_offset >= 512:
                current_block += 1
                byte_offset = 0

        self._update_slot(slot_idx, current_block, byte_offset, len(text_bytes))
        self._save_superblock()
        return True

    def read_file(self, filename):
        """Datei komplett lesen. Returns String oder None."""
        slot_idx = self._get_slot(filename)
        if slot_idx is None:
            return None

        slot = self._read_slot(slot_idx)
        start = slot["start_block"]
        current = slot["current_block"]
        byte_off = slot["byte_offset"]
        total_size = slot["size_low"] | (slot["size_high"] << 32)

        if total_size == 0:
            return ""

        content = bytearray()
        remaining = total_size
        block_num = start

        while remaining > 0 and block_num <= current:
            data = self._read_block(block_num)
            if not data:
                break
            if block_num == current:
                to_read = min(byte_off, remaining)
            else:
                to_read = min(512, remaining)
            content.extend(data[:to_read])
            remaining -= to_read
            block_num += 1

        return content.decode("utf-8", errors="replace")

    def get_status(self):
        """Status aller Slots ausgeben."""
        print("\n--- SD-Card Status ---")
        print(f"{'Slot':<5}{'Datei':<16}{'Groesse':<12}"
              f"{'Blocks used':<14}{'Voll%'}")
        print("-" * 55)
        for i in range(NUM_SLOTS):
            slot = self._read_slot(i)
            if not slot["name"]:
                print(f"  {i+1:<3} (leer)")
                continue
            total = slot["size_low"] | (slot["size_high"] << 32)
            blocks_used = slot["current_block"] - slot["start_block"]
            percent = (blocks_used / slot["max_blocks"]) * 100
            if total < 1024:
                size_str = f"{total} B"
            elif total < 1048576:
                size_str = f"{total/1024:.1f} KB"
            else:
                size_str = f"{total/1048576:.1f} MB"
            print(f"  {i+1:<3} {slot['name']:<16}{size_str:<12}"
                  f"{blocks_used:<14}{percent:.4f}%")
        print()

    def close(self):
        """SPI und GPIO freigeben."""
        if self.spi:
            self.spi.close()
            self.spi = None
        if self.h:
            lgpio.gpiochip_close(self.h)
            self.h = None


# ============================================================
# SELBSTTEST
# ============================================================

if __name__ == "__main__":
    print("=== SDCardWriter Selbsttest ===\n")

    try:
        sd = SDCardWriter()
        print("Init OK\n")

        sd.append_to_file("DMLOG.CSV",
                          "timestamp,sender,key,text,path,hops,status\n")
        sd.append_to_file("DMLOG.CSV",
                          "2026-06-11 10:00,TestUser,abc123,Hallo,direct,0,replied\n")
        sd.append_to_file("DMLOG.CSV",
                          "2026-06-11 10:01,Paul,def456,Test,via_xy,1,replied\n")

        sd.append_to_file("PACKETS.CSV",
                          "timestamp,type,from,rssi\n")
        sd.append_to_file("PACKETS.CSV",
                          "2026-06-11 10:00,ADVERT,Node1,-85\n")

        sd.get_status()

        print("--- DMLOG.CSV ---")
        content = sd.read_file("DMLOG.CSV")
        if content:
            print(content)

        print("--- PACKETS.CSV ---")
        content = sd.read_file("PACKETS.CSV")
        if content:
            print(content)

        sd.close()
        print("=== FERTIG ===")

    except Exception as e:
        print(f"FEHLER: {e}")
        import traceback
        traceback.print_exc()
