"""Conservative page detection, deskew and physical-size border rendering."""
from dataclasses import dataclass
import math
import cv2
import numpy as np
from PIL import Image, ImageOps
from card_edges import detect_card


@dataclass
class Settings:
    crop: bool = True
    deskew: bool = True
    margin: float = 0.3
    mode: str = 'Page edges'


def page_rectangle(rgb):
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 25, 85)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    # Pale card backs can have a broken edge in a gray scanner background.
    # Color distance supplies a closed outer silhouette in that case.
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    border = np.concatenate([lab[:8].reshape(-1,3),lab[-8:].reshape(-1,3),
                             lab[:,:8].reshape(-1,3),lab[:,-8:].reshape(-1,3)])
    background = np.median(border,axis=0)
    noise = np.percentile(np.linalg.norm(border-background,axis=1),90)
    mask = (np.linalg.norm(lab-background,axis=2)>max(10,noise+5)).astype(np.uint8)*255
    mask = cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((7,7),np.uint8))
    silhouettes,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    contours=list(contours)
    for silhouette in silhouettes:
        x,y,w,h=cv2.boundingRect(silhouette)
        if x>1 and y>1 and x+w<rgb.shape[1]-1 and y+h<rgb.shape[0]-1:
            contours.append(silhouette)
    area = gray.size
    candidates = []
    for contour in contours:
        rect = cv2.minAreaRect(contour)
        (cx, cy), (w, h), angle = rect
        if w * h < area * .015 or min(w, h) < 40:
            continue
        if cv2.contourArea(contour) / (w * h) < .88:
            continue
        if angle > 45:
            w, h, angle = h, w, angle - 90
        elif angle < -45:
            w, h, angle = h, w, angle + 90
        if abs(angle) > 15:
            continue
        candidates.append((w*h, (cx, cy, w, h, angle)))
    return max(candidates, default=(0, None))[1]


def text_angle(rgb):
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi/720, 45,
                            minLineLength=max(35, gray.shape[1]//12), maxLineGap=15)
    if lines is None:
        return 0.0
    angles = []
    for x1, y1, x2, y2 in lines.reshape(-1, 4):
        angle = math.degrees(math.atan2(y2-y1, x2-x1))
        if abs(angle) < 12:
            angles.append(angle)
    return float(np.median(angles)) if len(angles) >= 4 else 0.0


def extract_surround(image, rect, margin):
    """Expand the crop in source coordinates; never create surrounding pixels."""
    cx, cy, w, h, angle = rect
    if abs(angle) < .01:
        wanted = (math.floor(cx-w/2-margin), math.floor(cy-h/2-margin),
                  math.ceil(cx+w/2+margin), math.ceil(cy+h/2+margin))
        clipped = (max(0,wanted[0]), max(0,wanted[1]), min(image.width,wanted[2]), min(image.height,wanted[3]))
        return image.crop(clipped), clipped != wanted, 0.0
    a = math.radians(angle)
    u, v = np.array([math.cos(a), math.sin(a)]), np.array([-math.sin(a), math.cos(a)])
    center = np.array([cx,cy])
    def inside(pad):
        corners = [center+sx*u*(w/2+pad)+sy*v*(h/2+pad) for sx,sy in [(-1,-1),(1,-1),(1,1),(-1,1)]]
        return all(0 <= pt[0] <= image.width-1 and 0 <= pt[1] <= image.height-1 for pt in corners)
    if not inside(0):
        # Straightening would lose part of the card or invent corner pixels.
        return image.copy(), True, 0.0
    available = margin
    if not inside(margin):
        low, high = 0.0, margin
        for _ in range(24):
            mid = (low+high)/2
            if inside(mid): low = mid
            else: high = mid
        available = low
    w, h = w+2*available, h+2*available
    origin = center-u*w/2-v*h/2
    ow, oh = max(1,round(w)), max(1,round(h))
    result = image.transform((ow,oh),Image.Transform.AFFINE,
        (u[0]*w/ow,v[0]*h/oh,origin[0],u[1]*w/ow,v[1]*h/oh,origin[1]),Image.Resampling.BICUBIC)
    return result, available+1 < margin, angle


def process(image, dpi, settings, rotation=0, manual=None, tilt=0):
    source_image = image
    if image.mode != 'RGB':
        image = image.convert('RGB')
    margin = max(0,min(25,settings.margin))*dpi/25.4
    scale = min(1,2000/max(image.size))
    small = None
    def analysis_image():
        nonlocal small
        if small is None:
            small = np.asarray(image.resize((max(1,round(image.width*scale)),max(1,round(image.height*scale)))))
        return small
    rect = None
    note = 'Original scan retained'
    if manual:
        x1,y1,x2,y2 = manual
        rect = ((x1+x2)*image.width/2,(y1+y2)*image.height/2,
                (x2-x1)*image.width,(y2-y1)*image.height,0)
        note = 'Manual crop with scanned surround'
    elif settings.crop and settings.mode in ('Page edges','Card outline'):
        detected = detect_card(analysis_image())
        if detected:
            cx,cy,w,h,angle = detected
            rect = (cx/scale,cy/scale,w/scale,h/scale,angle)
            note = 'Card edges detected; 5 mm working surround'
    elif settings.crop and settings.mode in ('Content + border','Content + space'):
        ys,xs = np.where(np.min(np.asarray(image),axis=2)<245)
        if len(xs):
            x1,y1,x2,y2 = int(xs.min()),int(ys.min()),int(xs.max())+1,int(ys.max())+1
            rect = ((x1+x2)/2,(y1+y2)/2,x2-x1,y2-y1,0)
            note = 'Content crop with scanned surround'
    correction = 0.0
    if rect:
        cx,cy,w,h,detected = rect
        if not settings.deskew:
            points=cv2.boxPoints(((cx,cy),(w,h),detected))
            x1,y1=points.min(axis=0); x2,y2=points.max(axis=0)
            cx,cy,w,h,detected=(x1+x2)/2,(y1+y2)/2,x2-x1,y2-y1,0
        # Physical outline determines skew. Printed text and photograph borders
        # may themselves be crooked relative to the card mount.
        # First retain a 5 mm working surround in original pixel coordinates.
        # Cropping this working region is lossless; only final deskew resamples.
        points=cv2.boxPoints(((cx,cy),(w,h),detected+tilt))
        guard=max(5,settings.margin)*dpi/25.4
        left=max(0,math.floor(float(points[:,0].min())-guard))
        top=max(0,math.floor(float(points[:,1].min())-guard))
        right=min(image.width,math.ceil(float(points[:,0].max())+guard))
        bottom=min(image.height,math.ceil(float(points[:,1].max())+guard))
        image=image.crop((left,top,right,bottom))
        cx-=left; cy-=top
        image, limited, correction = extract_surround(image,(cx,cy,w,h,detected+tilt),margin)
        if limited:
            note += ' — extra space limited by captured scan'
    else:
        if settings.crop and margin:
            note = 'No outer card edge found; full scan kept (no added border)'
        if (settings.deskew or tilt):
            angle = (text_angle(analysis_image()) if settings.deskew else 0)+tilt
            if abs(angle)>.12:
                note += ' — insufficient surrounding scan to straighten without clipping'
    if rotation%360:
        image=image.rotate(-rotation,expand=True)
    if image is source_image:
        image = image.copy()
    return image, f'{note}  •  correction {correction:+.1f}°  •  final gap {settings.margin:g} mm'
