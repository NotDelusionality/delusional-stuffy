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

# -----------------
# Removed: import speech_recognition as sr
# Added Vosk and sounddevice imports
from vosk import Model, KaldiRecognizer
import sounddevice as sd
import json
# -----------------

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

# -----------------
# Removed original speech_recognition recognizer and mic
# recognizer = sr.Recognizer()
# mic = sr.Microphone()
# -----------------

# Initialize Vosk model and recognizer
model = Model("model")  # Make sure you have downloaded the Vosk model folder named 'model'
recognizer = KaldiRecognizer(model, 16000)

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
        for cmd, keys in command_map.items():
            if cmd in text:
                try:
                    if len(keys)==1 and len(keys[0])==1 and keys[0].isalnum():
                        pyautogui.press(keys[0])
                    else:
                        pyautogui.hotkey(*keys)
                    print(f"[action] executed command map: {cmd} -> {keys}")
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

# -----------------
# Removed original speech_recognition background listener
# def speech_callback(recognizer_obj, audio):
#     try:
#         text = recognizer_obj.recognize_google(audio)
#         perform_command_from_text(text)
#     except sr.UnknownValueError:
#         pass
#     except sr.RequestError as e:
#         print("Speech recognition request error:", e)
#     except Exception as e:
#         print("Speech callback error:", e)

# def start_speech_listener():
#     with mic as source: recognizer.adjust_for_ambient_noise(source, duration=1)
#     stop_listening = recognizer.listen_in_background(mic, speech_callback, phrase_time_limit=5)
#     return stop_listening

# stop_speech = start_speech_listener()
# -----------------

# New Vosk callback function
def vosk_callback(indata, frames, time_info, status):
    if status:
        print(status)
    if recognizer.AcceptWaveform(indata):
        result = recognizer.Result()
        result_dict = json.loads(result)
        text = result_dict.get("text", "")
        if text:
            perform_command_from_text(text)

# Start Vosk listening in background thread
def start_vosk_listener():
    with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype='int16',
                           channels=1, callback=vosk_callback):
        print("[Vosk] Listening...")
        while True:
            sd.sleep(1000)

threading.Thread(target=start_vosk_listener, daemon=True).start()


# Camera & Head-tracking loop

DEADZONE_YAW = 2.0
DEADZONE_PITCH = 2.0
CURSOR_SMOOTHING = 0.2

prev_mouse_x, prev_mouse_y = CENTER_X, CENTER_Y

cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("Error: Camera not found")
    exit()

def landmark_to_np(landmark, w, h):
    return np.array([landmark.x * w, landmark.y * h, landmark.z * w])

while cap.isOpened():
    ret, frame = cap.read()
    if not ret: break

    h, w, _ = frame.shape
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = face_mesh.process(rgb)

    if results.multi_face_landmarks:
        face_landmarks = results.multi_face_landmarks[0]
        pts = [landmark_to_np(face_landmarks.landmark[i], w, h) for i in FACE_OUTLINE_INDICES]

        # Draw face outline
        for i in range(len(pts) - 1):
            cv2.line(frame, tuple(pts[i][:2].astype(int)), tuple(pts[i+1][:2].astype(int)), (0,255,0), 1)

        # Get key landmarks for yaw/pitch estimation
        left = landmark_to_np(face_landmarks.landmark[LANDMARKS["left"]], w, h)
        right = landmark_to_np(face_landmarks.landmark[LANDMARKS["right"]], w, h)
        top = landmark_to_np(face_landmarks.landmark[LANDMARKS["top"]], w, h)
        bottom = landmark_to_np(face_landmarks.landmark[LANDMARKS["bottom"]], w, h)
        front = landmark_to_np(face_landmarks.landmark[LANDMARKS["front"]], w, h)

        # Calculate yaw (horizontal rotation)
        dx = right[0] - left[0]
        dy = right[1] - left[1]
        yaw_rad = math.atan2(dy, dx)
        yaw_deg = math.degrees(yaw_rad)

        # Calculate pitch (vertical rotation)
        dx2 = top[0] - bottom[0]
        dy2 = top[1] - bottom[1]
        pitch_rad = math.atan2(dy2, dx2)
        pitch_deg = math.degrees(pitch_rad)

        # Normalize and apply calibration offset
        raw_yaw_deg = yaw_deg
        raw_pitch_deg = pitch_deg
        yaw_deg += calibration_offset_yaw
        pitch_deg += calibration_offset_pitch

        # Clamp and deadzone
        yaw_deg = np.clip(yaw_deg, -45, 45)
        pitch_deg = np.clip(pitch_deg, -30, 30)

        if abs(yaw_deg) < DEADZONE_YAW: yaw_deg = 0
        if abs(pitch_deg) < DEADZONE_PITCH: pitch_deg = 0

        # Map head rotation to mouse position
        mouse_x = CENTER_X + yaw_deg / 45 * (MONITOR_WIDTH / 2)
        mouse_y = CENTER_Y + pitch_deg / 30 * (MONITOR_HEIGHT / 2)

        # Smooth movement
        prev_mouse_x = (1 - CURSOR_SMOOTHING) * prev_mouse_x + CURSOR_SMOOTHING * mouse_x
        prev_mouse_y = (1 - CURSOR_SMOOTHING) * prev_mouse_y + CURSOR_SMOOTHING * mouse_y

        with mouse_lock:
            mouse_target[0] = prev_mouse_x
            mouse_target[1] = prev_mouse_y

        # Display info
        cv2.putText(frame, f"Yaw: {yaw_deg:.1f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255,0,0), 2)
        cv2.putText(frame, f"Pitch: {pitch_deg:.1f}", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1, (255,0,0), 2)
        cv2.putText(frame, f"Mode: {mode.upper()}", (10, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 2)

    cv2.imshow("Assistive Head & Speech Control", frame)
    key = cv2.waitKey(1) & 0xFF
    if key == 27 or keyboard.is_pressed("esc"):
        break

cap.release()
cv2.destroyAllWindows()
