================================================================================
  Chromebook Toggle Tool - README
================================================================================

1. WHAT THIS SCRIPT DOES
--------------------------------------------------------------------------------
This is a small Windows desktop program (a GUI, not a command-line script)
that lets an IT admin Disable or Re-enable one or many Chromebooks in
Google Workspace, without having to type raw GAM commands by hand.

You pick an action (Disable or Re-enable) and how you want to supply the list
of devices:

  - Type or paste a list of serial numbers directly into the window.
  - Point it at a CSV file that has a column of serial numbers.
  - Paste the URL of a Google Sheet that has a column of serial numbers.

For the "type/paste" and "CSV file" methods, the tool looks up every device's
current status first and shows you a review table (device by device) before
anything is changed, so you can see exactly what will happen and cancel if
something looks wrong. For the "Google Sheet" method, GAM reads the sheet
directly when you confirm, so there is no device-by-device preview - double
check the sheet itself before confirming.

This tool only ever does two things to a device: Disable it, or Re-enable it.
It does not deprovision devices, and it does not do anything else to a
Chromebook, a user account, or an OU.

2. REQUIREMENTS
--------------------------------------------------------------------------------
  - Operating System: Windows 10 or Windows 11 (any PC that already has GAM7
    installed and set up).
  - Admin rights needed to RUN the tool: No. The tool itself does not require
    running as Administrator.
  - Admin rights / permissions needed to actually change devices: whatever
    rights your own GAM7 install already has in Google Workspace. This tool
    does not grant, check, or restrict permissions itself - if your GAM
    account cannot change a device today, this tool cannot either.
  - Software dependencies:
      * GAM7 must already be installed locally on the PC running this tool,
        with its own Google Workspace sign-in (oauth2) already set up and
        working. The default expected location is C:\GAM7\gam.exe - this can
        be changed in settings.ini if a particular PC's GAM7 install lives
        somewhere else (see section 4 below).
      * No other software is required. The tool is packaged as a self-
        contained folder (see "HOW TO RUN IT" below) - a separate Python
        install is NOT required to run the packaged EXE.
  - Network access needed: Yes. GAM7 needs network access to reach Google's
    servers to look up and change device status. This tool does not talk to
    the network directly itself - GAM7 does.

3. HOW TO RUN IT
--------------------------------------------------------------------------------
  This tool is distributed as a folder, not a single installer file. There is
  nothing to "install" - you copy a folder to the target PC and run the EXE
  inside it.

  Step-by-step:

  1. On the PC where you built or received the tool, locate the folder named
     "ChromebookToggle" inside the "dist" folder (the full path looks like
     ...\Chromebook-Toggle-Tool\dist\ChromebookToggle\).
  2. Copy the ENTIRE ChromebookToggle folder (not just the .exe file) to the
     target PC - for example onto the Desktop, or into a folder like
     C:\Tools\ChromebookToggle. Every file inside that folder is required;
     the EXE will not run correctly if you copy only ChromebookToggle.exe by
     itself.
  3. Confirm GAM7 is already installed and working on that PC (test with a
     normal "gam.exe version" from a Command Prompt if unsure). This tool
     depends entirely on GAM7 already being set up - it does not install or
     configure GAM7 for you.
  4. Double-click ChromebookToggle.exe inside the copied folder to launch the
     tool. No shell, no command-line flags, and no Administrator rights are
     needed for this step.
  5. If a "GAM was not found" error pops up immediately, GAM7 is either not
     installed on this PC, or the path in settings.ini does not match where
     GAM7 actually lives on this PC - see section 7 (Troubleshooting) below.

  To rebuild the tool from source (developer/maintainer use only, not needed
  to simply run the tool): run Build-EXE.bat from the project's root folder.
  This requires Python 3.10 or later and PyInstaller (py -m pip install
  pyinstaller) to be installed on the machine doing the build. Build-EXE.bat
  produces the dist\ChromebookToggle\ folder referenced in step 1 above.

4. PARAMETERS / OPTIONS
--------------------------------------------------------------------------------
  This tool has no command-line parameters - it is a GUI, launched by
  double-clicking the EXE. All of its "options" are chosen inside the window
  itself, or configured ahead of time in settings.ini.

  ACTIONS (choose one):
    - Disable    - marks the selected device(s) DISABLED in Google Workspace.
    - Re-enable  - marks the selected device(s) ACTIVE in Google Workspace.
  There is no "deprovision" option - this tool intentionally does not offer
  that action.

  INPUT METHODS (choose one):
    - Individual - type or paste serial numbers into the text box, one
      serial per line. Blank lines are ignored. Whatever you have typed is
      kept if you Cancel out of the review screen or switch to a different
      input method and back, so you do not have to retype a long list after
      fixing a typo.
    - CSV file - click Browse and pick a .csv file. The file must contain a
      column whose header is either "Serial" or "SerialNumber" - matching is
      not case-sensitive and ignores stray spaces around the header text
      (so "serial", "SERIAL NUMBER" spelled as "SerialNumber", etc. are all
      accepted). Files saved from Excel (which add a hidden marker at the
      start of the file) are handled automatically.
    - Google Sheet - paste the URL of a Google Sheet. The sheet must have a
      column with the header spelled EXACTLY "Serial" (not "SerialNumber" or
      any other variant) - unlike CSV mode, GAM reads the Google Sheet
      directly when you confirm, so this tool never gets a chance to
      normalize a differently-spelled header the way it does for an uploaded
      CSV file. The sheet must also be shared (at least view access) with
      the Workspace account configured as sheet_acting_email in settings.ini
      (gam-admin@example.com by default) - GAM reads the sheet as that
      account, not as you.

  settings.ini (plain text file, sits directly next to ChromebookToggle.exe -
  NOT inside the _internal folder - edit it with Notepad, no rebuild needed):
    - gam_path           - full path to gam.exe on this PC.
                            Default: C:\GAM7\gam.exe
    - sheet_acting_email - the Workspace account GAM uses to read a Google
                            Sheet in Google Sheet mode.
                            Default: gam-admin@example.com
  If settings.ini is missing, deleted, or has a typo in it, the tool falls
  back to the two defaults above automatically rather than failing to start.

5. WHAT IT CHANGES / SIDE EFFECTS
--------------------------------------------------------------------------------
  - The ONLY thing this tool changes is the enabled/disabled status of the
    Chromebook device(s) you select, via GAM7/Google Workspace. It does not
    touch user accounts, does not move devices between organizational units,
    and does not deprovision or wipe any device.
  - It does not modify anything on the local PC's registry, files (other
    than its own Logs\ folder, see section 6), or services.
  - It does not modify settings.ini itself - that file is only ever read,
    never written to, by the running tool.
  - For Individual and CSV mode, a small temporary CSV file is created under
    the Windows TEMP folder while an action is running (this is how GAM is
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
    file to a "Logs" folder that sits directly next to ChromebookToggle.exe
    (the Logs folder is created automatically the first time a log is
    written - it does not need to exist ahead of time).
      Filename format:  ChromebookToggle_<action>_<MM-DD-YYYY_HH-MM-SS>.csv
      Example:          ChromebookToggle_disable_08-10-2026_14-32-05.csv
      Columns:           Serial, Action, PreviousStatus, NewStatus, Result,
                          Timestamp
      Result is written as the word SUCCESS or FAILED for each device -
      "success" is only ever recorded after the tool independently looks the
      device up again AFTER the action ran and confirms its status actually
      changed to the expected value; it is never simply assumed from GAM
      reporting "no error."
  - Google Sheet mode does NOT write one of these CSV log files. There is no
    per-device before/after data to log for that mode (GAM acts on the sheet
    directly, and there is no local list to re-check afterward the way there
    is for Individual/CSV mode). Instead, the raw text GAM printed for that
    run is shown on screen at the end - that on-screen text is the only
    record of a Google Sheet mode run.
  - These logs are LOCAL ONLY. There is no shared or network copy - nothing
    is copied to a file server or shared drive. If you need a district-wide
    record of changes, you will need to collect these Logs folders from each
    PC this tool is installed on.
  - Log files are never automatically deleted by the tool. Clean them up
    periodically by hand if disk space or clutter becomes a concern; there is
    no fixed retention period enforced.
  - Log files never contain passwords, credentials, or personally
    identifying information - only device serial numbers, the action taken,
    before/after status values, success/failure, and a timestamp.

7. TROUBLESHOOTING
--------------------------------------------------------------------------------
  "GAM was not found, so this tool cannot look up or change any devices
  right now" (shown at startup, and the Look Up Devices button is disabled):
      - GAM7 is not installed on this PC, OR
      - The gam_path value in settings.ini does not match where gam.exe
        actually lives on this PC.
      Fix: install/verify GAM7 on this PC, or edit settings.ini's gam_path
      to point at the correct location, then restart the tool.

  CSV file is rejected with a message about a missing "Serial" or
  "SerialNumber" column:
      - The CSV's header row does not contain either accepted spelling.
      Fix: open the CSV and rename the appropriate column's header to either
      "Serial" or "SerialNumber" (any capitalization is fine), save, and try
      again. Make sure the header row is the very first row in the file.

  Google Sheet mode: the run appears to do nothing, or GAM reports it could
  not find rows/could not access the sheet:
      - Most common cause: the sheet's header is not spelled exactly
        "Serial" (for example "SerialNumber" or "serial #" will NOT work in
        Sheet mode, even though those work fine in CSV mode).
      - Second most common cause: the sheet has not been shared with the
        account configured as sheet_acting_email in settings.ini
        (gam-admin@example.com by default). Share the sheet with that account
        (view access is enough) and try again.

  A device shows as "FAILED" on the results screen even though no error
  message appeared:
      - This means the action ran without GAM reporting an error, but when
        the tool looked the device up again afterward, its status did not
        match what the action was supposed to produce. This can happen if
        the device was offline/unable to sync the policy change, or if
        something else changed the device's status around the same time.
        Check the device directly in the Google Admin console.

  The window seems frozen on "Looking up devices..." or "Working...":
      - This is expected for a minute or two on a large list - GAM calls can
        take a while. If it truly never finishes (several minutes with no
        change), GAM itself may be hung; close the tool and check GAM7's own
        behavior directly (e.g. run the same kind of "gam info cros"
        command by hand from a Command Prompt) before trying again.

8. KNOWN LIMITATIONS
--------------------------------------------------------------------------------
  - Google Sheet mode has no per-device review screen before you confirm.
    Unlike Individual and CSV mode, you do not get a table showing which
    devices were found, their current status, or which will be
    skipped/processed - GAM reads the sheet directly at the moment you
    confirm. Double-check the sheet's contents (and its exact header
    spelling) before confirming a Google Sheet run.
  - This tool does not enforce any campus, building, or organizational-unit
    restriction on who can be changed. It relies entirely on the
    permissions already granted to the GAM7/Workspace account in use.
  - Only two actions are offered: Disable and Re-enable. There is no
    deprovision option, and no other device-status actions.
  - There is no shared or network copy of the log files - see section 6.
    Each PC this tool runs on keeps its own local Logs folder only.
  - Google Sheet mode does not write a structured CSV log entry the way
    Individual/CSV mode does - only the raw GAM output shown on screen at
    the end of that run is available afterward.
  - A device that cannot be found by GAM (typo'd serial, wrong serial, or a
    serial not enrolled in this Workspace) is skipped automatically and
    reported on the review screen - it is never a hard error that stops the
    whole run.
  - Two runs completed within the same second will overwrite each other's
    log file (extremely unlikely given this is a human-driven tool).
================================================================================
