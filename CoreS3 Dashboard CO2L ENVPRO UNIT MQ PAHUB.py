# CoreS3 + PaHub + CO2L + ENV PRO + MQ  (UIFlow2 MicroPython, LVGL/msui)
# October 2025 — binding-agnostic + backpressure-safe + legends & badges

import M5
from M5 import *
import time
import lvgl as lv
import m5ui

from hardware import I2C, Pin
from unit import CO2LUnit, ENVPROUnit, MQUnit, PAHUBUnit

# ----------------------------
# Configuration
# ----------------------------
# I2C0 on CoreS3 Port A
I2C_SCL_PIN = 1
I2C_SDA_PIN = 2
I2C_FREQ    = 100_000

# PaHub channels (0..5). Adjust to your wiring.
PAHUB_CO2L_CH   = 0
PAHUB_ENVPRO_CH = 2
PAHUB_MQ_CH     = 1

# Optional explicit addresses (None = driver default)
ADDR_CO2L   = None  # scd41 ~0x62
ADDR_ENVPRO = None  # bme688 ~0x77
ADDR_MQ     = None  # 0x11

# Sampling periods (ms)
PERIOD_CO2L_MS   = 5_000
PERIOD_ENVPRO_MS = 1_000
PERIOD_MQ_MS     = 1_000

# --- Performance & pacing ---
FRAME_MS         = 60      # ~16-17 FPS max UI work
UI_THROTTLE_MS   = 200     # don't update labels/charts more frequently per sensor
RANGE_REFRESH_MS = 1200    # how often to try rescaling chart Y
HISTORY_LEN      = 40      # lighter on LVGL

_last_ui = {"co2": 0, "env": 0, "mq": 0}

# ----------------------------
# Globals
# ----------------------------
i2c0 = None
co2l = None
envp = None
mq   = None

# UI containers & widgets
page_root = tabview = None
tab_dash = tab_co2 = tab_env = tab_mq = None

# Dashboard widgets
dash_title = dash_co2 = dash_temp = dash_hum = dash_press = dash_mq = None

# CO2L widgets
co2_title = co2_co2 = co2_temp = co2_hum = co2_status = None
co2_chart = co2_series = None
co2_history = []
co2_legend = co2_badge = None

# ENV widgets
env_title = env_temp = env_hum = env_press = env_gas = None
env_chart = env_temp_ser = env_hum_ser = env_press_ser = None
env_hist_temp = []
env_hist_hum  = []
env_hist_press= []
env_legend = env_badge = None

# MQ widgets
mq_title = mq_valid = mq_adc8 = mq_adc12 = None
mq_chart = mq_series = None
mq_history = []
mq_legend = mq_badge = None
# (If you ever want both MQ signals:)
# mq_series8 = None

# timers
t0 = t1 = t2 = 0


# ----------------------------
# Utilities
# ----------------------------
def now_ms():
    return time.ticks_ms()

def elapsed_ms(since):
    return time.ticks_diff(now_ms(), since)

def append_with_limit(arr, v, limit=HISTORY_LEN):
    arr.append(v)
    if len(arr) > limit:
        del arr[0:len(arr)-limit]

# ASCII sanitizer for fonts without certain glyphs
_REPLACE_MAP = {
    "₂": "2", "₃": "3", "₄": "4",
    "Ω": "Ohm", "µ": "u",
    "²": "^2", "³": "^3",
    "–": "-", "—": "-", "…": "...",
    # If ° causes tofu on your build, swap to " deg"
}
def safe_text(s: str) -> str:
    return "".join(_REPLACE_MAP.get(ch, ch) for ch in s)

def set_text_if_changed(label, s):
    s = safe_text(s)
    last = getattr(label, "_last", None)
    if last != s:
        label.set_text(s)
        label._last = s

def set_label_color(label, hexcolor):
    r = (hexcolor >> 16) & 0xFF
    g = (hexcolor >> 8)  & 0xFF
    b = (hexcolor)       & 0xFF
    try:
        label.set_text_color(r, g, b, 255); return
    except TypeError:
        pass
    try:
        label.set_text_color(r, g, b); return
    except TypeError:
        pass
    try:
        label.set_text_color(lv.color_hex(hexcolor))
    except Exception:
        pass

def _gate(kind):
    now = time.ticks_ms()
    if time.ticks_diff(now, _last_ui[kind]) < UI_THROTTLE_MS:
        return False
    _last_ui[kind] = now
    return True

# CO2 bands (ppm) for color/status
CO2_BANDS = [
    (0,    800,  0x22CC22, "Good"),
    (800,  1200, 0xE6A600, "Fair"),
    (1200, 2000, 0xCC5522, "Poor"),
    (2000, 5000, 0xCC2233, "Very Poor"),
]
def co2_band(ppm: int):
    for lo, hi, color, label in CO2_BANDS:
        if lo <= ppm < hi:
            return color, label
    return 0x888888, "Unknown"


# ----------------------------
# Chart helpers (binding-agnostic + backpressure-aware)
# ----------------------------
_CHART_STATE = {}  # {id(chart): {"can_range": bool, "norm_min": int, "norm_max": int, "last_rng_ms": int}}

def _try_set_chart_range(chart, axis, ymin, ymax):
    try:
        if hasattr(chart, "set_range"):
            chart.set_range(axis, int(ymin), int(ymax)); return True
    except: pass
    try:
        if hasattr(chart, "set_y_range"):
            chart.set_y_range(int(ymin), int(ymax)); return True
    except: pass
    try:
        if hasattr(chart, "set_axis_range"):
            chart.set_axis_range(axis, int(ymin), int(ymax)); return True
    except: pass
    return False

def _append_chart_value(chart, series, v):
    if hasattr(chart, "set_next_value"):
        try:
            chart.set_next_value(series, v); return
        except: pass
    if hasattr(lv.chart, "set_next_value"):
        try:
            lv.chart.set_next_value(chart, series, v); return
        except: pass
    if hasattr(series, "add_point"):
        try:
            series.add_point(v); return
        except: pass
    # else silently drop

def _should_refresh_range(st, ymin, ymax):
    now = time.ticks_ms()
    if st["last_rng_ms"] is None:
        return True
    dt = time.ticks_diff(now, st["last_rng_ms"])
    if dt >= RANGE_REFRESH_MS:
        return True
    prev_span = (st["norm_max"] - st["norm_min"]) or 1
    new_span  = (ymax - ymin) or 1
    if new_span > prev_span * 1.2 or new_span < prev_span * 0.8:
        return True
    return False

def chart_append_point(chart, series, value, y_min=None, y_max=None, history=None):
    cid = id(chart)
    st = _CHART_STATE.get(cid)
    if st is None:
        st = {"can_range": None, "norm_min": 0, "norm_max": 100, "last_rng_ms": None}
        _CHART_STATE[cid] = st

    # desired bounds
    if history and len(history) > 0:
        ymin = min(history); ymax = max(history)
    else:
        v = int(value)
        ymin = v if y_min is None else y_min
        ymax = v if y_max is None else y_max
    if ymin == ymax:
        ymin -= 1; ymax += 1

    if st["can_range"] is None:
        st["can_range"] = _try_set_chart_range(chart, lv.chart.AXIS.PRIMARY_Y, ymin, ymax)
        st["norm_min"], st["norm_max"] = ymin, ymax
        st["last_rng_ms"] = time.ticks_ms()

    if st["can_range"]:
        if _should_refresh_range(st, ymin, ymax):
            if _try_set_chart_range(chart, lv.chart.AXIS.PRIMARY_Y, ymin, ymax):
                st["norm_min"], st["norm_max"] = ymin, ymax
                st["last_rng_ms"] = time.ticks_ms()
        v_plot = int(value)
    else:
        # normalize 0..100
        span = (ymax - ymin) or 1
        v_plot = int((int(value) - ymin) * 100 / span)
        if v_plot < 0: v_plot = 0
        if v_plot > 100: v_plot = 100

    _append_chart_value(chart, series, v_plot)


# ----------------------------
# Hardware setup
# ----------------------------
def setup_i2c_and_units():
    global i2c0, co2l, envp, mq
    i2c0 = I2C(0, scl=Pin(I2C_SCL_PIN), sda=Pin(I2C_SDA_PIN), freq=I2C_FREQ)

    hub_ch_co2   = PAHUBUnit(i2c=i2c0, channel=PAHUB_CO2L_CH)
    hub_ch_env   = PAHUBUnit(i2c=i2c0, channel=PAHUB_ENVPRO_CH)
    hub_ch_mq    = PAHUBUnit(i2c=i2c0, channel=PAHUB_MQ_CH)

    # CO2L
    try:
        co2l = CO2LUnit(hub_ch_co2) if ADDR_CO2L is None else CO2LUnit(hub_ch_co2, ADDR_CO2L)
        # stop-if-running to avoid "block cannot be executed while periodic is running"
        try:
            if hasattr(co2l, "set_stop_periodic_measurement"):
                co2l.set_stop_periodic_measurement()
                time.sleep_ms(500)
        except Exception:
            pass
        try:
            if hasattr(co2l, "set_start_periodic_measurement"):
                co2l.set_start_periodic_measurement()
        except Exception as e:
            # ignore "already running" messages
            if "running" not in str(e).lower():
                raise
    except Exception as e:
        print("CO2L init failed:", e)
        co2l = None

    # ENV PRO
    try:
        envp = ENVPROUnit(hub_ch_env) if ADDR_ENVPRO is None else ENVPROUnit(hub_ch_env, ADDR_ENVPRO)
    except Exception as e:
        print("ENVPRO init failed:", e)
        envp = None

    # MQ
    try:
        mq = MQUnit(hub_ch_mq) if ADDR_MQ is None else MQUnit(hub_ch_mq, ADDR_MQ)
        mq.set_mq_mode(1)  # continuous heater
    except Exception as e:
        print("MQ init failed:", e)
        mq = None


# ----------------------------
# UI
# ----------------------------
def make_label(parent, text, x, y, font=lv.font_montserrat_16, color=0x000000):
    lbl = m5ui.M5Label(safe_text(text), x=x, y=y, text_c=color, bg_c=0xFFFFFF, bg_opa=0,
                       font=font, parent=parent)
    lbl._last = None
    return lbl

def make_title(parent, text):
    lbl = m5ui.M5Label(safe_text(text), x=12, y=10, text_c=0x000000, bg_c=0xFFFFFF, bg_opa=0,
                       font=lv.font_montserrat_16, parent=parent)
    lbl._last = None
    return lbl

def make_chart(parent, x, y, w, h):
    chart = lv.chart(parent)
    chart.set_size(w, h); chart.set_pos(x, y)
    chart.set_update_mode(lv.chart.UPDATE_MODE.CIRCULAR)
    chart.set_point_count(HISTORY_LEN)
    chart.set_div_line_count(2, 3)
    series = chart.add_series(lv.color_hex(0x000000), lv.chart.AXIS.PRIMARY_Y)
    return chart, series

def build_ui():
    global page_root, tabview, tab_dash, tab_co2, tab_env, tab_mq
    global dash_title, dash_co2, dash_temp, dash_hum, dash_press, dash_mq
    global co2_title, co2_co2, co2_temp, co2_hum, co2_status, co2_chart, co2_series, co2_legend, co2_badge
    global env_title, env_temp, env_hum, env_press, env_gas, env_chart, env_temp_ser, env_hum_ser, env_press_ser, env_legend, env_badge
    global mq_title, mq_valid, mq_adc8, mq_adc12, mq_chart, mq_series, mq_legend, mq_badge
    # global mq_series8  # if plotting both MQ signals

    Widgets.setRotation(1)  # landscape
    m5ui.init()
    page_root = m5ui.M5Page(bg_c=0xFFFFFF)

    # IMPORTANT: single-argument constructor on this firmware
    tabview   = lv.tabview(page_root)
    tabview.set_size(320, 240)
    tab_dash = tabview.add_tab("Dashboard")
    tab_co2  = tabview.add_tab("CO2L")
    tab_env  = tabview.add_tab("ENV Pro")
    tab_mq   = tabview.add_tab("MQ")

    # Dashboard
    dash_title = make_title(tab_dash, "Air Monitor")
    dash_co2   = make_label(tab_dash, "CO2: -- ppm", 12, 48, lv.font_montserrat_16)
    dash_temp  = make_label(tab_dash, "Temp: -- C",  12, 80)
    dash_hum   = make_label(tab_dash, "Hum:  -- %",  12, 108)
    dash_press = make_label(tab_dash, "Press: -- hPa", 12, 136)
    dash_mq    = make_label(tab_dash, "MQ ADC: --",  12, 164)

    # CO2 tab
    co2_title   = make_title(tab_co2, "CO2L (SCD41)")
    co2_co2     = make_label(tab_co2, "CO2: -- ppm", 12, 54, lv.font_montserrat_16)
    co2_temp    = make_label(tab_co2, "Temp: -- C",  12, 82)
    co2_hum     = make_label(tab_co2, "Hum:  -- %",  12, 110)
    co2_status  = make_label(tab_co2, "Status: waiting...", 12, 138)
    co2_chart, co2_series = make_chart(tab_co2, 160, 46, 148, 140)
    co2_legend  = make_label(tab_co2, "Plot: CO2 (ppm)", 162, 28, lv.font_montserrat_14)
    co2_badge   = make_label(tab_co2, "—", 312, 46, lv.font_montserrat_14)
    try:
        co2_series.set_style_line_color(lv.color_hex(0x222222), 0)
    except Exception:
        pass

    # ENV tab
    env_title   = make_title(tab_env, "ENV Pro (BME688)")
    env_temp    = make_label(tab_env, "Temp: -- C",  12, 54)
    env_hum     = make_label(tab_env,  "Hum:  -- %", 12, 82)
    env_press   = make_label(tab_env, "Press: -- hPa", 12, 110)
    env_gas     = make_label(tab_env,   "Gas:  -- Ohm", 12, 138)
    env_chart, env_temp_ser = make_chart(tab_env, 160, 46, 148, 140)
    env_hum_ser   = env_chart.add_series(lv.color_hex(0x000000), lv.chart.AXIS.PRIMARY_Y)
    env_press_ser = env_chart.add_series(lv.color_hex(0x000000), lv.chart.AXIS.PRIMARY_Y)
    env_legend = make_label(tab_env, "Plot: Temp/Hum/Press", 162, 28, lv.font_montserrat_14)
    env_badge  = make_label(tab_env, "—", 312, 46, lv.font_montserrat_14)
    try:
        env_temp_ser.set_style_line_color(lv.color_hex(0xAA0000), 0)  # red-ish
        env_hum_ser.set_style_line_color(lv.color_hex(0x0066AA), 0)   # blue-ish
        env_press_ser.set_style_line_color(lv.color_hex(0x008844), 0) # green-ish
    except Exception:
        pass

    # MQ tab
    mq_title = make_title(tab_mq, "MQ Unit")
    mq_valid = make_label(tab_mq, "Valid: --", 12, 54)
    mq_adc8  = make_label(tab_mq, "ADC(8b): --", 12, 82)
    mq_adc12 = make_label(tab_mq, "ADC(12b): --", 12, 110)
    mq_chart, mq_series = make_chart(tab_mq, 160, 46, 148, 140)
    mq_legend = make_label(tab_mq, "Plot: MQ (12-bit ADC)", 162, 28, lv.font_montserrat_14)
    mq_badge  = make_label(tab_mq, "—", 312, 46, lv.font_montserrat_14)
    try:
        mq_series.set_style_line_color(lv.color_hex(0x222222), 0)
    except Exception:
        pass

    # (If you want to plot both MQ signals:)
    # global mq_series8
    # mq_series8 = mq_chart.add_series(lv.color_hex(0x777777), lv.chart.AXIS.PRIMARY_Y)
    # set_text_if_changed(mq_legend, "Plot: MQ (8b + 12b)")

    page_root.screen_load()


# ----------------------------
# Pollers
# ----------------------------
def poll_co2l():
    if co2l is None:
        set_text_if_changed(co2_status, "Status: Not available")
        return

    # readiness check (method name may vary)
    ready = False
    try:
        if hasattr(co2l, "is_data_ready"):
            ready = co2l.is_data_ready()
        elif hasattr(co2l, "data_isready"):
            ready = co2l.data_isready()
    except:
        ready = False

    if not ready:
        set_text_if_changed(co2_status, "Status: Waiting...")
        return

    # read measurement
    try:
        ppm    = int(getattr(co2l, "co2", -1))
        temp_c = float(getattr(co2l, "temperature", float("nan")))
        rh     = float(getattr(co2l, "humidity", float("nan")))
        if ppm < 0 or str(temp_c) == "nan":
            co2l.get_sensor_measurement()
            ppm    = int(getattr(co2l, "co2", -1))
            temp_c = float(getattr(co2l, "temperature", float("nan")))
            rh     = float(getattr(co2l, "humidity", float("nan")))
    except Exception:
        set_text_if_changed(co2_status, "Status: Read error")
        return

    if not _gate("co2"):
        return

    color, label = co2_band(ppm)
    set_text_if_changed(co2_co2, f"CO2: {ppm} ppm")
    set_label_color(co2_co2, color)
    set_text_if_changed(co2_temp, f"Temp: {temp_c:.1f} C")
    set_text_if_changed(co2_hum,  f"Hum:  {rh:.1f} %")
    set_text_if_changed(co2_status, f"Status: {label}")

    set_text_if_changed(dash_co2, f"CO2: {ppm} ppm")

    append_with_limit(co2_history, ppm)
    chart_append_point(co2_chart, co2_series, ppm, history=co2_history)
    set_text_if_changed(co2_badge, f"{ppm}")


def poll_envpro():
    if envp is None:
        set_text_if_changed(env_temp, "Temp: -- (not available)")
        return

    try:
        t = float(envp.get_temperature())
        h = float(envp.get_humidity())
        p = float(envp.get_pressure())
        g = None
        if hasattr(envp, "get_gas_resistance"):
            try:
                g = float(envp.get_gas_resistance())
            except:
                g = None
    except Exception:
        return

    if not _gate("env"):
        return

    set_text_if_changed(env_temp,  f"Temp: {t:.1f} C")
    set_text_if_changed(env_hum,   f"Hum:  {h:.1f} %")
    set_text_if_changed(env_press, f"Press: {p:.1f} hPa")
    set_text_if_changed(env_gas,   f"Gas:  {g:.0f} Ohm" if g is not None else "Gas:  --")

    set_text_if_changed(dash_temp,  f"Temp: {t:.1f} C")
    set_text_if_changed(dash_hum,   f"Hum:  {h:.1f} %")
    set_text_if_changed(dash_press, f"Press: {p:.1f} hPa")

    append_with_limit(env_hist_temp, t)
    append_with_limit(env_hist_hum,  h)
    append_with_limit(env_hist_press, p)

    merged = (env_hist_temp + env_hist_hum + env_hist_press) or [0]
    ymin, ymax = min(merged), max(merged)
    if ymin == ymax:
        ymin -= 1; ymax += 1

    chart_append_point(env_chart, env_temp_ser,  t, y_min=ymin, y_max=ymax, history=env_hist_temp)
    chart_append_point(env_chart, env_hum_ser,   h, y_min=ymin, y_max=ymax, history=env_hist_hum)
    chart_append_point(env_chart, env_press_ser, p, y_min=ymin, y_max=ymax, history=env_hist_press)

    # Badge shows the first (Temp) series' current value
    set_text_if_changed(env_badge, f"{t:.1f} C")


def poll_mq():
    if mq is None:
        set_text_if_changed(mq_valid, "Valid: -- (not available)")
        return

    try:
        valid = mq.get_valid_tags()
        adc8  = mq.get_adc_value(0)
        adc12 = mq.get_adc_value(1)
    except Exception:
        return

    if not _gate("mq"):
        return

    set_text_if_changed(mq_valid, f"Valid: {valid}")
    set_text_if_changed(mq_adc8,  f"ADC(8b): {adc8}")
    set_text_if_changed(mq_adc12, f"ADC(12b): {adc12}")
    set_text_if_changed(dash_mq,  f"MQ ADC: {adc12}")

    # Plot ONLY 12-bit by default (steady line). To plot 8-bit instead, swap adc12->adc8.
    append_with_limit(mq_history, int(adc12))
    chart_append_point(mq_chart, mq_series, int(adc12), history=mq_history)
    set_text_if_changed(mq_badge, f"{adc12}")

    # (If plotting both signals)
    # chart_append_point(mq_chart, mq_series8, int(adc8), history=mq_history)
    # set_text_if_changed(mq_badge, f"12b:{adc12}  8b:{adc8}")


# ----------------------------
# Main
# ----------------------------
def setup():
    global t0, t1, t2
    M5.begin()
    Widgets.fillScreen(0xFFFFFF)
    setup_i2c_and_units()
    build_ui()

    # Stagger first polls
    now = now_ms()
    t0 = now - PERIOD_CO2L_MS + 250
    t1 = now - PERIOD_ENVPRO_MS + 500
    t2 = now - PERIOD_MQ_MS + 750

def loop():
    global t0, t1, t2
    frame_start = time.ticks_ms()

    M5.update()  # allow m5ui/port to drain schedule queue

    if elapsed_ms(t0) >= PERIOD_CO2L_MS:
        t0 = now_ms()
        poll_co2l()

    if elapsed_ms(t1) >= PERIOD_ENVPRO_MS:
        t1 = now_ms()
        poll_envpro()

    if elapsed_ms(t2) >= PERIOD_MQ_MS:
        t2 = now_ms()
        poll_mq()

    # Frame pacing
    elapsed = time.ticks_diff(time.ticks_ms(), frame_start)
    to_sleep = FRAME_MS - elapsed
    if to_sleep > 0:
        time.sleep_ms(to_sleep)
    else:
        time.sleep_ms(1)


if __name__ == "__main__":
    try:
        setup()
        while True:
            loop()
    except (Exception, KeyboardInterrupt) as e:
        try:
            m5ui.deinit()
        except Exception:
            pass
        raise
