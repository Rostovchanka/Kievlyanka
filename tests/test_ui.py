import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
QtWidgets=pytest.importorskip('PySide6.QtWidgets')

from elsewhere_studio import Elsewhere


def test_desktop_inspector_has_photo_tools_and_raw_exceptions(qt_app):
    win=Elsewhere()
    required={'Develop','Color','HSL','Curves','Color Wheels','Atmosphere',
              'Optics','Geometry','Presets','RAW Settings'}
    assert required==set(win.nav)
    assert all(not widget.isEnabled() for widget in win.raw_controls)
    assert win.geometry['zoom']==100
    win.apply_preset('Level 0 · Yellow Lobby')
    assert win.settings['fluorescent']>0
    win.undo()
    assert win.settings['fluorescent']==0
    win.close()


@pytest.fixture
def qt_app():
    app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


def test_keyboard_slider_changes_support_undo(qt_app):
    win=Elsewhere()
    slider, label, div=win.slider_controls['exposure']
    slider.setValue(20)
    assert win.settings['exposure']==1.0
    win.timer.stop()
    win.undo()
    assert win.settings['exposure']==0.0
    win.timer.stop()
    win.close()


def test_overlapping_image_loads_ignore_stale_results(qt_app,tmp_path,monkeypatch):
    from PIL import Image
    import numpy as np
    win=Elsewhere()
    # Queue the IO worker without actually launching threads.
    jobs=[]
    monkeypatch.setattr(win,'start_job',lambda job:jobs.append(job))
    a=tmp_path/'a.png';b=tmp_path/'b.png'
    Image.new('RGB',(12,9),'red').save(a)
    Image.new('RGB',(12,9),'blue').save(b)
    win.open_path(str(a)); old_token=win.load_token
    win.open_path(str(b))
    assert win.load_token!=old_token and not win.export_btn.isEnabled()
    frame=np.full((8,8,3),255,dtype=np.uint8)
    win.loaded(frame,{'camera':'Raster photograph','resolution':'8 × 8','bit_depth':'8-bit','format':'PNG'},False,str(a),old_token)
    assert win.image_data is None
    win.timer.stop()
    win.close()


def test_raw_redevelop_preserves_grade(qt_app,monkeypatch):
    win=Elsewhere()
    win.filepath='sample.cr3'
    win.apply_preset('Level 0 · Yellow Lobby')
    grade=win.settings.copy()
    captured=[]
    monkeypatch.setattr(win,'open_path',lambda path,**kwargs:captured.append((path,kwargs)))
    win.wb_combo.setCurrentText('Auto')
    win.redecode_raw()
    assert win.raw_options['white_balance']=='auto'
    assert captured==[('sample.cr3',{'preserve_edits':True})]
    assert win.settings==grade
    win.timer.stop()
    win.close()


def test_malformed_recipe_does_not_modify_state(qt_app,tmp_path,monkeypatch):
    import json
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    p=tmp_path/'bad.json';p.write_text(json.dumps({'settings':{'exposure':'NaN'}}))
    monkeypatch.setattr(QFileDialog,'getOpenFileName',lambda *a,**kw:(str(p),'Elsewhere recipe (*.json)'))
    errors=[]
    monkeypatch.setattr(QMessageBox,'critical',lambda *a,**kw:errors.append(a[2]))
    win=Elsewhere()
    original=win.settings.copy()
    win.load_recipe()
    assert win.settings==original
    assert errors and 'exposure' in errors[0]
    win.timer.stop()
    win.close()


def test_export_dialog_refuses_to_overwrite_source(qt_app,tmp_path,monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    p=tmp_path/'original.png';p.write_bytes(b'original photo placeholder')
    win=Elsewhere()
    win.filepath=str(p)
    monkeypatch.setattr(QFileDialog,'getSaveFileName',
        lambda *a,**kw:(str(p),'16-bit PNG (*.png)'))
    messages=[]
    monkeypatch.setattr(QMessageBox,'warning',
        lambda *a,**kw:messages.append(a[2]))
    monkeypatch.setattr(win,'start_job',
        lambda job:pytest.fail('Export must not launch for the original filename'))
    win.export_dialog()
    assert messages and 'original' in messages[0].lower()
    assert p.read_bytes()==b'original photo placeholder'
    win.close()
