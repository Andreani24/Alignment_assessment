import cv2
import numpy as np
import math
import time
import tkinter as tk
from tkinter import filedialog, messagebox
import os
import sys
import ctypes
import csv
import datetime
import glob
import re
import subprocess

SW_RESTORE = 9


def _bring_window_to_front(title, fallback_tk=True, wait=0.05):
    try:
        time.sleep(wait)
        hwnd = ctypes.windll.user32.FindWindowW(None, title)
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            return True
    except Exception:
        pass

    if fallback_tk:
        try:
            tmp = tk.Tk()
            tmp.withdraw()
            tmp.attributes("-topmost", True)
            tmp.update()
            tmp.attributes("-topmost", False)
            tmp.destroy()
            return True
        except Exception:
            pass

    return False


def get_next_daily_csv_path(directory="."):
    """
    Return a path like `DD_MM_N_analysis.csv` in `directory`, where N is the next
    measurement number for today's date (DD_MM). This is called once per session.
    """
    os.makedirs(directory, exist_ok=True)
    date_str = datetime.datetime.now().strftime("%d_%m")
    pattern = os.path.join(directory, f"{date_str}_*_analysis.csv")
    files = glob.glob(pattern)
    max_n = 0
    for f in files:
        basename = os.path.basename(f)
        m = re.match(rf"{re.escape(date_str)}_(\d+)_analysis\.csv$", basename)
        if m:
            try:
                n = int(m.group(1))
                if n > max_n:
                    max_n = n
            except ValueError:
                pass
    next_n = max_n + 1
    return os.path.join(directory, f"{date_str}_{next_n}_analysis.csv")


# This global is now just a fallback, it will be overridden by session logic.
ANALYSIS_CSV_PATH = get_next_daily_csv_path()


def record_analysis_result(filename, apparent_radius_px, apparent_angular_width_deg, real_angular_width_deg,
                           correction_factor_angle, angle_app_top_deg, angle_app_bottom_deg, angle_app_midpoint_deg,
                           csv_path=None):
    # Use the provided csv_path if available, otherwise use the global fallback.
    target_csv_path = csv_path if csv_path is not None else ANALYSIS_CSV_PATH
    file_exists = os.path.isfile(target_csv_path)
    with open(target_csv_path, mode='a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            "filename",
            "apparent_radius_px",
            "apparent_angular_width_deg",
            "real_angular_width_deg",
            "correction_factor_angle",
            "angle_app_top_deg",
            "angle_app_bottom_deg",
            "angle_app_midpoint_deg"
        ])
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "filename": filename,
            "apparent_radius_px": f"{apparent_radius_px:.2f}",
            "apparent_angular_width_deg": f"{apparent_angular_width_deg:.2f}",
            "real_angular_width_deg": f"{real_angular_width_deg:.2f}",
            "correction_factor_angle": f"{correction_factor_angle:.4f}",
            "angle_app_top_deg": f"{angle_app_top_deg:.2f}",
            "angle_app_bottom_deg": f"{angle_app_bottom_deg:.2f}",
            "angle_app_midpoint_deg": f"{angle_app_midpoint_deg:.2f}"
        })


class CoreAnalyser:
    def __init__(self, image, real_catheter_diameter_mm, real_feature_width_mm, filename_prefix="capture",
                 csv_path=None):
        if image is None:
            raise ValueError("Error: Input image cannot be None.")

        self.real_catheter_diameter_mm = real_catheter_diameter_mm
        self.real_feature_width_mm = real_feature_width_mm
        self.real_angular_width = self._calculate_real_angular_width()

        self.original_image = image
        self.window_name = "Manual Catheter Analysis"
        self.filename_prefix = filename_prefix
        # Store the session-specific CSV path
        self.session_csv_path = csv_path
        self.restart_requested = False

        self.phase = "ALIGNMENT"
        self.show_edges = True
        self.clicked_points = []
        self.point_history = []
        self.zoom_level = 1.0
        self.pan_offset = np.array([0.0, 0.0])
        self.is_panning = False
        self.pan_start = np.array([0, 0])

        self.info_panel_height = 120

        max_display_width = 1200
        max_display_height = 800
        h, w = self.original_image.shape[:2]
        scale = min(max_display_width / w, max_display_height / h, 1.0)
        self.initial_scale_factor = scale

        new_w = max(1, int(w * self.initial_scale_factor))
        new_h = max(1, int(h * self.initial_scale_factor))
        self.scaled_image = cv2.resize(self.original_image, (new_w, new_h), interpolation=cv2.INTER_AREA)
        self.scaled_h, self.scaled_w = self.scaled_image.shape[:2]

        self.edge_display_image = self._create_edge_display(self.original_image)
        self.scaled_edge_image = cv2.resize(self.edge_display_image, (self.scaled_w, self.scaled_h),
                                            interpolation=cv2.INTER_AREA)

    def _calculate_real_angular_width(self):
        if self.real_catheter_diameter_mm <= 0 or self.real_feature_width_mm <= 0:
            raise ValueError("Real-world dimensions must be positive values.")
        if self.real_feature_width_mm > self.real_catheter_diameter_mm:
            raise ValueError("Feature width cannot be greater than catheter diameter.")
        real_radius = self.real_catheter_diameter_mm / 2.0
        return 2 * math.asin((self.real_feature_width_mm / 2.0) / real_radius)

    def _create_edge_display(self, image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        sobelx = cv2.Sobel(blurred, cv2.CV_64F, 1, 0, ksize=5)
        sobely = cv2.Sobel(blurred, cv2.CV_64F, 0, 1, ksize=5)
        magnitude = cv2.magnitude(sobelx, sobely)
        edges = cv2.normalize(magnitude, None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)
        return cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)

    def _update_display(self):
        base_scaled = self.scaled_edge_image if self.show_edges else self.scaled_image

        zoomed_w = max(1, int(self.scaled_w * self.zoom_level))
        zoomed_h = max(1, int(self.scaled_h * self.zoom_level))

        self.pan_offset[0] = np.clip(self.pan_offset[0], 0, max(0, zoomed_w - self.scaled_w))
        self.pan_offset[1] = np.clip(self.pan_offset[1], 0, max(0, zoomed_h - self.scaled_h))
        view_x, view_y = int(self.pan_offset[0]), int(self.pan_offset[1])

        zoomed_display_image = cv2.resize(base_scaled, (zoomed_w, zoomed_h), interpolation=cv2.INTER_LINEAR)
        visible_region = zoomed_display_image[view_y:view_y + self.scaled_h, view_x:view_x + self.scaled_w]
        self.display_image = visible_region.copy()

        for i, (ox, oy) in enumerate(self.clicked_points):
            sx = ox * self.initial_scale_factor
            sy = oy * self.initial_scale_factor
            vx = int(sx * self.zoom_level - view_x)
            vy = int(sy * self.zoom_level - view_y)
            color = (255, 0, 0) if (self.phase == "ALIGNMENT" or i < 2) else (0, 0, 255)
            cv2.circle(self.display_image, (vx, vy), 5, color, -1)
            cv2.circle(self.display_image, (vx, vy), 5, (255, 255, 255), 1)

        panel = np.zeros((self.info_panel_height, self.display_image.shape[1], 3), dtype=np.uint8)
        self._draw_info_text(panel)
        self.display_image = cv2.vconcat([self.display_image, panel])

        cv2.imshow(self.window_name, self.display_image)

    def _draw_info_text(self, panel):
        def put_text(text, y_pos, color=(255, 255, 255), font_scale=0.6):
            cv2.putText(panel, text, (10, y_pos), cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, 1, cv2.LINE_AA)

        put_text(f"PHASE: {self.phase}", 20, color=(0, 255, 255))
        put_text("Press 'Tab' to toggle Original/Edge view.", 95, font_scale=0.5)
        if self.phase == "ALIGNMENT":
            put_text("Click 2 points to define a horizontal line.", 45)
            if len(self.clicked_points) > 0:
                put_text(f"Point 1: {self.clicked_points[0]}", 65, font_scale=0.5)
            if len(self.clicked_points) == 2:
                put_text("Confirm alignment? (y/n)", 85, color=(0, 255, 0))
        elif self.phase == "MEASUREMENT":
            instructions = ["1. Catheter Top", "2. Catheter Bottom", "3. Gap Top Edge", "4. Gap Bottom Edge"]
            idx_text = instructions[len(self.clicked_points)] if len(self.clicked_points) < 4 else "Done"
            put_text(f"Click 4 points: {idx_text}", 45)
            coords_str = ", ".join(map(str, self.clicked_points))
            put_text(f"Points: [{coords_str}]", 65, font_scale=0.5)
            put_text("Press 'z' undo, 'r' reset, 'q' quit.", 85, font_scale=0.5)

    def _mouse_callback(self, event, x, y, flags, _):
        if event == cv2.EVENT_RBUTTONDOWN:
            self.is_panning = True
            self.pan_start = np.array([x, y])
        elif event == cv2.EVENT_RBUTTONUP:
            self.is_panning = False
        elif event == cv2.EVENT_MOUSEMOVE and self.is_panning:
            delta = self.pan_start - np.array([x, y])
            self.pan_offset += delta
            self.pan_start = np.array([x, y])
        elif event == cv2.EVENT_MOUSEWHEEL:
            cursor_on_scaled_x = (self.pan_offset[0] + x) / self.zoom_level
            cursor_on_scaled_y = (self.pan_offset[1] + y) / self.zoom_level
            zoom_factor = 1.1 if flags > 0 else 1 / 1.1
            self.zoom_level = np.clip(self.zoom_level * zoom_factor, 1.0, 20.0)
            self.pan_offset[0] = (cursor_on_scaled_x * self.zoom_level) - x
            self.pan_offset[1] = (cursor_on_scaled_y * self.zoom_level) - y
        elif event == cv2.EVENT_LBUTTONDOWN:
            if y < self.scaled_h:
                if (self.phase == "ALIGNMENT" and len(self.clicked_points) < 2) or \
                        (self.phase == "MEASUREMENT" and len(self.clicked_points) < 4):
                    self.point_history.append(list(self.clicked_points))
                    scaled_px = (self.pan_offset[0] + x) / self.zoom_level
                    scaled_py = (self.pan_offset[1] + y) / self.zoom_level
                    px = int(scaled_px / self.initial_scale_factor)
                    py = int(scaled_py / self.initial_scale_factor)
                    self.clicked_points.append((px, py))
        self._update_display()

    def _align_image(self):
        p1, p2 = self.clicked_points
        delta_y = p2[1] - p1[1]
        delta_x = p2[0] - p1[0]
        angle_rad = math.atan2(delta_y, delta_x)
        angle_deg = math.degrees(angle_rad)

        h, w = self.original_image.shape[:2]
        center = (w // 2, h // 2)
        rot_mat = cv2.getRotationMatrix2D(center, angle_deg, 1.0)
        cos = np.abs(rot_mat[0, 0])
        sin = np.abs(rot_mat[0, 1])
        new_w = int((h * sin) + (w * cos))
        new_h = int((h * cos) + (w * sin))
        rot_mat[0, 2] += (new_w / 2) - center[0]
        rot_mat[1, 2] += (new_h / 2) - center[1]

        self.original_image = cv2.warpAffine(self.original_image, rot_mat, (new_w, new_h))
        self.edge_display_image = self._create_edge_display(self.original_image)

        new_scaled_w = max(1, int(new_w * self.initial_scale_factor))
        new_scaled_h = max(1, int(new_h * self.initial_scale_factor))
        self.scaled_image = cv2.resize(self.original_image, (new_scaled_w, new_scaled_h), interpolation=cv2.INTER_AREA)
        self.scaled_edge_image = cv2.resize(self.edge_display_image, (new_scaled_w, new_scaled_h),
                                            interpolation=cv2.INTER_AREA)
        self.scaled_w, self.scaled_h = new_scaled_w, new_scaled_h

        self.clicked_points = []
        self.point_history = []
        self.phase = "MEASUREMENT"
        self.zoom_level = 1.0
        self.pan_offset = np.array([0.0, 0.0])

    def _calculate_and_save_results(self):
        y1, y2 = self.clicked_points[0][1], self.clicked_points[1][1]
        y3, y4 = self.clicked_points[2][1], self.clicked_points[3][1]

        apparent_radius_px = abs(y1 - y2) / 2.0
        catheter_midpoint_y = (y1 + y2) / 2.0
        if apparent_radius_px == 0:
            messagebox.showerror("Calculation Error", "Catheter radius is zero. Cannot divide by zero.")
            return

        offset_app_top = y3 - catheter_midpoint_y
        offset_app_bottom = y4 - catheter_midpoint_y
        ratio_top = np.clip(offset_app_top / apparent_radius_px, -1.0, 1.0)
        ratio_bottom = np.clip(offset_app_bottom / apparent_radius_px, -1.0, 1.0)
        angle_app_top_rad = math.asin(ratio_top)
        angle_app_bottom_rad = math.asin(ratio_bottom)
        angle_app_width_rad = abs(angle_app_top_rad - angle_app_bottom_rad)
        if angle_app_width_rad == 0:
            messagebox.showerror("Calculation Error", "Apparent angular width is zero. Cannot divide by zero.")
            return

        correction_factor_angle = self.real_angular_width / angle_app_width_rad
        angle_app_midpoint_rad = (angle_app_top_rad + angle_app_bottom_rad) / 2.0
        final_angle_rad = angle_app_midpoint_rad * correction_factor_angle
        final_angle_deg = math.degrees(final_angle_rad)

        final_result_image = self.original_image.copy()
        corrected_offset_px = apparent_radius_px * math.sin(final_angle_rad)
        true_centerline_y = int(catheter_midpoint_y + corrected_offset_px)
        img_width = final_result_image.shape[1]
        cv2.line(final_result_image, (0, int(catheter_midpoint_y)), (img_width, int(catheter_midpoint_y)),
                 (255, 255, 0), 2)
        cv2.line(final_result_image, (0, true_centerline_y), (img_width, true_centerline_y), (0, 255, 255), 2)

        final_panel = np.zeros(((self.info_panel_height) * 2, img_width, 3), dtype=np.uint8)
        text = f"Rotation Angle: {final_angle_deg:.2f} degrees"
        font_scale = 5
        font_thickness = 3
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, font_thickness)
        text_x = (final_panel.shape[1] - tw) // 2
        text_y = (self.info_panel_height + th) // 2
        cv2.putText(final_panel, text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 255, 0),
                    font_thickness, cv2.LINE_AA)

        final_image = cv2.vconcat([final_result_image, final_panel])

        max_display_width = 1200
        max_display_height = 800
        h_final, w_final = final_image.shape[:2]
        final_scale = min(max_display_width / w_final, max_display_height / h_final, 1.0)
        final_image_display = cv2.resize(final_image, (int(w_final * final_scale), int(h_final * final_scale)),
                                         interpolation=cv2.INTER_AREA)

        # --- Record results to CSV ---
        # Explicitly use the session_csv_path stored during initialization
        record_analysis_result(
            filename=self.filename_prefix,
            apparent_radius_px=apparent_radius_px,
            apparent_angular_width_deg=math.degrees(angle_app_width_rad),
            real_angular_width_deg=math.degrees(self.real_angular_width),
            correction_factor_angle=correction_factor_angle,
            angle_app_top_deg=math.degrees(angle_app_top_rad),
            angle_app_bottom_deg=math.degrees(angle_app_bottom_rad),
            angle_app_midpoint_deg=math.degrees(angle_app_midpoint_rad),
            csv_path=self.session_csv_path
        )

        result_window_name = "Final Result"
        cv2.imshow(result_window_name, final_image_display)
        while True:
            if cv2.getWindowProperty(result_window_name, cv2.WND_PROP_VISIBLE) < 1:
                break
            key = cv2.waitKey(10) & 0xFF
            # Pressing 'q' now just closes this result window, returning to the Picture Mode loop
            if key == ord('q'):
                break
            if key == ord('s'):
                root = tk.Tk()
                root.withdraw()
                output_path = filedialog.asksaveasfilename(
                    defaultextension=".png",
                    filetypes=[("PNG files", "*.png"), ("JPEG files", "*.jpg"), ("All files", "*.*")],
                    initialdir=os.path.abspath("analysis_output"),
                    initialfile=f"{self.filename_prefix}_analysis.png",
                    title="Save Analysis Image")
                root.destroy()
                if output_path:
                    try:
                        cv2.imwrite(output_path, final_image)
                        messagebox.showinfo("Save Success", f"Result saved to:\n{os.path.abspath(output_path)}")
                    except Exception as e:
                        messagebox.showerror("Save Error", f"Could not save the file.\n\n{e}")
        cv2.destroyWindow(result_window_name)

    def run(self):
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.window_name, self.scaled_w, self.scaled_h + self.info_panel_height)
        _bring_window_to_front(self.window_name)
        cv2.setMouseCallback(self.window_name, self._mouse_callback)
        self._update_display()

        while True:
            if cv2.getWindowProperty(self.window_name, cv2.WND_PROP_VISIBLE) < 1:
                break
            key = cv2.waitKey(20) & 0xFF
            if key == ord('q'):
                break
            if key == 9:  # Tab key
                self.show_edges = not self.show_edges
                self._update_display()
            if key == ord('z'):
                if self.point_history:
                    self.clicked_points = self.point_history.pop()
                    self._update_display()

            if self.phase == "ALIGNMENT":
                if len(self.clicked_points) == 2:
                    if key == ord('y'):
                        self._align_image()
                        self._update_display()
                    elif key == ord('n'):
                        self.clicked_points = []
                        self.point_history = []
                        self._update_display()
            elif self.phase == "MEASUREMENT":
                if key == ord('r'):
                    self.clicked_points = []
                    self.point_history = []
                    self._update_display()
                if len(self.clicked_points) == 4:
                    self._calculate_and_save_results()
                    # After calculation, break the loop to close the analysis window
                    # This will return control to the Picture Mode loop
                    break

        cv2.destroyWindow(self.window_name)
        return self.restart_requested


class PictureAnalyser:
    def __init__(self, image_path, real_catheter_diameter_mm, real_feature_width_mm, csv_path=None):
        self.image_path = image_path
        self.real_catheter_diameter_mm = real_catheter_diameter_mm
        self.real_feature_width_mm = real_feature_width_mm
        self.csv_path = csv_path  # Store session csv_path

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
            filename_prefix=filename_prefix,
            csv_path=self.csv_path  # Pass session path to CoreAnalyser
        )
        return analyser.run()


class AnalysisApp:
    def __init__(self, root, session_csv_path):
        self.root = root
        self.root.title("Catheter Analysis Tool")

        # This is the unique CSV file for this entire session
        self.session_csv_path = session_csv_path
        print(f"New session started. Logging all results to: {self.session_csv_path}")

        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(100, lambda: self.root.attributes("-topmost", False))

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

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
        instruction_label = tk.Label(frame, text="Select a session mode:", font=("Helvetica", 12))
        instruction_label.pack(pady=(0, 10))
        button_frame = tk.Frame(frame)
        button_frame.pack()
        photo_button = tk.Button(button_frame, text="Picture Mode Session", command=self.run_picture_mode_session,
                                 font=("Helvetica", 10), width=20)
        photo_button.pack(side=tk.LEFT, padx=5)
        camera_button = tk.Button(button_frame, text="Camera Mode Session", command=self.run_camera_mode_session,
                                  font=("Helvetica", 10),
                                  width=20)
        camera_button.pack(side=tk.LEFT, padx=5)

    def run_picture_mode_session(self):
        self.root.withdraw()  # Hide the main menu

        # Start the continuous Picture Mode loop
        while True:
            file_path = filedialog.askopenfilename(
                title="Select an image file (or Cancel to end session)",
                filetypes=[("Image Files", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff"), ("All Files", "*.*")]
            )
            # If the user cancels the file dialog, end the session.
            if not file_path:
                print("Picture Mode session ended by user.")
                break

            # Run analysis on the selected file
            try:
                analyser = PictureAnalyser(
                    image_path=file_path,
                    real_catheter_diameter_mm=self.real_catheter_diameter_mm,
                    real_feature_width_mm=self.real_gap_width_mm,
                    csv_path=self.session_csv_path
                )
                analyser.run()
            except (ValueError, FileNotFoundError) as e:
                messagebox.showerror("Error", f"An error occurred: {e}")
                # After an error, we can choose to continue or break
                # Here, we continue the loop, asking for the next file
                continue

        self.on_close()  # Close the app when the loop is broken

    def run_camera_mode_session(self):
        self.root.withdraw()  # Hide the main menu
        try:
            automation_py_path = os.path.join(os.path.dirname(__file__), "automation.py")
            csv_abs_path = os.path.abspath(self.session_csv_path)

            print("Launching automation.py at:", automation_py_path)
            print("Session CSV path:", csv_abs_path)

            subprocess.Popen(
                [sys.executable, automation_py_path, csv_abs_path],
                cwd=os.path.dirname(__file__)
            )
            self.root.iconify()  # minimize
        except Exception as e:
            messagebox.showerror("Error", f"Could not launch automation script.\n\n{e}")
            self.root.deiconify()
        self.on_close

    def on_close(self):
        """
        Ask the user where to save the session CSV before exiting.
        """
        if os.path.isfile(self.session_csv_path):
            save_path = filedialog.asksaveasfilename(
                parent=self.root,
                title="Save Session CSV File",
                defaultextension=".csv",
                initialfile=os.path.basename(self.session_csv_path),
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
            )

            if save_path:
                try:
                    import shutil
                    shutil.copy2(self.session_csv_path, save_path)
                    messagebox.showinfo("CSV Saved", f"Session CSV saved to:\n{save_path}", parent=self.root)
                except Exception as e:
                    messagebox.showerror("Save Error", f"Could not save CSV file.\n\n{e}", parent=self.root)

        # ✅ Now safely close window after dialogs finish
        self.root.destroy()


def _compute_default_gap(catheter_mm=1.4, electrode_mm=0.5):
    if electrode_mm * 4 >= catheter_mm * math.pi:
        raise ValueError("Electrode widths are too large for the given catheter diameter.")
    R_real = catheter_mm / 2.0
    theta_electrode_rad = 2 * math.asin((electrode_mm / 2.0) / R_real)
    theta_gap_rad = (2 * math.pi - 4 * theta_electrode_rad) / 4.0
    return 2 * R_real * math.sin(theta_gap_rad / 2.0)


if __name__ == "__main__":
    # Case 1: Script is launched by automation.py for analysis.
    # It will have an image path and a csv_path as arguments.
    if len(sys.argv) >= 3:
        image_path = sys.argv[1]
        csv_path = sys.argv[2]
        if not os.path.exists(image_path):
            print(f"Auto-start: image not found: {image_path}")
            sys.exit(1)
        try:
            gap = _compute_default_gap()
            # Run the analyser, passing the specific csv_path from the session
            analyser = PictureAnalyser(image_path,
                                       real_catheter_diameter_mm=1.4,
                                       real_feature_width_mm=gap,
                                       csv_path=csv_path)
            analyser.run()
        except Exception as e:
            print(f"Auto-start failed: {e}")
            sys.exit(1)

    # Case 2: Script is launched by the user to start a new session.
    else:
        main_root = tk.Tk()
        # Determine the CSV path for the new session ONCE.
        session_csv_path = get_next_daily_csv_path()
        # Pass this unique path to the app.
        app = AnalysisApp(main_root, session_csv_path)
        main_root.mainloop()