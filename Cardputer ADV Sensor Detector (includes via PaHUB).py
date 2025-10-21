# CardPuter ADV — Live I2C watcher with event feed + expanded fingerprint
# UIFlow2 MicroPython

import time
import M5
from M5 import Display
from machine import I2C, Pin

# ---------- CONFIG (CardPuter ADV HY2.0) ----------
# HY2.0: Yellow=G2 (SDA), White=G1 (SCL)  →  SDA=2, SCL=1
SDA_PIN = 2
SCL_PIN = 1
I2C_FREQ = 400_000

USE_PAHUB = True                 # set False if you’re not using PaHUB
PAHUB_ADDR = 0x70                # TCA/TCA9548A default
PAHUB_CHANNELS = list(range(6))  # 0..5
SCAN_INTERVAL_MS = 1000          # gentle & stable
EVENT_HISTORY_MAX = 10           # keep last N event lines

# If the screen is still 90° off on your unit, change 1 -> 3.
ROTATION = 1  # intended landscape for CardPuter ADV

# ---------- Expanded best-effort fingerprint ----------
# Notes:
# - Many addrs are shared by multiple devices; names are hints, not guarantees.
# - Add/remove as you discover more Units you care about.
FINGERPRINT = {
    0x11: "Unit MQ (Default)",
    0x20: "PCF8574 (IO expander)",
    0x21: "PCF8574 (IO expander)",
    0x23: "BH1750 (Light)",
    0x27: "LCD Backpack (PCF8574)",
    0x29: "TCS34725/VL53L0X (Color/ToF)",
    0x3C: "SSD1306 OLED",
    0x40: "INA219 / SI7021 / PCA9685",  # shared by several
    0x44: "SHT3x (Temp/Hum)",
    0x45: "SHT3x (Temp/Hum alt)",
    0x48: "ADS1115 / LM75",
    0x4A: "MCP4725 (DAC)",
    0x5A: "MLX90614 (IR Temp)",
    0x5C: "QMP6988 (Pressure)",
    0x57: "MAX3010x (Pulse/Ox)",
    0x58: "SGP30 (Air Quality)",
    0x59: "SGP41 (Air Quality)",
    0x60: "MCP4725/MCP23008 (varies)",
    0x62: "SCD4x (CO2L)",
    0x68: "MPU6050/RTC/IMU",
    0x69: "MPU/ICM IMU (alt)",
    0x6A: "IMU (MPU6886/ICM)",
    0x70: "PaHUB",
    0x76: "BME280/BMP280",
    0x77: "ENV Pro",
}

# ---------- INIT ----------
M5.begin()
Display.setRotation(ROTATION)
Display.clear(0x000000)
Display.setTextColor(0xFFFFFF, 0x000000)
Display.setCursor(0, 0)
Display.print("CardPuter ADV I2C watcher…")

i2c = I2C(0, scl=Pin(SCL_PIN), sda=Pin(SDA_PIN), freq=I2C_FREQ)

# ---------- PaHUB helpers ----------
def pahub_present():
    try:
        return PAHUB_ADDR in i2c.scan()
    except Exception:
        return False

def pahub_select_channel(ch: int) -> bool:
    try:
        i2c.writeto(PAHUB_ADDR, bytes([1 << ch]))  # select channel bit
        return True
    except Exception:
        return False

def pahub_disable_all():
    try:
        i2c.writeto(PAHUB_ADDR, b"\x00")
    except Exception:
        pass

# ---------- Scan ----------
def scan_base_bus():
    try:
        return set(i2c.scan())
    except Exception:
        return set()

def scan_pahub_channels(ch_list):
    out = {}
    for ch in ch_list:
        if not pahub_select_channel(ch):
            out[ch] = set()
            continue
        time.sleep_ms(10)  # tiny settle
        try:
            s = set(i2c.scan())
            # REMOVE the PaHUB’s own address (0x70) so it doesn’t clutter the channel output
            if PAHUB_ADDR in s:
                s.remove(PAHUB_ADDR)
            out[ch] = s
        except Exception:
            out[ch] = set()
    pahub_disable_all()
    return out


def name_for(addr: int) -> str:
    return FINGERPRINT.get(addr, "")

def fmt_addr_set(s):
    if not s:
        return "[]"
    parts = []
    for a in sorted(s):
        tag = name_for(a)
        parts.append(f"0x{a:02X}" + (f" ({tag})" if tag else ""))
    return "[" + ", ".join(parts) + "]"

# ---------- Event feed ----------
_event_lines = []

def push_event(line: str):
    global _event_lines
    ts = time.ticks_ms() // 1000  # seconds since boot
    entry = f"[{ts:>5}s] {line}"
    _event_lines.append(entry)
    if len(_event_lines) > EVENT_HISTORY_MAX:
        _event_lines = _event_lines[-EVENT_HISTORY_MAX:]

def diff_sets(scope: str, new: set, old: set):
    """Emit events for additions/removals: scope like 'base' or 'ch2'."""
    for a in sorted(new - old):
        tag = name_for(a)
        push_event(f"{scope} +0x{a:02X}" + (f" {tag}" if tag else ""))
    for a in sorted(old - new):
        tag = name_for(a)
        push_event(f"{scope} -0x{a:02X}" + (f" {tag}" if tag else ""))

# ---------- UI ----------
def draw_snapshot(snapshot):
    # snapshot = {"base": set(), "pahub": {ch:set()}, "hub_ok": bool}
    Display.clear(0x000000)
    y = 0
    line_h = 16

    def line(txt):
        nonlocal y
        Display.setCursor(0, y)
        Display.print(txt)
        y += line_h

    # Top: current state
    line("I2C Watcher — CardPuter ADV")
    line(f"Base: {fmt_addr_set(snapshot['base'])}")
    if USE_PAHUB:
        if snapshot["hub_ok"]:
            for ch in sorted(snapshot["pahub"].keys()):
                line(f"PaHUB ch{ch}: {fmt_addr_set(snapshot['pahub'][ch])}")
        else:
            line("PaHUB: not detected")

    # Divider
    y += 4
    Display.setCursor(0, y)
    Display.print("-" * 24)
    y += line_h

    # Event feed (most recent at bottom)
    line("Events (last {}):".format(EVENT_HISTORY_MAX))
    for ev in _event_lines[-EVENT_HISTORY_MAX:]:
        if y > 200:  # fit roughly on screen; trim if needed
            break
        line(ev)

    # Footer tip
    y += 4
    line("Tip: change ROTATION=1→3 if sideways.")

# ---------- Main loop ----------
def main():
    last_base = set()
    last_pahub = {ch: set() for ch in PAHUB_CHANNELS}
    hub_ok = pahub_present() if USE_PAHUB else False

    # Initial snapshot + draw
    base = scan_base_bus()
    if USE_PAHUB and hub_ok:
        pahub_map = scan_pahub_channels(PAHUB_CHANNELS)
    else:
        pahub_map = {}

    # Emit initial events relative to empty
    diff_sets("base", base, set())
    if USE_PAHUB and hub_ok:
        for ch in sorted(pahub_map.keys()):
            diff_sets(f"ch{ch}", pahub_map[ch], set())

    draw_snapshot({"base": base, "pahub": pahub_map, "hub_ok": hub_ok})
    last_base = base
    last_pahub = {ch: set(addrs) for ch, addrs in pahub_map.items()}

    # Loop
    while True:
        base = scan_base_bus()
        if USE_PAHUB:
            # (Re)detect PaHUB cheap check each loop
            hub_ok = pahub_present()
        pahub_map = scan_pahub_channels(PAHUB_CHANNELS) if (USE_PAHUB and hub_ok) else {}

        # Generate events on changes
        if base != last_base:
            diff_sets("base", base, last_base)
            last_base = base

        # Per-channel diffs
        if USE_PAHUB and hub_ok:
            all_channels = sorted(set(list(last_pahub.keys()) + list(pahub_map.keys())))
            for ch in all_channels:
                new_set = pahub_map.get(ch, set())
                old_set = last_pahub.get(ch, set())
                if new_set != old_set:
                    diff_sets(f"ch{ch}", new_set, old_set)
            last_pahub = {ch: set(v) for ch, v in pahub_map.items()}
        else:
            # If previously had channels, mark them as removed
            if any(last_pahub.values()):
                for ch, old_set in last_pahub.items():
                    if old_set:
                        diff_sets(f"ch{ch}", set(), old_set)
            last_pahub = {ch: set() for ch in PAHUB_CHANNELS}

        # Redraw on any change to current snapshot or if there were new events
        draw_snapshot({"base": base, "pahub": pahub_map, "hub_ok": hub_ok})

        time.sleep_ms(SCAN_INTERVAL_MS)

try:
    main()
except Exception as e:
    Display.clear(0x000000)
    Display.setCursor(0, 0)
    Display.print("Error:\n" + str(e))
