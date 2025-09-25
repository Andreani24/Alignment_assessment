# Catheter Alignment Assessment Tool

## Overview

This tool provides a semi-automated system for measuring the rotational alignment of a medical catheter. It integrates with a Thorlabs cage rotator for physical positioning and uses Swift Imaging software for image capture. The analysis is performed using a custom GUI built with OpenCV and Tkinter.

The system can operate in two primary modes:

- **Camera Mode**: A real-time, hands-on session where the user controls the Thorlabs rotator, captures images via Swift Imaging, and instantly analyses them.
- **Picture Mode**: An offline session for analysing pre-existing images of the catheter.

All measurements from a session are logged to a single CSV file, which can be saved at the end.

## Requirements

### Hardware
- A computer running Windows
- Thorlabs Cage Rotator (e.g., K10CR1) connected via USB
- A camera compatible with the provided Swift Imaging software

### Software
- **Python**: This project was tested with Python 3.10. Other 3.x versions may work but are not guaranteed.

**Included Software:**
- The `Thorlabs/Kinesis` folder containing the necessary hardware drivers (.dll files) must be present
- The `Swift/Imaging` folder containing the `imaging.exe` capture software must be present

## Setup Instructions

Follow these steps to set up the software environment on a new computer.

### 1. Clone the Repository

First, get the project files. If you're using Git, clone the repository. Otherwise, download and unzip the project folder.

### 2. Create a Virtual Environment

It is highly recommended to use a virtual environment to keep project dependencies isolated. Open a terminal or command prompt in the project's root directory and run:

```bash
python -m venv .venv
```

### 3. Activate the Environment

Before installing packages, you must activate the environment:

```bash
.venv\Scripts\activate
```

You will see `(.venv)` appear at the beginning of your terminal prompt.

### 4. Install Python Packages

Install all the required Python libraries using the provided requirements.txt file:

```bash
pip install -r requirements.txt
```

### 5. Verify Hardware Serial Number

Open the `automation.py` script and ensure the serial number for your Thorlabs rotator is correct. Find this line and edit the number if necessary:

```python
# inside automation.py
serial_no = "55000414"   # <--- replace with your rotator serial number
```

## How to Use

To launch the main menu, run the included batch file from the project directory.

```bash
CatheterAnalysis.bat
```

This will open the main menu where you can choose between "Picture Mode Session" and "Camera Mode Session".

## Camera Mode Session

This mode gives you real-time control over the hardware for live analysis.

### 1. Launch

Click the "Camera Mode Session" button from the main menu.

The main menu will minimise, The Swift Imaging software window should appear shortly

### 2. Controls (in the terminal window)

**Homing**: Before you begin, you must home the device. Press **h** to start the homing sequence.

**Manual Rotation**:
- Press the **Up Arrow** ↑ to rotate the motor forward continuously
- Press the **Down Arrow** ↓ to rotate the motor backward continuously
- Release the key to stop

**Precise Rotation**:
- Type a number (e.g., `12.5`)
- Press `+` to rotate that many degrees forward
- Press `-` to rotate that many degrees backward

**Capture & Analyse**:
- Position the catheter as desired
- Press **Enter**. This automatically triggers a quick save in Swift Imaging (F4) and opens the analysis window with the new image
- see the full Analysis Loop below

**Exiting**:
- Press **Esc** to end the Camera Mode session. This will close the control console and bring back the main menu, prompting you to save the session's CSV log.

## Picture Mode Session

This mode allows you to analyse a batch of images you have already captured.

### 1. Launch

Click the "Picture Mode Session" button from the main menu.

A file dialog will open, prompting you to select an image.

### 2. Analysis Loop

1. Select an image file to analyse. The analysis window will open.
2. Once you finish analysing an image, the analysis window will close, and a new file dialog will appear, asking for the next image.
3. This loop continues, logging all results to the same session CSV file.
4. To end the session, simply click "Cancel" in the file dialog. You will then be prompted to save the session's CSV log.

## The Analysis Window

Whether in Camera or Picture Mode, the analysis process is the same.

### Phase 1: Alignment

The goal is to make the catheter perfectly horizontal in the image.

1. Click two points along a feature you know should be horizontal (e.g., the top edge of the catheter)
2. Press `y` to confirm. The image will be automatically rotated.

### Phase 2: Measurement

Click four points in the following order:

1. The top edge of the catheter
2. The bottom edge of the catheter
3. The top edge of the feature (the gap)
4. The bottom edge of the feature (the gap)

Once the fourth point is clicked, the calculation is performed, and the Final Result window appears.

### Controls in the Analysis Window

| Key | Action |
|-----|--------|
| **Mouse Wheel** | Zoom in and out |
| **Right-Click + Drag** | Pan the zoomed image |
| **Tab** | Toggle between the original image and an edge-detected view to help with point placement |
| **z** | Undo the last clicked point |
| **r** | Reset all points in the current phase |
| **q** | Quit the current analysis |

## Final Result Window

- Displays the calculated rotation angle
- Press `s` to save a high-resolution image of the analysis
- Press `q` to close the window and proceed (either to the next image in Picture Mode or back to the controls in Camera Mode)

## Output Files

At the end of each session, you will be prompted to save a `.csv` file. This file contains a detailed log of every measurement performed during that session, including:

- `filename`: The source image file
- `catheter_radius_px`: The apparent radius of the catheter in pixels
- `angular_width_deg`: The measured angular width of the feature
- `angle_top_deg`, `angle_bottom_deg`, `angle_midpoint_deg`: The raw angular measurements

## Contributing

Please feel free to submit issues and enhancement requests!

## License

[Your chosen license here]
