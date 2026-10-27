"""Safe schema and value validation for user-created development recipes."""
import math
from engine import DEFAULTS, DEFAULT_GEOMETRY, GROUPS, BANDS

LIMITS = {key:(float(lo),float(hi)) for category in GROUPS.values() for key, label, lo, hi, step in category}
for band in BANDS:
    for suffix in ('hue','sat','lum'):
        LIMITS[f'hsl_{band}_{suffix}']=(-100,100)
for position in (0,25,50,75,100):
    LIMITS[f'curve_{position}']=(0,100)
for area in ('shadow','mid','highlight'):
    LIMITS[f'{area}_hue']=(0,360)
    LIMITS[f'{area}_strength']=(0,100)
GEOMETRY_LIMITS = {'move_x':(-50,50),'move_y':(-50,50),
                   'zoom':(50,200),'rotation':(-180,180)}
RAW_CHOICES={'white_balance':{'camera','auto','daylight'},
             'highlight_mode':{'blend','clip','reconstruct'}}

def _numeric_map(proposed, defaults, limits):
    if not isinstance(proposed,dict):
        raise ValueError('The recipe must contain an object of numeric adjustments')
    result=defaults.copy()
    for key,value in proposed.items():
        if key not in defaults:
            continue  # old/future recipes can contain other fields
        try:
            num=float(value)
        except (ValueError,TypeError,OverflowError):
            raise ValueError(f'Invalid value for {key}') from None
        lo,hi=limits[key]
        if not math.isfinite(num) or not lo<=num<=hi:
            raise ValueError(f'{key} must be between {lo:g} and {hi:g}')
        result[key]=num
    return result

def validated_recipe(payload):
    if not isinstance(payload,dict):
        raise ValueError('Recipe root must be an object')
    settings=_numeric_map(payload.get('settings',{}),DEFAULTS,LIMITS)
    geometry=_numeric_map(payload.get('geometry',{}),DEFAULT_GEOMETRY,GEOMETRY_LIMITS)
    raw=dict(white_balance='camera',highlight_mode='blend')
    proposed=payload.get('raw_options',{})
    if not isinstance(proposed,dict):
        raise ValueError('Invalid RAW options')
    for key,choices in RAW_CHOICES.items():
        if key in proposed:
            if proposed[key] not in choices:
                raise ValueError(f'Unsupported {key} setting')
            raw[key]=proposed[key]
    return settings,geometry,raw
