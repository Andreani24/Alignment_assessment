import cv2
import os
import time
from tkinter import messagebox
from core_analysis_engine import CoreAnalyser

class PictureAnalyser:
    """Handles loading an image from a file and running the analysis."""
    def __init__(self, image_path, real_catheter_diameter_mm, real_feature_width_mm):
        self.image_path = image_path
        self.real_catheter_diameter_mm = real_catheter_diameter_mm
        self.real_feature_width_mm = real_feature_width_mm

    def run(self):
        if not os.path.exists(self.image_path):
            raise FileNotFoundError(f"Error: Image not found at {self.image_path}")
        image = cv2.imread(self.image_path)
        if image is None:
            raise ValueError(f"Error: Could not read image from {self.image_path}")
        base_filename = os.path.basename(self.image_path)
        filename_prefix = os.path.splitext(base_filename)[0]
        analyser = CoreAnalyser(
            image=image,
            real_catheter_diameter_mm=self.real_catheter_diameter_mm,
            real_feature_width_mm=self.real_feature_width_mm,
            filename_prefix=filename_prefix
        )
        return analyser.run()


class CameraAnalyser:
    """Handles capturing an image from the camera and running the analysis."""
    def __init__(self, real_catheter_diameter_mm, real_feature_width_mm):
        self.real_catheter_diameter_mm = real_catheter_diameter_mm
        self.real_feature_width_mm = real_feature_width_mm

    def _capture_from_camera(self):
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            messagebox.showerror("Camera Error", "Could not open camera.")
            return None
        while True:
            ret, frame = cap.read()
            if not ret:
                messagebox.showerror("Camera Error", "Can't receive frame. Exiting ...")
                break
            display_frame = frame.copy()
            cv2.putText(display_frame, "Press 'c' to capture, 'q' to quit", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.imshow('Camera Feed', display_frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                cap.release()
                cv2.destroyAllWindows()
                return None
            elif key == ord('c'):
                cap.release()
                cv2.destroyAllWindows()
                return frame
        cap.release()
        cv2.destroyAllWindows()
        return None

    def run(self):
        captured_image = self._capture_from_camera()
        if captured_image is not None:
            filename_prefix = f"capture_{int(time.time())}"
            analyser = CoreAnalyser(
                image=captured_image,
                real_catheter_diameter_mm=self.real_catheter_diameter_mm,
                real_feature_width_mm=self.real_feature_width_mm,
                filename_prefix=filename_prefix
            )
            return analyser.run()
