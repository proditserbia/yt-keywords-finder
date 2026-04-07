# YT Keywords Finder

A Python application that searches public YouTube videos by keyword and saves
matching video URLs into local text files.  Supports both a simple Tkinter
**GUI** and a headless **CLI**.

---

## Project Structure

```
yt-keywords-finder/
├── app.py                      # Main launcher (GUI / CLI dispatcher)
├── requirements.txt
├── README.md
└── src/
    ├── config/
    │   └── constants.py        # App-wide defaults and constants
    ├── youtube/
    │   └── search_service.py   # YouTube search via yt-dlp (platform adapter)
    ├── core/
    │   └── processor.py        # Shared processing logic (keyword loop, output)
    ├── filters/
    │   └── validators.py       # Duration filter, filename sanitizer, etc.
    ├── output/
    │   └── writer.py           # TXT and CSV file writers
    ├── gui/
    │   └── app_gui.py          # Tkinter GUI frontend
    └── cli/
        └── parser.py           # argparse CLI frontend
```

---

## Install

### Requirements

- Python 3.11+
- `pip install -r requirements.txt`

On **Debian/Ubuntu** you may also need Tkinter for the GUI:

```bash
sudo apt install python3-tk
```

### Steps

```bash
git clone https://github.com/proditserbia/yt-keywords-finder.git
cd yt-keywords-finder
pip install -r requirements.txt
```

---

## CLI Usage

```bash
# Basic: search for multiple keywords, collect up to 100 results each,
# skip videos shorter than 5 minutes
python app.py --mode cli \
              --keywords "fashion street,runway,summer outfits" \
              --max-results 100 \
              --min-duration 5 \
              --output ./results

# Load keywords from a file (one keyword per line)
python app.py --mode cli \
              --keywords-file keywords.txt \
              --max-results 50 \
              --min-duration 3 \
              --output ./results

# Disable CSV and combined TXT output
python app.py --mode cli \
              --keywords "runway" \
              --max-results 20 \
              --no-csv --no-combined-txt

# Enable verbose (debug) logging
python app.py --mode cli --keywords "fashion" --verbose

# Search + download: videos > 1 hour long, published in the last year
python app.py --mode cli \
              --keywords "documentary nature,space exploration" \
              --max-results 5 \
              --min-duration 60 \
              --published-within-days 365 \
              --download \
              --download-dir ./videos

# Search + download with a keywords file
python app.py --mode cli \
              --keywords-file keywords.txt \
              --max-results 10 \
              --min-duration 60 \
              --published-within-days 365 \
              --download \
              --download-dir ./videos
```

### CLI flags

| Flag | Default | Description |
|---|---|---|
| `--mode` | `gui` | `cli` for headless, `gui` for Tkinter window |
| `--keywords` | — | Comma/newline-separated keywords |
| `--keywords-file` | — | Path to plain-text keywords file |
| `--max-results` | `50` | Max valid URLs per keyword |
| `--min-duration` | `0` | Min video duration in minutes (0 = no filter) |
| `--published-within-days` | `None` | Only include videos published within the last N days (e.g. `365`) |
| `--output` | `./results` | Output directory for URL lists / CSV |
| `--no-csv` | off | Disable CSV summary |
| `--no-combined-txt` | off | Disable `all_keywords.txt` |
| `--download` | off | Download matching videos after collecting URLs |
| `--download-dir` | `./downloads` | Root folder for downloads; one sub-folder per keyword |
| `--verbose` | off | DEBUG-level console logging |

---

## GUI Usage

```bash
python app.py          # defaults to --mode gui
# or explicitly:
python app.py --mode gui
```

1. Enter keywords (one per line, or comma-separated) in the **Keywords** box.
2. Set **Max results per keyword** and **Minimum duration**.
3. Choose an **Output folder** (or type a path directly).
4. Click **▶ Start** – progress messages stream into the log panel in real time.
5. Click **■ Stop** to cancel after the current keyword finishes.
6. Click **📂 Open Folder** to view results in your file manager.

---

## Output Files

For each keyword, one file is created in the output folder:

| File | Contents |
|---|---|
| `<keyword>.txt` | One video URL per line |
| `all_keywords.txt` | All URLs from all keywords combined |
| `all_keywords_summary.csv` | Full metadata: keyword, title, url, duration, channel |
| `yt_finder.log` | Full debug log |

When `--download` is used, videos are saved under `--download-dir`:

```
downloads/
└── <keyword>/
    ├── <title> [<video_id>].mp4
    └── .download_history.json   # duplicate-guard sidecar (auto-generated)
```

The `.download_history.json` sidecar is read on every run so that re-running
the same keyword never re-downloads a video already on disk.

---

## How GUI and CLI Share the Same Backend

Both frontends call `src.core.processor.process_keywords()` with the same
parameters.  The only difference is *how* log messages are surfaced:

- **CLI** – messages go to Python's `logging` module (stdout + log file).
- **GUI** – a `log_callback` parameter forwards each message into a thread-safe
  queue which the Tkinter main loop drains every 100 ms.

Processing runs in a background thread in the GUI (preventing UI freezes) and
in the main thread in the CLI.

---

## Adding Vimeo Support

The YouTube-specific code lives entirely in `src/youtube/search_service.py`.
To add Vimeo:

1. Create `src/vimeo/search_service.py` with a `VimeoSearchService` class
   exposing the same `search()` method signature as `YouTubeSearchService`.
2. Add a `--platform` argument to `src/cli/parser.py` (values: `youtube`, `vimeo`).
3. In `src/core/processor.py`, replace the hardcoded `YouTubeSearchService()`
   instantiation with a factory that returns the right service based on the
   platform argument.
4. Add a platform selector to the GUI (a `ttk.Combobox` widget).

No other files need to change.

---

## Packaging as a Windows Executable

```bash
pip install pyinstaller
pyinstaller --onefile --windowed app.py --name yt-keywords-finder
```

The resulting `dist/yt-keywords-finder.exe` is a self-contained executable.
Add `--icon icon.ico` to embed a custom icon.
