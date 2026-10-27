"""Repeatable CPU-only renderer timing. Not a Lightroom comparison."""
import time
import platform
import numpy as np
from engine import render, DEFAULTS

def main():
    print('Elsewhere render benchmark |',platform.platform())
    rng=np.random.default_rng(21)
    for h,w in ((512,512),(1080,1440),(2200,3300)):
        rgb=rng.integers(0,65536,(h,w,3),dtype=np.uint16)
        for name,grade in [('neutral',DEFAULTS),('liminal',DEFAULTS|dict(bloom=25,clarity=12,hsl_green_sat=20,fluorescent=20))]:
            start=time.perf_counter()
            image=render(rgb,grade,source_linear=False,out_bits=16,fast=True)
            secs=time.perf_counter()-start
            print(f'{w}x{h}  {name}: {secs:.3f}s; output={image.dtype}')
if __name__=='__main__':main()
