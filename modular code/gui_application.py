import tkinter as tk
from tkinter import filedialog, messagebox
import math
from analyser_types import PictureAnalyser, CameraAnalyser

class AnalysisApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Catheter Analysis Tool")
        self.real_catheter_diameter_mm = 1.4
        self.real_electrode_width_mm = 0.5
        self.real_gap_width_mm = self._calculate_real_gap_width()
        self.create_widgets()

    def _calculate_real_gap_width(self):
        if self.real_electrode_width_mm * 4 >= self.real_catheter_diameter_mm * math.pi:
            raise ValueError("Electrode widths are too large for the given catheter diameter.")
        R_real = self.real_catheter_diameter_mm / 2.0
        theta_electrode_rad = 2 * math.asin((self.real_electrode_width_mm / 2.0) / R_real)
        theta_gap_rad = (2 * math.pi - 4 * theta_electrode_rad) / 4.0
        return 2 * R_real * math.sin(theta_gap_rad / 2.0)

    def create_widgets(self):
        frame = tk.Frame(self.root, padx=20, pady=20)
        frame.pack(padx=10, pady=10)
        title_label = tk.Label(frame, text="Catheter Analysis Tool", font=("Helvetica", 16, "bold"))
        title_label.pack(pady=(0, 15))
        instruction_label = tk.Label(frame, text="Select an input source for analysis:", font=("Helvetica", 12))
        instruction_label.pack(pady=(0, 10))
        button_frame = tk.Frame(frame)
        button_frame.pack()
        photo_button = tk.Button(button_frame, text="Use Picture", command=self.run_picture_mode,
                                 font=("Helvetica", 10), width=15)
        photo_button.pack(side=tk.LEFT, padx=5)
        camera_button = tk.Button(button_frame, text="Use Camera", command=self.run_camera_mode, font=("Helvetica", 10),
                                  width=15)
        camera_button.pack(side=tk.LEFT, padx=5)

    def run_picture_mode(self):
        self.root.withdraw()
        file_path = filedialog.askopenfilename(
            title="Select an image file",
            filetypes=[("Image Files", "*.png *.jpg *.jpeg *.bmp"), ("All Files", "*.*")]
        )
        if file_path:
            self._run_analyser(PictureAnalyser, image_path=file_path)
        else:
            self.root.deiconify()

    def run_camera_mode(self):
        self.root.withdraw()
        self._run_analyser(CameraAnalyser)

    def _run_analyser(self, AnalyserClass, **kwargs):
        try:
            analyser = AnalyserClass(real_catheter_diameter_mm=self.real_catheter_diameter_mm, real_feature_width_mm=self.real_gap_width_mm, **kwargs)
            if not analyser.run():
                self.root.destroy()
            else:
                self.root.deiconify()
        except (ValueError, FileNotFoundError) as e:
            messagebox.showerror("Error", f"An error occurred: {e}")
            self.root.deiconify()
