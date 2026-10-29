"""Detect physical card surfaces, excluding gray scanner backing and shadows."""
import cv2
import numpy as np


def normalize(rect):
    (cx, cy), (w, h), angle = rect
    if angle > 45: w,h,angle=h,w,angle-90
    elif angle < -45: w,h,angle=h,w,angle+90
    return cx,cy,w,h,angle


def detect_card(rgb):
    height,width=rgb.shape[:2]
    if min(height,width)<40: return None
    lab=cv2.cvtColor(rgb,cv2.COLOR_RGB2LAB).astype(np.float32)
    band=max(3,round(width*.035))
    # Estimate backing locally for each row, handling scanner illumination gradients.
    left=np.median(lab[:,:band],axis=1)
    right=np.median(lab[:,-band:],axis=1)
    left=cv2.GaussianBlur(left.reshape(height,1,3),(1,31),0).reshape(height,3)
    right=cv2.GaussianBlur(right.reshape(height,1,3),(1,31),0).reshape(height,3)
    t=np.linspace(0,1,width,dtype=np.float32)[None,:,None]
    background=left[:,None,:]*(1-t)+right[:,None,:]*t
    delta=lab-background
    chroma=np.linalg.norm(delta[:,:,1:],axis=2)
    edge_noise=np.concatenate((chroma[:,:band].ravel(),chroma[:,-band:].ravel()))
    color_threshold=max(5.0,float(np.percentile(edge_noise,98))+2)
    # A cast shadow darkens the backing; it is not part of the card surface.
    surface=(chroma>color_threshold) | (delta[:,:,0]>max(14,color_threshold*2))
    mask=surface.astype(np.uint8)*255
    mask=cv2.medianBlur(mask,5)
    mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8))
    contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    candidates=[]
    for contour in contours:
        area=cv2.contourArea(contour)
        if area<width*height*.015: continue
        x,y,bw,bh=cv2.boundingRect(contour)
        if x<=1 or y<=1 or x+bw>=width-1 or y+bh>=height-1: continue
        cx,cy,w,h,angle=normalize(cv2.minAreaRect(contour))
        if min(w,h)<35 or abs(angle)>15 or area/(w*h)<.88: continue
        # Surface coverage, rather than edge strength, selects the full mount
        # instead of a printed rectangle inside the photograph.
        candidates.append((area,(cx,cy,w,h,angle),contour))
    if not candidates: return None
    _,rect,contour=max(candidates,key=lambda item:item[0])
    cx,cy,w,h,angle=rect
    # Robustly fit long straight side segments, excluding rounded/worn corners.
    points=contour.reshape(-1,2).astype(np.float32)
    rad=np.deg2rad(angle)
    u=np.array([np.cos(rad),np.sin(rad)])
    v=np.array([-np.sin(rad),np.cos(rad)])
    local=np.column_stack(((points-[cx,cy])@u,(points-[cx,cy])@v))
    angles=[]
    for axis,extent,other in [(0,w,h),(1,h,w)]:
        for sign in (-1,1):
            selected=points[(sign*local[:,axis]>extent*.38)&(np.abs(local[:,1-axis])<other*.36)]
            if len(selected)<8: continue
            vx,vy,_,_=cv2.fitLine(selected,cv2.DIST_HUBER,0,.01,.01).ravel()
            fitted=float(np.rad2deg(np.arctan2(vy,vx)))
            while fitted>45: fitted-=90
            while fitted<-45: fitted+=90
            if abs(fitted-angle)<3: angles.append(fitted)
    if len(angles)>=2: angle=float(np.median(angles))
    rad=np.deg2rad(angle)
    u=np.array([np.cos(rad),np.sin(rad)])
    v=np.array([-np.sin(rad),np.cos(rad)])
    pu,pv=points@u,points@v
    # Include the complete detected surface, with a one-pixel sampling allowance.
    lo_u,hi_u=float(pu.min())-1,float(pu.max())+1
    lo_v,hi_v=float(pv.min())-1,float(pv.max())+1
    center=u*(lo_u+hi_u)/2+v*(lo_v+hi_v)/2
    return float(center[0]),float(center[1]),hi_u-lo_u,hi_v-lo_v,angle
