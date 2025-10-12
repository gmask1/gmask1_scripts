import os, sys, io
import M5
from M5 import *
import network
import requests2



label0 = None
wlan = None
http_req = None


key = None
JsonResponse = None
currentTempPath = None
currentTemp = None

# Describe this function...
def get_by_path():
  global key, JsonResponse, currentTempPath, currentTemp, label0, wlan, http_req
  for key in (currentTempPath):
    JsonResponse = JsonResponse[key]

  return JsonResponse


def setup():
  global label0, wlan, http_req, JsonResponse, currentTempPath, key, currentTemp

  M5.begin()
  Widgets.fillScreen(0x000000)
  label0 = Widgets.Label("label0", 130, 69, 1.0, 0xffffff, 0x222222, Widgets.FONTS.DejaVu18)

  wlan = network.WLAN(network.STA_IF)
  #you will need to enter your wifi details here:
  wlan.connect('WIFI_ID', 'PWD')
  #change the location in the http address below:
  http_req = requests2.get('https://wttr.in/Melbourne?format=j2', headers={'Content-Type': 'application/json'})
  currentTempPath = ('current_condition', 0, 'temp_C')
  JsonResponse = http_req.json()
  currentTemp = get_by_path()
  label0.setText(str(currentTemp))


def loop():
  global label0, wlan, http_req, JsonResponse, currentTempPath, key, currentTemp
  M5.update()


if __name__ == '__main__':
  try:
    setup()
    while True:
      loop()
  except (Exception, KeyboardInterrupt) as e:
    try:
      from utility import print_error_msg
      print_error_msg(e)
    except ImportError:
      print("please update to latest firmware")
