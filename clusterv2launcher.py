import customtkinter as ctk
import threading, subprocess, os, re, sys
from CTkMessagebox import CTkMessagebox
from PIL import Image, ImageTk
import cv2
import time
import speech_recognition as sr

# ---------------- COLORS ----------------
BG = "#16181d"
CARD = "#23242a"
NEON_CYAN = "#00fff7"
NEON_PURPLE = "#a259f7"
NEON_DANGER = "#ff005a"
FADE = "#393b40"
TEXT = "#e9e9e9"
HEADER = "#ffffff"
SUBTLE = "#b0b1bb"

# ---------------- PATHS ----------------
# Logic to handle both running from source and from a cx_Freeze executable
if getattr(sys, "frozen", False):
    # Running in a bundle
    SCRIPT_DIR = os.path.dirname(sys.executable)
    EXE_NAME = "BocelliCore.exe" if sys.platform == "win32" else "BocelliCore"
    SCRIPT_NAME = os.path.join(SCRIPT_DIR, EXE_NAME)
else:
    # Running in a normal Python environment
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    SCRIPT_NAME = os.path.join(SCRIPT_DIR, "clusterv2.py")

running_process = None

# ------------------ Camera Preview State ------------------
_preview_thread = None
_preview_running = False
_preview_lock = threading.Lock()
_preview_capture = None
_preview_photo = None

# ------------------ Selected devices ------------------
selected_camera = None
selected_microphone = None

# ---------------- CORE FUNCTIONS ----------------
def start_system():
    global running_process, _preview_running
    # If the launcher is running a preview, stop it to free the camera for the subprocess
    if _preview_running:
        stop_camera_preview()
        add_log("Camera preview stopped to allow the control app to start.")

    if running_process is not None:
        CTkMessagebox(title="Already Running", message="System is already running.", icon="info")
        return
    if not os.path.exists(SCRIPT_NAME):
        CTkMessagebox(title="Error", message=f"Script not found:\n{SCRIPT_NAME}", icon="cancel")
        return

    def run():
        global running_process
        try:
            cam_idx = 0
            mic_idx = 0
            if selected_camera and selected_camera.get():
                try:
                    cam_idx = int(re.search(r'\d+$', selected_camera.get()).group())
                except (AttributeError, ValueError):
                    pass # Keep default if parsing fails

            if selected_microphone and selected_microphone.get():
                try:
                    mic_idx = get_microphone_devices().index(selected_microphone.get())
                except (ValueError):
                    pass # Keep default if not found

            # When running from source, we need to invoke python.
            # When running from frozen, the script is an executable.
            if getattr(sys, "frozen", False):
                 command = [SCRIPT_NAME, f"--camera={cam_idx}", f"--mic={mic_idx}"]
            else:
                 command = [sys.executable, SCRIPT_NAME, f"--camera={cam_idx}", f"--mic={mic_idx}"]

            add_log(f"Starting with command: {' '.join(command)}")

            running_process = subprocess.Popen(command)
            running_process.wait()
        except Exception as e:
            add_log(f"Failed to launch. Get Better lol: {e}")
        finally:
            running_process = None
            set_status("OFFLINE", NEON_DANGER)
            add_log("System off :(")

    threading.Thread(target=run, daemon=True).start()
    set_status("ONLINE", NEON_CYAN)
    add_log("System on Bros.")


def stop_system():
    global running_process
    if running_process is not None:
        try:
            running_process.terminate()
            add_log("Sent terminate to system process.")
        except Exception as e:
            add_log(f"Error terminating process: {e}")
        running_process = None
        set_status("OFFLINE", NEON_DANGER)
        add_log("System stopped by user.")
    else:
        add_log("No running process to stop.")


def set_status(text, color):
    status_label.configure(text=text, text_color=color)
    status_bar.configure(fg_color=color)


def add_log(msg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    log_textbox.configure(state="normal")
    log_textbox.insert("end", f"[{timestamp}] {msg}\n")
    log_textbox.configure(state="disabled")
    log_textbox.see("end")

# ---------------- Helper: parse commands from clusterv2.py ----------------
def parse_commands_from_script(path):
    """Parse command keys and mouse commands from the clusterv2.py script without executing it."""
    commands = []
    mouse_cmds = []
    try:
        text = open(path, 'r', encoding='utf-8').read()
    except Exception:
        return commands, mouse_cmds

    # Find command_map keys like "copy": [ ... ]
    keys = re.findall(r'["\']([^"\']+)["\']\s*:\s*\[', text)
    commands.extend(sorted(set(keys)))

    # Find mouse_commands tuple
    m = re.search(r'mouse_commands\s*=\s*\((.*?)\)', text, re.DOTALL)
    if m:
        inner = m.group(1)
        mouse_cmds = re.findall(r'["\']([^"\']+)["\']', inner)

    # Also add generated groups: f1-f12, press a-z, press 0-9
    fn_keys = [f"f{i}" for i in range(1,13)]
    press_letters = [f"press {c}" for c in 'abcdefghijklmnopqrstuvwxyz']
    press_nums = [f"press {i}" for i in range(10)]

    commands += fn_keys + press_letters + press_nums

    # De-dup and sort
    commands = sorted(set(commands), key=lambda s: (len(s), s))
    mouse_cmds = sorted(set(mouse_cmds))
    return commands, mouse_cmds

# ---------------- Camera Preview ----------------
from PIL import Image, ImageTk

def _camera_loop(label_widget, camera_index=0):
    global _preview_running, _preview_capture, _preview_photo
    try:
        cap = cv2.VideoCapture(camera_index)
        if not cap.isOpened():
            add_log("Camera not found or in use.")
            _preview_running = False
            return
        _preview_capture = cap
        add_log("Camera preview started (launcher).")

        while _preview_running:
            ret, frame = cap.read()
            if not ret:
                break
            # Convert BGR to RGB and resize to fit the label
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, _ = frame.shape
            # Fit into preview area (max width 520, height 260)
            max_w, max_h = 520, 260
            scale = min(max_w / w, max_h / h, 1.0)
            new_w, new_h = int(w * scale), int(h * scale)
            frame = cv2.resize(frame, (new_w, new_h))
            img = Image.fromarray(frame)
            _preview_photo = ImageTk.PhotoImage(img)
            # Updating the label must happen in the main thread
            try:
                label_widget.configure(image=_preview_photo)
            except Exception:
                pass
            time.sleep(0.03)
    except Exception as e:
        add_log(f"Camera preview error: {e}")
    finally:
        try:
            if _preview_capture is not None:
                _preview_capture.release()
        except Exception:
            pass
        _preview_capture = None
        _preview_running = False
        label_widget.configure(image='')
        add_log("Camera preview stopped.")


def start_camera_preview(label_widget, camera_index=0):
    global _preview_thread, _preview_running
    if _preview_running:
        add_log("Preview already running.")
        return
    _preview_running = True
    _preview_thread = threading.Thread(target=_camera_loop, args=(label_widget, camera_index), daemon=True)
    _preview_thread.start()


def stop_camera_preview():
    global _preview_running, _preview_capture
    if not _preview_running:
        return
    _preview_running = False
    # release capture if present
    try:
        if _preview_capture is not None:
            _preview_capture.release()
    except Exception:
        pass

# ---------------- Device Discovery ----------------
def get_camera_devices():
    """Returns a list of camera device names."""
    devices = []
    i = 0
    while True:
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if not cap.isOpened():
            break
        devices.append(f"Camera {i}")
        cap.release()
        i += 1
    return devices if devices else ["No cameras found"]

def get_microphone_devices():
    """Returns a list of microphone device names."""
    try:
        return sr.Microphone.list_microphone_names()
    except Exception:
        return ["No microphones found"]

# ---------------- Help UI ----------------

def show_help_dialog():
    text = (
        "Usage Help:\n\n"
        "• Start: Launches the control app .\n"
        "• Stop: Terminates the control app.\n"
        "• Preview Camera: Opens a local camera preview in this launcher (won't affect clusterv2 unless both try to use the same camera).\n"
        "• Advanced options contain keyboard shortcuts used by the control app (clusterv2).\n\n"
        "Note: If the control app is already running, it will likely own the webcam. The launcher preview will stop automatically when starting the control app to avoid conflicts."
    )
    CTkMessagebox(title="Help — The Bocelli Launcher", message=text, icon="info")


def show_commands_window():
    commands, mouse_cmds = parse_commands_from_script(SCRIPT_NAME)
    win = ctk.CTkToplevel(root)
    win.title("Available Voice Commands")
    win.geometry("680x540")
    win.configure(bg=BG)

    header = ctk.CTkLabel(win, text="Words & Commands to Speak", font=("Segoe UI", 16, "bold"), text_color=NEON_CYAN)
    header.pack(pady=(14,6))

    subtitle = ctk.CTkLabel(win, text="This list is a list of commands for command mode. Practice", font=("Segoe UI", 10), text_color=SUBTLE)
    subtitle.pack(pady=(0,8))

    frame = ctk.CTkFrame(win, fg_color=CARD, corner_radius=8)
    frame.pack(fill="both", expand=True, padx=12, pady=12)

    text_widget = ctk.CTkTextbox(frame, width=640, height=420, font=("Consolas", 11), fg_color="#191a20", text_color=TEXT)
    text_widget.pack(padx=10, pady=10, fill="both", expand=True)

    text_widget.insert("end", "-- Command map words --\n")
    for c in commands:
        text_widget.insert("end", c + "\n")
    text_widget.insert("end", "\n-- Mouse & Special Commands --\n")
    for c in mouse_cmds:
        text_widget.insert("end", c + "\n")

    text_widget.configure(state="disabled")

    def copy_to_clipboard():
        win.clipboard_clear()
        content = text_widget.get(1.0, "end")
        win.clipboard_append(content)
        add_log("Commands copied to clipboard.")

    btn_frame = ctk.CTkFrame(win, fg_color="transparent")
    btn_frame.pack(pady=(4,12))
    copy_btn = ctk.CTkButton(btn_frame, text="Copy to Clipboard", command=copy_to_clipboard)
    copy_btn.pack()

# ---------------- MAIN UI ----------------
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

root = ctk.CTk()
root.title("BOCELLI - Assistive Control Dashboard")
root.geometry("980x640")
root.minsize(840, 540)
root.configure(bg=BG)

# ---- Header ----
header = ctk.CTkFrame(root, fg_color=CARD, border_width=0, corner_radius=0)
header.pack(fill="x", pady=(0, 6))
logo = ctk.CTkLabel(header, text="BOCELLI", font=("Segoe UI", 28, "bold"), text_color=NEON_CYAN)
logo.pack(side="left", padx=(22,5), pady=(12,12))
tagline = ctk.CTkLabel(header, text="The Best Head & Speech Control App", font=("Segoe UI", 13), text_color=FADE)
tagline.pack(side="left", padx=(8,0), pady=(22,0))

# Help menu (Option)
help_menu = ctk.CTkOptionMenu(header, values=["Help", "Show Commands", "Usage Help", "About"], command=lambda v: (show_commands_window() if v=="Show Commands" else (show_help_dialog() if v=="Usage Help" else (CTkMessagebox(title="About", message="Bocelli Launcher — 2025")))))
help_menu.set("Help...")
help_menu.pack(side="right", padx=(16,26), pady=(14,10))

# ---- Main Frame ----
body = ctk.CTkFrame(root, fg_color="transparent")
body.pack(fill="both", expand=True, padx=24, pady=(0,8))
body.columnconfigure(1, weight=1)
body.rowconfigure(0, weight=0)
body.rowconfigure(1, weight=1)

# ---- Control Card ----
card = ctk.CTkFrame(body, width=300, height=380, corner_radius=12, fg_color=CARD, border_width=2, border_color=FADE)
card.grid(row=0, column=0, rowspan=2, padx=(0,18), pady=(12,0), sticky="n")

status_label = ctk.CTkLabel(card, text="OFFLINE", font=("Segoe UI", 15, "bold"), text_color=NEON_DANGER)
status_label.pack(pady=(26,8))
status_bar = ctk.CTkLabel(card, text="", fg_color=NEON_DANGER, width=120, height=3, corner_radius=3)
status_bar.pack()

divider = ctk.CTkLabel(card, text="─" * 25, font=("Consolas", 8), text_color=FADE)
divider.pack(pady=(12,8))

start_btn = ctk.CTkButton(card, text="START SYSTEM", command=start_system,
    width=140, height=40, corner_radius=6, fg_color=NEON_CYAN, text_color="#18181d",
    font=("Segoe UI", 13, "bold"), hover_color=NEON_PURPLE, border_width=0)
start_btn.pack(pady=(8,8))

stop_btn = ctk.CTkButton(card, text="STOP SYSTEM", command=stop_system,
    width=140, height=40, corner_radius=6, fg_color=NEON_DANGER, text_color="#fff",
    font=("Segoe UI", 13, "bold"), hover_color=NEON_PURPLE, border_width=0)
stop_btn.pack()

# Advanced section helper
class ExpandableSection(ctk.CTkFrame):
    def __init__(self, master, title, content_func, *args, **kwargs):
        super().__init__(master, fg_color=CARD, corner_radius=9, *args, **kwargs)
        self.open = False
        self.content_func = content_func
        self.header = ctk.CTkButton(
            self, text=title, fg_color=CARD, corner_radius=9, hover_color=NEON_CYAN,
            font=("Segoe UI", 14, "bold"), text_color=HEADER, anchor="w", command=self.toggle
        )
        self.header.pack(fill="x", padx=3, pady=(6, 0))
        self.body = ctk.CTkFrame(self, fg_color=CARD, corner_radius=6)
        self.body.pack(fill="both", expand=False, padx=10, pady=(0, 8))
        self.body.pack_forget()

    def toggle(self):
        if self.open:
            self.body.pack_forget()
            self.open = False
        else:
            for widget in self.body.winfo_children():
                widget.destroy()
            self.content_func(self.body)
            self.body.pack(fill="both", expand=True, padx=10, pady=(0, 8))
            self.open = True


def advanced_content(parent):
    global selected_camera, selected_microphone
    ctk.CTkLabel(parent, text="Device Selection", font=("Segoe UI", 12, "bold"), text_color=NEON_CYAN).pack(anchor="nw", pady=(8,4))

    # Camera selection
    ctk.CTkLabel(parent, text="Camera:", font=("Segoe UI", 10)).pack(anchor="nw")
    camera_list = get_camera_devices()
    selected_camera = ctk.StringVar(value=camera_list[0])
    cam_menu = ctk.CTkOptionMenu(parent, variable=selected_camera, values=camera_list)
    cam_menu.pack(anchor="nw", fill="x", pady=(2,8))

    # Mic selection
    ctk.CTkLabel(parent, text="Microphone:", font=("Segoe UI", 10)).pack(anchor="nw")
    mic_list = get_microphone_devices()
    selected_microphone = ctk.StringVar(value=mic_list[0])
    mic_menu = ctk.CTkOptionMenu(parent, variable=selected_microphone, values=mic_list)
    mic_menu.pack(anchor="nw", fill="x", pady=(2,12))

    ctk.CTkLabel(parent, text="Calibration & Debug", font=("Segoe UI", 12, "bold"), text_color=NEON_CYAN).pack(anchor="nw", pady=(10,2))
    ctk.CTkLabel(
        parent,
        text=("• Press [C] in the camera window to calibrate center.\n"
              "• Press [F7] to toggle mouse control.\n"
              "• Press [Q] to quit the control app.\n"),
        font=("Segoe UI", 10),
        text_color=SUBTLE,
        justify="left"
    ).pack(anchor="nw", pady=2)

ExpandableSection(card, "Advanced Options", advanced_content).pack(fill="x", padx=10, pady=(18, 10))

# ----- Camera Preview Card (top right) -----
camera_card = ctk.CTkFrame(body, width=560, height=280, corner_radius=12, fg_color=CARD, border_width=2, border_color=FADE)
camera_card.grid(row=0, column=1, padx=(0,0), pady=(12,0), sticky="nsew")

camera_header = ctk.CTkLabel(camera_card, text="Camera Preview", font=("Segoe UI", 13, "bold"), text_color=NEON_CYAN)
camera_header.pack(anchor="w", padx=14, pady=(12,4))

preview_label = ctk.CTkLabel(camera_card, text="", width=520, height=260, fg_color="#0f1013", corner_radius=8)
preview_label.pack(padx=10, pady=(4,12))

# preview controls
preview_btn_frame = ctk.CTkFrame(camera_card, fg_color="transparent")
preview_btn_frame.pack(pady=(0,10))

def _toggle_preview():
    global _preview_running
    if _preview_running:
        stop_camera_preview()
        preview_toggle_button.configure(text="Start Preview")
    else:
        start_camera_preview(preview_label)
        preview_toggle_button.configure(text="Stop Preview")

preview_toggle_button = ctk.CTkButton(preview_btn_frame, text="Start Preview", command=_toggle_preview,
                                       width=140, height=36, corner_radius=6, fg_color=NEON_CYAN, text_color="#101214")
preview_toggle_button.pack()

# ---- Log Section (below camera) ----
log_card = ctk.CTkFrame(body, width=640, height=260, corner_radius=12, fg_color=CARD, border_width=2, border_color=FADE)
log_card.grid(row=1, column=1, padx=(0,0), pady=(12,12), sticky="nsew")

log_label = ctk.CTkLabel(log_card, text="SYSTEM LOG", font=("Segoe UI", 12, "bold"), text_color=NEON_CYAN)
log_label.pack(anchor="w", padx=18, pady=(16,0))

log_textbox = ctk.CTkTextbox(log_card, width=640, height=200, font=("Consolas", 11),
                             fg_color="#191a20", text_color=TEXT, border_width=0, corner_radius=8)
log_textbox.pack(padx=14, pady=(8,14), fill="both", expand=True)
log_textbox.insert("end", "Ready.\n")
log_textbox.configure(state="disabled")

# ---- Footer ----
footer = ctk.CTkLabel(root, text="© 2025 Bocelli Corp. All Rights Reserved Bukenya Abdul-Harkeem", font=("Segoe UI", 10), text_color=FADE)
footer.pack(side="bottom", pady=8)

# ---------------- Cleanup on close ----------------
def _on_close():
    try:
        stop_camera_preview()
    except Exception:
        pass
    try:
        if running_process is not None:
            running_process.terminate()
    except Exception:
        pass
    root.destroy()

root.protocol("WM_DELETE_WINDOW", _on_close)

root.mainloop()
