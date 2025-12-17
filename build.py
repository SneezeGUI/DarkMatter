import os
import shutil
import subprocess
import sys

def install_pyinstaller():
    try:
        import PyInstaller
        print("PyInstaller is already installed.")
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

def build_executable():
    print("Cleaning up previous builds...")
    if os.path.exists("build"):
        shutil.rmtree("build")
    if os.path.exists("dist"):
        shutil.rmtree("dist")

    print("Building executable...")
    
    # Define the PyInstaller command
    # --noconfirm: overwrite output directory
    # --onefile: package into a single exe
    # --windowed: no console window
    # --icon: set the application icon
    # --add-data: include the resources directory
    # --name: name of the executable
    
    sep = ";" if os.name == "nt" else ":"
    
    command = [
        "pyinstaller",
        "--noconfirm",
        "--onefile", # Package into a single exe
        "--windowed",
        "--icon=resources/favicon.ico",
        f"--add-data=resources{sep}resources",
        f"--add-data=ui{sep}ui",
        "--hidden-import=customtkinter",
        "--hidden-import=curl_cffi",
        "--name=DarkMatterBot",
        "main.py"
    ]

    try:
        subprocess.check_call(command)
        print("\nBuild successful! Executable is in the 'dist' directory.")
        
        # Create a zip file for distribution
        print("Creating distribution archive...")
        import zipfile
        with zipfile.ZipFile("DarkMatterBot_v3.6.0.zip", "w", zipfile.ZIP_DEFLATED) as zipf:
            zipf.write("dist/DarkMatterBot.exe", "DarkMatterBot.exe")

        print("Archive created: DarkMatterBot_v3.6.0.zip")
        
    except subprocess.CalledProcessError as e:
        print(f"\nBuild failed: {e}")

if __name__ == "__main__":
    # Ensure we are running in the venv
    venv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv")
    if os.path.exists(venv_path):
        # Check if sys.executable is inside the venv
        if not sys.executable.startswith(os.path.abspath(venv_path)):
            print("Not running in venv. Relaunching via venv...")
            if os.name == "nt":
                python_executable = os.path.join(venv_path, "Scripts", "python.exe")
            else:
                python_executable = os.path.join(venv_path, "bin", "python")
            
            if os.path.exists(python_executable):
                subprocess.check_call([python_executable] + sys.argv)
                sys.exit(0)
            else:
                print("Warning: .venv found but python executable not found. Continuing...")
    
    install_pyinstaller()
    build_executable()
