<p align="center">
  <img src="images/logo.png" width="128" alt="Inkstone logo — an ink drop on a page" />
</p>

# Inkstone

A simple, lightweight tabbed PDF reader for Windows and Linux that does more than
read: sign, fill, search, print, and reorganize pages — without the bloat,
subscriptions, or cloud uploads of commercial PDF software. Built to get away from
paid PDF suites for everyday reading, signing, and light editing.

## Download

Grab the latest release — no account, no installer wizard hassle:

| Platform | Download |
|----------|----------|
| **Windows installer** (fastest startup; Desktop + Start Menu shortcuts) | [Inkstone-Setup.exe](https://github.com/ShoneAnstey/Inkstone/releases/latest/download/Inkstone-Setup.exe) |
| **Windows portable** (single file, no install; unpacks itself on every launch, so it starts in seconds rather than instantly) | [Inkstone.exe](https://github.com/ShoneAnstey/Inkstone/releases/latest/download/Inkstone.exe) |
| **Linux** (portable AppImage) | [Inkstone-x86_64.AppImage](https://github.com/ShoneAnstey/Inkstone/releases/latest/download/Inkstone-x86_64.AppImage) |

All versions: [Releases page](https://github.com/ShoneAnstey/Inkstone/releases).
On Linux, make the AppImage executable first: `chmod +x Inkstone-x86_64.AppImage`.

The binaries are unsigned, so Windows SmartScreen may warn on first launch —
choose **More info → Run anyway**.

### Read & navigate
- Open, page through, zoom, and fit-to-width
- **Multiple tabs, one window** — every PDF opens in its own tab; drag tabs to
  reorder. Opening a PDF from the file manager while Inkstone is running adds
  a tab to the window you already have (and brings it to the front) instead
  of starting a second copy
- **Continuous vertical scrolling** with crisp HiDPI rendering
- **Sidebar** with page **thumbnails** and the document **outline / bookmarks** —
  click to jump (toggle with `F9`)
- **Find** text in a document (`Ctrl+F`) with match highlighting
- **Print** (`Ctrl+P`)
- **Recent files** menu, and drag-and-drop one or more PDFs onto the window
- **Dark mode** for the app interface (View → Dark Mode)

### Sign
- Apply your signature: **Signature ▾ → Place signature on page**, drag to
  position, drag the corner to resize, **rotate** with `R` / `Shift+R`, then save
- **No transparent PNG needed** — sign a blank sheet of paper, photograph it, and
  open the photo; Inkstone removes the paper background automatically (keeps the ink,
  even blue pen, and auto-crops)
- Remembers your signature image so you only pick it once

### Fill & edit
- **Typewriter / text tool** (`Ctrl+T`) — type directly onto a page (fill forms,
  add notes), then save
- **Highlighter** (`Ctrl+H`) — drop a marker-yellow highlight, drag it over the
  text, resize with the corner handle, `Delete` to remove; saved as a real PDF
  highlight annotation
- **Undo** (`Ctrl+Z`) — reverses annotation placement/removal (inside a text box
  it undoes typing)
- **Page surgery** — right-click any page to **extract it to a new PDF**,
  **rotate it left/right**, or **delete it** from the document
- **Append PDF** — File → Append PDF... merges another PDF onto the end of the
  open document
- Nothing above touches the file until you save: annotations and page changes
  alike are pending edits, shown by a dot on the tab

### Save
- **Save** (`Ctrl+S`, File → Save, or the toolbar button) writes every pending
  change over the file you opened. The new version is written beside it and
  swapped in whole, so a failed save never leaves a half-written PDF
- **Save As** (`Ctrl+Shift+S`) writes a copy and leaves the original alone
- Closing a tab or the window with unsaved changes asks **Save / Discard /
  Cancel**
- If the file is read-only or open in another program, Inkstone says so and
  keeps your changes so you can retry or Save As

> This applies a **visual image** of your signature. It is not a cryptographic /
> digital signature.

## Run from source

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt   # Windows: .venv\Scripts\python
.venv/bin/python main.py
```

Run the tests with:

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/
```

First use:
1. **Signature ▾ → Signature setup...** → pick your signature image (remembered
   after this). No signature file? Sign a blank sheet of paper, take a photo, and
   pick that — the paper background is removed for you.
2. **Open** a PDF (or drag one onto the window).
3. **Signature ▾ → Place signature on page**, position/resize/rotate it, then save.

### Shortcuts
- Open: `Ctrl+O`  •  Close tab: `Ctrl+W`  •  Save: `Ctrl+S`  •  Save As: `Ctrl+Shift+S`
- Find: `Ctrl+F`  •  Print: `Ctrl+P`  •  Add text: `Ctrl+T`  •  Highlight: `Ctrl+H`  •  Undo: `Ctrl+Z`  •  Toggle sidebar: `F9`
- Rotate signature: `R` / `Shift+R`
- Next / Previous page: `PageDown` / `PageUp`
- Zoom in / out: `Ctrl++` / `Ctrl+-`, or **Ctrl + mouse wheel**

## CI builds (GitHub Actions)

PyInstaller cannot cross-compile, so each binary is built on its own OS via the
bundled workflow (`.github/workflows/build-pdf.yml`). Pushing a `v*` tag builds
all three binaries and publishes them to a [GitHub Release](https://github.com/ShoneAnstey/Inkstone/releases)
automatically; the workflow can also be run from the **Actions** tab to get
artifacts without a release:

| Artifact | Contents |
|----------|----------|
| `Inkstone-windows-installer` | `Inkstone-Setup.exe` — installer with Desktop + Start Menu shortcuts |
| `Inkstone-windows-portable` | `Inkstone.exe` — portable, no install |
| `Inkstone-linux` | `Inkstone-x86_64.AppImage` — portable |

## Building locally

### Linux AppImage
```bash
bash packaging/build_appimage.sh
# -> dist/Inkstone-x86_64.AppImage   (chmod +x, then double-click)
```
Needs internet on first run (downloads `appimagetool`).

### Windows binaries
PyInstaller cannot cross-compile, so this runs under Windows Python (3.12+), in
its own virtual environment:

```powershell
# from Windows
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
```

```bash
# from WSL
powershell.exe -ExecutionPolicy Bypass -File "$(wslpath -w packaging/build_windows.ps1)" -Commit "$(git rev-parse HEAD)"
```

It builds in `%LOCALAPPDATA%\Inkstone-build` (safe to delete) and produces:

- `Inkstone\` — the one-dir bundle the installer installs. Nothing to unpack,
  so it starts in well under half a second and a second launch hands its PDF
  to the running window in about a quarter of a second.
- `Inkstone.exe` — the portable single file. It is a self-extracting archive
  that unpacks the Qt and PDF runtime to a temp folder on every launch, which
  costs about three seconds each time.
- `Inkstone-Setup.exe` — the installer, if Inno Setup is installed.

`packaging\build_windows.bat` does the PyInstaller step in place from `cmd`.

## Files
- `main.py` — entry point, app icon
- `single_instance.py` — one window per user: later launches hand their PDFs to it
- `viewer.py` — main window: tab host, toolbar, menus, sidebar, dark mode, navigation
- `document_tab.py` — one open PDF per tab: render, navigate, zoom, sign, text, find, page surgery
- `pdf_document.py` — PyMuPDF wrapper: render pages, thumbnails, outline, pending page changes, stamp/save, extract pages
- `sidebar.py` — page thumbnails + outline navigation panel
- `signature_item.py` — draggable / resizable / rotatable signature overlay
- `text_item.py` — draggable typewriter text overlay
- `highlight_item.py` — draggable / resizable highlight overlay
- `signature_processing.py` — turns a paper photo into a transparent-background signature
- `config.py` — remembers signature path, last folder, recent files, window geometry, UI prefs
- `version.py` — version string + CI build provenance
- `security/` — self-contained pre-commit security gate
- `packaging/` — PyInstaller spec, AppImage + Windows build scripts, Inno Setup
  installer script, icons

## License

Released into the **public domain** under [The Unlicense](LICENSE) — free for
anyone to use, modify, and distribute, forever, with no restrictions.

