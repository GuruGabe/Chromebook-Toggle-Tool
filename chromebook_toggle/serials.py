# chromebook_toggle/serials.py
#
# Script:   serials.py
# Author:   Gabriel Clifton (built with Claude). Originally created for a K-12 Google Workspace and generalized for public sharing.
# Created:  08-07-2026
# Modified: 08-10-2026
# Version:  1.1
#
# Purpose:
#   Turns each of the tool's three input modes into the same shape: a
#   deduped, order-preserving list of upper-cased serial numbers. Also
#   writes that list back out to a temp CSV so Individual-entry mode can
#   run through the exact same gam batch-csv command as CSV/Sheet mode.
#
# Notes:
#   CSV files are read tolerantly - "Serial" or "SerialNumber", any case -
#   because this module gets a chance to normalize them locally before GAM
#   ever sees them. Google Sheets do NOT go through this module's reader;
#   GAM reads those directly (handled in a later task), which is why the
#   Sheet's header must be exactly "Serial" - documented in README.txt and
#   shown in the GUI (both later tasks), not enforced here.
#
#   read_csv_serials() raises ValueError (never a raw OSError/traceback)
#   for every input-file problem it can hit: missing file, unreadable file,
#   no header row at all, or a header row present but missing a
#   Serial/SerialNumber column. This matches the "never let a script
#   silently fail" rule - the GUI (a later task) can catch ValueError and
#   show the IT admin one clear message regardless of which of these went
#   wrong.
#
#   write_temp_serial_csv() raises ValueError the same way if a serial in
#   the list cannot be written to the ascii-encoded temp file (e.g. a
#   smart quote or accented character that slipped past the upstream
#   normalization functions), and cleans up the partially-written temp
#   file before raising so a failed write never leaves a stray file under
#   %TEMP%. This matters because, per the plan's GUI design (a later
#   task), this function is called on a background thread with no
#   exception handling around the call site - an uncaught exception here
#   would die silently while the GUI is stuck on a "Working..." screen.

import csv
import os
import tempfile

# Both header spellings this tool will recognize as "the serial number
# column", compared case-insensitively against each CSV's actual header
# row. Kept as a module-level tuple (not hardcoded inline) so a future task
# can extend accepted spellings in one place if needed.
_SERIAL_HEADER_NAMES = ("serial", "serialnumber", "serialno")

# What the first dropdown choice in the GUI means: "work out which column holds
# the serial numbers". Spelled once here so the GUI and the tests agree.
AUTO_COLUMN = "(detect automatically)"


def _normalize_header(name):
    # "Serial Number", "serial_number", " SerialNumber " and "serialNumber" all
    # become "serialnumber": lower case, with spaces, underscores and other
    # punctuation removed. GAM's own download header is serialNumber.
    return "".join(ch for ch in (name or "").lower() if ch.isalnum())


def pick_serial_column(headers, preferred=""):
    # Which of these header names holds the serial numbers? The 'preferred'
    # name (for example the serial_column setting) wins when it is present
    # exactly or ignoring case/spacing; otherwise the first header that looks
    # like "Serial" / "SerialNumber". Returns "" when nothing fits.
    wanted = _normalize_header(preferred)
    if wanted:
        for name in headers:
            if name.strip() == preferred.strip():
                return name
        for name in headers:
            if _normalize_header(name) == wanted:
                return name
    for name in headers:
        if _normalize_header(name) in _SERIAL_HEADER_NAMES:
            return name
    return ""


def parse_multiline_serials(text):
    # Individual-entry mode's raw input: one serial per line, pasted or
    # typed into a text box. splitlines() (rather than text.split("\n"))
    # correctly handles files/pastes that use \r\n line endings too.
    seen = set()
    result = []
    for line in text.splitlines():
        # Strip surrounding whitespace (trailing spaces/tabs a user's paste
        # can carry) and upper-case, since Chromebook serials are
        # conventionally upper-alnum and GAM/Google's own reports return
        # them upper-case - normalizing here means a serial typed in either
        # case still matches the same device.
        serial = line.strip().upper()
        if not serial:
            # Drop blank lines (including lines that were pure whitespace
            # before stripping) rather than treating them as an empty
            # "serial number".
            continue
        if serial not in seen:
            # Keep first-seen order rather than sorting, so the order the
            # admin typed/pasted serials in is preserved in any later
            # per-serial gam output/log the admin has to cross-reference.
            seen.add(serial)
            result.append(serial)
    return result


def read_csv_headers(csv_path):
    # The column names in a CSV's first row, in order (so the GUI can offer
    # them in a dropdown). Raises ValueError, like read_csv_serials(), for a
    # missing/unreadable/empty file.
    try:
        with open(csv_path, newline="", encoding="utf-8-sig") as handle:
            reader = csv.reader(handle)
            first = next(reader, None)
    except OSError as open_error:
        raise ValueError("Could not open CSV file '{0}': {1}".format(csv_path, open_error)) from open_error
    except (csv.Error, UnicodeError) as read_error:
        raise ValueError("Could not read CSV file '{0}': {1}".format(csv_path, read_error)) from read_error
    if not first:
        raise ValueError("CSV file '{0}' has no header row".format(csv_path))
    return [name.strip() for name in first if name.strip()]


def read_csv_serials(csv_path, column=None):
    # column: the header of the column that holds the serials, chosen by the
    # person; None or AUTO_COLUMN means "find the Serial / SerialNumber column
    # automatically".
    if column == AUTO_COLUMN or (column is not None and not column.strip()):
        column = None
    try:
        # utf-8-sig quietly handles a leading byte-order-mark, which Excel
        # adds to CSVs it saves - without this, the first header cell would
        # come through with 3 stray BOM bytes glued to the front of
        # "Serial" and silently fail to match any entry in
        # _SERIAL_HEADER_NAMES.
        csv_file = open(csv_path, newline="", encoding="utf-8-sig")
    except OSError as open_error:
        # Covers a missing file (typo'd path, stale browse-dialog result)
        # as well as a file that exists but cannot be read (locked by
        # another program, permissions issue). Re-raised as ValueError,
        # matching every other failure mode in this function, so the GUI
        # (a later task) only has to catch one exception type from this
        # call.
        raise ValueError(
            "Could not open CSV file '{0}': {1}".format(csv_path, open_error)
        ) from open_error

    try:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames is None:
            # A completely empty file (zero bytes) has no header row at
            # all - DictReader leaves fieldnames as None rather than
            # raising, so this has to be checked explicitly.
            raise ValueError("CSV file '{0}' has no header row".format(csv_path))

        # Find whichever accepted header spelling is present, comparing
        # case-insensitively (and with stray whitespace stripped) so
        # "Serial", "SERIAL", " Serial ", and "SerialNumber" all match.
        column_name = None
        if column is not None:
            # The person picked a column: use exactly that one (ignoring case
            # and stray spaces) - never guess a different one.
            for name in reader.fieldnames:
                if name.strip().lower() == column.strip().lower():
                    column_name = name
                    break
            if column_name is None:
                raise ValueError(
                    "CSV file '{0}' has no column named '{1}'. Its columns are: {2}".format(
                        csv_path, column, ", ".join(n.strip() for n in reader.fieldnames))
                )
        else:
            column_name = pick_serial_column(reader.fieldnames) or None
        if column_name is None:
            raise ValueError(
                'CSV file \'{0}\' must have a "Serial" or "SerialNumber" '
                "column header (or choose the column that holds the serial "
                "numbers). Its columns are: {1}".format(
                    csv_path, ", ".join(n.strip() for n in reader.fieldnames))
            )

        seen = set()
        result = []
        for row in reader:
            # .get(column_name) can legitimately be None if a data row has
            # fewer columns than the header row (a ragged/hand-edited
            # CSV); "or \"\"" turns that into an empty string so
            # .strip().upper() below never blows up on None.
            raw_value = row.get(column_name) or ""
            serial = raw_value.strip().upper()
            if not serial:
                # Drop blank cells in the serial column rather than
                # treating them as an empty "serial number".
                continue
            if serial not in seen:
                # Keep first-seen order, same reasoning as
                # parse_multiline_serials() above.
                seen.add(serial)
                result.append(serial)
        return result
    finally:
        # Always close the file handle, whether reading succeeded, raised
        # a ValueError we constructed above, or raised something
        # unexpected (e.g. csv.Error on a genuinely malformed row) that we
        # deliberately let propagate as-is.
        csv_file.close()


def write_temp_serial_csv(serial_list):
    try:
        # delete=False because the caller (the gam subprocess, wired up in
        # a later task) needs to open this file by path after we close it
        # here; the caller is responsible for deleting it once the gam
        # command has finished running.
        temp_file = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".csv",
            prefix="chromebook_toggle_",
            delete=False,
            newline="",
            encoding="ascii",
        )
    except OSError as create_error:
        # Covers the temp directory being unwritable/full - unlikely on a
        # normal district PC, but a clear message beats a raw traceback if
        # it ever happens (e.g. a locked-down TEMP folder via GPO).
        raise ValueError(
            "Could not create a temporary CSV file: {0}".format(create_error)
        ) from create_error

    try:
        writer = csv.writer(temp_file)
        # Same header GAM expects on the CSV/Sheet-mode path, so Individual
        # -entry mode can be handed to the identical gam batch-csv command
        # (wired up in a later task) without any special-casing.
        writer.writerow(["Serial"])
        for serial in serial_list:
            # The file was opened with encoding="ascii" (see below), so
            # writerow() raises UnicodeEncodeError the moment it hits a
            # non-ASCII character. This is genuinely reachable in
            # practice: parse_multiline_serials() only strips/uppercases
            # (it does not filter to ASCII), so a serial pasted from Word/
            # Outlook/a scanned inventory sheet can carry a smart quote or
            # accented character straight through; read_csv_serials()
            # opens with utf-8-sig too, so a hand-edited or garbled CSV's
            # Serial column can carry non-ASCII bytes through untouched as
            # well. Per the plan's GUI design (a later task), this
            # function runs on a background thread with no exception
            # handling around the call site - an uncaught exception here
            # would die silently while the GUI sits on a "Working..."
            # screen forever, which is exactly the "never let a script
            # silently fail" rule this module's docstring promises to
            # uphold.
            writer.writerow([serial])
    except UnicodeError as write_error:
        # Close the handle before removing it - on Windows, os.remove()
        # fails with PermissionError on a file that is still open.
        temp_file.close()
        # Do not leave a partially-written temp CSV orphaned under
        # %TEMP% just because one serial in the list was bad; clean up
        # before reporting the failure. exist_ok-style tolerance is not
        # needed here since the file was just created by this same
        # function and is not shared with any other process yet.
        os.remove(temp_file.name)
        # Re-raise as ValueError, naming the specific offending serial,
        # matching the pattern already established in config.py's
        # save_settings() for its own ascii-encoded write.
        raise ValueError(
            "Could not write serial '{0}' to temporary CSV file - it "
            "contains a non-ASCII character: {1}".format(serial, write_error)
        ) from write_error
    finally:
        # Always close, even if writing raised partway through, so the
        # temp file handle is not leaked. Closing an already-closed file
        # (the UnicodeError branch above already closed it) is a no-op,
        # not an error.
        temp_file.close()

    return temp_file.name
