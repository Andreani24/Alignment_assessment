import subprocess
import time
import pyautogui
import pygetwindow as gw
import os

# Path to Swift Imaging executable (update if needed)
APP_PATH = r"C:\Program Files\Swift\Imaging\x64\imaging.exe"

def ensure_app_running():
    """Start Swift Imaging if possible, otherwise prompt user."""
    if os.path.exists(APP_PATH):
        try:
            subprocess.Popen([APP_PATH])
            print("Starting Swift Imaging...")
            time.sleep(5)  # wait for app to open
        except Exception as e:
            print("Could not start app automatically:", e)
            input("Please open Swift Imaging manually, then press ENTER to continue...")
    else:
        print("App not found at", APP_PATH)
        input("Please open Swift Imaging manually, then press ENTER to continue...")

def focus_window(title="Swift Imaging"):
    """Try to bring Swift Imaging window to front."""
    for _ in range(10):  # retry for up to ~10 seconds
        wins = gw.getWindowsWithTitle(title)
        if wins:
            win = wins[0]
            win.activate()
            print(f"Activated window: {title}")
            return True
        time.sleep(1)
    print("Could not find window automatically.")
    return False

def capture_and_save():
    """Press F8 then F4 inside the app."""
    pyautogui.press('f8')
    print("Pressed F8 (capture)")
    time.sleep(1)
    pyautogui.press('f4')
    print("Pressed F4 (quick save)")

if __name__ == "__main__":
    ensure_app_running()

    if not focus_window("Swift Imaging"):
        input("Please click on the Swift Imaging window, then press ENTER...")

    time.sleep(1)
    capture_and_save()
