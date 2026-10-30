"""Bounded, shared full-quality renders for preview, thumbnails and export."""
from collections import OrderedDict
from threading import RLock
from concurrent.futures import CancelledError
from PIL import Image
from io import BytesIO
from processing import process

def image_bytes(image):
    # Pillow stores RGB pixels in four-byte slots. Include that padding when
    # budgeting retained images; source/working images remain separate.
    return image.width*image.height*(4 if image.mode == 'RGB' else len(image.getbands()))


class RenderCache:
    def __init__(self, limit=256*1024*1024, jpeg_limit=128*1024*1024, view_limit=32*1024*1024):
        self.limit = limit
        self.items = OrderedDict()
        self.bytes = 0
        self.lock = RLock()
        self.render_lock = RLock()
        self.generation = 0
        self.jpeg_limit = jpeg_limit
        self.jpegs = OrderedDict()
        self.jpeg_bytes = 0
        self.view_limit = view_limit
        self.views = OrderedDict()
        self.view_bytes = 0

    def clear(self):
        with self.lock:
            self.generation += 1
            for image,note in self.items.values(): image.close()
            self.items.clear()
            self.bytes = 0
            self.jpegs.clear()
            self.jpeg_bytes = 0
            for image,note in self.views.values(): image.close()
            self.views.clear()
            self.view_bytes = 0

    def preview(self, page, settings, size, cancelled=None):
        """Cache exact lossless display pixels, never decode an export JPEG."""
        if cancelled and cancelled(): raise CancelledError()
        key = (self.key(page, settings), tuple(size))
        with self.lock:
            if key in self.views:
                self.views.move_to_end(key)
                image,note = self.views[key]
                return image.copy(),note
            generation = self.generation
        image,note = self.render(page,settings,cancelled=cancelled)
        try:
            if cancelled and cancelled(): raise CancelledError()
            image.thumbnail(size,Image.Resampling.LANCZOS)
            amount = image_bytes(image)
            with self.lock:
                if amount <= self.view_limit and generation == self.generation:
                    previous = self.views.pop(key,None)
                    if previous is not None:
                        old,_ = previous
                        self.view_bytes -= image_bytes(old)
                        old.close()
                    while self.views and self.view_bytes+amount > self.view_limit:
                        old,_ = self.views.popitem(last=False)[1]
                        self.view_bytes -= image_bytes(old)
                        old.close()
                    self.views[key] = (image.copy(),note)
                    self.view_bytes += amount
            return image,note
        except BaseException:
            image.close()
            raise

    def for_export(self, page, settings):
        encoded = self.jpeg(page,settings)
        if encoded is not None: return encoded
        image,_ = self.render(page,settings,retain=False,consume=True)
        # A background render may have prepared a JPEG while export waited.
        encoded = self.jpeg(page,settings)
        if encoded is not None:
            image.close()
            return encoded
        return image

    @staticmethod
    def key(page, settings):
        stat = page.path.stat()
        return (str(page.path),stat.st_mtime_ns,stat.st_size,page.dpi,
                page.rotation,page.manual,page.tilt,settings.crop,
                settings.deskew,settings.margin,settings.mode)

    def jpeg(self, page, settings):
        key = self.key(page, settings)
        with self.lock:
            data = self.jpegs.get(key)
            if data is not None: self.jpegs.move_to_end(key)
            return data # Immutable bytes remain safe even if clear() runs.

    def _get(self, key, consume=False):
        if key in self.items:
            if consume:
                image,note = self.items.pop(key)
                self.bytes -= image_bytes(image)
                return image,note
            self.items.move_to_end(key)
            image,note = self.items[key]
            return image.copy(),note

    def render(self, page, settings, retain=True, cancelled=None, consume=False):
        if cancelled and cancelled(): raise CancelledError()
        key = self.key(page, settings)
        # Cache hits never wait for a different page's expensive render.
        with self.lock:
            hit = self._get(key, consume)
            if hit is not None: return hit
            generation = self.generation
        # Serialize misses to bound working memory and share duplicate requests.
        with self.render_lock:
            if cancelled and cancelled(): raise CancelledError()
            with self.lock:
                hit = self._get(key, consume)
                if hit is not None: return hit
            with Image.open(page.path) as source:
                image,note = process(source,page.dpi,settings,page.rotation,page.manual,page.tilt)
            size = image_bytes(image)
            encoded = None
            if retain and not consume and self.jpeg_limit:
                # Encode exactly once during background preparation. Export can
                # use these bytes even after the much larger pixels are evicted.
                try:
                    with BytesIO() as buffer:
                        image.save(buffer,format='JPEG',dpi=(page.dpi,page.dpi),quality=95,subsampling=0)
                        encoded = buffer.getvalue()
                except (OSError, ValueError):
                    pass # Optional preparation must never prevent review.
            with self.lock:
                if encoded is not None and len(encoded) <= self.jpeg_limit and generation == self.generation:
                    while self.jpegs and self.jpeg_bytes+len(encoded) > self.jpeg_limit:
                        self.jpeg_bytes -= len(self.jpegs.popitem(last=False)[1])
                    previous = self.jpegs.pop(key, None)
                    if previous is not None: self.jpeg_bytes -= len(previous)
                    self.jpegs[key] = encoded
                    self.jpeg_bytes += len(encoded)
                if retain and not consume and size <= self.limit and generation == self.generation:
                    while self.items and self.bytes+size > self.limit:
                        old,_ = self.items.popitem(last=False)[1]
                        self.bytes -= image_bytes(old)
                        old.close()
                    self.items[key] = (image,note)
                    self.bytes += size
                    return image.copy(),note
            return image,note

cache = RenderCache()
