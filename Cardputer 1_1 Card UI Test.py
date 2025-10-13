# CardPuter Card UI (Paginated Panels) with Top-Right Dots Indicator (spaced)
# - LEFT/RIGHT to change cards; ENTER opens stub "details" view, ENTER again returns.

import M5
from M5 import Display
from hardware import MatrixKeyboard
import time

# --- Screen / Input ---
Display.setRotation(1)
W, H = 240, 135
BG = 0x101015
kb = MatrixKeyboard()

# --- Cards ---
cards = [
    {"title": "System",  "bg": 0x1E2A78, "text": ["CPU Temp: <stub>", "Battery: <stub>"]},
    {"title": "Network", "bg": 0x174A7A, "text": ["Wi-Fi: <stub>", "IP: <stub>"]},
    {"title": "Logs",    "bg": 0x6B3E2E, "text": ["Last event: <stub>", "Count: <stub>"]},
    {"title": "Stats",   "bg": 0x1C7C54, "text": ["Load: <stub>", "Mem: <stub>"]},
]
index = 0

# --- Dots Indicator (top-right) ---
DOT_R   = 3      # radius of each dot
DOT_GAP = 10     # center-to-center distance (added spacing)
DOT_Y   = 9      # vertical position for dots
RIGHT_PAD = 10   # distance from right edge

def draw_dots(pos, total, bg_color):
    # compute total width of all dots so we can right-align nicely
    width = (total - 1) * DOT_GAP
    x_right = W - RIGHT_PAD
    x0 = x_right - width
    # clear a small strip behind dots to avoid artifacts when switching bg colors
    clear_w = RIGHT_PAD + width + DOT_R + 2
    Display.fillRect(W - clear_w, DOT_Y - DOT_R - 1, clear_w, DOT_R*2 + 2, bg_color)

    # draw dots: filled for current index, hollow for others
    for i in range(total):
        cx = x0 + i * DOT_GAP
        if i == pos:
            Display.fillCircle(cx, DOT_Y, DOT_R, 0xFFFFFF)
        else:
            Display.drawCircle(cx, DOT_Y, DOT_R, 0xFFFFFF)

def draw_card(i):
    c = cards[i]
    Display.fillRect(0, 0, W, H, c["bg"])

    # Header
    Display.setTextColor(0xFFFFFF, c["bg"])
    Display.setTextSize(1)
    Display.setCursor(10, 6)
    Display.print(f"{c['title']}  ({i+1}/{len(cards)})")
    draw_dots(i, len(cards), c["bg"])

    # Body
    y = 32
    for line in c["text"]:
        Display.setCursor(20, y)
        Display.print(line)
        y += 16

    # Footer hint
    Display.setCursor(10, H-14)
    Display.print("← / → navigate   ⏎ details")

def open_detail(i):
    c = cards[i]
    base = 0x20262C
    Display.fillRect(0, 0, W, H, base)
    Display.setTextColor(0xFFFFFF, base)
    Display.setTextSize(1)
    Display.setCursor(10, 6)
    Display.print(f"{c['title']} details")
    Display.fillRect(10, 22, W-20, H-42, 0x0C0F12)
    Display.drawRect(10, 22, W-20, H-42, 0xFFFFFF)

    # Per-card stub content
    Display.setCursor(16, 30)
    if c["title"] == "System":
        Display.print("- CPU/Temp meters (stub)")
    elif c["title"] == "Network":
        Display.print("- Wi-Fi scan/connect (stub)")
    elif c["title"] == "Logs":
        Display.print("- Recent events list (stub)")
    elif c["title"] == "Stats":
        Display.print("- Load/Mem graphs (stub)")
    Display.setCursor(10, H-14)
    Display.print("Press ⏎ to go back")

    # Wait to return
    while True:
        kb.tick()
        k = kb.get_key()
        if k in (13, 10, 32):  # Enter/Space
            break
        time.sleep(0.01)

    draw_card(index)

# Initial draw
draw_card(index)

# Main loop
while True:
    kb.tick()
    k = kb.get_key()
    if k is None:
        time.sleep(0.01)
        continue

    if k in (44, 65, 97):     # LEFT  ',' or A/a
        index = (index - 1) % len(cards)
        draw_card(index)
    elif k in (47, 68, 100):  # RIGHT '/' or D/d
        index = (index + 1) % len(cards)
        draw_card(index)
    elif k in (13, 10, 32):   # ENTER/SPACE
        open_detail(index)

    time.sleep(0.01)
