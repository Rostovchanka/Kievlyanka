from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import pytest
from engine import render,DEFAULTS,DEFAULT_GEOMETRY,geometry_transform,to_srgb
from io_formats import open_image,save_image


def test_neutral_8bit_raster_not_unexpectedly_modified():
    rng=np.random.default_rng(2)
    im=rng.integers(0,256,(24,37,3),dtype=np.uint8)
    o=render(im,source_linear=False,out_bits=8)
    assert np.max(np.abs(o.astype(int)-im.astype(int)))<=1


def test_16bit_raster_precision_not_truncated_to_8bit():
    ramp=(np.arange(2048,dtype=np.uint16)*31).reshape(32,64)
    src=np.stack([ramp,ramp,ramp],axis=2)
    out=render(src,source_linear=False,out_bits=16)
    assert out.dtype==np.uint16
    assert len(np.unique(out[:,:,0]))>1000
    assert np.max(np.abs(out[:,:,0].astype(int)-ramp.astype(int)))<8


def test_16bit_linear_raw_input_retains_high_resolution_tonal_values():
    ramp=np.arange(2048,dtype=np.uint16).reshape(32,64)*25
    src=np.stack([ramp,ramp,ramp],axis=2)
    out=render(src,source_linear=True,out_bits=16)
    assert out.dtype==np.uint16
    assert len(np.unique(out[:,:,1]))>1500


def test_8bit_jpg_source_is_not_magically_restored():
    src=np.arange(256,dtype=np.uint8).reshape(16,16)
    src=np.stack([src,src,src],axis=2)
    out=render(src,source_linear=False,out_bits=16)
    assert len(np.unique(out[:,:,0]))<=256


def test_jpg_png_tiff_receive_same_adjustments():
    rng=np.random.default_rng(103)
    # Construct an exactly representable 8-bit raster as 16-bit RGB.
    src8=rng.integers(0,256,(32,43,3),dtype=np.uint8)
    src16=src8.astype(np.uint16)*257
    p=DEFAULTS|dict(exposure=.7,vibrance=23,contrast=10,fluorescent=20,
                    hsl_green_sat=-45,bloom=10)
    a=render(src8,p,source_linear=False,out_bits=16)
    b=render(src16,p,source_linear=False,out_bits=16)
    assert np.max(np.abs(a.astype(int)-b.astype(int)))<=2


def test_hsl_curves_color_grading_and_atmosphere_change_output():
    yy,xx=np.mgrid[:45,:55]
    arr=np.stack([np.uint8(xx*4),np.uint8(yy*5),np.uint8((xx+yy)*2)],axis=-1)
    base=render(arr,out_bits=8)
    settings=DEFAULTS|dict(curve_25=14,curve_50=63,curve_75=85,
                           hsl_blue_hue=42,hsl_green_sat=-33,
                           shadow_strength=23,bloom=30,ground_fog=30)
    result=render(arr,settings,out_bits=8)
    assert np.mean(abs(result.astype(float)-base.astype(float)))>3


def test_geometry_moves_and_keeps_canvas_dimensions():
    a=np.zeros((60,100,3),dtype=np.float32)
    a[25:35,45:55,:]=1
    b=geometry_transform(a,dict(move_x=10,move_y=0,zoom=100,rotation=0))
    assert b.shape==a.shape
    assert b[30,60,0]>.9 and b[30,50,0]<.1


def test_export_16bit_png_tiff_and_8bit_jpeg(tmp_path):
    yy,xx=np.mgrid[:55,:65]
    a=np.stack([xx*100,yy*120,xx*51+yy*50],axis=-1).astype(np.uint16)
    png=tmp_path/'photo.png';tif=tmp_path/'photo.tif';jpg=tmp_path/'photo.jpg'
    save_image(png,a);save_image(tif,a)
    for path in (png,tif):
        src,meta,linear=open_image(path)
        assert src.dtype==np.uint16
        assert np.array_equal(a,src)
        assert not linear
    save_image(jpg,np.uint8(a//257))
    src,meta,linear=open_image(jpg)
    assert src.dtype==np.uint8 and src.shape==a.shape and not linear


def test_invalid_8bit_tiff_export_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        save_image(tmp_path/'a.tif',np.zeros((10,10,3),dtype=np.uint8))


def test_png_export_is_tagged_srgb(tmp_path):
    from PIL import Image
    a=np.full((10,12,3),40000,dtype=np.uint16)
    p=tmp_path/'tagged.png';save_image(p,a)
    with Image.open(p) as im:
        assert im.info.get('srgb')==0


def test_deterministic_liminal_effect_reproducible():
    rng=np.random.default_rng(99)
    a=rng.integers(0,65536,(23,29,3),dtype=np.uint16)
    p=DEFAULTS|dict(grain=40,fluorescent=31,ground_fog=44,halation=13)
    first=render(a,p,out_bits=16)
    second=render(a,p,out_bits=16)
    assert np.array_equal(first,second)


def test_16bit_tiff_contains_icc_profile(tmp_path):
    import tifffile
    a=np.full((9,13,3),23456,dtype=np.uint16)
    p=tmp_path/'tagged.tif';save_image(p,a)
    with tifffile.TiffFile(p) as t:
        assert t.pages[0].tags.get(34675) is not None
        assert t.pages[0].bitspersample==16
