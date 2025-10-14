import sys
from cx_Freeze import setup, Executable

# Dependencies
build_exe_options = {
    "packages": [
        "os", "sys", "subprocess", "threading", "time", "math", "random",
        "cv2", "mediapipe", "numpy", "pyautogui", "keyboard",
        "speech_recognition", "customtkinter", "PIL", "matplotlib", 
    ],
    "include_files": [
        ("clusterv2.py", "clusterv2.py"),   # main app
                       
    ],
    "excludes": ["tkinter.test", "unittest", "email"],
}

# Main launcher file — the one the user double-clicks
main_script = "clusterv2launcher.py"

# Hide console window if GUI app
base = None
if sys.platform == "win32":
    base = "Win32GUI"

setup(
    name="BocelliApp",
    version="1.0",
    description="Bocelli Voice and Facial Control",
    options={"build_exe": build_exe_options},
    executables=[
        Executable(main_script, base=base, target_name="BocelliApp.exe")
    ]
)
