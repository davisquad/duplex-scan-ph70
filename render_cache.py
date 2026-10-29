"""Bounded, shared full-quality renders for preview, thumbnails and export."""
from collections import OrderedDict
from threading import RLock
from concurrent.futures import CancelledError
from PIL import Image
from processing import process

class RenderCache:
    def __init__(self, limit=256*1024*1024):
        self.limit = limit
        self.items = OrderedDict()
        self.bytes = 0
        self.lock = RLock()
        self.render_lock = RLock()
        self.generation = 0

    def clear(self):
        with self.lock:
            self.generation += 1
            for image,note in self.items.values(): image.close()
            self.items.clear()
            self.bytes = 0

    def _get(self, key):
        if key in self.items:
            self.items.move_to_end(key)
            image,note = self.items[key]
            return image.copy(),note

    def render(self, page, settings, retain=True, cancelled=None):
        if cancelled and cancelled(): raise CancelledError()
        stat = page.path.stat()
        key = (str(page.path),stat.st_mtime_ns,stat.st_size,page.dpi,
               page.rotation,page.manual,page.tilt,settings.crop,
               settings.deskew,settings.margin,settings.mode)
        # Cache hits never wait for a different page's expensive render.
        with self.lock:
            hit = self._get(key)
            if hit is not None: return hit
            generation = self.generation
        # Serialize misses to bound working memory and share duplicate requests.
        with self.render_lock:
            if cancelled and cancelled(): raise CancelledError()
            with self.lock:
                hit = self._get(key)
                if hit is not None: return hit
            with Image.open(page.path) as source:
                image,note = process(source,page.dpi,settings,page.rotation,page.manual,page.tilt)
            size = image.width*image.height*len(image.getbands())
            with self.lock:
                if retain and size <= self.limit and generation == self.generation:
                    while self.items and self.bytes+size > self.limit:
                        old,_ = self.items.popitem(last=False)[1]
                        self.bytes -= old.width*old.height*len(old.getbands())
                        old.close()
                    self.items[key] = (image,note)
                    self.bytes += size
                    return image.copy(),note
            return image,note

cache = RenderCache()
