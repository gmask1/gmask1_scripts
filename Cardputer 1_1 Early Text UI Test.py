import os, sys, io
import M5
from M5 import *
from hardware import MatrixKeyboard



label0 = None
label1 = None
label2 = None
label3 = None
label4 = None
label5 = None
label6 = None
label7 = None
label8 = None
label9 = None
label10 = None
label11 = None
kb = None


keyPress = None
optionNumber = None

# Describe this function...
def setMainMenu():
  global keyPress, optionNumber, label0, label1, label2, label3, label4, label5, label6, label7, label8, label9, label10, label11, kb
  clearscreen()
  label0.setText(str('Option 1'))
  label1.setText(str('Option 2'))
  label2.setText(str('Option 3'))
  label3.setText(str('>'))
  label4.setText(str(' '))
  label5.setText(str(' '))

# Describe this function...
def clearscreen():
  global keyPress, optionNumber, label0, label1, label2, label3, label4, label5, label6, label7, label8, label9, label10, label11, kb
  label0.setColor(0xffffff, 0x000000)
  label0.setText(str(' '))
  label1.setColor(0xffffff, 0x000000)
  label1.setText(str(' '))
  label2.setColor(0xffffff, 0x000000)
  label2.setText(str(' '))
  label3.setColor(0xffffff, 0x000000)
  label3.setText(str(' '))
  label4.setColor(0xffffff, 0x000000)
  label4.setText(str(' '))
  label5.setColor(0xffffff, 0x000000)
  label5.setText(str(' '))
  label6.setColor(0xffffff, 0x000000)
  label6.setText(str(' '))
  label7.setColor(0xffffff, 0x000000)
  label7.setText(str(' '))
  label8.setColor(0xffffff, 0x000000)
  label8.setText(str(' '))
  label9.setColor(0xffffff, 0x000000)
  label9.setText(str(' '))
  label10.setColor(0xffffff, 0x000000)
  label10.setText(str(' '))
  label11.setColor(0xffffff, 0x000000)
  label11.setText(str(' '))


def kb_pressed_event(kb_0):
  global label0, label1, label2, label3, label4, label5, label6, label7, label8, label9, label10, label11, kb, keyPress, optionNumber
  keyPress = kb.get_key()
  label6.setText(str(keyPress))
  if optionNumber == 1 and keyPress == 46 or optionNumber == 3 and keyPress == 59:
    label3.setText(str(' '))
    label4.setText(str('>'))
    label5.setText(str(' '))
    optionNumber = 2
  else:
    if optionNumber == 2 and keyPress == 46 or optionNumber == 1 and keyPress == 59:
      label3.setText(str(' '))
      label4.setText(str(' '))
      label5.setText(str('>'))
      optionNumber = 3
    else:
      if optionNumber == 3 and keyPress == 46 or optionNumber == 2 and keyPress == 59:
        label3.setText(str('>'))
        label4.setText(str(' '))
        label5.setText(str(' '))
        optionNumber = 1
      else:
        if optionNumber == 1 and keyPress == 10:
          pass
        else:
          if optionNumber == 2 and keyPress == 10:
            pass
          else:
            if optionNumber == 3 and keyPress == 10:
              pass
            else:
              pass


def setup():
  global label0, label1, label2, label3, label4, label5, label6, label7, label8, label9, label10, label11, kb, keyPress, optionNumber

  kb = MatrixKeyboard()
  kb.set_callback(kb_pressed_event)
  M5.begin()
  Widgets.fillScreen(0x000000)
  label0 = Widgets.Label("label0", 70, 10, 1.0, 0xffffff, 0x222222, Widgets.FONTS.DejaVu18)
  label1 = Widgets.Label("label1", 70, 40, 1.0, 0xffffff, 0x222222, Widgets.FONTS.DejaVu18)
  label2 = Widgets.Label("label2", 70, 70, 1.0, 0xffffff, 0x222222, Widgets.FONTS.DejaVu18)
  label3 = Widgets.Label("label3", 10, 10, 1.0, 0xffffff, 0x222222, Widgets.FONTS.DejaVu18)
  label4 = Widgets.Label("label4", 10, 40, 1.0, 0xffffff, 0x222222, Widgets.FONTS.DejaVu18)
  label5 = Widgets.Label("label5", 10, 70, 1.0, 0xffffff, 0x222222, Widgets.FONTS.DejaVu18)
  label6 = Widgets.Label("label6", 170, 10, 1.0, 0xffffff, 0x222222, Widgets.FONTS.DejaVu18)
  label7 = Widgets.Label("label7", 170, 40, 1.0, 0xffffff, 0x222222, Widgets.FONTS.DejaVu18)
  label8 = Widgets.Label("label8", 170, 70, 1.0, 0xffffff, 0x222222, Widgets.FONTS.DejaVu18)
  label9 = Widgets.Label("label9", 170, 100, 1.0, 0xffffff, 0x222222, Widgets.FONTS.DejaVu18)
  label10 = Widgets.Label("label10", 10, 100, 1.0, 0xffffff, 0x222222, Widgets.FONTS.DejaVu18)
  label11 = Widgets.Label("label11", 70, 100, 1.0, 0xffffff, 0x222222, Widgets.FONTS.DejaVu18)

  optionNumber = 1
  setMainMenu()


def loop():
  global label0, label1, label2, label3, label4, label5, label6, label7, label8, label9, label10, label11, kb, keyPress, optionNumber
  M5.update()
  kb.tick()
  label7.setText(str(optionNumber))


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
