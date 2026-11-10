================================================================================
  Chromebook Toggle Tool - README                              (version 1.5)
================================================================================

1. WHAT THIS PROGRAM DOES
--------------------------------------------------------------------------------
This is a small desktop program (a GUI, not a command-line script) for
Windows, macOS and Linux. It lets an IT admin Disable or Re-enable one or many
Chromebooks in Google Workspace - and, when IT has switched it on, Deprovision
them - without typing raw GAM commands by hand.

You pick an action and how you want to supply the list of devices:

  - Type or paste a list of serial numbers directly into the window.
  - Point it at a CSV file that has a column of serial numbers.
  - Paste the URL of a Google Sheet that has a column of serial numbers.

For the "type/paste" and "CSV file" methods, the tool looks up every device's
current status first and shows you a review table (device by device) before
anything is changed, so you can see exactly what will happen and cancel if
something looks wrong. For the "Google Sheet" method, GAM reads the sheet
directly when you confirm, so there is no device-by-device preview - double
check the sheet itself before confirming.

The program also keeps itself up to date (see section 3, "UPDATING"), and it
can renew GAM's Google sign-in for you (see "RENEWING GAM'S SIGN-IN" in
section 3), so nobody needs a command line to run "gam oauth update".

The actions are:
  - Disable     - marks the device DISABLED in Google Workspace.
  - Re-enable   - marks the device ACTIVE again.
  - Deprovision - PERMANENTLY removes the device from management. It cannot be
                  undone. It is HIDDEN unless IT turns it on (see section 4).
Nothing else is done to a Chromebook, a user account, or an OU.

2. REQUIREMENTS
--------------------------------------------------------------------------------
  - Operating system: Windows 10/11, macOS, or Linux with a desktop.
  - Admin rights needed to RUN the tool: No. (Installing for ALL users on
    Windows, or installing the Linux .deb/.rpm, needs administrator approval
    once; a "just me" Windows install does not.)
  - Admin rights / permissions needed to actually change devices: whatever
    rights your own GAM7 install already has in Google Workspace. This tool
    does not grant, check, or restrict permissions itself - if your GAM
    account cannot change a device today, this tool cannot either.
  - Software dependencies:
      * GAM7 must already be installed locally on the PC running this tool,
        with its own Google Workspace sign-in (oauth2) already set up and
        working. The default expected location is C:\GAM7\gam.exe on Windows;
        change it with gam_path in settings.ini if GAM7 lives somewhere else
        (see section 4 below).
      * No other software is required. The installers and zips are self-
        contained - Python is NOT needed to run them.
  - Network access needed: Yes. GAM7 needs network access to reach Google's
    servers. The program itself talks to the network only to check GitHub for
    updates (and to download one when you accept it).

3. HOW TO RUN IT
--------------------------------------------------------------------------------
  Download the file for your system from the project's GitHub "Releases" page
  (X.Y below is the version number):

    Windows           ChromebookToggle-X.Y-Setup.exe        (installer)
                      ChromebookToggle-X.Y-Windows.zip      (portable)
    macOS             ChromebookToggle-X.Y.dmg              (installer)
                      ChromebookToggle-X.Y-macOS.zip        (portable)
    Linux (Debian)    chromebooktoggle_X.Y_amd64.deb
    Linux (Fedora)    chromebooktoggle-X.Y-1.x86_64.rpm
    Linux portable    ChromebookToggle-X.Y-Linux.tar.gz

  WINDOWS INSTALLER
    1. Double-click ChromebookToggle-X.Y-Setup.exe and follow the wizard.
       Choose "all users" (needs administrator approval; installs to
       Program Files) or "just me" (no approval needed).
    2. Open "Chromebook Toggle Tool" from the Start Menu or the desktop
       shortcut. Windows may say the publisher is unrecognized because the
       program is not signed with a paid certificate: choose More info, then
       Run anyway.
    3. To remove it: Settings > Apps > Installed apps > Chromebook Toggle
       Tool > Uninstall.

  WINDOWS PORTABLE ZIP
    1. Unzip it and keep the ENTIRE ChromebookToggle folder together (the EXE
       needs the _internal folder next to it).
    2. Double-click ChromebookToggle.exe. No installation, no Administrator
       rights.

  MACOS
    1. Open the .dmg and drag Chromebook Toggle Tool (ChromebookToggle.app)
       onto Applications.
    2. The first time, macOS says it cannot verify the app (it is signed with
       a free ad-hoc signature, not a paid Apple certificate). Right-click the
       app, choose Open, then Open again - or use System Settings > Privacy &
       Security > Open Anyway.

  LINUX
    - Debian/Ubuntu:  sudo apt install ./chromebooktoggle_X.Y_amd64.deb
    - Fedora/RHEL:    sudo dnf install ./chromebooktoggle-X.Y-1.x86_64.rpm
    Then start it from the applications menu, or run:  chromebooktoggle
    - Portable: unpack the tar.gz, keep the ChromebookToggle folder together,
      and run the ChromebookToggle program inside it.

  FIRST START
    The program checks that GAM7 can be found and tells you right away if it
    cannot. Try Individual mode with ONE real serial number first, check that
    the review screen looks right, and Cancel before confirming anything.

  INSTALLING WITHOUT THE WIZARD (Windows, for IT)
    Run the Setup from a Command Prompt, for example:

      ChromebookToggle-X.Y-Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
        /ALLUSERS /GAMPATH="C:\GAM7\gam.exe"
        /SHEETEMAIL="gam-admin@your-domain.example" /ALLOWDEPROV=1

    (Type it all on one line.) /CURRENTUSER installs for just the person
    running it. /GAMPATH, /SHEETEMAIL and /ALLOWDEPROV=1 write those values
    into settings.ini; any switch you leave off leaves that setting exactly as
    it already is. An upgrade never overwrites settings.ini.

  UPDATING
    Once a day (and whenever you choose Help > Check for updates now) the
    program asks GitHub whether a newer release exists. If so, it shows what
    changed and asks before doing anything. If you say yes, it downloads the
    file that matches how YOU installed it, and checks the file's SHA-256
    against the checksum published in that release's notes. If the checksum is
    missing or does not match, NOTHING is installed. Otherwise it closes,
    swaps in the new version (keeping settings.ini, the Logs folder and state
    files; restoring the old version if anything fails) and starts again.
      - Windows per-user Setup install, and the Windows/Linux portable
        copies: update fully by themselves.
      - Windows all-users Setup install: runs the new Setup silently; Windows
        asks for administrator approval once.
      - macOS: the app is replaced by the new, signature-checked app.
      - Linux .deb/.rpm: the package is downloaded and checked, then the
        program shows you the one "sudo" command that installs it.
      - Running from source (python ChromebookToggle.py): does not update
        itself.
    Version 1.3 and earlier have no updater: install 1.4 or newer by hand once.
    To stop the daily check, set check_for_updates = false in settings.ini.

  RENEWING GAM'S SIGN-IN (no command line needed)
    GAM keeps its own Google sign-in. When it expires GAM prints messages such
    as "Reauthentication is needed", "invalid_grant" or "No Client Access
    allowed". Normally you would run "gam oauth update" in a command line.
    This program does it for you:
      - When a lookup fails for that reason, the error box asks whether to
        open the GAM sign-in window. Answer Yes.
      - Or choose GAM > "GAM sign-in (renew Google sign-in)..." in the menu bar.
    The window shows who GAM is signed in as. Then:
      1. Click "Renew sign-in (gam oauth update)". (If GAM has no sign-in at
         all yet, click "First-time sign-in (gam oauth create)" instead - the
         window enables the right button for you.)
      2. A command window and your web browser open. In the browser, sign in
         with the GAM administrator account and click Allow.
      3. If the command window shows a numbered list of permissions, type c
         and press Enter to keep what is already selected.
      4. When GAM says the authentication flow has completed, go back and
         click "Check again".
    The optional email box fills in the administrator for you; leave it
    alone unless IT tells you otherwise.
    If the Windows Command Prompt is switched off on this PC, the program
    starts gam.exe in its own window instead (that window closes by itself
    when GAM is done - use "Check again" to see the result). If no terminal
    program is found (some Linux setups), the window shows the exact command
    for IT to run.
    This only renews the sign-in. It cannot create GAM's Google Cloud project
    ("gam create project"): if GAM says a client secrets file is missing, IT
    must set GAM up first.

  BUILDING IT YOURSELF (maintainer use only)
    Windows: run Build-EXE.bat (needs Python 3.10+ and PyInstaller). To also
    make the Setup.exe install Inno Setup 6 and run, from the repository
    folder:   iscc /DMyAppVersion=1.5 installer\chromebooktoggle.iss
    macOS/Linux: ./build-app.sh, then installer/build-macos-dmg.sh <version> or
    installer/build-linux-packages.sh <version>. Releases are normally built
    on GitHub (docs\RELEASING.md).

4. PARAMETERS / OPTIONS
--------------------------------------------------------------------------------
  This tool has no command-line parameters for normal use - it is a GUI. All
  of its options are chosen inside the window, or configured ahead of time in
  settings.ini. (The only command-line switch, --apply-update, is used by the
  program itself during an update and is not meant to be typed by hand.)

  ACTIONS (choose one):
    - Disable      - marks the selected device(s) DISABLED.
    - Re-enable    - marks the selected device(s) ACTIVE.
    - Deprovision  - ONLY shown when allow_deprovision = true in settings.ini.
                     PERMANENT: the device leaves Google management, cannot
                     be re-enabled from this tool or the Admin console, and
                     must be wiped and re-enrolled to be managed again. You
                     choose a reason, which Google records:
                        Retiring the device
                        Replacing it with the same model
                        Replacing it with a different model
                        Upgrade transfer
                     Extra safeguards: the review screen is red and states
                     the action is permanent; the confirm button works only
                     after you TYPE the word DEPROVISION; devices that are
                     already deprovisioned are skipped; every device is
                     verified afterward. In Google Sheet mode there is no
                     preview, so the confirmation shows the sheet's address
                     and warns about this - check the sheet before you
                     confirm.

  INPUT METHODS (choose one):
    - Individual - type or paste serial numbers into the text box, one
      serial per line. Blank lines are ignored. Whatever you have typed is
      kept if you Cancel out of the review screen or switch to a different
      input method and back, so you do not have to retype a long list after
      fixing a typo.
    - CSV file - click Browse and pick a .csv file. The file must contain a
      column whose header is either "Serial" or "SerialNumber" - matching is
      not case-sensitive and ignores stray spaces around the header text.
      Files saved from Excel (which add a hidden marker at the start of the
      file) are handled automatically.
    - Google Sheet - paste the URL of a Google Sheet. The sheet must have a
      column with the header spelled EXACTLY "Serial" (not "SerialNumber" or
      any other variant) - unlike CSV mode, GAM reads the Google Sheet
      directly when you confirm, so this tool never gets a chance to
      normalize a differently-spelled header. The sheet must also be shared
      (at least view access) with the Workspace account configured as
      sheet_acting_email in settings.ini - GAM reads the sheet as that
      account, not as you.

  settings.ini (plain text file; edit it with Notepad or any text editor, no
  rebuild needed). Where it lives:
      - Windows: in the install folder, directly next to ChromebookToggle.exe
        (NOT inside the _internal folder).
      - Linux .deb/.rpm: /opt/ChromebookToggle/settings.ini (edit as root).
      - macOS: the signed app must not be edited, so create
        ~/Library/Application Support/ChromebookToggle/settings.ini and the
        app uses that file.
    Settings:
    - gam_path           - full path to gam.exe (GAM) on this PC.
                            Default: C:\GAM7\gam.exe
    - sheet_acting_email - the Workspace account GAM uses to read a Google
                            Sheet in Google Sheet mode.
                            Default: gam-admin@example.com

                            IMPORTANT: gam-admin@example.com is a placeholder,
                            not a real account - it ships this way and will
                            NOT work as-is. Before using Google Sheet mode,
                            change this to a real Google Workspace account in
                            your own domain that GAM is authorized to act as,
                            and share every Google Sheet you want to read
                            with that same account. Individual-entry and CSV
                            mode do not use this setting at all.
    - allow_deprovision  - true or false. Default: false. Turns the permanent
                            Deprovision action on. A typo here leaves it OFF.
                            Windows Setup can set it (tick-box, or
                            /ALLOWDEPROV=1).
    - check_for_updates  - true or false. Default: true.
    - update_repo        - advanced; the GitHub "owner/name" the updater asks.
                            Only change this for your own fork.
    - update_api_base    - advanced; for testing the updater against a local
                            stand-in for GitHub. Leave it commented out.
  If settings.ini is missing, deleted, or has a typo in it, the tool falls
  back to the defaults automatically rather than failing to start (and a typo
  never switches Deprovision on).

5. WHAT IT CHANGES / SIDE EFFECTS
--------------------------------------------------------------------------------
  - The ONLY thing this tool changes in Google Workspace is the status of the
    Chromebook device(s) you select: disabled, active, or (only if IT turned
    it on) permanently deprovisioned. It does not touch user accounts and
    does not move devices between organizational units.
  - On the local computer it writes only its own Logs folder and a tiny
    state.ini (when it last checked for updates), see section 6. The Windows
    installer also adds Start Menu / desktop shortcuts, an uninstaller, an
    "Installed apps" entry, and the registry key
    HKLM (or HKCU) \SOFTWARE\ChromebookToggle (Version, InstallLocation) that
    lets the updater recognize an installed copy.
  - It never writes settings.ini itself; the installer writes it only when you
    use the /GAMPATH, /SHEETEMAIL or /ALLOWDEPROV=1 switches or tick the
    Deprovision box.
  - During an update it downloads one file into a temporary folder, checks it,
    replaces the program files, and deletes the temporary folder. Update
    activity is written to update.log in the Logs folder.
  - For Individual and CSV mode, a small temporary CSV file is created under
    the system TEMP folder while an action is running (this is how GAM is
    told which serials to act on) and is automatically deleted immediately
    afterward, whether the action succeeded or failed.
  - This tool does NOT restrict who can be changed by campus, building, or
    organizational unit. It relies entirely on the permissions already
    granted to the GAM7 install / Workspace account being used - if that
    account can see and change a device, so can this tool. Be careful who
    this tool is deployed to.

6. LOG FILES
--------------------------------------------------------------------------------
  - Individual mode and CSV mode: every completed run writes one CSV log
    file to a "Logs" folder. Where:
      - next to the program, when that folder is writable (portable copies,
        "just me" installs);
      - otherwise in your own application-data folder, because a standard
        user cannot write to Program Files or /opt:
          Windows: %LOCALAPPDATA%\ChromebookToggle\Logs
          macOS:   ~/Library/Application Support/ChromebookToggle/Logs
          Linux:   ~/.local/share/ChromebookToggle/Logs
    Help > Open the logs folder takes you there. The folder is created
    automatically the first time a log is written.
      Filename format:  ChromebookToggle_<action>_<MM-DD-YYYY_HH-MM-SS>.csv
      Example:          ChromebookToggle_disable_08-10-2026_14-32-05.csv
      (For deprovision, <action> is the GAM word, for example
       deprovision_retiring_device.)
      Columns:           Serial, Action, PreviousStatus, NewStatus, Result,
                          Timestamp
      Result is written as the word SUCCESS or FAILED for each device -
      "success" is only ever recorded after the tool independently looks the
      device up again AFTER the action ran and confirms its status actually
      changed to the expected value; it is never simply assumed from GAM
      reporting "no error."
  - Google Sheet mode does NOT write one of these CSV log files. There is no
    per-device before/after data to log for that mode. Instead, the raw text
    GAM printed for that run is shown on screen at the end - that on-screen
    text is the only record of a Google Sheet mode run.
  - update.log (same Logs folder) records update attempts. It contains only
    version numbers, file names and results.
  - These logs are LOCAL ONLY. There is no shared or network copy. If you
    need a central record, collect the Logs folders from each PC.
  - Log files are never automatically deleted (update work folders in TEMP
    are). Clean up by hand if clutter becomes a concern.
  - Log files never contain passwords, credentials, or personally
    identifying information - only device serial numbers, the action taken,
    before/after status values, success/failure, and a timestamp.

7. TROUBLESHOOTING
--------------------------------------------------------------------------------
  "GAM was not found, so this tool cannot look up or change any devices
  right now" (shown at startup, and the Look Up Devices button is disabled):
      - GAM7 is not installed on this PC, OR
      - The gam_path value in settings.ini does not match where gam actually
        lives on this PC.
      Fix: install/verify GAM7 on this PC, or edit settings.ini's gam_path
      to point at the correct location, then restart the tool.

  GAM says "Reauthentication is needed", "invalid_grant" or "No Client Access
  allowed":
      - GAM's Google sign-in expired or is missing. Use GAM > "GAM sign-in" in
        the menu bar (see section 3, RENEWING GAM'S SIGN-IN).

  There is no Deprovision choice in the window:
      - That is the default. See allow_deprovision in section 4.

  CSV file is rejected with a message about a missing "Serial" or
  "SerialNumber" column:
      Fix: open the CSV and rename the appropriate column's header to either
      "Serial" or "SerialNumber" (any capitalization is fine), save, and try
      again. Make sure the header row is the very first row in the file.

  Google Sheet mode: the run appears to do nothing, or GAM reports it could
  not find rows/could not access the sheet:
      - Most common cause: the sheet's header is not spelled exactly
        "Serial" ("SerialNumber" or "serial #" will NOT work in Sheet mode,
        even though those work fine in CSV mode).
      - Second most common cause: the sheet has not been shared with the
        account configured as sheet_acting_email in settings.ini. Share the
        sheet with that account (view access is enough) and try again.

  A device shows as "FAILED" on the results screen even though no error
  message appeared:
      - The action ran without GAM reporting an error, but when the tool
        looked the device up again afterward, its status did not match what
        the action was supposed to produce. This can happen if the device was
        offline, or if something else changed the device at the same time.
        Check the device directly in the Google Admin console.

  The window seems frozen on "Looking up devices..." or "Working...":
      - This is expected for a minute or two on a large list. If it truly
        never finishes (several minutes), GAM itself may be hung; close the
        tool and run the same kind of "gam info cros" command by hand.

  Update message says the program "cannot update itself":
      - It is being run from source, or sits in a folder the program is not
        allowed to change. Download the new release from the Releases page.

  Update stops with "no published checksum" or "checksum does not match":
      - This is the safety check working. Nothing was installed. Download the
        file by hand from the Releases page, or try again later; if it keeps
        happening, tell the project maintainer.

  Update fails and the old version is still there:
      - See update.log in the Logs folder for the reason. The old version is
        always restored when a swap fails.

8. KNOWN LIMITATIONS
--------------------------------------------------------------------------------
  - Google Sheet mode has no per-device review screen before you confirm.
    Unlike Individual and CSV mode, you do not get a table showing which
    devices were found, their current status, or which will be skipped -
    GAM reads the sheet directly at the moment you confirm. Double-check the
    sheet's contents (and its exact header spelling) before confirming. For
    Deprovision this matters most, because it cannot be undone.
  - This tool does not enforce any campus, building, or organizational-unit
    restriction on who can be changed.
  - Deprovision is not reversible, and this tool has no "undo" for it.
  - The GAM sign-in window renews or creates GAM's sign-in only. It cannot
    create the Google Cloud project, and it needs a web browser on the PC.
    It was checked against a real GAM for status reading and command
    building; the full browser sign-in itself is GAM's own (unchanged) flow.
  - There is no shared or network copy of the log files.
  - Google Sheet mode does not write a structured CSV log entry.
  - Linux .deb/.rpm installs cannot update themselves silently, because they
    live in a folder only an administrator may change; the program shows the
    command to run instead.
  - The macOS and Linux versions are built and checked automatically on
    GitHub but are not hand-tested on real devices by the author for every
    release. Please report problems.
  - A device that cannot be found by GAM (typo'd serial, wrong serial, or a
    serial not enrolled in this Workspace) is skipped automatically and
    reported on the review screen - it is never a hard error that stops the
    whole run.
  - Two runs completed within the same second will overwrite each other's
    log file (extremely unlikely given this is a human-driven tool).
================================================================================
