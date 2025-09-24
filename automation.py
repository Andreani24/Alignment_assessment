import clr
import os
import time
import sys
import subprocess
import keyboard   # pip install keyboard
import pyautogui  # pip install pyautogui
import pygetwindow as gw
import cv2
import numpy as np
import queue
import threading

# --- Add references to Thorlabs Kinesis DLLs ---
clr.AddReference(r"C:\Program Files\Thorlabs\Kinesis\Thorlabs.MotionControl.DeviceManagerCLI.dll")
clr.AddReference(r"C:\Program Files\Thorlabs\Kinesis\Thorlabs.MotionControl.GenericMotorCLI.dll")
clr.AddReference(r"C:\Program Files\Thorlabs\Kinesis\ThorLabs.MotionControl.IntegratedStepperMotorsCLI.dll")

from Thorlabs.MotionControl.DeviceManagerCLI import *
from Thorlabs.MotionControl.GenericMotorCLI import *
from Thorlabs.MotionControl.IntegratedStepperMotorsCLI import *

# --- Swift Imaging Path / Titles (update if needed) ---
SWIFT_EXE = r"C:\Program Files\Swift\Imaging\x64\imaging.exe"
SWIFT_TITLE = "Swift Imaging"

# --- Integration with BetterGUI ---
IMAGES_DIR = r"C:\Users\admin\Desktop\images"
BETTERGUI_PY = os.path.join(os.path.dirname(__file__), "BetterGUI.py")
POLL_TIMEOUT = 15.0  # seconds to wait for saved file
POLL_INTERVAL = 0.5
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".raw"}

# --- Rotation input / calibration ---
DEGREES_PER_SECOND = 5  # calibrate this to match your motor speed (open-loop timing)
_angle_buffer = []
_buffer_lock = threading.Lock()
_rotation_queue = queue.Queue()

def _on_key_event(event):
    # runs in keyboard hook thread
    if event.event_type != "down":
        return
    name = (event.name or "").lower()
    with _buffer_lock:
        # numeric input
        if name in set("0123456789") or name in ("dot", "decimal", "."):
            ch = "." if name in ("dot", "decimal", ".") else name
            _angle_buffer.append(ch)
            print("Angle buffer:", "".join(_angle_buffer))
        elif name in ("backspace", "delete"):
            if _angle_buffer:
                _angle_buffer.pop()
                print("Angle buffer:", "".join(_angle_buffer))
        # plus keys
        elif name in ("+", "plus", "add", "=", "shift+=", "kp_add"):
            s = "".join(_angle_buffer).strip()
            _angle_buffer.clear()
            try:
                val = float(s)
            except Exception:
                print("Invalid angle input:", s)
                return
            _rotation_queue.put((abs(val), "plus"))
            print(f"Enqueued rotation: {val} degrees (+)")
        # minus keys
        elif name in ("-", "minus", "subtract", "kp_subtract"):
            s = "".join(_angle_buffer).strip()
            _angle_buffer.clear()
            try:
                val = float(s)
            except Exception:
                print("Invalid angle input:", s)
                return
            _rotation_queue.put((abs(val), "minus"))
            print(f"Enqueued rotation: {val} degrees (-)")
        # ignore other keys

# register hook once (will be unhooked in finally)
keyboard.hook(_on_key_event)


def bring_swift_to_front(timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        wins = gw.getWindowsWithTitle(SWIFT_TITLE)
        if not wins:
            time.sleep(0.2)
            continue
        win = wins[0]
        try:
            if getattr(win, "isMinimized", False):
                try:
                    win.restore()
                except Exception:
                    pass
                time.sleep(0.15)
            try:
                win.activate()
            except Exception:
                try:
                    win.restore()
                    time.sleep(0.05)
                    win.activate()
                except Exception:
                    pass
            time.sleep(0.2)
            return True
        except Exception:
            time.sleep(0.1)
    return False

def ensure_swift_running():
    if bring_swift_to_front():
        print("Swift Imaging already running and brought to front.")
        return
    print("Launching Swift Imaging...")
    try:
        os.startfile(SWIFT_EXE)
        time.sleep(4)
        if bring_swift_to_front():
            print("Swift Imaging launched and brought to front.")
            return
    except Exception as e:
        print(f"Could not launch Swift Imaging automatically: {e}")
    input("Please open Swift Imaging manually, then press ENTER...")

def activate_swift():
    try:
        win = gw.getWindowsWithTitle(SWIFT_TITLE)[0]
        win.activate()
        time.sleep(0.5)
        return True
    except IndexError:
        print("Swift Imaging window not found.")
        return False

def quick_save():
    if activate_swift():
        pyautogui.press("f4")
        print("Quick Save triggered (F4).")

def _get_latest_file(folder, exts=None):
    try:
        files = [
            os.path.join(folder, f)
            for f in os.listdir(folder)
            if os.path.splitext(f)[1].lower() in (exts or IMAGE_EXTS)
        ]
    except FileNotFoundError:
        return None
    if not files:
        return None
    return max(files, key=os.path.getmtime)

def wait_for_file_ready(path, stable_time=0.8, timeout=8.0, poll=0.2):
    deadline = time.time() + timeout
    prev_size = -1
    stable_since = None
    while time.time() < deadline:
        try:
            size = os.path.getsize(path)
        except OSError:
            size = -1
        now = time.time()
        if size > 0 and size == prev_size:
            if stable_since is None:
                stable_since = now
            elif now - stable_since >= stable_time:
                try:
                    with open(path, "rb") as f:
                        data = f.read()
                    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)
                    if img is not None:
                        return True
                except Exception:
                    pass
        else:
            stable_since = None
        prev_size = size
        time.sleep(poll)
    return False

def wait_for_new_file(folder, start_time, timeout=POLL_TIMEOUT):
    deadline = time.time() + timeout
    while time.time() < deadline:
        latest = _get_latest_file(folder)
        if latest and os.path.getmtime(latest) >= start_time:
            if wait_for_file_ready(latest, timeout=min(6.0, deadline - time.time())):
                return latest
        time.sleep(POLL_INTERVAL)
    return None

def launch_bettergui_with_file(path, csv_path):
    try:
        # Pass the image path AND the csv path as arguments
        subprocess.Popen([sys.executable, BETTERGUI_PY, path, csv_path], close_fds=True)
        print(f"Launched BetterGUI for {path}")
        print(f"Using session CSV: {csv_path}")
    except Exception as e:
        print("Failed to launch BetterGUI:", e)

def _process_rotation_queue(device):
    # process all queued rotation requests (non-blocking)
    while not _rotation_queue.empty():
        try:
            angle_deg, sign = _rotation_queue.get_nowait()
        except queue.Empty:
            break
        # compute duration from calibration
        duration = max(0.0, float(angle_deg) / float(DEGREES_PER_SECOND))
        direction = MotorDirection.Forward if sign == "plus" else MotorDirection.Backward
        print(f"Rotating {angle_deg} degrees {'+' if sign=='plus' else '-'} (duration {duration:.2f}s)")
        try:
            device.MoveContinuous(direction)
            time.sleep(duration)
            device.StopImmediate()
            print("Rotation complete.")
        except Exception as e:
            print("Rotation failed:", e)

def main():
    # This script now expects the session CSV path as a command-line argument
    if len(sys.argv) > 1:
        session_csv_path = sys.argv[1]
        print(f"Automation script started with session CSV: {session_csv_path}")
    else:
        print("Error: This script must be launched from BetterGUI.py with a session CSV path.")
        print("Exiting.")
        time.sleep(3)
        return

    ensure_swift_running()

    DeviceManagerCLI.BuildDeviceList()
    serial_no = "55000414"   # <--- replace with your rotator serial number
    device = CageRotator.CreateCageRotator(serial_no)
    device.Connect(serial_no)

    if not device.IsSettingsInitialized():
        device.WaitForSettingsInitialized(10000)
    device.StartPolling(250)
    time.sleep(0.25)
    device.EnableDevice()
    time.sleep(0.25)
    print("Device enabled:", device.GetDeviceInfo().Description)

    homed = False
    print("Device not homed. Press 'h' to home the device when ready.")

    print("\nControls:")
    print(" Type digits (and optional '.') then press '+' or '-' to rotate that many degrees")
    print(" h    Home device")
    print(" ↑    Rotate forward (continuous)")
    print(" ↓    Rotate backward (continuous)")
    print(" ENTER  Capture image and launch analyser")
    print(" ESC   Exit Camera Mode Session\n")

    try:
        while True:
            # handle homing key
            if (not homed) and keyboard.is_pressed("h"):
                try:
                    print("Loading motor configuration and homing device...")
                    device.LoadMotorConfiguration(serial_no, DeviceConfiguration.DeviceSettingsUseOptionType.UseDeviceSettings)
                    print("Homing device...")
                    device.Home(60000)
                    homed = True
                    print("Homing complete.")
                    time.sleep(1.0)
                except Exception as e:
                    print("Homing failed:", e)
                    time.sleep(0.5)

            # movement controls
            if keyboard.is_pressed("up"):
                device.MoveContinuous(MotorDirection.Forward)
            elif keyboard.is_pressed("down"):
                device.MoveContinuous(MotorDirection.Backward)
            else:
                device.StopImmediate()

            # process any queued degree-rotations
            _process_rotation_queue(device)

            if keyboard.is_pressed("enter"):
                t0 = time.time()
                quick_save()
                latest = wait_for_new_file(IMAGES_DIR, start_time=t0, timeout=POLL_TIMEOUT)
                if latest:
                    print("Detected saved file:", latest)
                    # Pass both the new image path and the session CSV path
                    launch_bettergui_with_file(latest, session_csv_path)
                else:
                    print("No new image detected within timeout.")
                time.sleep(1)  # debounce

            if keyboard.is_pressed("esc"):
                print("Exiting...")
                break

            time.sleep(0.05)

    finally:
        keyboard.unhook_all()
        device.StopImmediate()
        device.StopPolling()
        device.Disconnect()
        print("Device disconnected.")

if __name__ == "__main__":
    main()