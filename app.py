"""
YT Keywords Finder – main entry point.

Dispatches to either the Tkinter GUI or the headless CLI based on the
``--mode`` argument (default: gui).

Usage::

    # Launch GUI (default)
    python app.py

    # Headless CLI
    python app.py --mode cli --keywords "fashion,runway" --max-results 50 --min-duration 5

    # Load keywords from file
    python app.py --mode cli --keywords-file keywords.txt --max-results 100 --min-duration 3
"""

import sys


def main() -> None:
    """Parse top-level arguments and delegate to the appropriate frontend."""
    from src.cli.parser import build_parser, run_cli

    parser = build_parser()
    args = parser.parse_args()

    if args.mode == "gui":
        try:
            import tkinter  # noqa: F401 – check availability before importing AppGUI
        except ImportError:
            print(
                "Error: Tkinter is not available in this Python installation.\n"
                "Install it (e.g. 'sudo apt install python3-tk' on Debian/Ubuntu) "
                "or run in CLI mode with '--mode cli'.",
                file=sys.stderr,
            )
            sys.exit(1)

        from src.gui.app_gui import run_gui

        run_gui()
    else:
        run_cli(args)


if __name__ == "__main__":
    main()
