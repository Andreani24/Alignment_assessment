import cv2
import numpy as np
import math
import os


def visualize_edge_and_line_detection(image):
    """
    Performs edge and line detection based on a Canny -> Hough pipeline
    and returns images for visualization.

    Args:
        image: The input image (as a NumPy array).

    Returns:
        A tuple containing:
        - edge_image: The result of Canny edge detection.
        - lines_image: The original image blended with the detected Hough lines.
    """
    if image is None:
        print("Error: Input image is None.")
        return None, None

    # --- Stage 1: Pre-processing and Canny Edge Detection ---
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    kernel_size = 5
    blur_gray = cv2.GaussianBlur(gray, (kernel_size, kernel_size), 0)

    low_threshold = 20
    high_threshold = 80
    edges = cv2.Canny(blur_gray, low_threshold, high_threshold)

    # --- Stage 2: Hough Line Detection ---
    # Define the Hough transform parameters
    rho = 1  # Distance resolution in pixels of the Hough grid
    theta = np.pi / 180  # Angular resolution in radians of the Hough grid
    threshold = 15  # Minimum number of votes (intersections in Hough grid cell)
    min_line_length = 100  # Minimum number of pixels making up a line
    max_line_gap = 20  # Maximum gap in pixels between connectable line segments

    # Create a blank image to draw the lines on
    line_image = np.copy(image) * 0

    # Run Hough on the edge-detected image
    lines = cv2.HoughLinesP(edges, rho, theta, threshold, np.array([]),
                            min_line_length, max_line_gap)

    if lines is not None:
        print(f"Success! Found {len(lines)} lines.")
        for line in lines:
            for x1, y1, x2, y2 in line:
                cv2.line(line_image, (x1, y1), (x2, y2), (255, 0, 0), 5)  # Draw lines in blue
    else:
        print("Warning: No lines were detected with the current parameters.")

    # --- Stage 3: Combine line image with the original image ---
    # cv2.addWeighted() combines two images. The 0.8 and 1 are the weights.
    lines_on_image = cv2.addWeighted(image, 0.8, line_image, 1, 0)

    return edges, lines_on_image


if __name__ == '__main__':
    # --- This block is for standalone testing of the image processor ---
    print("--- Running Image Processor in Test Mode ---")

    # IMPORTANT: Change this path to an image you want to test
    test_image_path = r"C:\Users\Linxi\PycharmProjects\Alignment_assessment\pictures\BIB10.jpg"
    output_dir = "alignment_test_output"

    if not os.path.exists(test_image_path):
        print(f"Error: Test image not found at '{test_image_path}'")
        print("Please update the 'test_image_path' variable in the script.")
    else:
        input_image = cv2.imread(test_image_path)

        # Process the image to get visualization steps
        edge_result, line_result = visualize_edge_and_line_detection(input_image)

        if edge_result is not None and line_result is not None:
            # Create the output directory
            os.makedirs(output_dir, exist_ok=True)
            base_filename = os.path.splitext(os.path.basename(test_image_path))[0]

            # Save the edge detection result
            edge_output_path = os.path.join(output_dir, f"{base_filename}_canny_edges.png")
            cv2.imwrite(edge_output_path, edge_result)
            print(f"Canny edge map saved to: {edge_output_path}")

            # Save the line detection result
            line_output_path = os.path.join(output_dir, f"{base_filename}_lines_detected.png")
            cv2.imwrite(line_output_path, line_result)
            print(f"Line detection result saved to: {line_output_path}")

            # Create resizable windows before displaying
            cv2.namedWindow("Canny Edge Detection", cv2.WINDOW_NORMAL)
            cv2.namedWindow("Hough Line Detection", cv2.WINDOW_NORMAL)

            # Display the results
            cv2.imshow("Canny Edge Detection", edge_result)
            cv2.imshow("Hough Line Detection", line_result)
            cv2.waitKey(0)
            cv2.destroyAllWindows()

