"""Regression coverage for EOS R5 RAW decode metadata failures.

Fake RAW objects simulate versions of rawpy with and without optional metadata.
"""
import sys
from types import SimpleNamespace
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import io_formats

class FakeRaw:
    def __init__(self, has_metadata=True):
        self.sizes = SimpleNamespace(width=8192, height=5464)
        if has_metadata:
            self.other = SimpleNamespace(iso_speed=800.0, shutter_speed=0.008, aperture=2.8)
            self.lens = SimpleNamespace(model='RF 24-105mm', make='Canon')
        self.postprocessing_options = None
    def __enter__(self): return self
    def __exit__(self, *exc): return False
    def postprocess(self, **kw):
        self.postprocessing_options = kw
        return np.full((10,14,3), 32768, dtype=np.uint16)

def fake_rawpy(monkeypatch, raw):
    module = SimpleNamespace(
        imread=lambda path: raw,
        HighlightMode=SimpleNamespace(Clip=0, Blend=1, ReconstructDefault=2),
        ColorSpace=SimpleNamespace(sRGB=1),
        FBDDNoiseReductionMode=SimpleNamespace(Light=1),
    )
    monkeypatch.setitem(sys.modules, 'rawpy', module)

def test_eos_r5_raw_opens_without_undocumented_camera_properties(monkeypatch):
    raw=FakeRaw(has_metadata=True)
    fake_rawpy(monkeypatch, raw)
    arr, meta, linear = io_formats.decode_raw('EOS_R5.CR3')
    assert linear is True and arr.dtype == np.uint16
    assert meta['resolution'] == '8192 × 5464'
    assert meta['iso'] == '800'
    assert meta['aperture'] == '2.8'
    assert meta['lens'] == 'RF 24-105mm'
    assert meta['camera'] == 'RAW photograph'
    assert raw.postprocessing_options['output_bps'] == 16

def test_raw_opens_when_exif_and_lens_metadata_are_not_exposed(monkeypatch):
    raw=FakeRaw(has_metadata=False)
    fake_rawpy(monkeypatch, raw)
    arr, meta, linear = io_formats.decode_raw('EOS_R5.CR3')
    assert arr.shape == (10,14,3)
    assert meta['iso'] == '—'
    assert meta['lens'] == '—'
    assert meta['shutter'] == '—'
    assert linear is True

def test_bad_optional_raw_metadata_does_not_crash(monkeypatch):
    raw=FakeRaw(has_metadata=True)
    raw.other=SimpleNamespace(iso_speed=0, shutter_speed=None, aperture='not a number')
    fake_rawpy(monkeypatch, raw)
    _,meta,_=io_formats.decode_raw('EOS_R5.CR3')
    assert meta['iso']=='—' and meta['shutter']=='—' and meta['aperture']=='—'
