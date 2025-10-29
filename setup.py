import sys
from cx_Freeze import setup, Executable

# Common options for both executables
build_exe_options = {
    "packages": [
        "os", "sys", "subprocess", "threading", "time", "math",
        "cv2", "mediapipe", "numpy", "pyautogui", "keyboard",
        "speech_recognition", "customtkinter", "PIL", "fuzzywuzzy"
    ],
    "excludes": ["tkinter"],
}

# Determine the base for the GUI application
base = None
if sys.platform == "win32":
    base = "Win32GUI"

# Define the executables
executables = [
    Executable(
        "clusterv2launcher.py",
        base=base,
        target_name="BocelliApp.exe" if sys.platform == "win32" else "BocelliApp",
    ),
    Executable(
        "clusterv2.py",
        target_name="BocelliCore.exe" if sys.platform == "win32" else "BocelliCore",
    ),
]

setup(
    name="BocelliApp",
    version="1.1",
    description="Bocelli Voice and Facial Control",
    options={"build_exe": build_exe_options},
    executables=executables,
)
