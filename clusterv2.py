# assistive_head_speech_control_stable.py
import cv2
import mediapipe as mp
import numpy as np
from collections import deque
import pyautogui
import math
import threading
import time
import keyboard
import speech_recognition as sr
import argparse
from fuzzywuzzy import process


# Global settings & state

MONITOR_WIDTH, MONITOR_HEIGHT = pyautogui.size()
CENTER_X = MONITOR_WIDTH // 2
CENTER_Y = MONITOR_HEIGHT // 2

mouse_control_enabled = True
filter_length = 8

# Shared mouse target position
mouse_target = [CENTER_X, CENTER_Y]
mouse_lock = threading.Lock()


calibration_offset_yaw = 0.0
calibration_offset_pitch = 0.0

# Buffers to smooth ray origin & direction
ray_origins = deque(maxlen=filter_length)
ray_directions = deque(maxlen=filter_length)

# Last raw angles for calibration
raw_yaw_deg = 180.0
raw_pitch_deg = 180.0

# Speech Mode
mode = "typing"
state_lock = threading.Lock()

# Recognizer
recognizer = sr.Recognizer()

# --- Argument parsing for camera/mic ---
parser = argparse.ArgumentParser()
parser.add_argument("--camera", type=int, default=0, help="Index of the camera to use.")
parser.add_argument("--mic", type=int, default=0, help="Index of the microphone to use.")
parser.add_argument("--super-accuracy", action="store_true", help="Enable super accuracy mode.")
args = parser.parse_args()

mic = sr.Microphone(device_index=args.mic)


# MediaPipe Face Mesh init

mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(static_image_mode=False,
                                  max_num_faces=1,
                                  refine_landmarks=True,
                                  min_detection_confidence=0.5,
                                  min_tracking_confidence=0.5)


LANDMARKS = {"left": 234, "right": 454, "top": 10, "bottom": 152, "front": 1}

# Face outline indices for visualization
FACE_OUTLINE_INDICES = [
    10, 338, 297, 332, 284, 251, 389, 356,
    454, 323, 361, 288, 397, 365, 379, 378,
    400, 377, 152, 148, 176, 149, 150, 136,
    172, 58, 132, 93, 234, 127, 162, 21,
    54, 103, 67, 109
]

# Command map dictionary

command_map = {
    # Editing
    "copy": ["ctrl", "c"], "paste": ["ctrl", "v"], "cut": ["ctrl", "x"],
    "select all": ["ctrl", "a"], "save": ["ctrl", "s"], "undo": ["ctrl", "z"],
    "redo": ["ctrl", "y"], "find": ["ctrl", "f"],
    # Browser
    "new tab": ["ctrl", "t"], "close tab": ["ctrl", "w"], "reopen tab": ["ctrl", "shift", "t"],
    # Windows
    "desktop": ["win", "d"], "file explorer": ["win", "e"], "lock": ["win", "l"],
    "run": ["win", "r"], "search": ["win", "s"], "task manager": ["ctrl", "shift", "esc"],
    "switch window": ["alt", "tab"], "screenshot": ["win", "printscreen"],
    # Special keys
    "enter": ["enter"], "backspace": ["backspace"], "tab": ["tab"], "space": ["space"],
    "escape": ["esc"], "delete": ["delete"], "up": ["up"], "down": ["down"],
    "left": ["left"], "right": ["right"], "control": ["ctrl"], "shift": ["shift"], "alt": ["alt"], "windows": ["win"]
}

# Function keys
for i in range(1, 13):
    command_map[f"f{i}"] = [f"f{i}"]

# Letters and numbers
for letter in "abcdefghijklmnopqrstuvwxyz":
    command_map[f"press {letter}"] = [letter]
for num in range(10):
    command_map[f"press {num}"] = [str(num)]

# ------------------------
# Mouse commands handled separately
# ------------------------
mouse_commands = ("left click", "right click", "double click", "click and hold",
                  "release click", "scroll up", "scroll down", "move mouse to center",
                  "center mouse", "toggle mouse", "calibrate", "center")


# Mouse mover function

def mouse_mover():
    global mouse_target, mouse_control_enabled
    while True:
        if mouse_control_enabled:
            with mouse_lock:
                x, y = mouse_target
            try:
                pyautogui.moveTo(int(x), int(y))
            except Exception:
                pass
        time.sleep(0.02)

threading.Thread(target=mouse_mover, daemon=True).start()


# Speech command handler

def perform_command_from_text(text):
    global mode, mouse_control_enabled, calibration_offset_yaw, calibration_offset_pitch, raw_yaw_deg, raw_pitch_deg
    text = text.lower().strip()
    print(f"[voice] {text}")

    with state_lock:
        if text in ("command mode", "command"):
            mode = "command"
            print("[mode] -> COMMAND")
            return
        if text in ("typing mode", "typing", "dictation mode", "dictation"):
            mode = "typing"
            print("[mode] -> TYPING")
            return
        if "calibrate" in text or "center" in text:
            calibration_offset_yaw = 180.0 - raw_yaw_deg
            calibration_offset_pitch = 180.0 - raw_pitch_deg
            print(f"[calibration] offsets set yaw={calibration_offset_yaw}, pitch={calibration_offset_pitch}")
            return
        if "toggle mouse" in text or "toggle cursor" in text:
            mouse_control_enabled = not mouse_control_enabled
            print(f"[mouse] {'enabled' if mouse_control_enabled else 'disabled'} by voice")
            return

        current_mode = mode

    if current_mode == "typing":
        try:
            pyautogui.typewrite(text + " ")
            print("[typed]", text)
        except Exception as e:
            print("Typing error:", e)
        return

    if current_mode == "command":
        # --- Fuzzy matching for command mode ---
        all_commands = list(command_map.keys()) + list(mouse_commands)
        best_match, score = process.extractOne(text, all_commands)

        if args.super_accuracy:
            text = best_match
            print(f"[voice] SUPER ACCURACY corrected to '{text}' with score {score}")
        elif score > 80: # Confidence threshold
            text = best_match
            print(f"[voice] corrected to '{text}' with score {score}")

        # Mouse actions
        if "left click" in text or text == "click":
            pyautogui.click(); print("[action] left click"); return
        if "right click" in text or "right-click" in text:
            pyautogui.click(button="right"); print("[action] right click"); return
        if "double click" in text or "double-click" in text:
            pyautogui.doubleClick(); print("[action] double click"); return
        if "click and hold" in text or "hold click" in text:
            pyautogui.mouseDown(); print("[action] mouse down"); return
        if "release" in text or "release click" in text:
            pyautogui.mouseUp(); print("[action] mouse up"); return
        if "scroll up" in text:
            pyautogui.scroll(500); print("[action] scroll up"); return
        if "scroll down" in text:
            pyautogui.scroll(-500); print("[action] scroll down"); return
        if "move mouse to center" in text or text == "center mouse":
            with mouse_lock: mouse_target[0]=CENTER_X; mouse_target[1]=CENTER_Y
            print("[action] mouse moved to center"); return

        # Command map
        if text in command_map:
            keys = command_map[text]
            try:
                if len(keys)==1 and len(keys[0])==1 and keys[0].isalnum():
                    pyautogui.press(keys[0])
                else:
                    pyautogui.hotkey(*keys)
                print(f"[action] executed command map: {text} -> {keys}")
            except Exception as e:
                print("Hotkey error:", e)
            return

        # fallback: press <char>
        tokens = text.split()
        if len(tokens) >= 2 and tokens[0] in ("press", "type"):
            target = tokens[1]
            if len(target)==1: pyautogui.press(target); print(f"[action] pressed {target}"); return
            words_to_nums = {"zero":"0","one":"1","two":"2","three":"3","four":"4","five":"5","six":"6","seven":"7","eight":"8","nine":"9","ten":"10"}
            if target in words_to_nums: pyautogui.press(words_to_nums[target]); print(f"[action] pressed {words_to_nums[target]}"); return

        print("[voice] command not recognized in command mode:", text)

def speech_callback(recognizer_obj, audio):
    try:
        text = recognizer_obj.recognize_google(audio)
        perform_command_from_text(text)
    except sr.UnknownValueError:
        pass
    except sr.RequestError as e:
        print("Speech recognition request error:", e)
    except Exception as e:
        print("Speech callback error:", e)

def start_speech_listener():
    with mic as source: recognizer.adjust_for_ambient_noise(source, duration=1)
    stop_listening = recognizer.listen_in_background(mic, speech_callback, phrase_time_limit=5)
    return stop_listening

# Start speech listener in background
stop_speech = start_speech_listener()


# Camera & Head-tracking loop

DEADZONE_YAW = 2.0
DEADZONE_PITCH = 2.0
CURSOR_SMOOTHING = 0.2

prev_mouse_x, prev_mouse_y = CENTER_X, CENTER_Y

cap = cv2.VideoCapture(args.camera)
if not cap.isOpened():
    print(f"Error: Camera with index {args.camera} not found")
    exit()

def landmark_to_np(landmark, w, h):
    return np.array([landmark.x * w, landmark.y * h, landmark.z * w])

while cap.isOpened():
    ret, frame = cap.read()
    if not ret: break

    h, w, _ = frame.shape
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = face_mesh.process(rgb)

    landmarks_frame = np.zeros_like(frame)

    if results.multi_face_landmarks:
        face_landmarks = results.multi_face_landmarks[0].landmark
        outline_pts = []

        # Draw landmarks
        for i, landmark in enumerate(face_landmarks):
            pt = landmark_to_np(landmark, w, h)
            x, y = int(pt[0]), int(pt[1])
            if 0 <= x < w and 0 <= y < h:
                color = (155, 155, 155) if i in FACE_OUTLINE_INDICES else (255, 25, 10)
                cv2.circle(landmarks_frame, (x, y), 2, color, -1)
                frame[y, x] = (255, 255, 255)

        # Extract key points
        key_points = {name: landmark_to_np(face_landmarks[idx], w, h) for name, idx in LANDMARKS.items()}
        left, right, top, bottom, front = key_points["left"], key_points["right"], key_points["top"], key_points["bottom"], key_points["front"]

        # Oriented axes
        right_axis = (right - left) / np.linalg.norm(right - left)
        up_axis = (top - bottom) / np.linalg.norm(top - bottom)
        forward_axis = np.cross(right_axis, up_axis)
        forward_axis /= np.linalg.norm(forward_axis)
        forward_axis = -forward_axis  # ensure outward

        center = (left + right + top + bottom + front) / 5
        half_width = np.linalg.norm(right - left) / 2
        half_height = np.linalg.norm(top - bottom) / 2
        half_depth = 80

        ray_origins.append(center)
        ray_directions.append(forward_axis)

        avg_origin = np.mean(ray_origins, axis=0)
        avg_direction = np.mean(ray_directions, axis=0)
        avg_direction /= np.linalg.norm(avg_direction)

        reference_forward = np.array([0, 0, -1])
        xz_proj = np.array([avg_direction[0], 0, avg_direction[2]])
        xz_proj /= np.linalg.norm(xz_proj)
        yaw_rad = math.acos(np.clip(np.dot(reference_forward, xz_proj), -1, 1))
        if avg_direction[0] < 0: yaw_rad = -yaw_rad

        yz_proj = np.array([0, avg_direction[1], avg_direction[2]])
        yz_proj /= np.linalg.norm(yz_proj)
        pitch_rad = math.acos(np.clip(np.dot(reference_forward, yz_proj), -1, 1))
        if avg_direction[1] > 0: pitch_rad = -pitch_rad

        yaw_deg = np.degrees(yaw_rad)
        pitch_deg = np.degrees(pitch_rad)

        if yaw_deg < 0: yaw_deg = abs(yaw_deg)
        elif yaw_deg < 180: yaw_deg = 360 - yaw_deg
        if pitch_deg < 0: pitch_deg = 360 + pitch_deg

        raw_yaw_deg = yaw_deg
        raw_pitch_deg = pitch_deg

        yaw_deg += calibration_offset_yaw
        pitch_deg += calibration_offset_pitch

        # ------------------------
        # Deadzone + smoothing
        # ------------------------
        yaw_diff = yaw_deg - 180.0
        pitch_diff = pitch_deg - 180.0
        if abs(yaw_diff) < DEADZONE_YAW: yaw_deg = 180.0
        if abs(pitch_diff) < DEADZONE_PITCH: pitch_deg = 180.0

        yawDegrees = 20
        pitchDegrees = 10

        screen_x = int(((yaw_deg - (180 - yawDegrees)) / (2 * yawDegrees)) * MONITOR_WIDTH)
        screen_y = int(((180 + pitchDegrees - pitch_deg) / (2 * pitchDegrees)) * MONITOR_HEIGHT)

        screen_x = max(10, min(MONITOR_WIDTH - 10, screen_x))
        screen_y = max(10, min(MONITOR_HEIGHT - 10, screen_y))

        smooth_x = int(prev_mouse_x + (screen_x - prev_mouse_x) * CURSOR_SMOOTHING)
        smooth_y = int(prev_mouse_y + (screen_y - prev_mouse_y) * CURSOR_SMOOTHING)

        with mouse_lock:
            mouse_target[0] = smooth_x
            mouse_target[1] = smooth_y

        prev_mouse_x, prev_mouse_y = smooth_x, smooth_y

    # Display frames
    cv2.imshow("Head-Aligned Cube", frame)
    cv2.imshow("Landmarks", landmarks_frame)

    # Keyboard shortcuts
    if keyboard.is_pressed('f7'):
        mouse_control_enabled = not mouse_control_enabled
        print(f"[Mouse Control] {'Enabled' if mouse_control_enabled else 'Disabled'}")
        time.sleep(0.3)

    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break
    elif key == ord('c'):
        calibration_offset_yaw = 180 - raw_yaw_deg
        calibration_offset_pitch = 180 - raw_pitch_deg
        print(f"[Calibrated] Offset Yaw: {calibration_offset_yaw}, Offset Pitch: {calibration_offset_pitch}")

cap.release()
cv2.destroyAllWindows()
