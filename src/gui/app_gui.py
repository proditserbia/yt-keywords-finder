"""
Tkinter GUI frontend for YT Keywords Finder.

The GUI runs in the main thread while all processing is offloaded to a
background :class:`threading.Thread`.  The thread posts log messages to a
thread-safe queue which the main thread drains every 100 ms – this keeps the
window responsive even during long searches.

Architecture note:
    The GUI is a thin frontend.  All processing is done by
    :func:`src.core.processor.process_keywords`.  The GUI only handles:
      - collecting user input from widgets
      - spawning / cancelling the background thread
      - displaying progress messages in the log widget
"""

import logging
import os
import platform
import queue
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Optional

from src.config.constants import (
    APP_NAME,
    DEFAULT_MAX_RESULTS,
    DEFAULT_MIN_DURATION,
    DEFAULT_OUTPUT_DIR,
    VERSION,
)
from src.core.processor import process_keywords
from src.filters.validators import parse_keywords

logger = logging.getLogger(__name__)

# Colour / font constants – easy to customise without touching layout code
_BG = "#1e1e2e"
_FG = "#cdd6f4"
_ACCENT = "#89b4fa"
_BTN_START = "#a6e3a1"
_BTN_STOP = "#f38ba8"
_BTN_OPEN = "#89dceb"
_BTN_FG = "#1e1e2e"
_LOG_BG = "#181825"
_LOG_FG = "#a6e3a1"
_FONT = ("Segoe UI", 10)
_FONT_MONO = ("Consolas", 9)


class AppGUI(tk.Tk):
    """Main application window for the Tkinter GUI frontend."""

    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME}  v{VERSION}")
        self.configure(bg=_BG)
        self.resizable(True, True)
        self.minsize(720, 580)

        self._cancel_flag: Optional[threading.Event] = None
        self._worker_thread: Optional[threading.Thread] = None
        self._log_queue: queue.Queue[str] = queue.Queue()

        self._build_ui()
        self._poll_log_queue()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        """Create and layout all widgets."""
        pad = {"padx": 10, "pady": 6}

        # ── Left panel (inputs) ──────────────────────────────────────────────
        left = tk.Frame(self, bg=_BG)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(10, 5), pady=10)

        self._make_label(left, "Keywords (one per line or comma-separated):")
        self._keywords_text = scrolledtext.ScrolledText(
            left,
            width=38,
            height=7,
            bg=_LOG_BG,
            fg=_FG,
            insertbackground=_FG,
            font=_FONT_MONO,
            relief=tk.FLAT,
        )
        self._keywords_text.pack(fill=tk.X, **pad)

        self._make_label(left, "Max results per keyword:")
        self._max_results_var = tk.StringVar(value=str(DEFAULT_MAX_RESULTS))
        self._make_entry(left, self._max_results_var)

        self._make_label(left, "Minimum duration (minutes):")
        self._min_duration_var = tk.StringVar(value=str(DEFAULT_MIN_DURATION))
        self._make_entry(left, self._min_duration_var)

        self._make_label(left, "Output folder:")
        folder_frame = tk.Frame(left, bg=_BG)
        folder_frame.pack(fill=tk.X, **pad)
        self._output_dir_var = tk.StringVar(value=DEFAULT_OUTPUT_DIR)
        tk.Entry(
            folder_frame,
            textvariable=self._output_dir_var,
            bg=_LOG_BG,
            fg=_FG,
            insertbackground=_FG,
            font=_FONT,
            relief=tk.FLAT,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(
            folder_frame,
            text="Browse…",
            command=self._browse_folder,
            bg=_ACCENT,
            fg=_BTN_FG,
            font=_FONT,
            relief=tk.FLAT,
            cursor="hand2",
        ).pack(side=tk.LEFT, padx=(4, 0))

        # Options checkboxes
        self._csv_var = tk.BooleanVar(value=True)
        self._combined_txt_var = tk.BooleanVar(value=True)
        self._make_checkbox(left, "Create CSV summary", self._csv_var)
        self._make_checkbox(left, "Create combined all_keywords.txt", self._combined_txt_var)

        # ── Buttons ──────────────────────────────────────────────────────────
        btn_frame = tk.Frame(left, bg=_BG)
        btn_frame.pack(fill=tk.X, **pad)

        self._start_btn = tk.Button(
            btn_frame,
            text="▶  Start",
            command=self._start,
            bg=_BTN_START,
            fg=_BTN_FG,
            font=(*_FONT[:1], 11, "bold"),
            relief=tk.FLAT,
            cursor="hand2",
            width=10,
        )
        self._start_btn.pack(side=tk.LEFT, padx=(0, 6))

        self._stop_btn = tk.Button(
            btn_frame,
            text="■  Stop",
            command=self._stop,
            bg=_BTN_STOP,
            fg=_BTN_FG,
            font=(*_FONT[:1], 11, "bold"),
            relief=tk.FLAT,
            cursor="hand2",
            width=10,
            state=tk.DISABLED,
        )
        self._stop_btn.pack(side=tk.LEFT, padx=(0, 6))

        tk.Button(
            btn_frame,
            text="📂  Open Folder",
            command=self._open_output_folder,
            bg=_BTN_OPEN,
            fg=_BTN_FG,
            font=_FONT,
            relief=tk.FLAT,
            cursor="hand2",
        ).pack(side=tk.LEFT)

        # ── Status bar ───────────────────────────────────────────────────────
        self._status_var = tk.StringVar(value="Ready")
        tk.Label(
            left,
            textvariable=self._status_var,
            bg=_BG,
            fg=_ACCENT,
            font=_FONT,
            anchor="w",
        ).pack(fill=tk.X, padx=10, pady=(0, 4))

        # ── Right panel (log) ─────────────────────────────────────────────────
        right = tk.Frame(self, bg=_BG)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 10), pady=10)

        self._make_label(right, "Log output:")
        self._log_widget = scrolledtext.ScrolledText(
            right,
            bg=_LOG_BG,
            fg=_LOG_FG,
            insertbackground=_LOG_FG,
            font=_FONT_MONO,
            state=tk.DISABLED,
            relief=tk.FLAT,
            wrap=tk.WORD,
        )
        self._log_widget.pack(fill=tk.BOTH, expand=True, padx=10)

        tk.Button(
            right,
            text="Clear log",
            command=self._clear_log,
            bg=_BG,
            fg=_FG,
            font=_FONT,
            relief=tk.FLAT,
            cursor="hand2",
        ).pack(anchor="e", padx=10, pady=(4, 0))

    # ── Widget helpers ────────────────────────────────────────────────────────

    def _make_label(self, parent: tk.Widget, text: str) -> None:
        tk.Label(parent, text=text, bg=_BG, fg=_FG, font=_FONT, anchor="w").pack(
            fill=tk.X, padx=10, pady=(6, 0)
        )

    def _make_entry(self, parent: tk.Widget, var: tk.StringVar) -> None:
        tk.Entry(
            parent,
            textvariable=var,
            bg=_LOG_BG,
            fg=_FG,
            insertbackground=_FG,
            font=_FONT,
            relief=tk.FLAT,
        ).pack(fill=tk.X, padx=10, pady=(0, 2))

    def _make_checkbox(self, parent: tk.Widget, text: str, var: tk.BooleanVar) -> None:
        tk.Checkbutton(
            parent,
            text=text,
            variable=var,
            bg=_BG,
            fg=_FG,
            selectcolor=_LOG_BG,
            activebackground=_BG,
            activeforeground=_FG,
            font=_FONT,
        ).pack(anchor="w", padx=10, pady=(2, 0))

    # ── Button callbacks ──────────────────────────────────────────────────────

    def _browse_folder(self) -> None:
        chosen = filedialog.askdirectory(
            title="Select output folder",
            initialdir=self._output_dir_var.get() or ".",
        )
        if chosen:
            self._output_dir_var.set(chosen)

    def _open_output_folder(self) -> None:
        folder = Path(self._output_dir_var.get()).resolve()
        folder.mkdir(parents=True, exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(folder)  # type: ignore[attr-defined]
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except OSError as exc:
            messagebox.showerror("Error", f"Could not open folder:\n{exc}")

    def _clear_log(self) -> None:
        self._log_widget.configure(state=tk.NORMAL)
        self._log_widget.delete("1.0", tk.END)
        self._log_widget.configure(state=tk.DISABLED)

    def _start(self) -> None:
        """Validate inputs and launch the background worker thread."""
        raw_keywords = self._keywords_text.get("1.0", tk.END).strip()
        if not raw_keywords:
            messagebox.showwarning("No keywords", "Please enter at least one keyword.")
            return

        keywords = parse_keywords(raw_keywords)
        if not keywords:
            messagebox.showwarning("No keywords", "No valid keywords found in the input.")
            return

        try:
            max_results = int(self._max_results_var.get())
            if max_results <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid input", "Max results must be a positive integer.")
            return

        try:
            min_duration = float(self._min_duration_var.get())
            if min_duration < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid input", "Minimum duration must be a non-negative number.")
            return

        output_dir = self._output_dir_var.get().strip() or DEFAULT_OUTPUT_DIR

        self._cancel_flag = threading.Event()
        self._start_btn.configure(state=tk.DISABLED)
        self._stop_btn.configure(state=tk.NORMAL)
        self._status_var.set("Running…")
        self._append_log(f"=== Starting search for {len(keywords)} keyword(s) ===\n")

        self._worker_thread = threading.Thread(
            target=self._worker,
            args=(keywords, max_results, min_duration, output_dir),
            daemon=True,
        )
        self._worker_thread.start()

    def _stop(self) -> None:
        """Signal the background thread to stop after the current keyword."""
        if self._cancel_flag:
            self._cancel_flag.set()
        self._stop_btn.configure(state=tk.DISABLED)
        self._status_var.set("Stopping…")

    def _worker(
        self,
        keywords: list[str],
        max_results: int,
        min_duration: float,
        output_dir: str,
    ) -> None:
        """Background thread target – calls :func:`process_keywords`."""
        try:
            process_keywords(
                keywords=keywords,
                max_results=max_results,
                min_duration_minutes=min_duration,
                output_dir=output_dir,
                create_csv=self._csv_var.get(),
                create_combined_txt=self._combined_txt_var.get(),
                log_callback=lambda msg: self._log_queue.put(msg),
                cancel_flag=self._cancel_flag,
            )
        except Exception as exc:
            self._log_queue.put(f"\nFATAL ERROR: {exc}")
            logger.exception("Unhandled exception in GUI worker thread")
        finally:
            self._log_queue.put("__DONE__")

    # ── Log widget helpers ────────────────────────────────────────────────────

    def _poll_log_queue(self) -> None:
        """Drain the log queue and update the log widget every 100 ms."""
        try:
            while True:
                msg = self._log_queue.get_nowait()
                if msg == "__DONE__":
                    self._start_btn.configure(state=tk.NORMAL)
                    self._stop_btn.configure(state=tk.DISABLED)
                    self._status_var.set("Done")
                else:
                    self._append_log(msg)
        except queue.Empty:
            pass
        # Schedule next poll
        self.after(100, self._poll_log_queue)

    def _append_log(self, msg: str) -> None:
        """Append *msg* to the log widget and scroll to the bottom."""
        self._log_widget.configure(state=tk.NORMAL)
        self._log_widget.insert(tk.END, msg + "\n")
        self._log_widget.see(tk.END)
        self._log_widget.configure(state=tk.DISABLED)


def run_gui() -> None:
    """Launch the Tkinter GUI application."""
    app = AppGUI()
    app.mainloop()
