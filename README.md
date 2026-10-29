# Duplex Scan for the PH70

A local Windows scanning app for the Visioneer Patriot PH70 duplex scanner. Version **1.11.0**.

![App icon](DuplexScan-Neon.png)

## Features

- Duplex scanning with optional 180-degree rotation.
- Live PH70 page arrival: completed sides appear and start cropping/straightening while the feeder continues. Click thumbnails to review during scanning; saving and editing unlock when capture finishes. Completed sides remain available after a stopped or failed scan.
- Physical card-edge detection, skew correction, and adjustable space outside the card.
- Wide hardware capture, a 5 mm working surround, and a final crop preserving real scanned background.
- Modern Focus workspace with a large preview, batch thumbnails, compact finishing controls, and selectable Light, Dark, or System appearance (Light by default).
- High-quality JPEGs saved directly to `Pictures/Scanned Photos` under the current user's home directory.
- Batch clears after successful export; failed saves retain the scans for retry.
- Full-quality render reuse, a 256 MB cache limit, and background preview processing.
- Finished JPEGs are prepared during background review and retained in a separate 128 MB cache, so Save usually writes ready bytes without repeating processing or encoding. Changes to images or finishing settings invalidate those results. The cache clears with the batch; JPEG quality remains 95 with no chroma subsampling.
- Image/multipage TIFF import, manual cropping, rotation, and fine tilt.

## Install on Windows (no Python required)

**[Download the Windows installer](https://github.com/davisquad/duplex-scan-ph70/releases/latest/download/DuplexScan-Setup-1.11.0-x64.exe)**

Open the setup file and click **Install**. It installs for your Windows account, creates desktop and Start menu shortcuts, and opens the app. It downloads and verifies the NAPS2 engine automatically (internet required, about 70 MB). No manual extraction, Python installation, or separate NAPS2 setup is needed.

Install [Visioneer's PH70 driver](https://www.visioneer.com/drivers-and-manuals/) once before scanning if it is not already installed. Hardware drivers are not bundled or installed automatically. The Start menu includes a driver-download shortcut.

This release is **unsigned**. Windows may show a warning or block it with Smart App Control. The installer does not bypass those protections or change security settings. Code signing remains necessary for reliable distribution to protected PCs.

Uninstall from Windows Settings > Apps. Saved photos and user settings are preserved. Installing a newer setup updates the app in the same location.

## Requirements for running from source

- Windows 11, 64-bit (the tested platform).
- Python 3.12, 64-bit, including Tkinter, to run from source.
- Manufacturer's PH70 drivers including the 64-bit TWAIN source.
- NAPS2 scanner engine and its bundled 64-bit TWAIN DSM, installed separately.

Obtain NAPS2 from https://www.naps2.com and retain its licenses. The tested engine version is 8.6.0. Place the complete portable distribution so the following paths exist under this project folder, or an ancestor of the packaged app:

```text
scanner-engine/
  App/
    NAPS2.Console.exe
    lib/
      _win64/
        twaindsm.dll
```

The engine locator also checks `%ProgramFiles%/NAPS2/NAPS2.Console.exe`. PH70 capture expects `lib/_win64/twaindsm.dll` relative to that engine directory. Keep the complete distribution, not only these two files. Scanner drivers and NAPS2 are not included here.

## Run

From PowerShell inside this repository:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Choose TWAIN, the PH70, and Both sides. Resolution defaults to 600 DPI. The clean-install **Edge space** defaults to **0.6 mm**. Settings are remembered on normal exit.

Scan, review both sides, and click **Save JPEGs**. Exports use quality 95, no chroma subsampling, and unique filenames. If saving fails, already-completed JPEGs may remain in the output folder while the batch stays available for retry.

## Build

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm 'Duplex Scan.spec'
```

Run `dist/Duplex Scan/Duplex Scan.exe`. Keep the complete output folder and install the scanner engine as described above. Local builds are unsigned and Windows Smart App Control may block them. Public distribution should use trusted code signing. The application does not change security settings.

### Build the installer

The **Build Windows installer** GitHub Actions workflow packages Python and the app, preserves third-party license files, and compiles `installer/DuplexScan.iss` using Inno Setup 6.5 or newer. It tests a clean install, reinstall/upgrade, packaged GUI/image/scanner-engine initialization, shortcut creation, and uninstall on a Windows runner. It does not perform a hardware scan.

For a local installer build, after the PyInstaller command above:

```powershell
.\.venv\Scripts\python.exe installer/collect_licenses.py
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer/DuplexScan.iss
```

Output: `installer-output/DuplexScan-Setup-1.11.0-x64.exe`. NAPS2 is downloaded directly from its official release during installation and checked against a pinned SHA-256 digest. Keep that URL, version, archive size, and digest together when updating the engine.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest test_app -q
```

The 28 tests cover edge preservation, skew correction, margins, cache behavior, capture callbacks, image export, and save recovery. Tests use generated images and mocked scanner hardware, not personal scans. Real PH70 capture was separately exercised during development; the recent performance improvements have not been timed through a fresh complete hardware batch.

## Privacy and limitations

All image processing is local. This repository contains no personal scans, settings, drivers, or packaged dependencies. Temporary original scans remain until normal app exit. Saving clears the review and processed-image cache. Native bitmap captures use more temporary disk space to avoid compression work.

Hardware controls the overscan extent; software cannot recover edges the scanner did not capture. Similar card and backing colors can prevent detection. Review damaged or rounded cards carefully. Ambiguous boundaries retain the full scan. Other scanner models have not been validated.

Independent project, not affiliated with Epson, Visioneer, or NAPS2. Third-party packages and the separate scanner engine retain their own licenses.
