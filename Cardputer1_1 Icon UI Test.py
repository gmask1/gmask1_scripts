# CardPuter 2x3 Icon Grid with Detail Pages (no animations) — UIFlow 2 / MicroPython
# - Screen: 240x135, rotation=1 (landscape)
# - Colors: 0xRRGGBB ints
# - Keyboard: MatrixKeyboard.get_key() returns integer ASCII codes
#   Arrows: ','=LEFT(44), '.'=DOWN(46), '/'=RIGHT(47), ';'=UP(59)
#   WASD also supported; Enter/Space select; ESC or Enter returns from detail

import M5
from M5 import Display
from hardware import MatrixKeyboard
import time

# ---------- Display / Input ----------
Display.setRotation(1)  # 240x135 landscape
W, H = 240, 135
BG = 0x101015
Display.clear(BG)
kb = MatrixKeyboard()

# ---------- Key helpers (ASCII) ----------
K = {
    "LEFT":  [44, 65, 97],     # ',' or 'A'/'a'
    "RIGHT": [47, 68, 100],    # '/' or 'D'/'d'
    "UP":    [59, 87, 119],    # ';' or 'W'/'w'
    "DOWN":  [46, 83, 115],    # '.' or 'S'/'s'
    "ENTER": [13, 10, 32],     # Enter, newline, Space
    "ESC":   [27, 113],        # ESC, 'q'
}
def key_in(code, names):
    if code is None:
        return False
    for n in names:
        if code in K[n]:
            return True
    return False

# ---------- Grid & Tiles (2 x 3) ----------
COLS, ROWS = 3, 2
TILE_W, TILE_H = 70, 52
GAP_X, GAP_Y = 15, 10
TITLE_H = 14

total_w = COLS * TILE_W + (COLS - 1) * GAP_X
total_h = ROWS * TILE_H + (ROWS - 1) * GAP_Y
start_x = (W - total_w) // 2
start_y = ((H - TITLE_H) - total_h) // 2 + TITLE_H  # push grid below title

tiles = [
    {"label": "Settings", "bg": 0x1E2A78, "icon": "gear"},
    {"label": "Stats",    "bg": 0x1C7C54, "icon": "chart"},
    {"label": "Files",    "bg": 0x8344AD, "icon": "folder"},
    {"label": "Network",  "bg": 0x174A7A, "icon": "chart"},
    {"label": "Logs",     "bg": 0x6B3E2E, "icon": "folder"},
    {"label": "About",    "bg": 0x7A8A2F, "icon": "gear"},
]
focus = 0  # index 0..5

def idx_to_rc(i):
    return i // COLS, i % COLS

def rc_to_idx(r, c):
    return r * COLS + c

def tile_coords(i):
    r, c = idx_to_rc(i)
    x = start_x + c * (TILE_W + GAP_X)
    y = start_y + r * (TILE_H + GAP_Y)
    return x, y

# ---------- Vector icons ----------
def draw_gear(cx, cy, r, color):
    Display.drawCircle(cx, cy, r, color)
    Display.drawCircle(cx, cy, r-4, color)
    for dx,dy in [(0,-r+2),(0,r-2),(-r+2,0),(r-2,0)]:
        Display.drawLine(cx, cy, cx+dx, cy+dy, color)
    t = r + 3
    pts = [(cx,cy-t),(cx+t,cy),(cx,cy+t),(cx-t,cy)]
    for i in range(len(pts)):
        x1,y1 = pts[i]
        x2,y2 = pts[(i+1)%len(pts)]
        Display.drawLine(x1,y1,x2,y2,color)

def draw_chart(x, y, w, h, color):
    Display.drawLine(x+6, y+h-8, x+w-6, y+h-8, color)   # x-axis
    Display.drawLine(x+6, y+10,   x+6,   y+h-8, color)   # y-axis
    bw = (w-20)//3
    bx = x+10
    heights = [h//3, h//2, (h*2)//3]
    for i,hv in enumerate(heights):
        Display.fillRect(bx + i*(bw+5), y+h-8-hv, bw, hv, color)
        Display.drawRect(bx + i*(bw+5), y+h-8-hv, bw, hv, 0xFFFFFF)

def draw_folder(x, y, w, h, color):
    tab_w, tab_h = w//3, h//5
    Display.fillRect(x, y+tab_h, w, h-tab_h, color)
    Display.fillRect(x+6, y, tab_w, tab_h, color)
    Display.drawRect(x, y+tab_h, w, h-tab_h, 0xFFFFFF)
    Display.drawRect(x+6, y, tab_w, tab_h, 0xFFFFFF)

def draw_icon(kind, x, y, w, h):
    if kind == "gear":
        cx = x + w//2
        cy = y + h//2 - 6
        r = min(w,h)//5 + 6
        draw_gear(cx, cy, r, 0xFFFFFF)
    elif kind == "chart":
        draw_chart(x+10, y+12, w-20, h-26, 0xFFFFFF)
    elif kind == "folder":
        draw_folder(x+10, y+16, w-20, h-30, 0xFFFFFF)

# ---------- Drawing ----------
def draw_title():
    Display.setTextColor(0xFFFFFF, BG)
    Display.setTextSize(1)  # size=1 as you preferred
    Display.fillRect(0, 0, W, TITLE_H, BG)
    Display.setCursor(12, 3)
    Display.print("Launcher")

def draw_tile(i, focused=False):
    x, y = tile_coords(i)
    bg = tiles[i]["bg"]
    # clear tile area (including any old focus ring)
    Display.fillRect(x-4, y-4, TILE_W+8, TILE_H+8, BG)
    # shadow
    Display.fillRect(x+2, y+3, TILE_W, TILE_H, 0x000000)
    # body
    Display.fillRect(x, y, TILE_W, TILE_H, bg)
    # focus ring
    if focused:
        Display.drawRect(x-2, y-2, TILE_W+4, TILE_H+4, 0xFFFFFF)
        Display.drawRect(x-3, y-3, TILE_W+6, TILE_H+6, 0xFFFFFF)
    # icon + label
    draw_icon(tiles[i]["icon"], x, y, TILE_W, TILE_H)
    Display.fillRect(x, y+TILE_H-18, TILE_W, 18, 0x000000)
    Display.setCursor(x+6, y+TILE_H-15)
    Display.setTextColor(0xFFFFFF, 0x000000)
    Display.setTextSize(1)
    Display.print(tiles[i]["label"])

def draw_grid(initial=False):
    if initial:
        Display.clear(BG)
        draw_title()
    for i in range(len(tiles)):
        draw_tile(i, focused=(i == focus))

def update_focus(prev_i, new_i):
    if prev_i == new_i:
        return
    draw_tile(prev_i, focused=False)
    draw_tile(new_i,  focused=True)

# ---------- Focus movement ----------
def move_left(i):
    r, c = idx_to_rc(i)
    c = (c - 1) % COLS
    return rc_to_idx(r, c)

def move_right(i):
    r, c = idx_to_rc(i)
    c = (c + 1) % COLS
    return rc_to_idx(r, c)

def move_up(i):
    r, c = idx_to_rc(i)
    r = (r - 1) % ROWS
    return rc_to_idx(r, c)

def move_down(i):
    r, c = idx_to_rc(i)
    r = (r + 1) % ROWS
    return rc_to_idx(r, c)

# ---------- Detail page helpers ----------
def draw_detail_chrome(title):
    base = 0x20262C
    Display.fillRect(0, 0, W, H, base)
    # header
    Display.setTextColor(0xFFFFFF, base)
    Display.setTextSize(1)
    Display.setCursor(10, 6)
    Display.print(title)
    # content box
    Display.fillRect(10, 22, W-20, H-42, 0x0C0F12)
    Display.drawRect(10, 22, W-20, H-42, 0xFFFFFF)
    # hint
    Display.setCursor(10, H-14)
    Display.print("Enter/ESC: Back")

# ---- Stub handlers (jumping-off points) ----
def handle_settings():
    draw_detail_chrome("Settings")
    # TODO: add real controls here (e.g., toggles, list items)
    Display.setCursor(16, 30)
    Display.print("- WiFi: <stub>")
    Display.setCursor(16, 44)
    Display.print("- Brightness: <stub>")
    Display.setCursor(16, 58)
    Display.print("- Sound: <stub>")

def handle_stats():
    draw_detail_chrome("Stats")
    Display.setCursor(16, 30)
    Display.print("CPU: <stub>")
    Display.setCursor(16, 44)
    Display.print("Temp: <stub>")
    Display.setCursor(16, 58)
    Display.print("Battery: <stub>")

def handle_files():
    draw_detail_chrome("Files")
    Display.setCursor(16, 30)
    Display.print("/flash: <stub>")
    Display.setCursor(16, 44)
    Display.print("/sd: <stub>")

def handle_network():
    draw_detail_chrome("Network")
    Display.setCursor(16, 30)
    Display.print("Scan: <stub>")
    Display.setCursor(16, 44)
    Display.print("Connect: <stub>")

def handle_logs():
    draw_detail_chrome("Logs")
    Display.setCursor(16, 30)
    Display.print("Recent events: <stub>")

def handle_about():
    draw_detail_chrome("About")
    Display.setCursor(16, 30)
    Display.print("CardPuter UI Demo")
    Display.setCursor(16, 44)
    Display.print("Version: 0.1")

HANDLERS = [
    handle_settings,
    handle_stats,
    handle_files,
    handle_network,
    handle_logs,
    handle_about,
]

def open_detail(index):
    # Call the tile-specific stub, then wait for Enter/ESC to return
    HANDLERS[index]()
    while True:
        kb.tick()
        k = kb.get_key()
        if key_in(k, ["ENTER", "ESC"]):
            break
        time.sleep(0.01)
    # Redraw launcher after return
    draw_grid(initial=True)

# ---------- Main ----------
draw_grid(initial=True)

last_move = 0
DEBOUNCE_MS = 90

while True:
    kb.tick()
    k = kb.get_key()
    now = time.ticks_ms()

    if k is None:
        time.sleep(0.01)
        continue

    prev = focus
    acted = False

    if key_in(k, ["LEFT"]) and time.ticks_diff(now, last_move) > DEBOUNCE_MS:
        focus = move_left(focus); acted = True
    elif key_in(k, ["RIGHT"]) and time.ticks_diff(now, last_move) > DEBOUNCE_MS:
        focus = move_right(focus); acted = True
    elif key_in(k, ["UP"]) and time.ticks_diff(now, last_move) > DEBOUNCE_MS:
        focus = move_up(focus); acted = True
    elif key_in(k, ["DOWN"]) and time.ticks_diff(now, last_move) > DEBOUNCE_MS:
        focus = move_down(focus); acted = True
    elif key_in(k, ["ENTER"]):
        open_detail(focus)    # ← open the tile's detail page
        acted = True

    if acted:
        update_focus(prev, focus)
        last_move = now

    time.sleep(0.01)
