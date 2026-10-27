"""Format-independent image IO. RAW-specific processing is isolated here."""
from __future__ import annotations
from pathlib import Path
import numpy as np
import cv2
import tifffile
from PIL import Image, ImageCms, ImageOps
import io
import zlib
import struct
import os
import tempfile

from engine import RAW_EXTENSIONS

RASTER_EXTENSIONS = {'.jpeg','.jpg','.png','.tif','.tiff','.bmp'}


def _flatten_rgba(rgba, *, background=65535, associated=False):
    """Composite transparent photos to white without discarding hidden alpha.

    Retain uint16 precision when the source has 16-bit alpha.
    """
    if rgba.dtype not in (np.uint8, np.uint16):
        raise ValueError('Unsupported alpha image precision')
    max_value=65535 if rgba.dtype==np.uint16 else 255
    target=max_value if background==65535 else background
    alpha=rgba[...,3:4].astype(np.uint32)
    rgb=rgba[...,:3].astype(np.uint32)
    if associated:
        # Associated alpha means RGB has already been multiplied by alpha.
        return np.minimum(max_value,
            rgb + (target*(max_value-alpha)+max_value//2)//max_value).astype(rgba.dtype)
    return ((rgb*alpha + target*(max_value-alpha)+max_value//2)//max_value).astype(rgba.dtype)



def _optional_raw_attribute(obj, name, default=None):
    """Camera metadata must never prevent sensor pixels from being decoded.

    Not every rawpy/LibRaw version exposes the same properties. Some properties
    may also raise when a particular file does not contain that metadata.
    """
    if obj is None:
        return default
    try:
        value = getattr(obj, name, default)
    except Exception:
        return default
    return default if value is None else value


def _capture_text(value, *, digits=None):
    """Format optional EXIF-like numeric metadata without fictional zeros."""
    try:
        number = float(value)
        if not np.isfinite(number) or number <= 0:
            return '—'
        if digits is not None:
            return f'{number:.{digits}f}'
        return f'{number:g}'
    except (TypeError, ValueError, OverflowError):
        return '—'


def _raw_metadata(raw):
    """Read the public rawpy API, falling back gracefully on older builds.

    RawPy does NOT expose camera_make/camera_model. Camera identity is left
    generic rather than guessing the model from the RAW filename or EXIF.
    """
    sizes = raw.sizes
    other = _optional_raw_attribute(raw, 'other')
    lens = _optional_raw_attribute(raw, 'lens')
    lens_model = _optional_raw_attribute(lens, 'model')
    if isinstance(lens_model, bytes):
        lens_model = lens_model.decode('utf-8', errors='replace')
    return {
        'camera': 'RAW photograph',
        'resolution': f'{sizes.width} × {sizes.height}',
        'iso': _capture_text(_optional_raw_attribute(other, 'iso_speed')),
        'shutter': _capture_text(_optional_raw_attribute(other, 'shutter_speed')),
        'aperture': _capture_text(_optional_raw_attribute(other, 'aperture'), digits=1),
        'lens': lens_model.strip() if isinstance(lens_model, str) and lens_model.strip() else '—',
        'bit_depth': '16-bit linear',
        'format': 'RAW',
    }


def decode_raw(path, *, half_size=False, white_balance='camera', highlights='blend'):
    import rawpy
    modes = {'clip': rawpy.HighlightMode.Clip, 'blend': rawpy.HighlightMode.Blend,
             'reconstruct': rawpy.HighlightMode.ReconstructDefault}
    if highlights not in modes:
        raise ValueError('Invalid highlight mode')
    if white_balance not in ('camera','auto','daylight'):
        raise ValueError('Invalid white balance source')
    with rawpy.imread(str(path)) as raw:
        meta = _raw_metadata(raw)
        arr = raw.postprocess(
            use_camera_wb=white_balance=='camera',use_auto_wb=white_balance=='auto',
            no_auto_bright=True,output_color=rawpy.ColorSpace.sRGB,output_bps=16,
            gamma=(1,1),half_size=half_size,
            highlight_mode=modes[highlights],
            fbdd_noise_reduction=rawpy.FBDDNoiseReductionMode.Light,
        )
    return np.ascontiguousarray(arr),meta,True


def decode_raster(path, *, limit=None):
    path=Path(path)
    ext=path.suffix.lower()
    meta={'camera':'Raster photograph','format':ext.lstrip('.').upper(),'iso':'—',
          'shutter':'—','aperture':'—','lens':'—'}
    if ext in ('.tif','.tiff'):
        with tifffile.TiffFile(str(path)) as tf:
            arr=tf.asarray()
            extras=tf.pages[0].extrasamples if len(tf.pages) else ()
            associated=any(int(sample)==1 for sample in extras)
            planar=int(tf.pages[0].planarconfig) if len(tf.pages) else 1
        if planar==2 and arr.ndim == 3 and arr.shape[0] in (3,4):
            # TIFF planarity is in file metadata; don't guess from image width.
            arr=np.moveaxis(arr,0,-1)
        if arr.ndim == 3 and arr.shape[2]==4:
            arr=_flatten_rgba(arr,associated=associated)
            meta['alpha']='Composited over white'
    elif ext=='.png':
        arr=cv2.imdecode(np.fromfile(str(path),dtype=np.uint8),cv2.IMREAD_UNCHANGED)
        if arr is None: raise ValueError('Cannot open PNG image')
        if arr.ndim == 3 and arr.shape[2]==4:
            arr=cv2.cvtColor(arr,cv2.COLOR_BGRA2RGBA)
            arr=_flatten_rgba(arr)
            meta['alpha']='Composited over white'
        elif arr.ndim == 3 and arr.shape[2]==3:
            arr=cv2.cvtColor(arr,cv2.COLOR_BGR2RGB)
    else:
        with Image.open(path) as img:
            # Honor orientation tags from camera-generated JPEGs.
            img=ImageOps.exif_transpose(img)
            # For 8-bit JPEG, apply embedded ICC profile when Pillow supports it.
            if img.info.get('icc_profile'):
                try:
                    src=ImageCms.ImageCmsProfile(io.BytesIO(img.info['icc_profile']))
                    dst=ImageCms.createProfile('sRGB')
                    img=ImageCms.profileToProfile(img.convert('RGB'),src,dst,outputMode='RGB')
                    meta['input_profile']='Converted to sRGB'
                except Exception:
                    img=img.convert('RGB')
                    meta['input_profile']='WARNING: embedded color profile could not be converted; colors may differ'
            arr=np.asarray(img.convert('RGB')).copy()
    if ext in ('.png','.tif','.tiff'):
        # OpenCV/tifffile retain 16-bit pixels, but they do not automatically
        # transform arbitrary embedded ICC profiles into the chosen sRGB workspace.
        try:
            with Image.open(path) as metadata_img:
                if metadata_img.info.get('icc_profile'):
                    meta['input_profile']='WARNING: embedded ICC not converted; treated as sRGB'
        except Exception:
            pass
    if arr.ndim==2: arr=np.repeat(arr[...,None],3,axis=2)
    if arr.ndim!=3 or arr.shape[2]!=3 or arr.dtype not in (np.uint8,np.uint16):
        raise ValueError('Only grayscale or RGB/RGBA 8/16-bit photographs are supported')
    h,w=arr.shape[:2]
    meta['resolution']=f'{w} × {h}'
    meta['bit_depth']='16-bit' if arr.dtype==np.uint16 else '8-bit'
    if limit and max(h,w)>limit:
        factor=limit/max(h,w)
        arr=cv2.resize(arr,(max(1,int(w*factor)),max(1,int(h*factor))),interpolation=cv2.INTER_AREA)
    return np.ascontiguousarray(arr),meta,False


def open_image(path, *, preview=False, options=None):
    options=options or {}
    if Path(path).suffix.lower() in RAW_EXTENSIONS:
        arr,meta,linear=decode_raw(path,half_size=preview,
            white_balance=options.get('white_balance','camera'),
            highlights=options.get('highlight_mode','blend'))
        if preview and max(arr.shape[:2])>1900:
            h,w=arr.shape[:2];ratio=1900/max(h,w)
            arr=cv2.resize(arr,(max(1,int(w*ratio)),max(1,int(h*ratio))),interpolation=cv2.INTER_AREA)
        return arr,meta,linear
    return decode_raster(path,limit=1900 if preview else None)


def save_image(path, arr):
    """Save true RGB 16-bit TIFF/PNG or 8-bit JPEG, according to extension."""
    path=Path(path)
    ext=path.suffix.lower()
    if arr.ndim!=3 or arr.shape[2]!=3 or arr.dtype not in (np.uint8,np.uint16):
        raise ValueError('Expected RGB uint8 or uint16 image for export')
    if ext in ('.tif','.tiff'):
        if arr.dtype!=np.uint16: raise ValueError('TIFF export requires uint16 RGB')
        profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
        tifffile.imwrite(str(path),arr,photometric='rgb',compression='deflate',
                         extratags=[(34675,'B',len(profile),profile,False)])
    elif ext=='.png':
        if arr.dtype!=np.uint16: raise ValueError('PNG export requires uint16 RGB')
        # OpenCV preserves RGB 16-bit precision; converts to BGR for encoder.
        # cv2.imwrite cannot reliably handle non-ASCII paths on all Windows
        # installations. imencode + tofile works with Unicode paths.
        success, data=cv2.imencode('.png',cv2.cvtColor(arr,cv2.COLOR_RGB2BGR),
                                  [cv2.IMWRITE_PNG_COMPRESSION,6])
        if not success:raise IOError('Failed to encode PNG')
        # Avoid copying the entire (potentially huge) encoded image a second time.
        encoded=memoryview(data).cast('B')
        if bytes(encoded[:8])!=b'\x89PNG\r\n\x1a\n':
            raise IOError('PNG signature invalid')
        first_length=struct.unpack('>I',encoded[8:12])[0]
        insert_at=8+12+first_length
        chunk_type=b'sRGB'; payload=b'\x00'
        crc=zlib.crc32(chunk_type+payload)&0xffffffff
        chunk=struct.pack('>I',len(payload))+chunk_type+payload+struct.pack('>I',crc)
        # Single committed write: never leave a partially modified original
        # PNG if the process fails between encoding and metadata injection.
        with tempfile.NamedTemporaryFile(dir=str(path.parent),suffix='.png',delete=False) as temp:
            tempname=temp.name
            temp.write(encoded[:insert_at]);temp.write(chunk);temp.write(encoded[insert_at:])
        try:
            os.replace(tempname,path)
        finally:
            if os.path.exists(tempname):os.unlink(tempname)
    elif ext in ('.jpg','.jpeg'):
        if arr.dtype!=np.uint8:raise ValueError('JPEG export requires uint8 RGB')
        profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
        Image.fromarray(arr).save(path,quality=96,subsampling=0,icc_profile=profile)
    else:raise ValueError('Unsupported output extension')
