import tempfile
import unittest
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from pypdf import PdfReader
from processing import Settings, process, page_rectangle
from app import Page, export_pages, valid_dpi
from backend import scan_args


def sample(angle=0):
    page = Image.new('RGB', (600, 800), 'white')
    draw = ImageDraw.Draw(page)
    draw.rectangle((25, 25, 575, 775), outline='#1b5591', width=4)
    for y in range(140, 680, 50):
        draw.line((70, y, 530, y), fill='#333333', width=4)
    rotated = page.rotate(angle, Image.Resampling.BICUBIC, expand=True, fillcolor=(130,130,130))
    scan = Image.new('RGB', (900, 1100), (130,130,130))
    scan.paste(rotated, ((900-rotated.width)//2, (1100-rotated.height)//2))
    return scan


class ProcessingTests(unittest.TestCase):
    def test_export_does_not_evict_pages_it_has_yet_to_save(self):
        from render_cache import RenderCache
        from unittest.mock import patch
        import hashlib
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);pages=[]
            for n in range(6):
                path=root/f'{n}.png'
                Image.new('RGB',(100,150),(n*30,40,60)).save(path)
                pages.append(Page(path,300,str(n)))
            settings=Settings(False,False,0)
            cache=RenderCache(limit=100*150*3*3)
            for page in pages: cache.render(page,settings)
            with patch('app.cache',cache), patch('render_cache.process',wraps=process) as wrapped:
                result=Path(export_pages(pages,settings,root/'out','JPEG',direct=True))
                self.assertEqual(wrapped.call_count,3)
            outputs=sorted(result.glob('*.jpg'))
            self.assertEqual(len(outputs),6)
            import io
            for page,path in zip(pages,outputs):
                with Image.open(page.path) as source:
                    expected,_=process(source,300,settings)
                buffer=io.BytesIO();expected.save(buffer,format='JPEG',quality=95,subsampling=0,dpi=(300,300))
                self.assertEqual(path.read_bytes(),buffer.getvalue())

    def test_cancelled_render_skips_processing(self):
        from render_cache import RenderCache
        from concurrent.futures import CancelledError
        from unittest.mock import patch
        with patch('render_cache.process') as renderer:
            with self.assertRaises(CancelledError):
                RenderCache().render(Page(Path('unused'),300,'page'),Settings(),cancelled=lambda:True)
            renderer.assert_not_called()

    def test_save_pauses_background_work_and_error_resumes_review(self):
        from app import App
        from unittest.mock import Mock,patch
        from queue import Queue
        app=App.__new__(App)
        app.busy=False;app.saving=False;app.pages=[Page(Path('source'),600,'page')]
        app.settings=Mock(return_value=Settings());app.start=Mock();app.root=Mock()
        app.preview_serial=4;app.grid_serial=5;app.grid_timer='timer'
        app.save()
        self.assertTrue(app.saving)
        self.assertEqual((app.preview_serial,app.grid_serial),(5,6))
        app.root.after_cancel.assert_called_once_with('timer')
        app.events=Queue();app.events.put(('error','disk full'))
        app.finish=Mock();app.status=Mock();app.schedule_preview=Mock();app.schedule_grid=Mock()
        with patch('app.messagebox.showerror'): app.poll()
        self.assertFalse(app.saving)
        self.assertEqual(len(app.pages),1)
        app.schedule_preview.assert_called_once()
        app.schedule_grid.assert_called_once()

    def test_cached_page_is_available_during_another_render_and_clear_is_final(self):
        from render_cache import RenderCache
        from threading import Event
        from concurrent.futures import ThreadPoolExecutor
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            first=Path(folder)/'first.png'; second=Path(folder)/'second.png'
            Image.new('RGB',(50,80),'red').save(first)
            Image.new('RGB',(50,80),'blue').save(second)
            cache=RenderCache();settings=Settings(False,False,0)
            cached=Page(first,300,'first');cold=Page(second,300,'second')
            cache.render(cached,settings)
            entered=Event();release=Event()
            def slow(*args,**kwargs):
                entered.set()
                if not release.wait(5): raise RuntimeError('test timeout')
                return process(*args,**kwargs)
            with patch('render_cache.process',side_effect=slow), ThreadPoolExecutor(2) as pool:
                pending=pool.submit(cache.render,cold,settings)
                try:
                    self.assertTrue(entered.wait(2))
                    hit=pool.submit(cache.render,cached,settings).result(timeout=2)
                    self.assertEqual(hit[0].getpixel((0,0)),(255,0,0))
                    cache.clear()
                finally:
                    release.set()
                self.assertEqual(pending.result()[0].getpixel((0,0)),(0,0,255))
            self.assertEqual(cache.bytes,0)
            self.assertFalse(cache.items)

    def test_thumbnail_arrival_updates_only_its_tile(self):
        from app import App
        from unittest.mock import Mock,patch
        from queue import Queue
        app=App.__new__(App)
        app.events=Queue();app.grid_serial=3;app.grid_images={}
        app.grid_slots={'key':[(10,11)]};app.grid_canvas=Mock()
        app.root=Mock();app.draw_grid=Mock()
        app.events.put(('grid',(3,'key',Image.new('RGB',(10,10)))))
        with patch('app.ImageTk.PhotoImage',return_value='photo'):
            app.poll()
        app.draw_grid.assert_not_called()
        self.assertEqual(app.grid_canvas.itemconfigure.call_count,2)

    def test_native_capture_keeps_identical_pixels_and_both_sides(self):
        from unittest.mock import MagicMock, patch
        from capture import run
        with tempfile.TemporaryDirectory() as folder:
            expected = sample(3)
            native = MagicMock()
            native.save.side_effect = lambda path: expected.save(path,format='BMP')
            source = MagicMock()
            def acquire(after,before,**kwargs):
                after(native,True)
                after(native,False)
            source.acquire_natively.side_effect = acquire
            manager = MagicMock()
            manager.__enter__.return_value.open_source.return_value.__enter__.return_value = source
            with patch('capture.twain.SourceManager',return_value=manager), patch('capture.configure',return_value={}), patch('capture.backend.engine',return_value=Path(folder)/'engine.exe'):
                code=run(['--folder',folder,'--device','PH70','--source','duplex','--dpi','600','--size','letter','--color','color'])
            self.assertEqual(code,0)
            files=sorted(Path(folder).glob('page-*.bmp'))
            self.assertEqual(len(files),2)
            self.assertFalse(list(Path(folder).glob('*.partial.bmp')))
            for path in files:
                with Image.open(path) as image:
                    self.assertEqual(image.tobytes(),expected.tobytes())

    def test_render_cache_matches_original_and_invalidates_edits(self):
        from render_cache import RenderCache
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'scan.png'
            sample(4).save(path)
            page = Page(path,300,'scan',180)
            settings = Settings(True,True,.6,'Card outline')
            cache = RenderCache()
            with Image.open(path) as source:
                expected,note = process(source,300,settings,180)
            with patch('render_cache.process',wraps=process) as wrapped:
                first,_ = cache.render(page,settings)
                self.assertEqual(first.tobytes(),expected.tobytes())
                first.thumbnail((30,30))
                second,_ = cache.render(page,settings)
                self.assertEqual(second.tobytes(),expected.tobytes())
                self.assertEqual(wrapped.call_count,1)
                settings.margin = 1
                cache.render(page,settings)
                page.rotation = 90
                cache.render(page,settings)
                self.assertEqual(wrapped.call_count,3)
            self.assertLessEqual(cache.bytes,cache.limit)

    def test_direct_jpeg_save_keeps_existing_files_and_avoids_subfolders(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root/'source.png'
            Image.new('RGB',(100,150),'red').save(source)
            target = root/'Scanned Photos'
            pages = [Page(source,300,'front'),Page(source,300,'back')]
            for _ in range(2):
                self.assertEqual(export_pages(pages,Settings(False,False,0),target,'JPEG',direct=True),str(target))
            files = list(target.iterdir())
            self.assertEqual(len(files),4)
            self.assertTrue(all(p.is_file() and p.suffix == '.jpg' for p in files))
            for path in files:
                with Image.open(path) as image:
                    self.assertEqual(image.format,'JPEG')
                    self.assertEqual(image.size,(100,150))
                    self.assertEqual(image.info['dpi'],(300,300))

    def test_physical_outline_ignores_shadow_and_printed_border(self):
        from card_edges import detect_card
        import cv2
        for angle in (-6,0,5):
            for color in ((235,198,185),(245,245,245)):
                height,width=1100,1100
                background=np.tile(np.linspace(155,190,width),(height,1)).astype(np.float32)
                rgb=np.repeat(background[:,:,None],3,axis=2)
                shadow=np.zeros((height,width),np.uint8)
                corners=cv2.boxPoints(((550,550),(450,760),angle)).astype(np.int32)
                cv2.fillConvexPoly(shadow,corners+np.array([20,14]),255)
                shade=cv2.GaussianBlur(shadow,(71,71),15)/255
                rgb=np.clip(rgb-50*shade[:,:,None],0,255).astype(np.uint8)
                cv2.fillConvexPoly(rgb,corners,color)
                inner=cv2.boxPoints(((550,550),(390,700),angle+1.5)).astype(np.int32)
                cv2.polylines(rgb,[inner],True,(30,30,30),5)
                rect=detect_card(rgb)
                self.assertIsNotNone(rect)
                cx,cy,w,h,found=rect
                self.assertLess(abs(w-450),7)
                self.assertLess(abs(h-760),7)
                self.assertLess(abs(found-angle),.4)
                result,note=process(Image.fromarray(rgb),254,Settings(True,True,.3,'Card outline'))
                self.assertLess(abs(result.width-458),9)
                self.assertLess(abs(result.height-768),9)

    def test_uniform_dark_scan_is_not_guessed(self):
        image=Image.new('RGB',(600,800),(50,50,50))
        result,note=process(image,300,Settings(True,True,.3,'Card outline'))
        self.assertEqual(image.tobytes(),result.tobytes())
        self.assertIn('No outer card edge',note)

    def test_margin_preserves_actual_source_pixels(self):
        image = Image.new('RGB', (400,500), (80,130,170))
        ImageDraw.Draw(image).rectangle((100,100,299,399),fill='red')
        output, _ = process(image,254,Settings(False,False,3),manual=(.25,.2,.75,.8))
        self.assertEqual(output.size,(260,360))
        self.assertEqual(output.getpixel((10,100)),(80,130,170))
        self.assertEqual(output.getpixel((40,100)),(255,0,0))

    def test_no_surround_is_invented(self):
        image=Image.new('RGB',(200,300),'red')
        output,_=process(image,254,Settings(True,False,3))
        self.assertEqual(output.size,image.size)
        self.assertEqual(output.tobytes(),image.tobytes())

    def test_margin_clamps_to_scan(self):
        image=Image.new('RGB',(200,300),(70,100,140))
        output,note=process(image,254,Settings(False,False,3),manual=(0,.1,1,.9))
        self.assertEqual(output.size,(200,300))
        self.assertEqual(output.getpixel((0,0)),(70,100,140))
        self.assertIn('limited',note)

    def test_page_deskew_both_directions(self):
        for angle in (-7, 0, 6):
            output, note = process(sample(angle), 254, Settings(True,True,3))
            self.assertIn('Card edges', note)
            self.assertLess(abs(output.width-662), 10)
            self.assertLess(abs(output.height-862), 10)
            rect = page_rectangle(np.asarray(output))
            self.assertIsNotNone(rect)
            self.assertLess(abs(rect[-1]), .5)

    def test_blank_page_retained(self):
        output, _ = process(Image.new('RGB',(300,400),'white'), 254, Settings(True,True,2))
        self.assertEqual(output.size, (300,400))

    def test_content_crop_keeps_edge_mark(self):
        image = Image.new('RGB', (300,400),'white')
        ImageDraw.Draw(image).rectangle((50,60,250,330), fill='black')
        output, _ = process(image,254,Settings(True,False,3,'Content + border'))
        self.assertEqual(output.size,(261,331))

    def test_manual_rotation_and_original_unchanged(self):
        original = Image.new('RGB',(400,600),'red')
        output, _ = process(original,254,Settings(False,False,0),90,(.1,.1,.9,.9))
        self.assertEqual(output.size,(480,320))
        self.assertEqual(original.size,(400,600))

    def test_pdf_page_sizes_and_image_formats(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            pages=[]
            for n, dpi in enumerate([100,200]):
                path=root/f'{n}.png'
                Image.new('RGB',(200,300),'red').save(path)
                pages.append(Page(path,dpi,str(n)))
            pdf = root/'batch.pdf'
            export_pages(pages,Settings(False,False,0),pdf,'PDF')
            reader=PdfReader(pdf)
            self.assertEqual(len(reader.pages),2)
            self.assertEqual(float(reader.pages[0].mediabox.width),144)
            self.assertEqual(float(reader.pages[1].mediabox.width),72)
            for kind in ('PNG','JPEG','TIFF'):
                target=Path(export_pages(pages,Settings(False,False,0),root,kind))
                self.assertEqual(len(list(target.iterdir())),2)
                with Image.open(next(target.iterdir())) as image:
                    self.assertEqual(image.size,(200,300))

    def test_duplex_command_and_dpi_fallback(self):
        args=scan_args('C:/test','Visioneer Patriot PH70','twain','duplex',300,'letter','color')
        self.assertEqual(args[args.index('--source')+1],'duplex')
        self.assertIn('page-$(nnnn).png',args[1])
        self.assertEqual(valid_dpi((0,0),300),300)
        self.assertEqual(valid_dpi((600,600),300),600)

    def test_card_on_full_letter_scan(self):
        image=Image.new('RGB',(1700,2200),(90,90,90))
        image.paste(Image.new('RGB',(500,780),'#eee2c0'),(600,550))
        output,note=process(image,200,Settings(True,True,5))
        self.assertIn('Card edges',note)
        self.assertLess(output.width,610)
        self.assertGreater(output.width,570)
        self.assertLess(output.height,890)
        self.assertGreater(output.height,850)

    def test_ph70_always_uses_explicit_capture(self):
        from backend import scan_command
        command=scan_command('C:/scan','Visioneer Patriot PH70','twain','duplex',300,'letter','color')
        self.assertIn('--capture',command)
        self.assertNotIn('--noprofile',command)

    def test_capture_disables_crop_after_layout(self):
        from capture import configure
        from twain.lowlevel import constants as c
        class Device:
            values={c.ICAP_PHYSICALWIDTH:8.5}
            calls=[]
            def get_capability_current(self,cap): return (c.TWTY_UINT16,self.values.get(cap,0))
            def set_capability(self,cap,kind,value): self.values[cap]=value; self.calls.append(cap)
            def set_image_layout(self,value): self.calls.append('layout')
            def get_image_layout(self): return ((0,0,8.5,11),1,1,1)
        device=Device(); configure(device,300,True,'color','letter')
        self.assertFalse(device.values[c.ICAP_AUTOMATICBORDERDETECTION])
        self.assertFalse(device.values[c.ICAP_AUTOMATICDESKEW])
        self.assertEqual(device.values[c.ICAP_OVERSCAN],c.TWOV_ALL)
        self.assertLess(device.calls.index('layout'),device.calls.index(c.ICAP_AUTOMATICBORDERDETECTION))


if __name__=='__main__': unittest.main()
