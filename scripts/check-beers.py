#!/usr/bin/env python3

import re
import sys
from pathlib import Path
from datetime import datetime


FILENAME_RE = re.compile(
    r"^(\d{8})-([a-z])-(\d+)\.jpg$",
    re.IGNORECASE
)


def validate_date(date_string):
    """Check that YYYYMMDD is a real date."""
    try:
        datetime.strptime(date_string, "%Y%m%d")
        return True
    except ValueError:
        return False


def validate_date_files(date, files):
    """
    Validate all files for one date.

    Rules:
    - Must start with a-1.
    - Letters must be consecutive: a, then b, then c.
    - Numbers for each letter must be consecutive: 1, then 2.
    """

    errors = []

    letters = sorted(set(letter for letter, number in files))

    # a-1 is mandatory.
    if ("a", 1) not in files:
        errors.append(f"{date}: missing required {date}-a-1.jpg")

    # Letters must be consecutive starting at a.
    expected_letters = list(
        "abcdefghijklmnopqrstuvwxyz"[:len(letters)]
    )

    if letters != expected_letters:
        errors.append(
            f"{date}: letters must be consecutive starting with a "
            f"(found: {', '.join(letters)})"
        )

    # Numbers for each letter must be consecutive starting at 1.
    for letter in letters:
        numbers = sorted(
            number for l, number in files if l == letter
        )

        expected_numbers = list(range(1, len(numbers) + 1))

        if numbers != expected_numbers:
            errors.append(
                f"{date}-{letter}: numbers must be consecutive "
                f"starting at 1 (found: {numbers})"
            )

    return errors


def validate_folder(folder):
    folder = Path(folder)

    if not folder.is_dir():
        print(f"Error: '{folder}' is not a directory.")
        sys.exit(1)

    jpg_files = sorted(
        path for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() == ".jpg"
    )

    if not jpg_files:
        print("No .jpg files found.")
        return

    invalid_files = []
    files_by_date = {}

    # Parse every filename.
    for path in jpg_files:
        match = FILENAME_RE.match(path.name)

        if not match:
            invalid_files.append(
                f"{path.name}: invalid filename format"
            )
            continue

        date, letter, number = match.groups()
        letter = letter.lower()
        number = int(number)

        # Validate date.
        if not validate_date(date):
            invalid_files.append(
                f"{path.name}: invalid date {date}"
            )
            continue

        files_by_date.setdefault(date, []).append(
            (letter, number)
        )

    # Validate each date's sequence.
    for date, entries in files_by_date.items():

        # Detect duplicates.
        if len(entries) != len(set(entries)):
            duplicates = sorted(
                set(
                    entry for entry in entries
                    if entries.count(entry) > 1
                )
            )

            for letter, number in duplicates:
                invalid_files.append(
                    f"{date}-{letter}-{number}.jpg: duplicate"
                )

        invalid_files.extend(
            validate_date_files(date, set(entries))
        )

    # ------------------------------------------------------------
    # Output
    # ------------------------------------------------------------

    print(f"Checked {len(jpg_files)} JPG file(s) in: {folder.resolve()}")
    print()

    if invalid_files:
        print("PROBLEMS FOUND:")

        for error in invalid_files:
            print(f"  {error}")

        print()
        print(f"Found {len(invalid_files)} problem(s).")
    else:
        print("All JPG filenames and sequences are valid.")

    # Distinct yyyymmdd-x codes.
    distinct_codes = set()

    for date, entries in files_by_date.items():
        for letter, number in entries:
            distinct_codes.add(f"{date}-{letter}")

    print()
    print("DISTINCT CODES:")

    for code in sorted(distinct_codes):
        print(code)


def main():
    # Default to the current working directory.
    folder = sys.argv[1] if len(sys.argv) > 1 else "."

    if len(sys.argv) > 2:
        print(
            f"Usage: {Path(sys.argv[0]).name} [folder]"
        )
        sys.exit(1)

    validate_folder(folder)


if __name__ == "__main__":
    main()