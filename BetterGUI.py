import cv2
import numpy as np
import math
import time
import tkinter as tk
from tkinter import filedialog, messagebox
import os


# Replace ONLY this class in your script.
class CoreAnalyser:
    """
    The core interactive analysis engine. Measures rotational angle by manually
    selecting points, correcting for geometric and perspective distortions.
    This class is instantiated by a specific analyser (e.g., PictureAnalyser).
    """

    def __init__(self, image, real_catheter_diameter_mm, real_feature_width_mm, filename_prefix="capture"):
        if image is None:
            raise ValueError("Error: Input image cannot be None.")

        # --- Real-world dimensions for correction ---
        self.real_catheter_diameter_mm = real_catheter_diameter_mm
        self.real_feature_width_mm = real_feature_width_mm
        self.real_angular_width = self._calculate_real_angular_width()

        # --- Image and display state ---
        self.original_image = image
        self.display_image = None
        self.window_name = "Manual Catheter Analysis"
        self.filename_prefix = filename_prefix
        self.restart_requested = False

        # --- Interaction state ---
        self.phase = "ALIGNMENT"
        self.clicked_points = []
        self.point_history = []
        self.zoom_level = 1.0
        self.pan_offset = np.array([0.0, 0.0])
        self.is_panning = False
        self.pan_start = np.array([0, 0])

        self.info_panel_height = 120

        # --- MINIMAL CHANGE: Re-introduced corrected scaling logic ---
        max_display_width = 1200
        max_display_height = 800
        h, w = self.original_image.shape[:2]

        # Calculate scale factor to fit the image in the window, but do not enlarge it.
        scale = min(max_display_width / w, max_display_height / h, 1.0)
        self.initial_scale_factor = scale

        # Create a scaled version of the image that will be used for display.
        new_w = int(w * self.initial_scale_factor)
        new_h = int(h * self.initial_scale_factor)
        self.scaled_image = cv2.resize(self.original_image, (new_w, new_h), interpolation=cv2.INTER_AREA)
        self.scaled_h, self.scaled_w = self.scaled_image.shape[:2]

    def _calculate_real_angular_width(self):
        if self.real_catheter_diameter_mm <= 0 or self.real_feature_width_mm <= 0:
            raise ValueError("Real-world dimensions must be positive values.")
        if self.real_feature_width_mm > self.real_catheter_diameter_mm:
            raise ValueError("Feature width cannot be greater than catheter diameter.")
        real_radius = self.real_catheter_diameter_mm / 2.0
        return 2 * math.asin((self.real_feature_width_mm / 2.0) / real_radius)

    def _update_display(self):
        # All zooming and panning now happens on the scaled_image.
        zoomed_w = int(self.scaled_w * self.zoom_level)
        zoomed_h = int(self.scaled_h * self.zoom_level)

        self.pan_offset[0] = np.clip(self.pan_offset[0], 0, max(0, zoomed_w - self.scaled_w))
        self.pan_offset[1] = np.clip(self.pan_offset[1], 0, max(0, zoomed_h - self.scaled_h))
        view_x, view_y = int(self.pan_offset[0]), int(self.pan_offset[1])

        zoomed_display_image = cv2.resize(self.scaled_image, (zoomed_w, zoomed_h), interpolation=cv2.INTER_LINEAR)

        visible_region = zoomed_display_image[view_y:view_y + self.scaled_h, view_x:view_x + self.scaled_w]
        self.display_image = visible_region.copy()

        # Points (stored as original coordinates) are converted to display coordinates for drawing.
        for i, (ox, oy) in enumerate(self.clicked_points):
            sx = ox * self.initial_scale_factor
            sy = oy * self.initial_scale_factor
            vx = int(sx * self.zoom_level - view_x)
            vy = int(sy * self.zoom_level - view_y)
            color = (255, 0, 0) if (self.phase == "ALIGNMENT" or i < 2) else (0, 0, 255)
            cv2.circle(self.display_image, (vx, vy), 5, color, -1)

        panel = np.zeros((self.info_panel_height, self.display_image.shape[1], 3), dtype=np.uint8)
        self._draw_info_text(panel)
        self.display_image = cv2.vconcat([self.display_image, panel])
        cv2.imshow(self.window_name, self.display_image)

    def _draw_info_text(self, panel):
        def put_text(text, y_pos, color=(255, 255, 255), font_scale=0.6):
            cv2.putText(panel, text, (10, y_pos), cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, 1, cv2.LINE_AA)

        put_text(f"PHASE: {self.phase}", 20, color=(0, 255, 255))
        if self.phase == "ALIGNMENT":
            put_text("Click 2 points to define a horizontal line.", 40)
            if len(self.clicked_points) > 0: put_text(f"Point 1: {self.clicked_points[0]}", 60)
            if len(self.clicked_points) == 2:
                put_text(f"Point 2: {self.clicked_points[1]}", 80)
                put_text("Confirm alignment? (y/n)", 100, color=(0, 255, 0))
        elif self.phase == "MEASUREMENT":
            instructions = ["1. Catheter Top", "2. Catheter Bottom", "3. Gap Top Edge", "4. Gap Bottom Edge"]
            put_text(
                f"Click 4 points: {instructions[len(self.clicked_points)] if len(self.clicked_points) < 4 else 'Done'}",
                40)
            coords_str = ", ".join(map(str, self.clicked_points))
            put_text(f"Points: [{coords_str}]", 60)
            put_text("Press 'z' to undo last point. 'r' to reset. 'q' to quit. 's' to restart.", 100)

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

                    # This is the corrected, accurate coordinate transformation
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

        # Rotate the original image
        self.original_image = cv2.warpAffine(self.original_image, rot_mat, (new_w, new_h))

        # Re-create the scaled image from the newly rotated original
        new_scaled_w = int(new_w * self.initial_scale_factor)
        new_scaled_h = int(new_h * self.initial_scale_factor)
        self.scaled_image = cv2.resize(self.original_image, (new_scaled_w, new_scaled_h), interpolation=cv2.INTER_AREA)
        self.scaled_h, self.scaled_w = self.scaled_image.shape[:2]

        self.clicked_points = []
        self.point_history = []
        self.phase = "MEASUREMENT"

    def _calculate_and_save_results(self):
        y1, y2 = self.clicked_points[0][1], self.clicked_points[1][1]
        y3, y4 = self.clicked_points[2][1], self.clicked_points[3][1]

        apparent_radius_px = abs(y1 - y2) / 2.0
        catheter_midpoint_y = (y1 + y2) / 2.0
        if apparent_radius_px == 0:
            messagebox.showerror("Calculation Error", "Catheter radius is zero.")
            return

        offset_app_top = y3 - catheter_midpoint_y
        offset_app_bottom = y4 - catheter_midpoint_y

        ratio_top = np.clip(offset_app_top / apparent_radius_px, -1.0, 1.0)
        ratio_bottom = np.clip(offset_app_bottom / apparent_radius_px, -1.0, 1.0)

        angle_app_top_rad = math.asin(ratio_top)
        angle_app_bottom_rad = math.asin(ratio_bottom)

        angle_app_width_rad = abs(angle_app_top_rad - angle_app_bottom_rad)

        if angle_app_width_rad == 0:
            messagebox.showerror("Calculation Error", "Apparent angular width is zero.")
            return

        correction_factor_angle = self.real_angular_width / angle_app_width_rad
        angle_app_midpoint_rad = (angle_app_top_rad + angle_app_bottom_rad) / 2.0
        final_angle_rad = angle_app_midpoint_rad * correction_factor_angle
        final_angle_deg = math.degrees(final_angle_rad)
        corrected_offset_px = apparent_radius_px * math.sin(final_angle_rad)
        true_centerline_y = int(catheter_midpoint_y + corrected_offset_px)
        img_width = self.original_image.shape[1]

        cv2.line(self.original_image, (0, int(catheter_midpoint_y)), (img_width, int(catheter_midpoint_y)),
                 (255, 255, 0), 2)
        cv2.line(self.original_image, (0, true_centerline_y), (img_width, true_centerline_y), (0, 255, 255), 2)

        final_panel = np.zeros((self.info_panel_height, self.original_image.shape[1], 3), dtype=np.uint8)
        text = f"Rotation Angle: {math.degrees(angle_app_midpoint_rad):.2f} degrees"

        font_scale = 3
        font_thickness = 4

        (w, h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, font_thickness)
        text_x = (final_panel.shape[1] - w) // 2
        text_y = (self.info_panel_height + h) // 2
        cv2.putText(final_panel, text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 255, 0),
                    font_thickness, cv2.LINE_AA)

        final_image = cv2.vconcat([self.original_image, final_panel])

        print(f"Apparent Radius (px): {apparent_radius_px:.2f}")
        print(f"Apparent Angular Width (deg): {math.degrees(angle_app_width_rad):.2f}")
        print(f"Real Angular Width (deg): {math.degrees(self.real_angular_width):.2f}")
        print(f"Angular Correction Factor: {correction_factor_angle:.4f}")
        print(f"Apparent Angle Top (deg): {math.degrees(angle_app_top_rad):.2f}")
        print(f"Apparent Angle Bottom (deg): {math.degrees(angle_app_bottom_rad):.2f}")
        print(f"Apparent Midpoint Angle (deg): {math.degrees(angle_app_midpoint_rad):.2f}")
        # print(f"Final Rotation Angle: {final_angle_deg:.2f} degrees")

        # --- MINIMAL CHANGE STARTS HERE ---

        # Define the maximum size for the final results window
        max_display_width = 1200
        max_display_height = 800
        h_final, w_final = final_image.shape[:2]

        # Recalculate the scale factor based on the FINAL image's dimensions
        final_scale = min(max_display_width / w_final, max_display_height / h_final, 1.0)

        # Use this new, correct scale factor to resize the display image
        final_image_display = cv2.resize(
            final_image,
            (int(w_final * final_scale), int(h_final * final_scale)),
            interpolation=cv2.INTER_AREA
        )

        # --- MINIMAL CHANGE ENDS HERE ---

        result_window_name = "Final Result"
        cv2.imshow(result_window_name, final_image_display)

        while True:
            if cv2.getWindowProperty(result_window_name, cv2.WND_PROP_VISIBLE) < 1: break
            key = cv2.waitKey(10) & 0xFF
            if key == ord('q'): break
            if key == ord('s'):
                root = tk.Tk()
                root.withdraw()
                default_output_dir = os.path.abspath("analysis_output")
                os.makedirs(default_output_dir, exist_ok=True)
                output_path = filedialog.asksaveasfilename(
                    defaultextension=".png",
                    filetypes=[("PNG files", "*.png"), ("JPEG files", "*.jpg"), ("All files", "*.*")],
                    initialdir=default_output_dir,
                    initialfile=f"{self.filename_prefix}_analysis.png",
                    title="Save Analysis Image"
                )
                root.destroy()
                if output_path:
                    try:
                        cv2.imwrite(output_path, final_image)
                    except Exception as e:
                        messagebox.showerror("Save Error", f"Could not save file.\n\n{e}")

    def run(self):
        # The window is sized to the scaled image, not the original.
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.window_name, self.scaled_w, self.scaled_h + self.info_panel_height)
        cv2.setMouseCallback(self.window_name, self._mouse_callback)
        self._update_display()
        while True:
            if cv2.getWindowProperty(self.window_name, cv2.WND_PROP_VISIBLE) < 1: break
            key = cv2.waitKey(20) & 0xFF
            if key == ord('q'): break
            if key == ord('s'):
                self.restart_requested = True
                break
            if key == ord('z'):
                if self.point_history:
                    self.clicked_points = self.point_history.pop()
                    self._update_display()
            if self.phase == "ALIGNMENT":
                if len(self.clicked_points) == 2:
                    if key == ord('y'):
                        self._align_image(); self._update_display()
                    elif key == ord('n'):
                        self.clicked_points = []; self.point_history = []; self._update_display()
            elif self.phase == "MEASUREMENT":
                if key == ord('r'): self.clicked_points = []; self.point_history = []; self._update_display()
                if len(self.clicked_points) == 4:
                    self._calculate_and_save_results()
                    self.restart_requested = True
                    break
        cv2.destroyAllWindows()
        return self.restart_requested


class PictureAnalyser:
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
        theta_electrode_rad = self.real_electrode_width_mm / R_real
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
        self.root.withdraw()  # Hide the main GUI window
        file_path = filedialog.askopenfilename(
            title="Select an image file",
            filetypes=[("Image Files", "*.png;*.jpg;*.jpeg;*.bmp")]
        )
        if file_path:
            try:
                analyser = PictureAnalyser(
                    image_path=file_path,
                    real_catheter_diameter_mm=self.real_catheter_diameter_mm,
                    real_feature_width_mm=self.real_gap_width_mm
                )
                restart = analyser.run()
                if not restart:
                    self.root.destroy()
                else:
                    self.root.deiconify()
            except (ValueError, FileNotFoundError) as e:
                messagebox.showerror("Error", f"An error occurred: {e}")
                self.root.deiconify()
        else:
            self.root.deiconify()

    def run_camera_mode(self):
        self.root.withdraw()  # Hide the main GUI window
        try:
            analyser = CameraAnalyser(
                real_catheter_diameter_mm=self.real_catheter_diameter_mm,
                real_feature_width_mm=self.real_gap_width_mm
            )
            restart = analyser.run()
            if not restart:
                self.root.destroy()
            else:
                self.root.deiconify()
        except (ValueError, FileNotFoundError) as e:
            messagebox.showerror("Error", f"An error occurred: {e}")
            self.root.deiconify()


if __name__ == "__main__":
    main_root = tk.Tk()
    app = AnalysisApp(main_root)
    main_root.mainloop()