"""Regression tests added after full project audit."""
import sys
from pathlib import Path
import numpy as np
import pytest
import cv2
import tifffile
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from engine import render, DEFAULTS, DEFAULT_GEOMETRY, apply_tone_curve
from recipe import validated_recipe
from io_formats import decode_raster, save_image, _flatten_rgba


def test_non_finite_recipe_fails_before_ui_is_changed():
    for bad in [float('nan'),float('inf'),float('-inf'),500, -500]:
        with pytest.raises(ValueError):
            validated_recipe({'settings':{'contrast':bad}})
    with pytest.raises(ValueError):
        validated_recipe({'geometry':{'zoom':0}})
    with pytest.raises(ValueError):
        validated_recipe({'raw_options':{'white_balance':'unknown'}})


def test_legacy_sparse_recipe_is_safe():
    settings,geom,raw=validated_recipe({'settings':{'exposure':1},'geometry':{'move_x':10}})
    assert settings['exposure']==1 and geom['zoom']==100
    assert raw=={'white_balance':'camera','highlight_mode':'blend'}


def test_curve_changes_luminance_without_color_shift():
    px=np.zeros((8,9,3),dtype=np.float32)
    px[:]=(.1,.35,.65)
    params=DEFAULTS|{'curve_25':38.,'curve_50':60.,'curve_75':86.}
    out=apply_tone_curve(px,params)
    assert out.shape==px.shape
    assert np.all(np.isfinite(out))
    ratios=out[0,0]/px[0,0]
    assert np.max(ratios)-np.min(ratios)<1e-5


def test_zero_pixel_curve_has_finite_output():
    px=np.zeros((1,1,3),dtype=np.float32)
    out=apply_tone_curve(px,DEFAULTS|{'curve_0':25})
    assert np.all(np.isfinite(out)) and np.all(out>0)


@pytest.mark.parametrize('shape', [(1,1),(1,2),(2,1),(2,2),(4,5),(55,61)])
def test_tiny_images_do_not_crash_with_chromatic_setting(shape):
    a=np.full((*shape,3),25000,dtype=np.uint16)
    params=DEFAULTS|{'chromatic':20, 'saturation':100, 'vibrance':100,
                     'hsl_blue_sat':100,'shadow_strength':100,'curve_75':100}
    out=render(a,params,out_bits=16)
    assert out.shape==a.shape and out.dtype==np.uint16


def test_png_alpha_is_composited_not_discarded(tmp_path):
    rgba=np.zeros((8,9,4),dtype=np.uint8)
    rgba[...,0]=100
    rgba[...,1]=50
    rgba[...,2]=20
    rgba[...,3]=0
    rgba[0,0,:]=[0,0,0,255]
    rgba[1,1,:]=[100,50,20,128]
    # input channels are RGBA; encoder uses BGRA.
    p=tmp_path/'transparency.png'
    assert cv2.imwrite(str(p),cv2.cvtColor(rgba,cv2.COLOR_RGBA2BGRA))
    rgb,meta,lin=decode_raster(p)
    assert np.array_equal(rgb[3,3], [255,255,255])
    assert np.array_equal(rgb[0,0],[0,0,0])
    assert np.allclose(rgb[1,1],[177,152,137],atol=1)
    assert meta['alpha']=='Composited over white'


def test_16bit_rgba_tiff_alpha_is_composited_without_8bit_loss(tmp_path):
    rgba=np.zeros((5,6,4),dtype=np.uint16)
    rgba[...,0]=32000;rgba[...,3]=32768
    p=tmp_path/'transparency.tif'
    tifffile.imwrite(str(p),rgba,photometric='rgb',extrasamples=['UNASSALPHA'])
    rgb,meta,lin=decode_raster(p)
    assert rgb.dtype==np.uint16
    assert 48000<rgb[0,0,0]<50000
    assert rgb[0,0,1]>32000
    assert meta['alpha']=='Composited over white'


def test_png_export_reimport_with_uint16_steps(tmp_path):
    vals=np.arange(1024,dtype=np.uint16)*63
    a=np.broadcast_to(vals.reshape(1,-1,1),(2,1024,3)).copy()
    p=tmp_path/'steps.png';save_image(p,a)
    reloaded,meta,linear=decode_raster(p)
    assert np.array_equal(a,reloaded)


def test_nonfinite_engine_value_is_rejected():
    with pytest.raises(ValueError):
        render(np.zeros((4,4,3),dtype=np.uint8),{'exposure':float('nan')})


def test_invalid_output_shape_rejected(tmp_path):
    with pytest.raises(ValueError):
        save_image(tmp_path/'invalid.tif',np.zeros((3,4,4),dtype=np.uint16))


def test_associated_alpha_tiff_is_composited_once(tmp_path):
    alpha=np.uint16(32768)
    rgba=np.zeros((8,8,4),dtype=np.uint16)
    rgba[...,0]=np.uint16(20000)  # Premultiplied sample
    rgba[...,3]=alpha
    p=tmp_path/'associated.tif'
    tifffile.imwrite(str(p),rgba,photometric='rgb',extrasamples=['ASSOCALPHA'])
    rgb,meta,linear=decode_raster(p)
    assert 52000<rgb[0,0,0]<54000
    assert 32000<rgb[0,0,1]<34000


def test_narrow_planar_tiff_channels_are_read_correctly(tmp_path):
    a=np.zeros((3,7,3),dtype=np.uint16)
    a[0,...]=1000;a[1,...]=30000;a[2,...]=60000
    p=tmp_path/'planar_width3.tif'
    tifffile.imwrite(str(p),a,photometric='rgb',planarconfig='separate')
    rgb,meta,linear=decode_raster(p)
    assert rgb.shape==(7,3,3)
    assert np.array_equal(rgb[0,0],[1000,30000,60000])


def test_unicode_png_filename_and_precision(tmp_path):
    image=np.full((4,7,3),51513,dtype=np.uint16)
    p=tmp_path/'é空間_список.png'
    save_image(p,image)
    reopened,meta,linear=decode_raster(p)
    assert np.array_equal(reopened,image)


def test_camera_jpeg_exif_orientation_is_honored(tmp_path):
    p=tmp_path/'orientation.jpg'
    im=Image.new('RGB',(30,12),'green')
    exif=Image.Exif();exif[274]=6  # 90° clockwise
    im.save(p,exif=exif)
    arr,meta,linear=decode_raster(p)
    assert arr.shape==(30,12,3)


def test_seeded_randomized_valid_photo_adjustments():
    from recipe import LIMITS
    rng=np.random.default_rng(2419)
    for j in range(48):
        h,w=[(1,1),(1,3),(3,1),(8,5),(17,16),(24,13)][j%6]
        dtype=np.uint16 if j%2 else np.uint8
        a=rng.integers(0,65536 if dtype==np.uint16 else 256,(h,w,3),dtype=dtype)
        settings=DEFAULTS.copy()
        for key in rng.choice(list(settings),size=10,replace=False):
            lo,hi=LIMITS[key]
            settings[key]=float(rng.uniform(lo,hi))
        g={'move_x':float(rng.uniform(-50,50)),
           'move_y':float(rng.uniform(-50,50)),
           'zoom':float(rng.uniform(50,200)),
           'rotation':float(rng.uniform(-180,180))}
        out=render(a,settings,g,out_bits=16,source_linear=bool(j%3==0))
        assert out.shape==a.shape and out.dtype==np.uint16
