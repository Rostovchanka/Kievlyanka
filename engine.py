"""Elsewhere photo engine. Photo-based processing only; no generated scene content.

RAW: 16-bit *linear sRGB* from LibRaw -> float32 linear corrections -> display-referred
sRGB creative adjustments -> integer PNG/TIFF/JPEG export.
Raster: JPEG/PNG/TIFF samples are display-referred sRGB and inverse-transferred
before shared photo adjustments. An 8-bit JPEG does not acquire 16-bit source detail.
"""
from __future__ import annotations
import math
import numpy as np
from scipy.ndimage import gaussian_filter, affine_transform
from scipy.interpolate import PchipInterpolator

RAW_EXTENSIONS = {'.cr3','.cr2','.dng','.nef','.arw','.raf','.orf','.rw2','.pef','.srw'}
DEFAULT_GEOMETRY = dict(move_x=0.0,move_y=0.0,zoom=100.0,rotation=0.0)
BANDS = ('red','orange','yellow','green','cyan','blue','purple','magenta')
BAND_CENTERS = np.array([0,30,60,120,180,240,280,320],dtype=np.float32)

DEFAULTS = dict(
    exposure=0., contrast=0., highlights=0., shadows=0., whites=0., blacks=0.,
    temperature=0., tint=0., saturation=0., vibrance=0.,
    dehaze=0., clarity=0., sharpen=0., denoise=0.,
    matte=0., haze=0., ground_fog=0., bloom=0., halation=0., vignette=0.,
    fluorescent=0., light_falloff=0., grain=0., chromatic=0.,
    shadow_hue=220.,shadow_strength=0.,mid_hue=60.,mid_strength=0.,
    highlight_hue=42.,highlight_strength=0.,
    curve_0=0.,curve_25=25.,curve_50=50.,curve_75=75.,curve_100=100.,
)
for band in BANDS:
    for typ in ('hue','sat','lum'):
        DEFAULTS[f'hsl_{band}_{typ}']=0.

GROUPS = {
 'Develop': [('exposure','Exposure · EV',-4,4,.05),('contrast','Contrast',-80,80,1),('highlights','Highlights',-100,100,1),('shadows','Shadows',-100,100,1),('whites','White point',-100,100,1),('blacks','Black point',-100,100,1),('clarity','Clarity',-100,100,1),('dehaze','Dehaze',-100,100,1),('sharpen','Sharpen',0,100,1),('denoise','Noise reduction',0,100,1)],
 'Color': [('temperature','Warmth',-100,100,1),('tint','Green ↔ magenta',-100,100,1),('saturation','Saturation',-100,100,1),('vibrance','Vibrance',-100,100,1)],
 'Atmosphere': [('matte','Black fade',0,100,1),('haze','Uniform haze',0,100,1),('ground_fog','Ground fog',0,100,1),('bloom','Highlight bloom',0,100,1),('halation','Red halation',0,100,1),('vignette','Vignette',0,100,1),('fluorescent','Fluorescent imbalance',0,100,1),('light_falloff','Ceiling illumination falloff',0,100,1)],
 'Optics': [('grain','Sensor/film grain',0,100,1),('chromatic','Chromatic edge offset',0,20,1)],
}
PRESETS = {
    'Neutral · Reference': {},
    'Level 0 · Yellow Lobby':dict(temperature=25,tint=-12,saturation=-20,contrast=-8,matte=14,fluorescent=45,light_falloff=25,grain=5,bloom=20),
    'Level 1 · Concrete':dict(temperature=-21,saturation=-38,contrast=17,shadows=-12,dehaze=8,vignette=28,grain=12),
    'Level 2 · Utilities':dict(temperature=-9,saturation=-25,contrast=20,blacks=-12,vignette=33,grain=9),
    'Level 3 · Electrical Station':dict(temperature=-15,tint=-8,saturation=-34,contrast=18,bloom=30,fluorescent=22,grain=8),
    'Level 4 · Abandoned Office':dict(saturation=-40,temperature=-9,contrast=-12,matte=20,haze=18,light_falloff=20),
    'Level 5 · Hotel':dict(temperature=25,saturation=-22,contrast=14,blacks=-12,halation=25,vignette=28),
    'Level 6 · Lights Out':dict(exposure=-1.4,contrast=26,saturation=-68,blacks=-28,vignette=68,grain=20),
    'Level 7 · Underwater':dict(temperature=-35,saturation=-30,ground_fog=30,haze=20,vignette=15),
    'Level 8 · Cavern':dict(exposure=-.6,contrast=22,saturation=-50,blacks=-26,vignette=60,grain=18),
    'Level 9 · Suburbs':dict(temperature=-12,saturation=-30,matte=20,haze=15,grain=8),
    'Level 10 · The Fields':dict(temperature=17,saturation=-18,contrast=-12,matte=15,haze=16),
    'Moonlit Concrete':dict(temperature=-33,tint=12,saturation=-24,shadows=-15,vignette=29,bloom=18,grain=10),
    'Sodium Afterimage':dict(temperature=44,saturation=-38,contrast=12,halation=28,grain=17,vignette=18),
    'Forgotten Mall':dict(temperature=-8,saturation=-55,matte=23,haze=23,bloom=28,light_falloff=25),
    'Indigo Vacancy':dict(temperature=-30,tint=30,saturation=-32,contrast=10,shadows=-12,bloom=12,vignette=25),
}

def normalized(rgb:np.ndarray)->np.ndarray:
    if rgb.ndim !=3 or rgb.shape[2]!=3 or rgb.dtype not in (np.dtype('uint8'),np.dtype('uint16')):
        raise ValueError('Expected RGB uint8 or uint16 image')
    return rgb.astype(np.float32)*(1.0/(65535.0 if rgb.dtype==np.uint16 else 255.0))

def to_linear(srgb):
    return np.where(srgb<=0.04045,srgb/12.92,((np.maximum(srgb,0)+0.055)/1.055)**2.4)

def to_srgb(linear):
    linear=np.maximum(linear,0)
    return np.where(linear<=.0031308,12.92*linear,1.055*np.power(linear,1/2.4)-.055)

def blur(a,r):
    if r<=.01: return a
    return gaussian_filter(a,sigma=(r,r,0),mode='reflect')

def rgb_to_hsv(a):
    import cv2
    hsv=cv2.cvtColor(np.ascontiguousarray(np.clip(a,0,1),dtype=np.float32),cv2.COLOR_RGB2HSV)
    return hsv

def hsv_to_rgb(a):
    import cv2
    return cv2.cvtColor(np.ascontiguousarray(a,dtype=np.float32),cv2.COLOR_HSV2RGB)

def curves_lut(p):
    anchors=[p[f'curve_{n}']/100 for n in (0,25,50,75,100)]
    # User points are allowed to bend curve in any direction; interpolate smoothly.
    xp=np.array([0,.25,.5,.75,1.],dtype=np.float32)
    lut=np.clip(PchipInterpolator(xp,anchors)(np.linspace(0,1,4097)),0,1).astype(np.float32)
    return lut

def apply_tone_curve(a,p):
    if all(abs(p[f'curve_{n}']-n)<1e-6 for n in (0,25,50,75,100)):
        return a
    # Operate on image luminance, not separately on RGB channels. This matches
    # the UI label and avoids unintended hue shifts from luminance-only curves.
    luminance=np.clip(.2126*a[...,0]+.7152*a[...,1]+.0722*a[...,2],0,1)
    lut=curves_lut(p)
    idx=luminance*4096.0
    lo=np.floor(idx).astype(np.int16); hi=np.minimum(lo+1,4096)
    mapped=lut[lo]*(1-(idx-lo))+lut[hi]*(idx-lo)
    ratio=(mapped / np.maximum(luminance,1e-5))[...,None]
    return np.where(luminance[...,None]>1e-5, a*ratio,
                    mapped[...,None]).astype(np.float32)

def geometry_transform(a,g):
    h,w=a.shape[:2]
    dx=float(g.get('move_x',0))/100*w; dy=float(g.get('move_y',0))/100*h
    scale=max(.05,float(g.get('zoom',100))/100)
    th=math.radians(float(g.get('rotation',0)))
    if abs(dx)+abs(dy)+abs(scale-1)+abs(th)<1e-8: return a
    c,s=math.cos(th),math.sin(th)
    mat=np.array([[c,s],[-s,c]],dtype=np.float64)/scale
    center=np.array([(h-1)/2,(w-1)/2]); offset=center-mat@(center+np.array([dy,dx]))
    return np.stack([affine_transform(a[:,:,k],mat,offset=offset,output_shape=(h,w),order=1,mode='constant',cval=0,prefilter=False) for k in range(3)],axis=-1)

def render(rgb,settings=None,geometry=None,*,source_linear=False,out_bits=8,fast=False):
    """Return accurate 8/16-bit RGB. Settings work identically for RAW/JPG/PNG.

    RAW sensor-only controls are performed during decode; all post-decode settings
    are the same for every supported image format. No scene-generation tools.
    """
    p=DEFAULTS|dict(settings or {})
    if any(not np.isfinite(value) for value in p.values()):
        raise ValueError('Invalid adjustment: non-finite number')
    a=normalized(rgb)
    # Exposure is applied in linear light, including inverse-transferred JPEG/PNG.
    if not source_linear: a=to_linear(a)
    a*=np.float32(2.**p['exposure'])
    # RAW scene values require a gentle output shoulder. JPEG/PNG/TIFF
    # are already display-referred: never re-tone-map a neutral raster image.
    if source_linear:
        a=a/(1+.25*np.maximum(a-.7,0))
    a=to_srgb(a)
    # Warmth / tint are creative controls common to RAW and raster sources.
    t=p['temperature']*.0022; ti=p['tint']*.0017
    a[...,0]*=1+t+.28*ti; a[...,1]*=1-.35*ti; a[...,2]*=1-t+.28*ti
    a=np.clip(a,0,4)
    lum=.2126*a[...,0]+.7152*a[...,1]+.0722*a[...,2]
    a+=p['shadows']/100*.36*np.power(np.clip(1-lum,0,1),2)[...,None]
    a+=p['highlights']/100*.36*np.power(np.clip(lum,0,1),2)[...,None]
    a+=(p['blacks']/100*.12)*np.power(np.clip(1-lum,0,1),3)[...,None]
    a+=(p['whites']/100*.12)*np.power(np.clip(lum,0,1),3)[...,None]
    a=(a-.45)*(1+p['contrast']/115)+.45
    a=np.clip(a,0,1)
    a=apply_tone_curve(a,p)
    hsv=rgb_to_hsv(a)
    if p['saturation']:
        hsv[...,1]*=max(0,1+p['saturation']/100)
    if p['vibrance']:
        hsv[...,1]*=np.maximum(0,1+p['vibrance']/100*(1-hsv[...,1]))
    if any(p[f'hsl_{band}_{t}'] for band in BANDS for t in ('hue','sat','lum')):
        hue=hsv[...,0]
        dh=np.zeros_like(hue); ds=np.zeros_like(hue); dv=np.zeros_like(hue)
        for band,center in zip(BANDS,BAND_CENTERS):
            difference=np.abs((hue-center+180)%360-180)
            weight=np.clip(1-difference/50,0,1)**2
            dh+=weight*p[f'hsl_{band}_hue']*.3
            ds+=weight*p[f'hsl_{band}_sat']/100
            dv+=weight*p[f'hsl_{band}_lum']/100*.30
        hsv[...,0]=(hsv[...,0]+dh)%360
        hsv[...,1]=np.clip(hsv[...,1]*(1+ds),0,1)
        hsv[...,2]=np.clip(hsv[...,2]+dv,0,1)
    # Color channel adjustments must not send invalid saturation/value to cv2.
    hsv[...,1]=np.clip(hsv[...,1],0,1)
    hsv[...,2]=np.clip(hsv[...,2],0,1)
    a=hsv_to_rgb(hsv)
    if any(p[k] for k in ('shadow_strength','mid_strength','highlight_strength')):
        l=.2126*a[...,0]+.7152*a[...,1]+.0722*a[...,2]
        for area,mask in [('shadow',np.clip((.55-l)/.55,0,1)),('mid',1-np.clip(abs(l-.5)/.5,0,1)),('highlight',np.clip((l-.45)/.55,0,1))]:
            strength=p[area+'_strength']/100
            if not strength:continue
            hue=math.radians(p[area+'_hue'])
            tint=np.array([.5+.5*math.cos(hue),.5+.5*math.cos(hue-2*math.pi/3),.5+.5*math.cos(hue+2*math.pi/3)],dtype=np.float32)
            a=np.clip(a+(tint-.5)*mask[...,None]*strength*.28,0,1)
    # Color-neutral local contrast / denoising; these are format-independent.
    if p['denoise'] and not fast:
        import cv2
        # Bilateral filtering preserves architectural boundaries.
        d=5 if p['denoise']<60 else 7
        filt=cv2.bilateralFilter(np.ascontiguousarray(a,dtype=np.float32),d, max(.005,p['denoise']*.0018),max(1,p['denoise']*.022))
        q=p['denoise']/100
        a=a*(1-q)+filt*q
    if p['clarity']:
        b=blur(a,max(1,min(a.shape[:2])*.006))
        a=np.clip(a+(a-b)*p['clarity']/115,0,1)
    if p['dehaze']:
        # Global haze approximation, not a physical atmospheric inverse model.
        amt=p['dehaze']/100
        a=np.clip((a-.48)*(1+amt*.55)+.48-amt*.035,0,1)
    if p['sharpen']:
        b=blur(a,1.1)
        a=np.clip(a+(a-b)*p['sharpen']/55,0,1)
    h,w=a.shape[:2]
    yy,xx=np.ogrid[-1:1:complex(h),-1:1:complex(w)]
    vig=p['vignette']/100
    if vig:
        r=np.sqrt((xx*.95)**2+(yy*1.05)**2)
        a*=1-np.clip((r-.15)/1,0,1)[...,None]**1.7*vig*.85
    if p['light_falloff']:
        q=p['light_falloff']/100
        luminance=np.clip((yy+1)/2,0,1)[...,None]
        a*=1-q*.2*luminance
    if p['fluorescent']:
        # Luminance/chromatic unevenness across the image, not inserted fixtures.
        q=p['fluorescent']/100
        uneven=np.cos((xx+1)*math.pi*1.6)*.5 + np.cos((yy+1)*math.pi*.8)*.5
        a[...,1]=np.clip(a[...,1]*(1+q*.065*uneven),0,1)
        a[...,0]=np.clip(a[...,0]*(1-q*.025*uneven),0,1)
    if p['matte']:
        q=p['matte']/100; a=a*(1-q*.3)+q*.065
    if p['haze']:
        q=p['haze']/100; a=a*(1-q*.3)+q*.20
    if p['ground_fog']:
        q=p['ground_fog']/100
        mask=np.clip((yy+.8)/1.65,0,1)[...,None]
        a=a*(1-mask*q*.5)+mask*q*.25
    if p['bloom'] or p['halation']:
        l=.2126*a[...,0]+.7152*a[...,1]+.0722*a[...,2]
        hot=np.clip((l-.48)*2.6,0,1)[...,None]
        b=blur(a,max(1,min(h,w)*.008))
        if p['bloom']:a=np.clip(a+b*hot*(p['bloom']/100)*.43,0,1)
        if p['halation']:
            a[...,0]=np.clip(a[...,0]+b[...,0]*hot[...,0]*(p['halation']/100)*.38,0,1)
    if p['chromatic'] and w>1:
        # When processing tiny images, shift must be smaller than their width.
        shift=min(w-1,max(1,int(p['chromatic']*w/2500)))
        red=a[...,0].copy(); blue=a[...,2].copy()
        a[:,shift:,0]=red[:,:-shift];a[:,:shift,0]=red[:,0:1]
        a[:,:-shift,2]=blue[:,shift:];a[:,-shift:,2]=blue[:,-1:]
    if p['grain']:
        noise=np.random.default_rng(8141).normal(0,p['grain']*.00075,(h,w,1)).astype(np.float32)
        a=np.clip(a+noise,0,1)
    a=np.clip(a,0,1)
    if geometry is not None:a=geometry_transform(a,geometry)
    if out_bits==8:return np.uint8(a*255+.5)
    if out_bits==16:return np.uint16(a*65535+.5)
    raise ValueError('out_bits must be 8 or 16')
