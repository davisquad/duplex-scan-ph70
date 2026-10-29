# Duplex Scan for the PH70

A local Windows scanning app for the Visioneer Patriot PH70 duplex scanner. Version **1.6.3**.

![App icon](DuplexScan-Neon.png)

## Features

- Duplex scanning with optional 180-degree rotation.
- Physical card-edge detection, skew correction, and adjustable space outside the card.
- Wide hardware capture, a 5 mm working surround, and a final crop preserving real scanned background.
- Large preview of the newest scan and a clickable thumbnail grid.
- High-quality JPEGs saved directly to `Pictures/Scanned Photos` under the current user's home directory.
- Batch clears after successful export; failed saves retain the scans for retry.
- Full-quality render reuse, a 256 MB cache limit, and background preview processing.
- Image/multipage TIFF import, manual cropping, rotation, and fine tilt.

## Requirements

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

Choose TWAIN, the PH70, and Both sides. Resolution defaults to 600 DPI. For CDVs, set **Final gap outside card** to **0.6 mm**; the clean-install default is 0.3 mm. Settings are remembered on normal exit.

Scan, review both sides, and click **Save JPEGs**. Exports use quality 95, no chroma subsampling, and unique filenames. If saving fails, already-completed JPEGs may remain in the output folder while the batch stays available for retry.

## Build

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm 'Duplex Scan.spec'
```

Run `dist/Duplex Scan/Duplex Scan.exe`. Keep the complete output folder and install the scanner engine as described above. Local builds are unsigned and Windows Smart App Control may block them. Public distribution should use trusted code signing. The application does not change security settings.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest test_app -q
```

The 22 tests cover edge preservation, skew correction, margins, cache behavior, capture callbacks, image export, and save recovery. Tests use generated images and mocked scanner hardware, not personal scans. Real PH70 capture was separately exercised during development; the recent performance improvements have not been timed through a fresh complete hardware batch.

## Privacy and limitations

All image processing is local. This repository contains no personal scans, settings, drivers, or packaged dependencies. Temporary original scans remain until normal app exit. Saving clears the review and processed-image cache. Native bitmap captures use more temporary disk space to avoid compression work.

Hardware controls the overscan extent; software cannot recover edges the scanner did not capture. Similar card and backing colors can prevent detection. Review damaged or rounded cards carefully. Ambiguous boundaries retain the full scan. Other scanner models have not been validated.

Independent project, not affiliated with Epson, Visioneer, or NAPS2. Third-party packages and the separate scanner engine retain their own licenses.
