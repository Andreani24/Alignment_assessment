import ctypes
import numpy as np
from imageio import imwrite
import threading
import time
import queue

# --- Load the DLL ---
try:
    dll = ctypes.WinDLL(r"C:\Program Files\Swift\Imaging\x64\swiftcam.dll")
except FileNotFoundError:
    print("Error: swiftcam.dll not found. Please ensure it's in the correct path.")
    exit()


# --- C-Style Structure Definitions ---
class SwiftcamDevice(ctypes.Structure):
    _fields_ = [
        ("displayname", ctypes.c_wchar * 64),
        ("id", ctypes.c_wchar * 64),
        ("model", ctypes.c_wchar * 64),
    ]


class FrameInfoV4(ctypes.Structure):
    _fields_ = [
        ("width", ctypes.c_uint),
        ("height", ctypes.c_uint),
        ("flag", ctypes.c_uint),
        ("seq", ctypes.c_uint),
        ("timestamp", ctypes.c_ulonglong),
        ("reserved", ctypes.c_uint * 8),
    ]


# --- DLL Function Prototypes ---
def setup_func(func_name, restype, argtypes):
    func = getattr(dll, func_name)
    func.restype = restype
    func.argtypes = argtypes
    return func


# Setup all DLL functions
Swiftcam_EnumV2 = setup_func("Swiftcam_EnumV2", ctypes.c_int, [ctypes.POINTER(SwiftcamDevice), ctypes.c_int])
Swiftcam_OpenByIndex = setup_func("Swiftcam_OpenByIndex", ctypes.c_void_p, [ctypes.c_int])
Swiftcam_Close = setup_func("Swiftcam_Close", None, [ctypes.c_void_p])
Swiftcam_Stop = setup_func("Swiftcam_Stop", None, [ctypes.c_void_p])
Swiftcam_get_Size = setup_func("Swiftcam_get_Size", ctypes.c_int,
                               [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)])
Swiftcam_get_PixelFormatSupport = setup_func("Swiftcam_get_PixelFormatSupport", ctypes.c_int,
                                             [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_int)])
Swiftcam_get_PixelFormatName = setup_func("Swiftcam_get_PixelFormatName", ctypes.c_char_p, [ctypes.c_int])
Swiftcam_deBayerV2 = setup_func("Swiftcam_deBayerV2", ctypes.c_int,
                                [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_int, ctypes.POINTER(ctypes.c_ubyte),
                                 ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int])
Swiftcam_StartPushModeV4 = setup_func("Swiftcam_StartPushModeV4", ctypes.c_int,
                                      [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p])
EVENT_CALLBACK_TYPE = ctypes.WINFUNCTYPE(None, ctypes.c_uint, ctypes.c_void_p)
Swiftcam_StartPullModeWithCallback = setup_func("Swiftcam_StartPullModeWithCallback", ctypes.c_int,
                                                [ctypes.c_void_p, EVENT_CALLBACK_TYPE, ctypes.c_void_p])
Swiftcam_PullImageV4 = setup_func("Swiftcam_PullImageV4", ctypes.c_int,
                                  [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ubyte), ctypes.c_int,
                                   ctypes.POINTER(FrameInfoV4)])

# --- Global Variables & Synchronization ---
hcam = None
camera_width = 0
camera_height = 0
chosen_fmt = None
chosen_bits = None
actual_bits = None  # New variable to track actual bit depth
BAYER_PATTERN = 3  # Changed to BGGR pattern

stop_event = threading.Event()
frame_queue = queue.Queue(maxsize=4)
frame_ready_event = threading.Event()

push_callback_ref = None
pull_event_callback_ref = None

PUSH_CALLBACK_TYPE = ctypes.WINFUNCTYPE(None, ctypes.POINTER(ctypes.c_ubyte), ctypes.POINTER(FrameInfoV4),
                                        ctypes.c_void_p)


def frame_callback_producer(data, info_ptr, ctx):
    if stop_event.is_set() or frame_queue.full():
        return

    info = info_ptr.contents
    bytes_per_pixel = 2 if chosen_bits > 8 else 1
    buffer_size = info.width * info.height * bytes_per_pixel

    raw_buffer = (ctypes.c_ubyte * buffer_size)()
    ctypes.memmove(raw_buffer, data, buffer_size)
    frame_queue.put(raw_buffer)


def frame_processor_consumer():
    frame_counter = 0
    while not stop_event.is_set():
        try:
            raw_buf = frame_queue.get(timeout=1)
            frame_counter += 1
            print(f"Processing frame {frame_counter}...")

            if frame_counter % 3 == 0:
                rgb_buf = (ctypes.c_ubyte * (camera_width * camera_height * 3))()

                # Use actual_bits for debayering while data is in chosen_bits container
                ret = Swiftcam_deBayerV2(
                    raw_buf,
                    actual_bits,  # Use actual bit depth (12 for RAW12)
                    rgb_buf,
                    24,
                    camera_width,
                    camera_height,
                    BAYER_PATTERN
                )

                if ret == 0:
                    arr = np.frombuffer(rgb_buf, dtype=np.uint8).reshape((camera_height, camera_width, 3))
                    fname = f"frame_push_color_{frame_counter}.png"
                    imwrite(fname, arr)
                    print(f"Saved {fname}")
                else:
                    print(f"deBayer failed with code: {ret}")
                    print(
                        f"Debug info: bits={actual_bits}, pattern={BAYER_PATTERN}, size={camera_width}x{camera_height}")

            if frame_counter >= 12:
                stop_event.set()

        except queue.Empty:
            continue
        except Exception as e:
            print(f"Error in frame processor: {e}")
            break


def event_callback_pull(event, ctx):
    if event == 0x0001:
        frame_ready_event.set()


def use_pull_mode():
    global pull_event_callback_ref

    pull_event_callback_ref = EVENT_CALLBACK_TYPE(event_callback_pull)
    ret = Swiftcam_StartPullModeWithCallback(hcam, pull_event_callback_ref, None)
    if ret != 0:
        print(f"Failed to start pull mode, code: {ret}")
        return False

    print("Pull mode started...")
    frame_counter = 0

    while frame_counter < 12 and not stop_event.is_set():
        if not frame_ready_event.wait(timeout=2):
            continue
        frame_ready_event.clear()

        bytes_per_pixel = 2 if chosen_bits > 8 else 1
        buf_size = camera_width * camera_height * bytes_per_pixel
        raw_buf = (ctypes.c_ubyte * buf_size)()
        frame_info = FrameInfoV4()

        ret = Swiftcam_PullImageV4(hcam, raw_buf, chosen_bits, ctypes.byref(frame_info))
        if ret == 0:
            frame_counter += 1
            if frame_counter % 3 == 0:
                rgb_buf = (ctypes.c_ubyte * (camera_width * camera_height * 3))()
                ret_db = Swiftcam_deBayerV2(raw_buf, actual_bits, rgb_buf, 24,
                                            camera_width, camera_height, BAYER_PATTERN)
                if ret_db == 0:
                    arr = np.frombuffer(rgb_buf, dtype=np.uint8).reshape((camera_height, camera_width, 3))
                    fname = f"frame_pull_{frame_counter}.png"
                    imwrite(fname, arr)
                    print(f"Saved {fname}")
                else:
                    print(f"deBayer failed with code: {ret_db}")
        elif ret != -2:
            time.sleep(0.1)

    return True


def main():
    global hcam, camera_width, camera_height, chosen_fmt, chosen_bits, actual_bits, push_callback_ref

    MAX_CAMERAS = 8
    devs = (SwiftcamDevice * MAX_CAMERAS)()
    num = Swiftcam_EnumV2(devs, MAX_CAMERAS)
    if num <= 0:
        print("No cameras found.")
        return

    hcam = Swiftcam_OpenByIndex(0)
    if not hcam:
        print("Failed to open camera.")
        return

    try:
        w, h = ctypes.c_int(), ctypes.c_int()
        if Swiftcam_get_Size(hcam, ctypes.byref(w), ctypes.byref(h)) != 0:
            print("Failed to get camera resolution.")
            return

        camera_width, camera_height = w.value, h.value
        print(f"Resolution: {camera_width}x{camera_height}")

        fmt = ctypes.c_int()
        supported_formats = {}
        for i in range(8):
            if Swiftcam_get_PixelFormatSupport(hcam, i, ctypes.byref(fmt)) == 0:
                name_ptr = Swiftcam_get_PixelFormatName(fmt.value)
                if name_ptr:
                    name = name_ptr.decode()
                    supported_formats[name] = fmt.value

        if "RAW12" in supported_formats:
            chosen_fmt = supported_formats["RAW12"]
            chosen_bits = 16  # Container depth
            actual_bits = 12  # Actual bit depth
            print("Using RAW12 format")
        elif "RAW8" in supported_formats:
            chosen_fmt = supported_formats["RAW8"]
            chosen_bits = actual_bits = 8
            print("Using RAW8 format")
        else:
            print("No supported RAW format found.")
            return

        consumer_thread = threading.Thread(target=frame_processor_consumer)
        consumer_thread.start()

        push_callback_ref = PUSH_CALLBACK_TYPE(frame_callback_producer)
        ret = Swiftcam_StartPushModeV4(hcam, push_callback_ref, None, None)

        if ret == 0:
            print("Push mode started successfully.")
            stop_event.wait(timeout=30)
        else:
            print(f"Push mode failed (code: {ret}), trying pull mode...")
            stop_event.set()
            consumer_thread.join()
            stop_event.clear()

            if not use_pull_mode():
                print("Both modes failed.")
                return

    finally:
        print("\nCleaning up...")
        stop_event.set()
        if 'consumer_thread' in locals() and consumer_thread.is_alive():
            consumer_thread.join()
        Swiftcam_Stop(hcam)
        Swiftcam_Close(hcam)
        print("Camera closed.")


if __name__ == "__main__":
    main()