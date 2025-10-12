# ----- CardPuter (UIFlow 2 MicroPython) Text UI Demo (integer-color mode) -----

import time
import M5
from M5 import Display
try:
    from hardware import MatrixKeyboard
except ImportError:
    MatrixKeyboard = None

# ------------- Color constants (integer, 0xRRGGBB) -------------
BLACK = 0x000000
WHITE = 0xFFFFFF
GRAY  = 0xA0A0A0
CYAN  = 0x00C8C8
YELL  = 0xFFDC00
GREEN = 0x00DC00

# ------------- Display helpers ----------------
def init_display():
    M5.begin()
    Display.setTextSize(1)
    Display.fillScreen(BLACK)
    return Display

def clear(_=None, color=BLACK):
    # color must be integer
    Display.fillScreen(color)

def draw_text(_, x, y, s, color=WHITE):
    Display.setCursor(x, y)
    Display.setTextColor(color)
    Display.print(s)

# ------------- Keyboard (Option A: polling) -------------
# --- REPLACE your existing make_keyboard() with this version ---
def make_keyboard():
    if MatrixKeyboard is None:
        def poll_key(): return None
        def tick(): pass
        return poll_key, tick

    kb = MatrixKeyboard()

    # Integer keycodes -> names
    SPECIALS_INT = {
        13: "ENTER",   # CR
        10: "ENTER",   # LF (just in case)
        27: "ESC",     # Escape
        8:  "BACK",    # Backspace
        # Add arrow codes here once known; common values vary by build/mapper.
        # e.g., 0xB4: "UP", 0xB5: "DOWN", 0xB6: "LEFT", 0xB7: "RIGHT"
    }

    def normalize(v):
        if v is None:
            return None

        # Your CardPuter firmware returns integer ASCII codes
        if isinstance(v, int):
            # Common control keys
            if v == 13 or v == 10:
                return "ENTER"
            if v == 27:
                return "ESC"
            if v == 8:
                return "BACK"

            # Comma/period/slash/semicolon used as arrow keys
            if v == 44:  # ','
                return "LEFT"
            if v == 46:  # '.'
                return "DOWN"
            if v == 47:  # '/'
                return "RIGHT"
            if v == 59:  # ';'
                return "UP"

            # Printable ASCII
            if 32 <= v <= 126:
                c = chr(v)
                if c in "wW":
                    return "UP"
                if c in "sS":
                    return "DOWN"
                if c in "aA":
                    return "LEFT"
                if c in "dD":
                    return "RIGHT"
                return c
            return None

        # Handle possible string returns for compatibility
        if isinstance(v, str):
            if v in ("\r", "\n"):
                return "ENTER"
            if v == "\x1b":
                return "ESC"
            if v == "\x08":
                return "BACK"
            if v in ",./;":
                return {",": "LEFT", ".": "DOWN", "/": "RIGHT", ";": "UP"}[v]
            if len(v) == 1 and 32 <= ord(v) <= 126:
                c = v
                if c in "wW":
                    return "UP"
                if c in "sS":
                    return "DOWN"
                if c in "aA":
                    return "LEFT"
                if c in "dD":
                    return "RIGHT"
                return c

        return None

    def poll_key():
        kb.tick()
        v = kb.get_key()
        if v is not None and v != 0:
            nv = normalize(v)
            if nv:
                return nv

        # Optional buffered read if available (also int codes)
        if hasattr(kb, "get_string"):
            s = kb.get_string()
            if s:
                first = s[0]
                # first may be int or str depending on firmware
                nv = normalize(first if not isinstance(s, bytes) else first)
                if nv:
                    return nv
        return None

    def tick():
        kb.tick()

    return poll_key, tick


# ------------- UI Router, Screens, etc. (same as before) -------------
class Screen:
    def __init__(self, name, render_fn, handle_key_fn):
        self.name = name
        self.render = render_fn
        self.handle_key = handle_key_fn

class App:
    def __init__(self, disp):
        self.disp = disp
        self.screens = {}
        self.nav_stack = []
        self.active = None

    def register(self, key, screen: Screen):
        self.screens[key] = screen

    def push(self, key):
        if self.active:
            self.nav_stack.append(self.active)
        self.active = key
        self.redraw()

    def pop(self):
        if self.nav_stack:
            self.active = self.nav_stack.pop()
        else:
            self.active = "menu"
        self.redraw()

    def redraw(self):
        clear(self.disp)
        scr = self.screens[self.active]
        scr.render(self)

    def dispatch_key(self, k):
        if not self.active:
            return
        self.screens[self.active].handle_key(self, k)

# --- MENU ---
MENU_OPTIONS = ["Status", "Logs", "Settings"]
menu_index = 0

def menu_render(app: App):
    d = app.disp
    draw_text(d, 6, 6, "CardPuter Demo", CYAN)
    draw_text(d, 6, 22, "Use UP/DOWN (W/S), ENTER", GRAY)
    draw_text(d, 6, 32, "ESC to exit a screen", GRAY)
    y = 52
    for i, opt in enumerate(MENU_OPTIONS):
        prefix = "-> " if i == menu_index else "   "
        color = YELL if i == menu_index else WHITE
        draw_text(d, 6, y, prefix + opt, color)
        y += 12

def menu_handle_key(app: App, k):
    global menu_index
    if k == "DOWN":
        menu_index = (menu_index + 1) % len(MENU_OPTIONS)
        app.redraw()
    elif k == "UP":
        menu_index = (menu_index - 1) % len(MENU_OPTIONS)
        app.redraw()
    elif k == "ENTER":
        choice = MENU_OPTIONS[menu_index].lower()
        app.push(choice)
    elif k in ("ESC", "BACK"):
        pass

menu_screen = Screen("menu", menu_render, menu_handle_key)

# --- STATUS ---
def status_render(app: App):
    d = app.disp
    draw_text(d, 6, 6, "Status", CYAN)
    draw_text(d, 6, 24, "Demo metrics:", WHITE)
    draw_text(d, 6, 42, "CPU: (stub)", WHITE)
    draw_text(d, 6, 54, "Temp: (stub)", WHITE)
    draw_text(d, 6, 78, "[ESC] Back", GRAY)

def status_handle_key(app: App, k):
    if k in ("ESC", "BACK"):
        app.pop()

status_screen = Screen("status", status_render, status_handle_key)

# --- LOGS ---
logs_buffer = [
    "System boot OK",
    "WiFi: disconnected",
    "RTC: set to demo",
    "App started",
    "Press ESC to go back",
]
logs_top = 0

def logs_render(app: App):
    d = app.disp
    draw_text(d, 6, 6, "Logs", CYAN)
    max_lines = 7
    y = 24
    for i in range(max_lines):
        idx = logs_top + i
        if 0 <= idx < len(logs_buffer):
            draw_text(d, 6, y, logs_buffer[idx], WHITE)
        y += 12
    draw_text(d, 6, 120, "[UP/DOWN] Scroll  [ESC] Back", GRAY)

def logs_handle_key(app: App, k):
    global logs_top
    if k == "DOWN":
        if logs_top + 1 < max(0, len(logs_buffer) - 1):
            logs_top += 1
            app.redraw()
    elif k == "UP":
        if logs_top > 0:
            logs_top -= 1
            app.redraw()
    elif k in ("ESC", "BACK"):
        app.pop()
    elif isinstance(k, str) and len(k) == 1 and 32 <= ord(k) <= 126:
        logs_buffer.append("Key: " + k)
        app.redraw()

logs_screen = Screen("logs", logs_render, logs_handle_key)

# --- SETTINGS ---
settings_items = [
    ("Brightness", 5, 0, 10),
    ("Mode", 0, 0, 2),
    ("WiFi", 0, 0, 1),
]
settings_index = 0

def settings_render(app: App):
    d = app.disp
    draw_text(d, 6, 6, "Settings", CYAN)
    draw_text(d, 6, 22, "LEFT/RIGHT to change", GRAY)
    y = 40
    for i, (name, val, lo, hi) in enumerate(settings_items):
        selector = "-> " if i == settings_index else "   "
        color = GREEN if i == settings_index else WHITE
        draw_text(d, 6, y, f"{selector}{name}: {val}", color)
        y += 12
    draw_text(d, 6, 120, "[UP/DOWN] Select  [ESC] Back", GRAY)

def settings_handle_key(app: App, k):
    global settings_index, settings_items
    if k == "DOWN":
        settings_index = (settings_index + 1) % len(settings_items)
        app.redraw()
    elif k == "UP":
        settings_index = (settings_index - 1) % len(settings_items)
        app.redraw()
    elif k == "RIGHT":
        name, val, lo, hi = settings_items[settings_index]
        val = min(hi, val + 1)
        settings_items[settings_index] = (name, val, lo, hi)
        app.redraw()
    elif k == "LEFT":
        name, val, lo, hi = settings_items[settings_index]
        val = max(lo, val - 1)
        settings_items[settings_index] = (name, val, lo, hi)
        app.redraw()
    elif k in ("ESC", "BACK"):
        app.pop()

settings_screen = Screen("settings", settings_render, settings_handle_key)

# ------------- Main ----------------
def main():
    disp = init_display()

    app = App(disp)
    app.register("menu", menu_screen)
    app.register("status", status_screen)
    app.register("logs", logs_screen)
    app.register("settings", settings_screen)

    poll_key, kb_tick = make_keyboard()

    app.push("menu")

    while True:
        k = poll_key()
        if k:
            app.dispatch_key(k)
        time.sleep_ms(20)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
