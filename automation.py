import clr
import os
import time
import sys
import cv2

# --- Add references to Thorlabs Kinesis DLLs ---
# Make sure the Kinesis software is installed to this path.
clr.AddReference("C:\\Program Files\\Thorlabs\\Kinesis\\Thorlabs.MotionControl.DeviceManagerCLI.dll")
clr.AddReference("C:\\Program Files\\Thorlabs\\Kinesis\\Thorlabs.MotionControl.GenericMotorCLI.dll")
clr.AddReference("C:\\Program Files\\Thorlabs\\Kinesis\\ThorLabs.MotionControl.IntegratedStepperMotorsCLI.dll")

# --- Import functions from the DLLs ---
from Thorlabs.MotionControl.DeviceManagerCLI import *
from Thorlabs.MotionControl.GenericMotorCLI import *
from Thorlabs.MotionControl.IntegratedStepperMotorsCLI import *
from System import Decimal  # Crucial for sending commands to the rotator


def run_experiment():
    """
    The main entry point for the automated experiment. This function connects
    to the hardware, runs the test loop, and ensures disconnection.
    """

    # --- Configuration ---
    ROTATOR_SERIAL = "55507804"  # <-- IMPORTANT: Replace with your rotator's serial number
    CAMERA_INDEX = 0  # Your camera's index (usually 0)
    OUTPUT_FOLDER = "experiment_run_1"
    ANGLES_TO_TEST = [0, 10, 20, 30, 45, 60, 75, 90]  # The angles you want to measure
    SETTLE_TIME_S = 0.5  # Time in seconds to wait for vibrations to stop after moving

    # --- Setup ---
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    device = None
    cap = None

    try:
        # --- Connect to Rotator ---
        print("Connecting to rotator...")
        DeviceManagerCLI.BuildDeviceList()
        device = CageRotator.CreateCageRotator(ROTATOR_SERIAL)
        device.Connect(ROTATOR_SERIAL)

        if not device.IsSettingsInitialized():
            device.WaitForSettingsInitialized(10000)

        device.StartPolling(250)
        device.EnableDevice()
        time.sleep(1)  # Wait for device to enable

        device.LoadMotorConfiguration(ROTATOR_SERIAL, DeviceConfiguration.DeviceSettingsUseOptionType.UseDeviceSettings)

        print("Homing rotator...")
        device.Home(60000)  # 60 second timeout for homing
        print("Rotator connected and homed.")

        # --- Connect to Camera ---
        print("Connecting to camera...")
        cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
        if not cap.isOpened():
            raise IOError(f"Could not open camera at index {CAMERA_INDEX}.")
        print("Camera connected.")

        # --- Automation Loop ---
        for angle in ANGLES_TO_TEST:
            print(f"\n--- Processing Angle: {angle} degrees ---")

            # 1. Rotate to the target angle
            print(f"Moving to {angle} degrees...")
            target_pos = Decimal(angle)  # Convert to .NET Decimal type
            device.MoveTo(target_pos, 60000)  # 60 second timeout for move
            print("Move complete.")

            # 2. Settle
            print(f"Waiting {SETTLE_TIME_S}s for vibrations to settle...")
            time.sleep(SETTLE_TIME_S)

            # 3. Capture Image
            ret, frame = cap.read()
            if not ret:
                print(f"Warning: Failed to capture frame at angle {angle}.")
                continue
            print("Image captured.")

            # 4. Save Image
            filename = os.path.join(OUTPUT_FOLDER, f"capture_angle_{angle}.png")
            cv2.imwrite(filename, frame)
            print(f"Image saved to {filename}")

        print("\nAutomation complete.")

    except Exception as e:
        print(f"An error occurred: {e}")

    finally:
        # --- Disconnect Hardware ---
        print("\nDisconnecting hardware...")
        if device and device.IsConnected:
            device.StopPolling()
            device.Disconnect(True)
            print("Disconnected from rotator.")
        if cap and cap.isOpened():
            cap.release()
            print("Camera released.")


if __name__ == "__main__":
    run_experiment()
