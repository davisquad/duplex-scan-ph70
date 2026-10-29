"""Duplex Scan: local Windows scan, review, and save workflow."""
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime
import json
import os
import queue
import subprocess
import tempfile
import threading
import uuid
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk, ImageOps, ImageSequence
from processing import Settings, process
import backend
from render_cache import cache

STATE = Path(os.environ.get('LOCALAPPDATA', str(Path.home())))/'DuplexScan'
STATE.mkdir(parents=True, exist_ok=True)


@dataclass
class Page:
    path: Path
    dpi: float
    label: str
    rotation: int = 0
    manual: tuple | None = None
    tilt: float = 0


def valid_dpi(value, fallback):
    try:
        result = float(value[0] if isinstance(value, (tuple, list)) else value)
        return result if 50 <= result <= 2400 else fallback
    except (TypeError, ValueError, IndexError):
        return fallback


def export_pages(pages, settings, target, kind, direct=False):
    """Stage exports alongside destination and commit only complete output."""
    target = Path(target)
    if kind == 'PDF':
        from reportlab.pdfgen import canvas
        from reportlab.lib.utils import ImageReader
        staged = target.with_name('.'+target.name+'.'+uuid.uuid4().hex+'.tmp')
        try:
            pdf = canvas.Canvas(str(staged))
            pdf.setTitle(target.stem)
            pdf.setCreator('Duplex Scan')
            for page in pages:
                rendered, _ = cache.render(page, settings, retain=False)
                width, height = (rendered.width*72/page.dpi, rendered.height*72/page.dpi)
                pdf.setPageSize((width, height))
                pdf.drawImage(ImageReader(rendered), 0, 0, width, height)
                pdf.showPage()
                rendered.close()
            pdf.save()
            os.replace(staged, target)
        finally:
            staged.unlink(missing_ok=True)
        return str(target)
    batch = 'Scan '+datetime.now().strftime('%Y-%m-%d %H-%M-%S')+' '+uuid.uuid4().hex[:8]
    folder = target if direct else target/batch
    folder.mkdir(parents=True, exist_ok=direct)
    def write_page(n, page, rendered):
        ext = {'PNG':'png', 'JPEG':'jpg', 'TIFF':'tif'}[kind]
        name = f'{batch} {n:04d}' if direct else f'page-{n:04d}'
        staged = folder/f'.{name}.tmp'
        try:
            rendered.save(staged, format=kind, dpi=(page.dpi, page.dpi),
                          **({'quality':95, 'subsampling':0} if kind == 'JPEG' else {}))
            staged.replace(folder/f'{name}.{ext}')
        finally:
            staged.unlink(missing_ok=True)
            rendered.close()
    if kind == 'JPEG':
        # One writer overlaps encoding/I/O with the next render. At most two
        # export images are live; no unbounded queue of full-resolution pages.
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix='jpeg-save') as writer:
            pending = None
            for n, page in enumerate(pages, 1):
                rendered, _ = cache.render(page, settings, retain=False, consume=True)
                try:
                    if pending is not None: pending.result()
                    pending = writer.submit(write_page, n, page, rendered)
                except BaseException:
                    rendered.close()
                    raise
            if pending is not None: pending.result()
    else:
        for n, page in enumerate(pages, 1):
            rendered, _ = cache.render(page, settings, retain=False)
            write_page(n, page, rendered)
    return str(folder)


class App:
    def __init__(self, root):
        self.root = root
        self.session = tempfile.TemporaryDirectory(prefix='session-', dir=STATE)
        self.pages = []
        self.events = queue.Queue()
        self.busy = False
        self.saving = False
        self.dirty = False
        self.worker = None
        self.cancel = threading.Event()
        self.controls = []
        self.preview_serial = 0
        self.preview_timer = None
        self.crop_start = None
        self.crop_rectangle = None
        self.preview_bounds = None
        self.thumb = None
        self.grid_images = {}
        self.grid_slots = {}
        self.grid_serial = 0
        self.grid_timer = None
        self.cfg = {}
        try:
            self.cfg = json.loads((STATE/'settings.json').read_text())
        except (OSError, ValueError):
            pass
        if self.cfg.get('capture_version',0) < 4:
            self.cfg.update(margin=.6,mode='Card outline',crop=True,deskew=True)
        self.driver = tk.StringVar(value=self.cfg.get('driver', 'twain'))
        self.device = tk.StringVar(value=self.cfg.get('device', 'Visioneer Patriot PH70'))
        self.dpi = tk.StringVar(value=self.cfg.get('dpi', '600'))
        self.source = tk.StringVar(value=self.cfg.get('source', 'Both sides (duplex)'))
        self.size = tk.StringVar(value=self.cfg.get('size', 'Letter'))
        self.color = tk.StringVar(value=self.cfg.get('color', 'Color'))
        self.margin = tk.StringVar(value=str(self.cfg.get('margin', .6)))
        self.autocrop = tk.BooleanVar(value=self.cfg.get('crop', True))
        self.deskew = tk.BooleanVar(value=self.cfg.get('deskew', True))
        self.mode = tk.StringVar(value=self.cfg.get('mode', 'Page edges').replace('Content + border', 'Content + space'))
        self.original = tk.BooleanVar(value=False)
        self.scan_flip = tk.BooleanVar(value=self.cfg.get('scan_flip', True))
        self.tilt = tk.StringVar(value='0')
        self.status = tk.StringVar(value='Ready. Load your pages, then choose Scan pages.')
        self.details = tk.StringVar(value='Your preview will appear here.')
        self.count = tk.StringVar(value='No pages yet')
        from focus_ui import build_focus_ui
        build_focus_ui(self)
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.report_callback_exception = self.ui_error
        root.after(100, self.poll)
        root.after(300, self.refresh)

    def update_review_controls(self):
        if not hasattr(self, 'save_button'): return
        count = len(self.pages)
        self.save_button.configure(text=f'Save {count} JPEGs' if count else 'Save JPEGs',
                                   state='normal' if count and not self.busy else 'disabled')
        self.scan_button.configure(text='Scan more' if count else 'Scan pages')
        index = self.current()
        self.current_label.set(f'Scan {index+1:02d}' if index is not None else 'No scan selected')
        self.batch_subtitle.set(f'{count} sides in this batch · Ready for review' if count else 'Load your cards to start a new batch')
        for widget in self.page_controls:
            widget.configure(state='normal' if count and not self.busy else 'disabled')

    def ui_error(self, kind, value, tb):
        with (STATE/'error.log').open('a', encoding='utf-8') as log:
            traceback.print_exception(kind, value, tb, file=log)
        self.status.set('Interface error: '+str(value))
        messagebox.showerror('Duplex Scan', str(value))
        # An error in rendering must not stop the queue that receives worker results.
        self.root.after(100, self.poll)

    def restore(self, manifest):
        data = json.loads(Path(manifest).read_text())
        self.pages = [Page(Path(row['path']), row['dpi'], row['label'], row.get('rotation',0)) for row in data]
        self.dirty = bool(self.pages)
        self.update_pages(len(self.pages)-1)

    def button(self, parent, text, command, **packing):
        style = packing.pop('style', 'TButton')
        button = ttk.Button(parent, text=text, command=command, style=style)
        button.pack(**packing); self.controls.append(button)
        return button

    def combo(self, parent, var, values, **packing):
        width = packing.pop('width', 25)
        widget = ttk.Combobox(parent, textvariable=var, values=values, state='readonly', width=width)
        widget.pack(pady=(2, 6), **packing); self.controls.append(widget)
        return widget

    def label_combo(self, parent, label, var, values):
        ttk.Label(parent, text=label).pack(anchor='w')
        return self.combo(parent, var, values)

    def settings(self):
        try:
            margin = float(self.margin.get())
            if not 0 <= margin <= 25: raise ValueError()
        except ValueError:
            raise ValueError('Enter edge space between 0 and 25 millimeters.')
        return Settings(self.autocrop.get(), self.deskew.get(), margin, self.mode.get())

    def current(self):
        selected = self.listbox.curselection()
        return selected[0] if selected and selected[0] < len(self.pages) else None

    def changed(self):
        if self.pages: self.dirty = True
        self.schedule_preview()
        self.schedule_grid()

    def select_page(self, event=None):
        index = self.current()
        if index is not None: self.tilt.set(str(self.pages[index].tilt))
        self.schedule_preview()
        self.draw_grid()
        self.update_review_controls()

    def update_pages(self, selected=0):
        self.listbox.delete(0, 'end')
        for n, page in enumerate(self.pages, 1):
            self.listbox.insert('end', f'  Page {n:02d}')
        self.count.set(f'{len(self.pages)} page'+('s' if len(self.pages) != 1 else ''))
        if self.pages:
            index = min(max(0, selected), len(self.pages)-1)
            self.listbox.selection_set(index); self.listbox.see(index)
        self.select_page()
        self.schedule_grid()

    def grid_select(self, event):
        if self.busy: return
        col = int(self.grid_canvas.canvasx(event.x)//128)
        row = int(self.grid_canvas.canvasy(event.y)//150)
        columns = max(1, self.grid_canvas.winfo_width()//128)
        index = row*columns+col
        if col < columns and index < len(self.pages):
            self.listbox.selection_clear(0, 'end')
            self.listbox.selection_set(index)
            self.select_page()

    def draw_grid(self):
        self.grid_canvas.delete('all')
        self.grid_slots = {}
        columns = max(1, self.grid_canvas.winfo_width()//128)
        selected = self.current()
        for index, page in enumerate(self.pages):
            x, y = (index%columns)*128, (index//columns)*150
            self.grid_canvas.create_rectangle(x+4,y+4,x+124,y+145,
                fill=self.palette['selected'] if index == selected else self.palette['panel'],
                outline=self.palette['accent'] if index == selected else self.palette['line'], width=2 if index == selected else 1)
            key = self.grid_key(page)
            photo = self.grid_images.get(key)
            tile = self.grid_canvas.create_image(x+64,y+64,image=photo if photo else '')
            label = self.grid_canvas.create_text(x+64,y+64,text='' if photo else 'Processing…',fill=self.palette['muted'])
            self.grid_slots.setdefault(key, []).append((tile,label))
            self.grid_canvas.create_text(x+64,y+130,text=f'Scan {index+1:02d}',fill=self.palette['text'],font=('Segoe UI',10))
        self.grid_canvas.configure(scrollregion=(0,0,columns*128,max(150,((len(self.pages)+columns-1)//columns)*150)))

    def grid_key(self, page):
        return (str(page.path), page.rotation, page.manual, page.tilt,
                self.margin.get(), self.autocrop.get(), self.deskew.get(), self.mode.get())

    def schedule_grid(self):
        self.grid_serial += 1
        if self.grid_timer: self.root.after_cancel(self.grid_timer)
        self.grid_timer = self.root.after(180, self.render_grid)

    def render_grid(self):
        self.grid_timer = None
        try: settings = self.settings()
        except ValueError: return
        serial = self.grid_serial
        work = [(self.grid_key(p), Page(p.path,p.dpi,p.label,p.rotation,p.manual,p.tilt)) for p in self.pages]
        active = {key for key, page in work}
        self.grid_images = {key:photo for key,photo in self.grid_images.items() if key in active}
        work = [(key,page) for key,page in work if key not in self.grid_images]
        self.draw_grid()
        columns = max(1,self.grid_canvas.winfo_width()//128)
        index = self.current()
        if index is not None:
            rows = max(1,(len(self.pages)+columns-1)//columns)
            self.grid_canvas.yview_moveto((index//columns)/rows)
        def render():
            for key,page in work:
                if serial != self.grid_serial: return
                try:
                    rendered,_ = cache.render(page,settings,cancelled=lambda:serial != self.grid_serial)
                    if serial != self.grid_serial:
                        rendered.close()
                        return
                    rendered.thumbnail((108,110),Image.Resampling.LANCZOS)
                    self.events.put(('grid', (serial,key,rendered)))
                except Exception:
                    self.events.put(('grid', (serial,key,Image.new('RGB',(80,100),'#d3dce8'))))
        threading.Thread(target=render,daemon=True).start()

    def schedule_preview(self):
        self.preview_serial += 1
        if self.preview_timer: self.root.after_cancel(self.preview_timer)
        self.preview_timer = self.root.after(120, self.preview)

    def preview(self):
        self.preview_timer = None
        if self.saving: return
        index = self.current()
        if index is None:
            self.canvas.delete('all')
            self.canvas.create_text(max(100, self.canvas.winfo_width()/2), max(100, self.canvas.winfo_height()/2),
                text='A clearer view of every page\n\nScan a batch or import images to begin.',
                justify='center', font=('Segoe UI', 16), fill=self.palette['muted'])
            self.details.set('Scans and edits stay on this computer.')
            self.preview_bounds = None
            return
        try: settings = self.settings()
        except ValueError as exc:
            self.status.set(str(exc)); return
        p = self.pages[index]
        page = Page(p.path,p.dpi,p.label,p.rotation,p.manual,p.tilt)
        self.preview_serial += 1
        serial = self.preview_serial
        original = self.original.get()
        preview_size = (max(10,self.canvas.winfo_width()-36),max(10,self.canvas.winfo_height()-36))
        # Reading and processing happen off the UI thread. Full resolution is retained for save.
        def render():
            try:
                if serial != self.preview_serial: return
                if original:
                    with Image.open(page.path) as source:
                        source = source.convert('RGB')
                        source.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
                        result, note = source.copy(), 'Original scan • Drag a rectangle to set a manual crop.'
                else:
                    result, note = cache.render(page, settings,cancelled=lambda:serial != self.preview_serial)
                if serial != self.preview_serial:
                    result.close()
                    return
                result.thumbnail(preview_size, Image.Resampling.LANCZOS)
                self.events.put(('preview', (serial, result, note, original, page.manual)))
            except Exception as exc:
                self.events.put(('preview_error', (serial, str(exc))))
        threading.Thread(target=render, daemon=True).start()

    def draw_preview(self, result):
        serial, rendered, note, original, manual = result
        if serial != self.preview_serial:
            rendered.close()
            return
        self.canvas.delete('all')
        width, height = max(10, self.canvas.winfo_width()-36), max(10, self.canvas.winfo_height()-36)
        rendered.thumbnail((width, height), Image.Resampling.LANCZOS)
        x, y = (self.canvas.winfo_width()-rendered.width)/2, (self.canvas.winfo_height()-rendered.height)/2
        self.thumb = ImageTk.PhotoImage(rendered)
        self.canvas.create_rectangle(x+4, y+4, x+rendered.width+4, y+rendered.height+4, fill=self.palette['shadow'], outline='')
        self.canvas.create_image(x, y, image=self.thumb, anchor='nw')
        self.preview_bounds = (x, y, rendered.width, rendered.height) if original else None
        if original and manual:
            self.canvas.create_rectangle(x+manual[0]*rendered.width, y+manual[1]*rendered.height,
                x+manual[2]*rendered.width, y+manual[3]*rendered.height, outline='#2463eb', width=3)
        self.details.set(note)

    def crop_begin(self, event):
        if self.busy or not self.preview_bounds: return
        self.crop_start = (event.x, event.y)
        self.crop_rectangle = self.canvas.create_rectangle(event.x, event.y, event.x, event.y, outline='#2463eb', width=3)

    def crop_drag(self, event):
        if self.crop_start:
            self.canvas.coords(self.crop_rectangle, *self.crop_start, event.x, event.y)

    def crop_end(self, event):
        if not self.crop_start or not self.preview_bounds: return
        x, y, w, h = self.preview_bounds
        sx, sy = self.crop_start
        self.crop_start = None
        x1, x2 = sorted([min(1, max(0, (sx-x)/w)), min(1, max(0, (event.x-x)/w))])
        y1, y2 = sorted([min(1, max(0, (sy-y)/h)), min(1, max(0, (event.y-y)/h))])
        index = self.current()
        if index is not None and (x2-x1)*w > 15 and (y2-y1)*h > 15:
            self.pages[index].manual = (x1,y1,x2,y2)
            self.original.set(False); self.changed()
        else: self.schedule_preview()

    def rotate(self, degrees):
        index = self.current()
        if index is not None:
            self.pages[index].rotation = (self.pages[index].rotation+degrees)%360
            self.original.set(False); self.changed()

    def move(self, direction):
        index = self.current()
        if index is not None and 0 <= index+direction < len(self.pages):
            self.pages[index], self.pages[index+direction] = self.pages[index+direction], self.pages[index]
            self.dirty = True; self.update_pages(index+direction)

    def remove(self):
        index = self.current()
        if index is not None:
            del self.pages[index]; self.dirty = True; self.update_pages(index)

    def reset_page(self):
        index = self.current()
        if index is not None:
            page = self.pages[index]
            page.rotation, page.manual, page.tilt = 0, None, 0
            self.tilt.set('0'); self.changed()

    def set_tilt(self):
        index = self.current()
        if index is None: return
        try:
            angle = float(self.tilt.get())
            if not -15 <= angle <= 15: raise ValueError()
        except ValueError:
            self.status.set('Fine tilt must be between -15° and 15°.'); return
        if self.pages[index].tilt != angle:
            self.pages[index].tilt = angle; self.original.set(False); self.changed()

    def start(self, message, job, scanning=False):
        if self.busy: return
        self.busy = True; self.cancel.clear()
        self.status.set(message); self.progress.start(12)
        for widget in self.controls: widget.configure(state='disabled')
        self.listbox.configure(state='disabled')
        self.stop_button.configure(state='normal' if scanning else 'disabled')
        def work():
            try: self.events.put(('done', job()))
            except Exception as exc: self.events.put(('error', str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def finish(self):
        self.busy = False; self.worker = None
        self.progress.stop(); self.stop_button.configure(state='disabled')
        for widget in self.controls:
            widget.configure(state='readonly' if isinstance(widget, ttk.Combobox) else 'normal')
        self.listbox.configure(state='normal')
        self.update_review_controls()

    def poll(self):
        try:
            while True:
                event, data = self.events.get_nowait()
                if event == 'preview': self.draw_preview(data)
                elif event == 'grid':
                    serial,key,rendered = data
                    if serial == self.grid_serial:
                        self.grid_images[key] = ImageTk.PhotoImage(rendered)
                        for tile,label in self.grid_slots.get(key, []):
                            self.grid_canvas.itemconfigure(tile,image=self.grid_images[key])
                            self.grid_canvas.itemconfigure(label,text='')
                    rendered.close()
                elif event == 'preview_error':
                    if data[0] == self.preview_serial: self.details.set('Preview unavailable: '+data[1])
                elif event == 'error':
                    self.finish(); self.status.set('Could not complete the operation. Your current pages are still available.')
                    if self.saving:
                        self.saving = False
                        self.schedule_preview()
                        self.schedule_grid()
                    messagebox.showerror('Duplex Scan', data)
                elif event == 'done':
                    self.finish()
                    kind, result = data
                    if kind == 'devices':
                        self.device_combo.configure(values=result)
                        match = next((name for name in result if 'PH70' in name.upper()), None)
                        if match: self.device.set(match)
                        elif result and self.device.get() not in result: self.device.set(result[0])
                        self.connection.set('●  PH70 connected' if match else '●  Scanner available' if result else '○  Scanner offline')
                        self.status.set('PH70 connected. Ready to scan.' if match else 'Choose a scanner.' if result else 'No scanners found. Check power, USB connection, and driver.')
                    elif kind == 'pages':
                        pages, warning = result
                        first = len(self.pages); self.pages.extend(pages)
                        if pages: self.dirty = True
                        self.update_pages(len(self.pages)-1)
                        self.status.set(warning or f'Added {len(pages)} pages. Review the edges, then save.')
                        if warning: messagebox.showwarning('Scan / import notice', warning)
                    elif kind == 'saved':
                        self.saving = False
                        self.clear_batch()
                        self.status.set(f'Saved JPEGs to {result}. Ready for the next batch.')
        except queue.Empty: pass
        self.root.after(80, self.poll)

    def refresh(self):
        driver = self.driver.get()
        self.start('Looking for scanners…', lambda:('devices', backend.devices(driver)))

    def store_images(self, files, dpi):
        pages, warnings = [], []
        for filename in files:
            try:
                with Image.open(filename) as source:
                    for frame in ImageSequence.Iterator(source):
                        actual_dpi = valid_dpi(frame.info.get('dpi'), dpi)
                        path = Path(self.session.name)/(uuid.uuid4().hex+'.png')
                        ImageOps.exif_transpose(frame).convert('RGB').save(path, dpi=(actual_dpi, actual_dpi), compress_level=1)
                        pages.append(Page(path, actual_dpi, Path(filename).name))
            except Exception as exc:
                warnings.append(f'{Path(filename).name}: {exc}')
        return pages, '\n'.join(warnings)

    def import_images(self):
        paths = filedialog.askopenfilenames(title='Import scans or photos', filetypes=[('Images', '*.png *.jpg *.jpeg *.tif *.tiff *.bmp')])
        if paths:
            dpi = int(self.dpi.get())
            self.start('Importing images…', lambda:('pages', self.store_images(paths, dpi)))

    def scan(self):
        if not self.device.get():
            messagebox.showinfo('Choose scanner', 'Connect your scanner and click Refresh.'); return
        dpi = int(self.dpi.get())
        size = {'Letter':'letter', 'A4':'a4', 'Legal':'legal', '4 × 6 in':'4x6in', '5 × 7 in':'5x7in', '8 × 10 in':'8x10in'}[self.size.get()]
        color = {'Color':'color', 'Grayscale':'gray', 'Black & white':'bw'}[self.color.get()]
        flip = self.scan_flip.get()
        folder = Path(self.session.name)/uuid.uuid4().hex; folder.mkdir()
        command = backend.scan_command(folder, self.device.get(), self.driver.get(),
                                'duplex' if self.source.get().startswith('Both') else 'feeder', dpi, size, color)
        def job():
            if self.cancel.is_set(): return 'pages', ([], 'Scan cancelled before starting.')
            self.worker = subprocess.Popen(command, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding='utf-8-sig', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW)
            if self.cancel.is_set(): self.worker.terminate()
            output, _ = self.worker.communicate()
            files = sorted([*folder.glob('page-*.png'),*folder.glob('page-*.bmp')])
            pages, warnings = [], []
            for path in files:
                try:
                    with Image.open(path) as image:
                        image.verify()
                    pages.append(Page(path, dpi, path.name))
                except Exception as exc:
                    warnings.append(f'{path.name}: {exc}')
            warning = '\n'.join(warnings)
            if flip:
                for page in pages: page.rotation = 180
            if self.cancel.is_set():
                warning = f'Scan stopped. {len(pages)} completed pages recovered. Check page order before scanning the remaining sheets.'
            elif self.worker.returncode:
                error_file=folder/'capture-error.txt'
                if error_file.exists(): output=error_file.read_text(encoding='utf-8')
                warning = f'Scanner reported a problem. {len(pages)} completed pages recovered.\n\n{output[-2500:]}'
            elif not pages:
                warning = 'No pages returned. Load the feeder and check the selected scanner and paper size.'
            return 'pages', (pages, warning)
        self.start('Scanning… Load complete batches before starting. Both sides are kept in driver order.', job, scanning=True)

    def stop(self):
        self.cancel.set()
        if self.worker and self.worker.poll() is None:
            subprocess.run(['taskkill', '/PID', str(self.worker.pid), '/T', '/F'], capture_output=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        self.status.set('Stopping scan… completed pages will be recovered if available.')
        self.stop_button.configure(state='disabled')

    def save(self):
        if self.busy: return
        if not self.pages:
            messagebox.showinfo('No pages', 'Scan or import pages first.'); return
        try: settings = self.settings()
        except ValueError as exc:
            messagebox.showerror('Border setting', str(exc)); return
        target = Path.home()/'Pictures'/'Scanned Photos'
        snapshot = [Page(p.path,p.dpi,p.label,p.rotation,p.manual,p.tilt) for p in self.pages]
        self.saving = True
        self.preview_serial += 1
        self.grid_serial += 1
        if self.grid_timer:
            self.root.after_cancel(self.grid_timer)
            self.grid_timer = None
        self.start('Saving JPEGs to Scanned Photos…',
                   lambda:('saved', export_pages(snapshot, settings, target, 'JPEG', direct=True)))

    def new_batch(self):
        if self.pages and not messagebox.askyesno('Start a new batch?', 'Clear the current pages? Save them first if you want to keep them.'): return
        self.clear_batch()

    def clear_batch(self):
        self.pages.clear()
        self.dirty = False
        self.original.set(False)
        self.tilt.set('0')
        self.crop_start = None
        self.preview_bounds = None
        self.thumb = None
        self.grid_images.clear()
        cache.clear()
        self.update_pages()

    def close(self):
        if self.busy:
            messagebox.showinfo('Operation in progress', 'Finish the current operation, or stop the scan before closing.'); return
        if self.dirty and self.pages and not messagebox.askyesno('Unsaved pages', 'Close and discard the unsaved pages or edits?'): return
        try:
            cfg = {key:getattr(self,key).get() for key in ['driver','device','dpi','source','size','color','margin','mode','appearance']}
            cfg.update(crop=self.autocrop.get(), deskew=self.deskew.get(), scan_flip=self.scan_flip.get(),capture_version=4)
            (STATE/'settings.json').write_text(json.dumps(cfg, indent=2))
        except OSError: pass
        self.root.destroy()
        try: self.session.cleanup()
        except OSError: pass


if __name__ == '__main__':
    if '--self-check' in sys.argv:
        from smoke_check import run
        raise SystemExit(run(sys.argv[sys.argv.index('--self-check')+1]))
    if '--capture' in sys.argv:
        from capture import run
        raise SystemExit(run(sys.argv[sys.argv.index('--capture')+1:]))
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('DuplexScan.PH70.Gallery')
    root = tk.Tk()
    icon = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))/'DuplexScan-Neon.ico'
    if icon.exists(): root.iconbitmap(default=str(icon))
    app = App(root)
    if '--restore' in sys.argv:
        app.restore(sys.argv[sys.argv.index('--restore')+1])
    root.mainloop()
