#!/bin/bash
# =============================================================================
# run_crisis_macos.command
# =============================================================================
# macOS launcher for the CRISIS GUI. Sets up a Python virtual environment,
# installs all required packages, and launches the CRISIS GUI.
#
# FIRST-TIME SETUP (only needed once per Mac, per copy of this file):
#   Downloading this file marks it as "quarantined" and strips its execute
#   permission, so double-clicking it in Finder will show:
#     "run_crisis_macos.command Not Opened — Apple could not verify..."
#   This is normal for any unsigned script downloaded from the internet, not
#   a sign the file is broken. Fix it once with either method below.
#
#   In Terminal (fastest, one line, copy-paste this exactly):
#     cd "<path to this folder>" && chmod +x run_crisis_macos.command && xattr -d com.apple.quarantine run_crisis_macos.command
#   Then double-click the file normally from now on.
#
#   NOTE if you received this file zipped from a Windows machine: Windows
#   has no concept of a Unix "execute" permission, so a .command file
#   zipped on Windows (e.g. via Explorer's "Compress to zip") always
#   arrives on the Mac without its execute bit, on top of the quarantine
#   flag above. The chmod above covers this too. To avoid it happening at
#   all, this file should be transferred without zipping on Windows first
#   (zip it on a Mac instead, or send the file directly / via git).
#
#   Or run it from Terminal directly:
#     ./run_crisis_macos.command              <- first run: creates venv + installs packages
#     ./run_crisis_macos.command              <- later runs: skips install, launches GUI
#     ./run_crisis_macos.command --reinstall  <- force reinstall of all packages
#
# "Permission denied" creating crisis_venv_macos, with a path containing
# "Safari.SandboxBroker" or "TemporaryItems":
#   You launched the file directly from Safari's download list/popover
#   instead of from its real location on disk. Safari auto-unzips downloads
#   and lets you open the result straight from that popover, but it then
#   runs from a locked-down temporary sandbox folder that scripts can't
#   write into. Fix: in Finder, go to ~/Downloads, move the extracted
#   folder to somewhere normal (Desktop, Documents), and double-click
#   run_crisis_macos.command from there instead.
#
# Still stuck after all of the above? As a last resort, run the Windows
# launcher (run_crisis.bat) instead, inside Windows running on the Mac via
# Parallels Desktop, VMware Fusion, or UTM (free), or Boot Camp on older
# Intel Macs. This sidesteps every macOS-specific issue above entirely.
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/crisis_venv_macos"
VENV_PY="$VENV_DIR/bin/python3"
MARKER="$VENV_DIR/.packages_installed"
REINSTALL=false

if [ "$1" == "--reinstall" ]; then
    REINSTALL=true
fi

echo
echo "+----------------------------------------------+"
echo "|      CRISIS Landslide Model Launcher         |"
echo "+----------------------------------------------+"
echo

# -----------------------------------------------------------------------------
# 0. Self-heal folder permissions
# -----------------------------------------------------------------------------
# This folder lives in a cloud-synced Desktop (iCloud Drive/OneDrive) and gets
# edited from both Windows and macOS. Windows has no concept of the Unix owner
# write bit, so when the sync engine re-lands this folder on macOS it
# sometimes arrives as dr-xr-xr-x (read+execute only) instead of drwxr-xr-x,
# even though the parent folder is fine. That silently breaks venv creation
# below with "Permission denied", and previously had to be fixed by hand each
# time with a manual chmod. Restore the write bit unconditionally on every run
# so this never requires manual intervention again.
if [ ! -w "$SCRIPT_DIR" ]; then
    chmod u+w "$SCRIPT_DIR" 2>/dev/null
    if [ ! -w "$SCRIPT_DIR" ]; then
        echo "ERROR: This folder is not writable and the automatic permission fix failed:"
        echo "  $SCRIPT_DIR"
        echo "Run this once in Terminal, then re-run this script:"
        echo "  chmod u+w \"$SCRIPT_DIR\""
        read -p "Press Enter to exit..."
        exit 1
    fi
fi

# -----------------------------------------------------------------------------
# 1. Locate Python (only needed to CREATE the venv the first time)
# -----------------------------------------------------------------------------
PYTHON_BIN=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3.9 python3.8 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
        PYTHON_BIN="$candidate"
        break
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "ERROR: Python 3 not found on PATH."
    echo "Install it from https://www.python.org/downloads/ (recommended — it"
    echo "bundles Tk/tkinter, which the GUI needs), or via Homebrew:"
    echo "  brew install python3 python-tk"
    read -p "Press Enter to exit..."
    exit 1
fi

PY_VER="$("$PYTHON_BIN" --version 2>&1)"

# The candidate loop above will happily settle for an old Python (down to
# 3.8) if that's all that's on PATH — but the pinned package versions in
# requirements.txt (numpy>=2.4.4, rasterio>=1.5.1) have no installable
# wheels below Python 3.12. Catching that here gives a clear, immediate
# error instead of a confusing "pip install" failure minutes into package
# installation.
PY_VER_NUM="$(echo "$PY_VER" | grep -oE '[0-9]+\.[0-9]+' | head -1)"
PY_MAJOR="${PY_VER_NUM%%.*}"
PY_MINOR="${PY_VER_NUM##*.}"
if [ -z "$PY_MAJOR" ] || [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 12 ]; }; then
    echo "ERROR: Found $PY_VER ($PYTHON_BIN), but CRISIS requires Python 3.12 or newer."
    echo "The pinned package versions in requirements.txt (numpy>=2.4.4, rasterio>=1.5.1)"
    echo "have no installable wheels below Python 3.12."
    echo
    echo "Install Python 3.12+ from https://www.python.org/downloads/ (recommended — it"
    echo "bundles Tk/tkinter, which the GUI needs), or via Homebrew:"
    echo "  brew install python3 python-tk"
    read -p "Press Enter to exit..."
    exit 1
fi

echo "Using $PY_VER to create the virtual environment (if needed)."
echo

# -----------------------------------------------------------------------------
# 2. Create virtual environment if it does not already exist (or is broken)
# -----------------------------------------------------------------------------
if [ ! -x "$VENV_PY" ]; then
    echo "Creating virtual environment at:"
    echo "  $VENV_DIR"
    rm -rf "$VENV_DIR"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to create virtual environment."
        read -p "Press Enter to exit..."
        exit 1
    fi
    echo "Done."
    echo
else
    echo "Virtual environment found at:"
    echo "  $VENV_DIR"
    echo
fi

# -----------------------------------------------------------------------------
# 3. Sanity-check the venv's own interpreter
# -----------------------------------------------------------------------------
# NOTE: We deliberately do NOT "source $VENV_DIR/bin/activate" and rely on
# bare "python3"/"pip" afterwards. Activation only changes PATH for the
# current shell; if this folder is ever moved, renamed, or copied to another
# Mac, or if the script is invoked in a context that doesn't carry the
# activated PATH through (e.g. some Finder double-click scenarios), "python3"
# can silently fall back to the system interpreter instead of the venv's —
# packages then appear to work only because they happen to also be installed
# globally, while the venv itself is never actually used. Calling "$VENV_PY"
# by its full path sidesteps that failure mode entirely, since it's the
# actual venv interpreter regardless of PATH or where the folder lives.
if ! "$VENV_PY" -c "import sys; print('Using venv interpreter:', sys.executable)"; then
    echo "ERROR: The virtual environment's Python interpreter is broken."
    echo "Delete the 'crisis_venv_macos' folder and re-run this script to rebuild it."
    read -p "Press Enter to exit..."
    exit 1
fi
echo

# -----------------------------------------------------------------------------
# 4. Install packages (skipped if marker exists and --reinstall not given)
# -----------------------------------------------------------------------------
if [ -f "$MARKER" ] && [ "$REINSTALL" != "true" ]; then
    echo "Packages already installed in the virtual environment. Use --reinstall to force a fresh install."
    echo
else
    echo "Installing packages into the virtual environment (this may take a few minutes the first time)..."
    echo

    "$VENV_PY" -m pip install --upgrade pip --quiet
    if [ $? -ne 0 ]; then
        echo "WARNING: pip upgrade failed, continuing with existing version..."
    fi

    install_error() {
        echo
        echo "ERROR: Package installation failed."
        echo "Try running with --reinstall or check your internet connection."
        read -p "Press Enter to exit..."
        exit 1
    }

    "$VENV_PY" -m pip install numpy                        || install_error
    "$VENV_PY" -m pip install pandas                       || install_error
    "$VENV_PY" -m pip install h5py                          || install_error
    "$VENV_PY" -m pip install openpyxl                      || install_error
    "$VENV_PY" -m pip install --force-reinstall shapely     || install_error
    "$VENV_PY" -m pip install pyproj                        || install_error
    "$VENV_PY" -m pip install geopandas                     || install_error
    "$VENV_PY" -m pip install matplotlib                    || install_error
    "$VENV_PY" -m pip install rasterio                      || install_error

    # Write marker so future runs skip installation
    touch "$MARKER"

    echo
    echo "All packages installed successfully."
    echo
fi

# -----------------------------------------------------------------------------
# 5. Verify imports (write a temp script, run it with the venv's python, delete it)
# -----------------------------------------------------------------------------
echo "Verifying imports..."

CHECK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/crisis_check.XXXXXX")"
CHECK_SCRIPT="$CHECK_DIR/check.py"
cat > "$CHECK_SCRIPT" << 'PYEOF'
import sys
print(f"  Interpreter: {sys.executable}")
print(f"  In virtual env: {sys.prefix != sys.base_prefix}")
missing = []
packages = {
    "numpy":      "numpy",
    "pandas":     "pandas",
    "h5py":       "h5py",
    "openpyxl":   "openpyxl",
    "shapely":    "shapely",
    "geopandas":  "geopandas",
    "matplotlib": "matplotlib",
    "rasterio":   "rasterio",
    "tkinter":    "tkinter",
}
for label, mod in packages.items():
    try:
        __import__(mod)
        print(f"  OK  {label}")
    except ImportError:
        print(f"  MISSING  {label}")
        missing.append(label)
if missing:
    print()
    print("ERROR: Some packages could not be imported:")
    for m in missing:
        print(f"  - {m}")
    print()
    if "tkinter" in missing:
        print("tkinter is bundled with the python.org installer, but often needs")
        print("a separate package on Homebrew Python:  brew install python-tk")
        print()
    print("Try running:  ./run_crisis_macos.command --reinstall")
    sys.exit(1)
PYEOF

"$VENV_PY" "$CHECK_SCRIPT"
CHECK_EXIT=$?
rm -rf "$CHECK_DIR"

if [ $CHECK_EXIT -ne 0 ]; then
    read -p "Press Enter to exit..."
    exit 1
fi

echo
echo "All imports OK."
echo

# -----------------------------------------------------------------------------
# 6. Launch the GUI (using the venv's interpreter directly)
# -----------------------------------------------------------------------------
echo "Launching CRISIS GUI..."
echo
cd "$SCRIPT_DIR"
"$VENV_PY" crisis_gui.py
