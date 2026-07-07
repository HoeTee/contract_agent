import argparse
from pathlib import Path

def check_file(
        path: Path, 
        verbose: bool
) -> int: 
    print(f"File received: {path}")

    if not path.exists():
        print("Error: file not found")
        return 2

    if not path.is_file(): 
        print("Error: not a file")
        return 2
    
    if verbose:
        print(f"file size: {path.stat().st_size} bytes")
        print(f"file suffix: {path.suffix}")
    
    print("File check passed")
    return 0

def main() -> int:
    parser = argparse.ArgumentParser(
        description="""
    检查 DOCX 文件。

    示例:
        python script.py a.docx
        python script.py a.docx --no-clean
    """, 
        prog="argparse_test", 
        epilog="Example: ...", 
        formatter_class=argparse.RawTextHelpFormatter, 
        add_help=True, 
        exit_on_error=True, 
        allow_abbrev=True
    )

    parser.add_argument(
        "-f", 
        "--file", 
        required=True,
        type=Path, 
        help="Path to the file to inspect."
    )
    parser.add_argument(
        "-v", 
        "--verbose", 
        action="store_true", 
        help="output more information"
    )

    args = parser.parse_args()

    return check_file(
        path=args.file, 
        verbose=args.verbose
    )

if __name__ == "__main__":
    raise SystemExit(main())


