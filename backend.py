"""NAPS2 is invoked as a separate, unmodified scanner bridge."""
from pathlib import Path
import subprocess
import sys
import os
from collections import deque
import threading
import time
import json


def stream_capture(worker, folder, on_page, on_status=None):
    """Watch atomically published native bitmaps, including windowless builds.

    Windowless Python may suppress stdout, so completed files are the source
    of truth. Drain diagnostics independently so the driver cannot fill a pipe.
    """
    tail = deque(maxlen=100)
    def drain():
        for line in worker.stdout: tail.append(line)
    reader = threading.Thread(target=drain,daemon=True)
    reader.start()
    seen = set()
    next_page = 1
    status_stamp = None
    def collect(final=False):
        nonlocal next_page,status_stamp
        # Native capture publishes sequential names. Check only the next file
        # instead of rescanning/sorting the entire growing batch ten times/sec.
        while True:
            path = Path(folder)/f'page-{next_page:04d}.bmp'
            if not path.exists(): break
            on_page(path)
            seen.add(path)
            next_page += 1
        if final:
            paths=sorted(Path(folder).glob('page-*.bmp'),key=lambda p:int(p.stem.split('-')[-1]))
        else: paths=[]
        for path in paths:
            if path not in seen:
                on_page(path)
                seen.add(path)
        if on_status:
            try:
                path=Path(folder)/'capture-state.json'
                stamp=path.stat().st_mtime_ns
                if stamp != status_stamp:
                    data=json.loads(path.read_text(encoding='utf-8'))
                    on_status(data['state'])
                    status_stamp=stamp
            except (OSError,ValueError,KeyError): pass
    while worker.poll() is None:
        collect()
        time.sleep(.1)
    worker.wait()
    collect(final=True)
    reader.join()
    return ''.join(tail)

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
