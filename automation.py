import pyautogui
import time
import pygetwindow as gw

# 1. Give yourself a few seconds to focus the Swift Imaging app manually
time.sleep(3)

# OR: try to bring window to front automatically
try:
    win = gw.getWindowsWithTitle("Swift Imaging")[0]
    win.activate()
except Exception as e:
    print("Could not activate window automatically:", e)
    print("Please make sure Swift Imaging is active.")

time.sleep(1)

# 2. Press F8 to capture
pyautogui.press('f8')
print("Pressed F8 (capture)")

time.sleep(1)

# 3. Press F4 to quick save
pyautogui.press('f4')
print("Pressed F4 (save)")
