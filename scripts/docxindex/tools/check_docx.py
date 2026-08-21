from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path


DOCXINDEX_ROOT = Path(__file__).resolve().parents[1]
if str(DOCXINDEX_ROOT) not in sys.path:
    sys.path.insert(0, str(DOCXINDEX_ROOT))

from docxindex.cleaning import clean_docx


OLE_DOC_SIGNATURE = bytes.fromhex("D0 CF 11 E0 A1 B1 1A E1") # convert to bytes object
ZIP_SIGNATURES = (
    b"PK\x03\x04",
    b"PK\x05\x06",
    b"PK\x07\x08",
)
REQUIRED_DOCX_PARTS = {
    "[Content_Types].xml",
    "word/document.xml",
}


def describe_header(header: bytes) -> str:
    if header.startswith(OLE_DOC_SIGNATURE):
        return "OLE Compound File, likely legacy .doc"
    if any(header.startswith(signature) for signature in ZIP_SIGNATURES):
        return "ZIP container, possible .docx"
    if header.startswith(b"%PDF"):
        return "PDF"
    return "unknown"


def check_file(path: Path, run_cleaner: bool) -> int:
    print(f"File: {path}")
    print(f"Suffix: {path.suffix or '(none)'}")

    if not path.exists():
        print("ERROR: file does not exist")
        return 2
    if not path.is_file():
        print("ERROR: path is not a file")
        return 2

    # Read the first 8 bytes of the file. 
    # docx files start with ZIP signatures (e.g., 50 4B 03 04)
    # doc files start with OLE signatures (e.g., D0 CF 11 E0 A1 B1 1A E1)
    header = path.read_bytes()[:8] # bytes object
    print(f"Header bytes: {header.hex(' ').upper() or '(empty)'}") # convert to hexadecimal string for display
    print(f"Detected container: {describe_header(header)}")

    if header.startswith(OLE_DOC_SIGNATURE):
        print("Result: renamed legacy .doc or OLE document; this is not a real .docx.")
        return 1

    # Check if the file is a valid ZIP package, which is required for .docx files. 
    is_zip = zipfile.is_zipfile(path) # works on any file and returns True if it's a valid ZIP package
    print(f"zipfile.is_zipfile: {is_zip}")
    if not is_zip:
        print("Result: not a valid ZIP package, so it is not a valid .docx.")
        return 1

    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist()) # {} - a set of all entries in the ZIP package
            # Check if the ZIP package contains all the required parts for a valid .docx file.
            missing = sorted(REQUIRED_DOCX_PARTS - names) # set operations - find the difference between the required parts and the actual parts
            # (No practical purpose) Check for any comment parts in the ZIP package.
            comment_parts = sorted(
                name
                for name in names
                if name.startswith("word/comments") and name.endswith(".xml")
            )

            print(f"ZIP entries: {len(names)}")
            print(f"Has [Content_Types].xml: {'[Content_Types].xml' in names}")
            print(f"Has word/document.xml: {'word/document.xml' in names}")
            print(f"Comment parts: {comment_parts if comment_parts else '(none)'}")

            if missing:
                print(f"Result: ZIP exists, but missing DOCX parts: {missing}")
                return 1
    except Exception as exc:
        print(f"Result: failed to inspect ZIP: {type(exc).__name__}: {exc}")
        return 1

    print("Result: file looks like a valid DOCX package.")

    if run_cleaner:
        print("Running clean_docx()...")
        cleaned_path: str | None = None
        try:
            # Clean the file
            cleaned_path = clean_docx(path) # pass the argument to the function
            print(f"clean_docx: OK -> {cleaned_path}")
        except Exception as exc:
            print(f"clean_docx: ERROR: {type(exc).__name__}: {exc}")
            return 1
        finally:
            if cleaned_path:
                cleaned = Path(cleaned_path)
                if cleaned.exists():
                    cleaned.unlink() # delete the temporary cleaned file
                    print("Temporary cleaned file removed.")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check whether a file is a real DOCX and optionally test clean_docx()."
    )
    parser.add_argument("file", help="Path to the file to inspect.")
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Only inspect the file; do not run clean_docx().",
    )
    args = parser.parse_args()

    return check_file(Path(args.file), run_cleaner=not args.no_clean)


if __name__ == "__main__":
    raise SystemExit(main())
