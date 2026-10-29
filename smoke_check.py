"""Installed-package check: never acquires images or changes app settings."""
import json
import ctypes
from pathlib import Path
import tkinter as tk
from PIL import Image, ImageTk
import backend
from processing import Settings, process

def run(report_path):
    result = {}
    try:
        engine = backend.engine()
        dsm = engine.parent/'lib'/'_win64'/'twaindsm.dll'
        ctypes.WinDLL(str(dsm))
        result['engine'] = str(engine)
        result['devices'] = backend.devices('twain')
        with Image.new('RGB',(80,120),'red') as source:
            output,_ = process(source,600,Settings(False,False,0),180)
        assert output.size == (80,120) and output.getpixel((0,0)) == (255,0,0)
        root = tk.Tk()
        root.withdraw()
        photo = ImageTk.PhotoImage(output,master=root)
        assert photo.width() == 80
        from app import App
        workspace = App(root)
        root.update_idletasks()
        assert str(workspace.save_button['state']) == 'disabled'
        assert workspace.settings_window.winfo_exists()
        root.destroy()
        workspace.session.cleanup()
        result['ok'] = True
    except Exception as exc:
        result.update(ok=False,error=f'{type(exc).__name__}: {exc}')
    Path(report_path).write_text(json.dumps(result,indent=2),encoding='utf-8')
    return 0 if result['ok'] else 1
