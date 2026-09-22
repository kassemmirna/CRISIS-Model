@echo off
:: =============================================================================
:: run_crisis.bat
:: =============================================================================
:: Sets up a Python virtual environment, installs all required packages,
:: and launches the CRISIS GUI.
::
:: USAGE:
::   Double-click this file, OR run from Command Prompt / PowerShell:
::     run_crisis.bat              <- first run: creates venv + installs packages
::     run_crisis.bat              <- later runs: skips install, launches GUI
::     run_crisis.bat --reinstall  <- force reinstall of all packages
:: =============================================================================

setlocal

set "SCRIPT_DIR=%~dp0"
set "VENV_DIR=%SCRIPT_DIR%crisis_venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "MARKER=%VENV_DIR%\.packages_installed"
set "REINSTALL=false"

if "%1"=="--reinstall" set "REINSTALL=true"

echo.
echo +----------------------------------------------+
echo ^|      CRISIS Landslide Model Launcher         ^|
echo +----------------------------------------------+
echo.

:: -----------------------------------------------------------------------------
:: 1. Locate Python (only needed to CREATE the venv the first time)
:: -----------------------------------------------------------------------------
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found on PATH.
    echo Please install Python 3.12 or newer from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PY_VER=%%i

:: The check above only confirms *some* Python is on PATH — but the pinned
:: package versions in requirements.txt (numpy>=2.4.4, rasterio>=1.5.1) have
:: no installable wheels below Python 3.12. Catching that here gives a
:: clear, immediate error instead of a confusing "pip install" failure
:: minutes into package installation.
set "PY_MAJOR="
set "PY_MINOR="
for /f "tokens=2 delims= " %%v in ("%PY_VER%") do set "PY_VER_NUM=%%v"
for /f "tokens=1,2 delims=." %%a in ("%PY_VER_NUM%") do (
    set "PY_MAJOR=%%a"
    set "PY_MINOR=%%b"
)
set "PY_TOO_OLD=false"
if "%PY_MAJOR%"=="" (
    set "PY_TOO_OLD=true"
) else (
    if %PY_MAJOR% LSS 3 set "PY_TOO_OLD=true"
    if %PY_MAJOR% EQU 3 if %PY_MINOR% LSS 12 set "PY_TOO_OLD=true"
)
if "%PY_TOO_OLD%"=="true" (
    echo ERROR: Found %PY_VER%, but CRISIS requires Python 3.12 or newer.
    echo The pinned package versions in requirements.txt ^(numpy^>=2.4.4, rasterio^>=1.5.1^)
    echo have no installable wheels below Python 3.12.
    echo.
    echo Please install Python 3.12 or newer from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

echo Using %PY_VER% to create the virtual environment ^(if needed^).
echo.

:: -----------------------------------------------------------------------------
:: 2. Create virtual environment if it does not already exist (or is broken)
:: -----------------------------------------------------------------------------
if not exist "%VENV_PY%" (
    echo Creating virtual environment at:
    echo   %VENV_DIR%
    if exist "%VENV_DIR%" rmdir /s /q "%VENV_DIR%"
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo Done.
    echo.
) else (
    echo Virtual environment found at:
    echo   %VENV_DIR%
    echo.
)

:: -----------------------------------------------------------------------------
:: 3. Sanity-check the venv's own interpreter
:: -----------------------------------------------------------------------------
:: NOTE: We deliberately do NOT call activate.bat and rely on bare "python"/"pip"
:: afterwards. activate.bat hardcodes an absolute VIRTUAL_ENV path at creation
:: time; if this folder is ever moved or renamed, that path goes stale, PATH
:: never actually gets the venv's Scripts directory prepended, and "python"
:: silently falls back to whatever system-wide interpreter comes next on PATH
:: (packages then appear to work only because they happen to also be
:: installed globally). Calling "%VENV_PY%" by its full path sidesteps that
:: failure mode entirely, since python.exe reads its own venv location from
:: pyvenv.cfg regardless of PATH or where the folder lives.
"%VENV_PY%" -c "import sys; print('Using venv interpreter:', sys.executable)"
if errorlevel 1 (
    echo ERROR: The virtual environment's Python interpreter is broken.
    echo Delete the "crisis_venv" folder and re-run this script to rebuild it.
    pause
    exit /b 1
)
echo.

:: -----------------------------------------------------------------------------
:: 3b. Sanity-check that pip actually exists in the venv
:: -----------------------------------------------------------------------------
:: python -m venv normally bootstraps pip via the stdlib ensurepip module, but
:: that bootstrap step can silently fail to leave a working pip behind (seen in
:: the wild with antivirus interference or a flaky first run) without venv
:: creation itself reporting an error. A previously-created venv can therefore
:: sit around indefinitely with no pip, and every future run would otherwise
:: fail deep inside step 4 with a confusing "No module named pip". Detect that
:: here and try to repair it with ensurepip (bundled with the interpreter, so
:: this works offline) before falling back to asking for a manual rebuild.
"%VENV_PY%" -m pip --version >nul 2>&1
if errorlevel 1 (
    echo pip is missing from the virtual environment. Attempting to repair it...
    "%VENV_PY%" -m ensurepip --upgrade >nul 2>&1
    "%VENV_PY%" -m pip --version >nul 2>&1
    if errorlevel 1 (
        echo ERROR: Could not bootstrap pip into the virtual environment.
        echo Delete the "crisis_venv" folder and re-run this script to rebuild it.
        echo If that still fails, your Python installation may be missing the
        echo ensurepip component ^(common with some Microsoft Store installs^) -
        echo reinstall Python from https://www.python.org/downloads/ instead.
        pause
        exit /b 1
    )
    echo pip repaired successfully.
    echo.
)

:: -----------------------------------------------------------------------------
:: 4. Install packages (skipped if marker exists and --reinstall not given)
:: -----------------------------------------------------------------------------
if exist "%MARKER%" if not "%REINSTALL%"=="true" goto :skip_install

echo Installing packages into the virtual environment (this may take a few minutes the first time)...
echo.

"%VENV_PY%" -m pip install --upgrade pip --quiet
if errorlevel 1 (
    echo WARNING: pip upgrade failed, continuing with existing version...
)

"%VENV_PY%" -m pip install numpy
if errorlevel 1 goto :install_error

"%VENV_PY%" -m pip install pandas
if errorlevel 1 goto :install_error

"%VENV_PY%" -m pip install h5py
if errorlevel 1 goto :install_error

"%VENV_PY%" -m pip install openpyxl
if errorlevel 1 goto :install_error

"%VENV_PY%" -m pip install --force-reinstall shapely
if errorlevel 1 goto :install_error

"%VENV_PY%" -m pip install pyproj
if errorlevel 1 goto :install_error

"%VENV_PY%" -m pip install geopandas
if errorlevel 1 goto :install_error

"%VENV_PY%" -m pip install matplotlib
if errorlevel 1 goto :install_error

"%VENV_PY%" -m pip install rasterio
if errorlevel 1 goto :install_error

:: Write marker so future runs skip installation
type nul > "%MARKER%"

echo.
echo All packages installed successfully.
echo.
goto :verify

:install_error
echo.
echo ERROR: Package installation failed.
echo Try running with --reinstall or check your internet connection.
pause
exit /b 1

:skip_install
echo Packages already installed in the virtual environment. Use --reinstall to force a fresh install.
echo.

:: -----------------------------------------------------------------------------
:: 5. Verify imports  (write a temp script, run it with the venv's python, delete it)
:: -----------------------------------------------------------------------------
:verify
echo Verifying imports...

set "CHECK_SCRIPT=%TEMP%\crisis_check_%RANDOM%.py"
(
    echo import sys
    echo print^(f"  Interpreter: {sys.executable}"^)
    echo print^(f"  In virtual env: {sys.prefix != sys.base_prefix}"^)
    echo missing = []
    echo packages = {
    echo     "numpy":      "numpy",
    echo     "pandas":     "pandas",
    echo     "h5py":       "h5py",
    echo     "openpyxl":   "openpyxl",
    echo     "shapely":    "shapely",
    echo     "geopandas":  "geopandas",
    echo     "matplotlib": "matplotlib",
    echo     "rasterio":   "rasterio",
    echo     "tkinter":    "tkinter",
    echo }
    echo for label, mod in packages.items^(^):
    echo     try:
    echo         __import__^(mod^)
    echo         print^(f"  OK  {label}"^)
    echo     except ImportError:
    echo         print^(f"  MISSING  {label}"^)
    echo         missing.append^(label^)
    echo if missing:
    echo     print^(^)
    echo     print^("ERROR: Some packages could not be imported:"^)
    echo     for m in missing:
    echo         print^(f"  - {m}"^)
    echo     print^(^)
    echo     print^("Try running:  run_crisis.bat --reinstall"^)
    echo     sys.exit^(1^)
) > "%CHECK_SCRIPT%"

"%VENV_PY%" "%CHECK_SCRIPT%"
set CHECK_EXIT=%errorlevel%
del "%CHECK_SCRIPT%" >nul 2>&1

if %CHECK_EXIT% neq 0 (
    pause
    exit /b 1
)

echo.
echo All imports OK.
echo.

:: -----------------------------------------------------------------------------
:: 6. Launch the GUI (using the venv's interpreter directly)
:: -----------------------------------------------------------------------------
echo Launching CRISIS GUI...
echo.
cd /d "%SCRIPT_DIR%"
"%VENV_PY%" crisis_gui.py

endlocal
