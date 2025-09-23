import cv2
import numpy as np
import math
import time
import tkinter as tk
from tkinter import filedialog, messagebox
import os


# This is the updated CoreAnalyser class with integrated edge detection.
class CoreAnalyser:
    """
    The core interactive analysis engine. Measures rotational angle by manually
    selecting points, correcting for geometric and perspective distortions.
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
        # NEW: Create an edge-detected version for the interactive display
        self.edge_display_image = self._create_edge_display(self.original_image)
        self.display_image = None
        self.window_name = "Manual Catheter Analysis"
        self.filename_prefix = filename_prefix
        self.restart_requested = False

        # --- Interaction state ---
        self.phase = "ALIGNMENT"
        self.show_edges = True  # New: Flag to control which image is shown
        self.clicked_points = []
        self.point_history = []
        self.zoom_level = 1.0
        self.pan_offset = np.array([0.0, 0.0])
        self.is_panning = False
        self.pan_start = np.array([0, 0])

        self.info_panel_height = 120
        self.h, self.w = self.original_image.shape[:2]

    def _calculate_real_angular_width(self):
        if self.real_catheter_diameter_mm <= 0 or self.real_feature_width_mm <= 0:
            raise ValueError("Real-world dimensions must be positive values.")
        if self.real_feature_width_mm > self.real_catheter_diameter_mm:
            raise ValueError("Feature width cannot be greater than catheter diameter.")
        real_radius = self.real_catheter_diameter_mm / 2.0
        return 2 * math.asin((self.real_feature_width_mm / 2.0) / real_radius)

    def _create_edge_display(self, image):
        """Creates a 3-channel BGR edge map from an image using the Sobel operator."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        sobelx = cv2.Sobel(blurred, cv2.CV_64F, 1, 0, ksize=5)
        sobely = cv2.Sobel(blurred, cv2.CV_64F, 0, 1, ksize=5)

        magnitude = cv2.magnitude(sobelx, sobely)
        edges = cv2.normalize(magnitude, None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)

        return cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)

    def _update_display(self):
        # NEW: Choose which image to display based on the toggle state
        if self.show_edges:
            base_image = self.edge_display_image
        else:
            base_image = self.original_image.copy()  # Use a copy to avoid drawing on the original

        zoomed_w, zoomed_h = int(self.w * self.zoom_level), int(self.h * self.zoom_level)
        view_x = int(self.pan_offset[0])
        view_y = int(self.pan_offset[1])

        view_x = np.clip(view_x, 0, zoomed_w - self.w)
        view_y = np.clip(view_y, 0, zoomed_h - self.h)
        self.pan_offset = np.array([float(view_x), float(view_y)])

        zoomed_image = cv2.resize(base_image, (zoomed_w, zoomed_h), interpolation=cv2.INTER_LINEAR)

        visible_region = zoomed_image[view_y:view_y + self.h, view_x:view_x + self.w]
        self.display_image = visible_region.copy()

        for i, (ox, oy) in enumerate(self.clicked_points):
            vx = int((ox * self.zoom_level) - self.pan_offset[0])
            vy = int((oy * self.zoom_level) - self.pan_offset[1])
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
        put_text("Press 'Tab' to toggle Original/Edge view.", 80)  # New instruction

        if self.phase == "ALIGNMENT":
            put_text("Click 2 points to define a horizontal line.", 40)
            if len(self.clicked_points) > 0:
                put_text(f"Point 1: {self.clicked_points[0]}", 60)
            if len(self.clicked_points) == 2:
                put_text("Confirm alignment? (y/n)", 100, color=(0, 255, 0))
        elif self.phase == "MEASUREMENT":
            instructions = [
                "1. Catheter Top", "2. Catheter Bottom",
                "3. Gap Top Edge", "4. Gap Bottom Edge"
            ]
            put_text(
                f"Click 4 points: {instructions[len(self.clicked_points)] if len(self.clicked_points) < 4 else 'Done'}",
                40)
            coords_str = ", ".join(map(str, self.clicked_points))
            put_text(f"Points: [{coords_str}]", 60)
            put_text("Press 'z' to undo. 'r' to reset. 'q' to quit. 's' to restart.", 100)

    def _mouse_callback(self, event, x, y, flags, _):
        if event == cv2.EVENT_RBUTTONDOWN:
            self.is_panning = True
            self.pan_start = np.array([x, y])
        elif event == cv2.EVENT_RBUTTONUP:
            self.is_panning = False
        elif event == cv2.EVENT_MOUSEMOVE and self.is_panning:
            delta = (self.pan_start - np.array([x, y]))
            self.pan_offset += delta
            self.pan_start = np.array([x, y])
        elif event == cv2.EVENT_MOUSEWHEEL:
            zoom_factor = 1.1 if flags > 0 else 1 / 1.1
            cursor_on_original_x = (self.pan_offset[0] + x) / self.zoom_level
            cursor_on_original_y = (self.pan_offset[1] + y) / self.zoom_level
            self.zoom_level *= zoom_factor
            self.zoom_level = np.clip(self.zoom_level, 1.0, 20.0)
            self.pan_offset[0] = (cursor_on_original_x * self.zoom_level) - x
            self.pan_offset[1] = (cursor_on_original_y * self.zoom_level) - y
        elif event == cv2.EVENT_LBUTTONDOWN:
            if y < self.h:
                if self.phase == "ALIGNMENT" and len(self.clicked_points) < 2:
                    self.point_history.append(list(self.clicked_points))
                    px = int((self.pan_offset[0] + x) / self.zoom_level)
                    py = int((self.pan_offset[1] + y) / self.zoom_level)
                    self.clicked_points.append((px, py))
                elif self.phase == "MEASUREMENT" and len(self.clicked_points) < 4:
                    self.point_history.append(list(self.clicked_points))
                    px = int((self.pan_offset[0] + x) / self.zoom_level)
                    py = int((self.pan_offset[1] + y) / self.zoom_level)
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
        self.h, self.w = self.original_image.shape[:2]

        # Regenerate the edge map after rotation
        self.edge_display_image = self._create_edge_display(self.original_image)

        self.clicked_points = []
        self.point_history = []
        self.phase = "MEASUREMENT"

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
        final_angle_rad = angle_app_midpoint_rad * 1
        final_angle_deg = math.degrees(final_angle_rad)

        final_result_image = self.original_image.copy()

        print(f"Apparent Radius (px): {apparent_radius_px:.2f}")
        print(f"Apparent Angular Width (deg): {math.degrees(angle_app_width_rad):.2f}")
        print(f"Real Angular Width (deg): {math.degrees(self.real_angular_width):.2f}")
        print(f"Angular Correction Factor: {correction_factor_angle:.4f}")
        print(f"Apparent Angle Top (deg): {math.degrees(angle_app_top_rad):.2f}")
        print(f"Apparent Angle Bottom (deg): {math.degrees(angle_app_bottom_rad):.2f}")
        print(f"Apparent Midpoint Angle (deg): {math.degrees(angle_app_midpoint_rad):.2f}")
        print(f"Final Rotation Angle: {final_angle_deg:.2f} degrees")


        corrected_offset_px = apparent_radius_px * math.sin(final_angle_rad)
        true_centerline_y = int(catheter_midpoint_y + corrected_offset_px)
        img_width = final_result_image.shape[1]

        cv2.line(final_result_image, (0, int(catheter_midpoint_y)), (img_width, int(catheter_midpoint_y)),
                 (255, 255, 0), 2)
        cv2.line(final_result_image, (0, true_centerline_y), (img_width, true_centerline_y), (0, 255, 255), 2)

        final_panel = np.zeros((self.info_panel_height, img_width, 3), dtype=np.uint8)
        text = f"Rotation Angle: {final_angle_deg:.2f} degrees"
        (w, h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1, 2)
        text_x = (final_panel.shape[1] - w) // 2
        text_y = (self.info_panel_height + h) // 2
        cv2.putText(final_panel, text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)
        final_image = cv2.vconcat([final_result_image, final_panel])

        result_window_name = "Final Result"
        cv2.namedWindow(result_window_name, cv2.WINDOW_NORMAL)
        cv2.imshow(result_window_name, final_image)

        while True:
            if cv2.getWindowProperty(result_window_name, cv2.WND_PROP_VISIBLE) < 1:
                break
            key = cv2.waitKey(10) & 0xFF
            if key == ord('q'):
                break
            if key == ord('s'):
                root = tk.Tk();
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

    def run(self):
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.window_name, self.w, self.h + self.info_panel_height)
        cv2.setMouseCallback(self.window_name, self._mouse_callback)
        self._update_display()
        while True:
            if cv2.getWindowProperty(self.window_name, cv2.WND_PROP_VISIBLE) < 1:
                break
            key = cv2.waitKey(20) & 0xFF
            if key == ord('q'):
                break
            if key == ord('s'):
                self.restart_requested = True
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
                    self.restart_requested = True
                    break
        cv2.destroyAllWindows()
        return self.restart_requested
