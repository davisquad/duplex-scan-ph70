"""NAPS2 is invoked as a separate, unmodified scanner bridge."""
from pathlib import Path
import subprocess
import sys
import os

ROOT = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent


def engine():
    paths = [folder/'scanner-engine'/'App'/'NAPS2.Console.exe' for folder in (ROOT, *ROOT.parents)]
    paths.append(Path(os.environ.get('ProgramFiles', 'C:/Program Files'))/'NAPS2'/'NAPS2.Console.exe')
    for path in paths:
        if path.exists():
            return path
    raise RuntimeError('Scanner engine is missing. Keep the scanner-engine folder alongside Duplex Scan.')


def run(args, timeout=60):
    result = subprocess.run([str(engine()), *args], capture_output=True, text=True,
                            encoding='utf-8-sig', errors='replace', timeout=timeout,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or 'The scanner driver reported an error.').strip())
    return result.stdout


def devices(driver):
    result = run(['--listdevices', '--driver', driver])
    return [line.strip() for line in result.splitlines() if line.strip()]


def scan_args(folder, device, driver, source, dpi, size, color):
    return ['-o', str(Path(folder)/'page-$(nnnn).png'), '--noprofile', '--driver', driver,
            '--device', device, '--source', source, '--dpi', str(dpi), '--pagesize', size,
            '--bitdepth', color, '--disableocr', '-v']


def scan_command(folder, device, driver, source, dpi, size, color):
    if driver == 'twain' and 'PH70' in device.upper():
        prefix = [sys.executable] if getattr(sys,'frozen',False) else [sys.executable,str(ROOT/'app.py')]
        return prefix + ['--capture','--folder',str(folder),'--device',device,'--source',source,
                         '--dpi',str(dpi),'--size',size,'--color',color]
    return [str(engine()),*scan_args(folder,device,driver,source,dpi,size,color)]
