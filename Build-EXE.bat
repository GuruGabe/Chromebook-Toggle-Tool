@ECHO OFF
:: =============================================================================
:: Script:   Build-EXE.bat
:: Author:   Gabriel Clifton (built with Claude). Originally created for a K-12 Google Workspace and generalized for public sharing.
:: Created:  08-07-2026
:: Modified: 11-10-2026
:: Version:  1.1
::
:: Purpose:
::   Builds the Chromebook Toggle Tool as a ONE-FOLDER app (dist\ChromebookToggle\)
::   using PyInstaller. Copy the whole dist\ChromebookToggle folder to each
::   target PC and launch ChromebookToggle.exe inside it.
::
:: IMPORTANT - why one-folder and why the extract step:
::   Python 3.14 uses Tcl/Tk 9, which stores its script library INSIDE the DLL
::   as a virtual zip filesystem (//zipfs:/...). PyInstaller 6.21 does not copy
::   that library into the build, so the app crashes at startup with
::   "Tcl data directory _tcl_data not found". extract_tcl.py pulls the Tcl and
::   Tk libraries out of the zipfs into build_res\, and this script bundles them
::   with --add-data. This is the same fix already proven working in the
::   GAMGUI project - reused here rather than re-solved.
::
:: Requirements:
::   Python 3.10+ on PATH and PyInstaller (py -m pip install pyinstaller).
:: =============================================================================
SETLOCAL ENABLEEXTENSIONS
CD /D "%~dp0"

:: Verify PyInstaller is available.
py -m PyInstaller --version >NUL 2>&1
IF ERRORLEVEL 1 (
    ECHO PyInstaller is not installed. Run:  py -m pip install pyinstaller
    EXIT /B 1
)

:: Step 1: extract the Tcl/Tk libraries out of the Tcl 9 zipfs into build_res\.
ECHO Extracting Tcl/Tk libraries from zipfs...
py extract_tcl.py
IF ERRORLEVEL 1 (
    ECHO Failed to extract Tcl/Tk data. Build aborted.
    EXIT /B 1
)

:: Step 2: build one-folder, bundling the extracted Tcl/Tk data.
::   --onedir   = folder of files (no fragile %TEMP% extraction at runtime)
::   --windowed = no console window behind the GUI
::   -y         = overwrite dist\ChromebookToggle\ without prompting, so this
::                script can be re-run after a code fix (e.g. rebuilding after
::                a bug fix) without a manual "delete dist\ first" step -
::                PyInstaller otherwise hard-errors ("output directory is not
::                empty") instead of prompting, since this runs non-interactively.
::   --add-data = ship the Tcl/Tk libraries as _tcl_data / _tk_data. NOTE:
::                settings.ini is deliberately NOT bundled with --add-data
::                here - that would land it inside dist\ChromebookToggle\
::                _internal\ alongside python314.dll and other internal
::                machinery, where an admin would never think to look for
::                it and could mistake it for something not to touch. It is
::                copied to its real location - directly beside the EXE -
::                in the step below instead.
py -m PyInstaller --onedir --windowed -y --name ChromebookToggle ^
    --add-data "build_res\_tcl_data;_tcl_data" ^
    --add-data "build_res\_tk_data;_tk_data" ^
    "ChromebookToggle.py"
IF ERRORLEVEL 1 (
    ECHO Build FAILED. Review the PyInstaller output above.
    EXIT /B 1
)

:: Step 3: copy the default settings.ini so it lands directly beside
:: ChromebookToggle.exe (NOT inside _internal\) - this is the file an admin
:: edits per-deployment (gam_path, sheet_acting_email) without a rebuild, so
:: it needs to be immediately visible next to the EXE, not buried among
:: PyInstaller's internal DLLs and support files.
ECHO Copying default settings.ini next to the EXE...
COPY /Y "settings.ini" "dist\ChromebookToggle\settings.ini"
IF ERRORLEVEL 1 (
    ECHO Failed to copy settings.ini into dist\ChromebookToggle\. Build aborted.
    EXIT /B 1
)

:: Step 4: copy the plain-English instructions beside the EXE as well, so
:: whoever receives the folder (or the zip) has them with the app.
COPY /Y "README.txt" "dist\ChromebookToggle\README.txt" >NUL
IF ERRORLEVEL 1 (
    ECHO Failed to copy README.txt into dist\ChromebookToggle\. Build aborted.
    EXIT /B 1
)

ECHO.
ECHO Build complete: dist\ChromebookToggle\  (run ChromebookToggle.exe inside it)
ECHO Copy the whole dist\ChromebookToggle folder to each target PC, or build the
ECHO Windows installer from it:  iscc /DMyAppVersion=1.6 installer\chromebooktoggle.iss
ENDLOCAL
