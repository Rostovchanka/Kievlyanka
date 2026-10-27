"""Elsewhere Studio — dedicated photographic development desktop application.

No brushes, painted gradients, synthetic photographic textures, or generation.
Requires dependencies at build time; Windows distribution bundles the runtime.
"""
from __future__ import annotations
import copy
import json
import sys
from pathlib import Path
import numpy as np
from PySide6.QtCore import Qt, QThread, QTimer, Signal, QSize, QPointF
from PySide6.QtGui import QAction, QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QHBoxLayout, QVBoxLayout, QGridLayout,
    QSplitter, QScrollArea, QTabWidget, QLabel, QPushButton, QToolButton, QComboBox,
    QSlider, QSpinBox, QDoubleSpinBox, QListWidget, QListWidgetItem, QFileDialog,
    QMessageBox, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QProgressBar,
    QLineEdit, QCheckBox, QGroupBox, QSizePolicy
)

import engine
from engine import DEFAULTS, DEFAULT_GEOMETRY, GROUPS, PRESETS, BANDS
from io_formats import open_image, save_image
from recipe import validated_recipe

APP_NAME='ELSEWHERE STUDIO'
APP_VERSION='0.6.2 · Audited'

STYLE = '''
QWidget{background:#17191e;color:#d9dee8;font:10pt "Segoe UI"}
QMainWindow{background:#111318}
QMenuBar,QMenu{background:#22252e;border:0;color:#d9dee8}
QMenuBar::item{padding:7px 11px} QMenuBar::item:selected,QMenu::item:selected{background:#404a61}
QFrame#top{background:#20232b;border-bottom:1px solid #343b48}
QFrame#rail{background:#191c22;border-right:1px solid #2e3340}
QFrame#inspector{background:#20232a;border-left:1px solid #343b48}
QFrame#stats{background:#20232a;border:1px solid #343a48;border-radius:6px}
QLabel#kicker{color:#94a9d7;font-size:9pt;font-weight:700;letter-spacing:2px}
QLabel#secondary{color:#98a1b0}
QLabel#brand{color:#eef1f8;font-size:18pt;font-weight:800;letter-spacing:2px}
QPushButton{background:#2a2f3a;color:#e5eaf2;border:1px solid #424958;border-radius:5px;padding:9px 12px}
QPushButton:hover{background:#353f52;border-color:#6a7ea9}
QPushButton:disabled{color:#737986;border-color:#343a44}
QPushButton#primary{background:#617eae;color:#ffffff;border:1px solid #8299c0;font-weight:700}
QPushButton#primary:hover{background:#7590ba}
QPushButton#nav{background:transparent;border:0;border-left:3px solid transparent;border-radius:0;text-align:left;padding:12px 14px;font-weight:600;color:#99a5b9}
QPushButton#nav:hover{background:#282e3a}
QPushButton#nav:checked{background:#30394a;border-left:3px solid #a6b9ec;color:#fff}
QSlider::groove:horizontal{height:4px;background:#414956;border-radius:2px}
QSlider::handle:horizontal{background:#aec1ef;width:12px;margin:-5px 0;border-radius:6px}
QSlider::sub-page:horizontal{background:#7c96c8;border-radius:2px}
QComboBox,QLineEdit,QSpinBox,QDoubleSpinBox{background:#15181f;color:#e1e6f0;border:1px solid #454d5c;border-radius:4px;padding:6px}
QComboBox QAbstractItemView{background:#222631;selection-background-color:#4b5b78}
QScrollArea{border:0;background:transparent} QScrollArea>QWidget>QWidget{background:transparent}
QGroupBox{border:1px solid #3b4251;border-radius:5px;margin-top:14px;padding:8px 5px 6px;font-weight:700;color:#adbee8}
QGroupBox::title{subcontrol-origin:margin;left:10px;padding:0 6px}
QListWidget{background:#191d25;border:1px solid #363e4e;border-radius:4px;outline:0}
QListWidget::item{padding:9px} QListWidget::item:selected{background:#3d506f;color:white}
QStatusBar{background:#20232b;color:#b3bdcf;border-top:1px solid #363b49}
QProgressBar{background:#272e3b;border:0;border-radius:3px;height:5px}
QProgressBar::chunk{background:#8ba5dd;border-radius:3px}
QTabWidget::pane{border:0;background:#20232a}
QTabBar::tab{background:#252a34;padding:9px 14px;color:#94a0b4}
QTabBar::tab:selected{background:#3a475f;color:#f6f8ff}
'''

class ImageCanvas(QGraphicsView):
    dropped = Signal(str)
    def __init__(self):
        super().__init__()
        self.scene=QGraphicsScene(self);self.setScene(self.scene)
        self.item=QGraphicsPixmapItem();self.scene.addItem(self.item)
        self.setBackgroundBrush(QColor('#0d0f14'))
        self.setFrameShape(QFrame.NoFrame)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setAcceptDrops(True)
        self.has_photo=False
    def set_picture(self, image):
        pix=QPixmap.fromImage(image)
        was_empty=not self.has_photo
        self.item.setPixmap(pix);self.scene.setSceneRect(self.item.boundingRect())
        self.has_photo=True
        if was_empty: self.fit_image()
    def fit_image(self):
        if self.has_photo:self.fitInView(self.item,Qt.KeepAspectRatio)
    def clear_picture(self):
        self.item.setPixmap(QPixmap())
        self.has_photo=False
        self.resetTransform()
        self.scene.setSceneRect(0,0,1,1)
    def wheelEvent(self,event):
        if not self.has_photo:return
        factor=1.15 if event.angleDelta().y()>0 else (1/1.15)
        self.scale(factor,factor)
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if self.has_photo and self.transform().m11()<.15:self.fit_image()
    def dragEnterEvent(self,e):
        if e.mimeData().hasUrls():e.acceptProposedAction()
        else:super().dragEnterEvent(e)
    def dragMoveEvent(self,e):
        if e.mimeData().hasUrls():e.acceptProposedAction()
        else:super().dragMoveEvent(e)
    def dropEvent(self,e):
        if e.mimeData().hasUrls():
            for u in e.mimeData().urls():
                if u.isLocalFile():self.dropped.emit(u.toLocalFile());e.acceptProposedAction();return
        super().dropEvent(e)

class Histogram(QWidget):
    def __init__(self):
        super().__init__();self.setMinimumHeight(114);self.hists=None
    def set_image(self,arr):
        # Histogram is based on the actual rendered preview, not the ungraded RAW.
        if arr is None: return
        a=arr[::max(1,arr.shape[0]//350),::max(1,arr.shape[1]//350),:]
        self.hists=[np.histogram(a[...,i],bins=128,range=(0,256))[0].astype(float) for i in range(3)]
        self.update()
    def paintEvent(self,e):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(),QColor('#14171d'))
        p.setPen(QPen(QColor('#333a48'),1))
        for i in range(1,4):
            y=self.height()*i/4;p.drawLine(0,int(y),self.width(),int(y))
        if not self.hists:return
        mx=max(np.percentile(h,98) for h in self.hists)+1e-5
        for hist,color in zip(self.hists,[QColor(230,95,96,130),QColor(85,220,156,120),QColor(111,156,252,140)]):
            path=QPainterPath();path.moveTo(0,self.height())
            for i,v in enumerate(hist):
                x=i/(len(hist)-1)*self.width();y=self.height()-min(v/mx,1)*self.height()
                path.lineTo(x,y)
            path.lineTo(self.width(),self.height());path.closeSubpath()
            p.fillPath(path,color)

class IOJob(QThread):
    loaded=Signal(object,dict,bool,str,int)
    exported=Signal(str,int)
    error=Signal(str,str,int)
    def __init__(self,mode,path,settings=None,geometry=None,options=None,token=0):
        super().__init__();self.mode=mode;self.path=path
        self.token=token
        self.settings=dict(settings or {});self.geometry=dict(geometry or {})
        self.options=dict(options or {})
    def run(self):
        try:
            if self.mode=='open':
                arr,meta,linear=open_image(self.path,preview=True,options=self.options)
                self.loaded.emit(arr,meta,linear,self.path,self.token)
            elif self.mode=='export':
                if Path(self.options['source']).resolve()==Path(self.path).resolve():
                    raise ValueError('Export destination must differ from the source photograph')
                src,meta,linear=open_image(self.options['source'],preview=False,options=self.options)
                bits=8 if Path(self.path).suffix.lower() in ('.jpg','.jpeg') else 16
                out=engine.render(src,self.settings,self.geometry,source_linear=linear,out_bits=bits)
                save_image(self.path,out)
                self.exported.emit(self.path,bits)
        except Exception as ex:
            self.error.emit(f'{type(ex).__name__}: {ex}',self.path,self.token)

class RenderJob(QThread):
    ready=Signal(object,int)
    error=Signal(str,int)
    def __init__(self,rgb,settings,geometry,linear,version):
        super().__init__();self.rgb=rgb;self.settings=dict(settings)
        self.geometry=dict(geometry);self.linear=linear;self.version=version
    def run(self):
        try:
            result=engine.render(self.rgb,self.settings,self.geometry,
                source_linear=self.linear,out_bits=8,fast=False)
            self.ready.emit(result,self.version)
        except Exception as e:self.error.emit(str(e),self.version)

class Elsewhere(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f'{APP_NAME} — {APP_VERSION}')
        self.resize(1560,970);self.setMinimumSize(1080,700)
        self.setStyleSheet(STYLE)
        self.image_data=None;self.linear=False;self.filepath=None;self.meta={}
        self.settings=DEFAULTS.copy();self.geometry=DEFAULT_GEOMETRY.copy()
        self.raw_options={'white_balance':'camera','highlight_mode':'blend'}
        self.slider_controls={};self.curve_controls={};self.wheel_controls={}
        self.raw_controls=[];self.current_preview=None
        self.version=0;self.load_token=0;self.render_thread=None;self.active_jobs=[]
        self._close_pending=False
        self.undo_states=[];self.redo_states=[];self.rebuilding=False
        self.original_visible=False;self.cached_original=None
        self.timer=QTimer(self);self.timer.setSingleShot(True)
        self.timer.setInterval(210);self.timer.timeout.connect(self.render_debounced)
        self.init_ui();self.init_menu();self.sync_ui()
        for c in self.raw_controls:c.setEnabled(False)
        self.statusBar().showMessage('Ready  ·  Open your photograph to begin')
    def snapshot(self):
        return (copy.deepcopy(self.settings),copy.deepcopy(self.geometry))
    def record_undo(self):
        snap=self.snapshot()
        if not self.undo_states or self.undo_states[-1]!=snap:
            self.undo_states.append(snap)
            self.undo_states=self.undo_states[-70:]
        # Any new editing action invalidates the redo branch, including when
        # its starting state is identical to the last stored undo snapshot.
        self.redo_states.clear()
    def undo(self):
        if not self.undo_states:return
        self.redo_states.append(self.snapshot())
        self.settings,self.geometry=self.undo_states.pop()
        self.sync_ui();self.schedule()
    def redo(self):
        if not self.redo_states:return
        self.undo_states.append(self.snapshot())
        self.settings,self.geometry=self.redo_states.pop()
        self.sync_ui();self.schedule()
    def init_menu(self):
        menu=self.menuBar()
        files=menu.addMenu('File')
        for label,shortcut,fn in [('Open photograph…','Ctrl+O',self.open_dialog),
                                  ('Export photograph…','Ctrl+Shift+S',self.export_dialog),
                                  ('Save development recipe…','Ctrl+S',self.save_recipe),
                                  ('Load development recipe…','Ctrl+L',self.load_recipe)]:
            a=QAction(label,self);a.setShortcut(shortcut);a.triggered.connect(fn);files.addAction(a)
        edit=menu.addMenu('Edit')
        for label,shortcut,fn in [('Undo','Ctrl+Z',self.undo),('Redo','Ctrl+Y',self.redo),
                                  ('Reset grade','Ctrl+R',self.reset_grade)]:
            a=QAction(label,self);a.setShortcut(shortcut);a.triggered.connect(fn);edit.addAction(a)
        view=menu.addMenu('View')
        for label,shortcut,fn in [('Fit image','Ctrl+0',self.canvas.fit_image),
                                  ('Before / after','\\',self.toggle_original)]:
            a=QAction(label,self);a.setShortcut(shortcut);a.triggered.connect(fn);view.addAction(a)
    def init_ui(self):
        outer=QWidget();self.setCentralWidget(outer)
        layout=QVBoxLayout(outer);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0)
        top=QFrame();top.setObjectName('top');topbox=QHBoxLayout(top);topbox.setContentsMargins(18,12,18,12)
        brand=QVBoxLayout();head=QLabel('ELSEWHERE');head.setObjectName('brand');brand.addWidget(head)
        sub=QLabel('LIMINAL PHOTOGRAPHIC LABORATORY');sub.setObjectName('kicker');brand.addWidget(sub)
        topbox.addLayout(brand);topbox.addStretch()
        self.before_btn=QPushButton('Before / After');self.before_btn.setCheckable(True)
        self.before_btn.clicked.connect(self.toggle_original);topbox.addWidget(self.before_btn)
        fit=QPushButton('Fit to Window');fit.clicked.connect(self.canvas_fit_action);topbox.addWidget(fit)
        open_btn=QPushButton('Open Photo');open_btn.clicked.connect(self.open_dialog);topbox.addWidget(open_btn)
        self.export_btn=QPushButton('Export');self.export_btn.setObjectName('primary')
        self.export_btn.clicked.connect(self.export_dialog);self.export_btn.setEnabled(False)
        topbox.addWidget(self.export_btn);layout.addWidget(top)
        split=QSplitter(Qt.Horizontal);split.setChildrenCollapsible(False);layout.addWidget(split,1)
        rail=QFrame();rail.setObjectName('rail');rail.setMinimumWidth(174);rail.setMaximumWidth(224)
        rail_l=QVBoxLayout(rail);rail_l.setContentsMargins(0,16,0,12);rail_l.setSpacing(3)
        label=QLabel('WORKSPACE');label.setObjectName('kicker');label.setContentsMargins(16,2,0,12);rail_l.addWidget(label)
        self.nav={}
        for text in ('Develop','Color','HSL','Curves','Color Wheels','Atmosphere','Optics','Geometry','Presets','RAW Settings'):
            btn=QPushButton(text);btn.setObjectName('nav');btn.setCheckable(True)
            btn.clicked.connect(lambda checked=False,n=text:self.activate(n))
            rail_l.addWidget(btn);self.nav[text]=btn
        rail_l.addStretch()
        note=QLabel('PHOTOGRAPHIC EDITING ONLY\n\nNo generative content.\nNo brushes or gradients.')
        note.setWordWrap(True);note.setContentsMargins(16,10,10,10)
        note.setStyleSheet('color:#77869c;font-size:9pt')
        rail_l.addWidget(note);split.addWidget(rail)
        center=QWidget();center_l=QVBoxLayout(center);center_l.setContentsMargins(6,6,6,4)
        self.canvas=ImageCanvas();self.canvas.dropped.connect(self.open_path)
        center_l.addWidget(self.canvas,1)
        status=QHBoxLayout()
        self.filename=QLabel('No photograph open');self.filename.setObjectName('secondary')
        status.addWidget(self.filename);status.addStretch()
        self.bitbadge=QLabel('RAW · JPEG · PNG · TIFF');self.bitbadge.setObjectName('secondary')
        status.addWidget(self.bitbadge);center_l.addLayout(status)
        split.addWidget(center)
        right=QFrame();right.setObjectName('inspector');right.setMinimumWidth(322);right.setMaximumWidth(436)
        right_l=QVBoxLayout(right);right_l.setContentsMargins(10,10,10,10);right_l.setSpacing(8)
        stats=QFrame();stats.setObjectName('stats');stats_l=QVBoxLayout(stats);stats_l.setContentsMargins(12,10,12,10)
        kicker=QLabel('LIVE RGB HISTOGRAM');kicker.setObjectName('kicker');stats_l.addWidget(kicker)
        self.hist=Histogram();stats_l.addWidget(self.hist)
        self.metadata=QLabel('No photograph loaded');self.metadata.setWordWrap(True)
        self.metadata.setObjectName('secondary');stats_l.addWidget(self.metadata)
        right_l.addWidget(stats)
        self.panel_title=QLabel('DEVELOP');self.panel_title.setObjectName('kicker');right_l.addWidget(self.panel_title)
        self.panels={};self.panels_stack=QTabWidget();self.panels_stack.tabBar().hide()
        right_l.addWidget(self.panels_stack,1)
        for section in ('Develop','Color','HSL','Curves','Color Wheels','Atmosphere','Optics','Geometry','Presets','RAW Settings'):
            if section in GROUPS:self.panels[section]=self.make_group(section)
            elif section=='HSL':self.panels[section]=self.make_hsl()
            elif section=='Curves':self.panels[section]=self.make_curves()
            elif section=='Color Wheels':self.panels[section]=self.make_wheels()
            elif section=='Geometry':self.panels[section]=self.make_geometry()
            elif section=='Presets':self.panels[section]=self.make_presets()
            elif section=='RAW Settings':self.panels[section]=self.make_raw_options()
            self.panels_stack.addTab(self.panels[section],section)
        self.progress=QProgressBar();self.progress.setMaximumHeight(6);self.progress.hide()
        right_l.addWidget(self.progress)
        split.addWidget(right);split.setSizes([180,990,380]);self.activate('Develop')
    def canvas_fit_action(self): self.canvas.fit_image()
    def activate(self,name):
        for n,b in self.nav.items():b.setChecked(n==name)
        for i in range(self.panels_stack.count()):
            if self.panels_stack.tabText(i)==name:
                self.panels_stack.setCurrentIndex(i);break
        self.panel_title.setText(name.upper())
    def page(self):
        w=QWidget();outer=QVBoxLayout(w);outer.setContentsMargins(0,0,0,0)
        sc=QScrollArea();sc.setWidgetResizable(True)
        content=QWidget();box=QVBoxLayout(content);box.setContentsMargins(4,5,4,5);box.setSpacing(13)
        sc.setWidget(content);outer.addWidget(sc)
        return w,box
    def control(self, key, label, low, high, step=1, *, geom=False):
        w=QWidget();v=QVBoxLayout(w);v.setContentsMargins(1,2,1,2);v.setSpacing(5)
        top=QHBoxLayout();nam=QLabel(label);top.addWidget(nam);top.addStretch()
        number=QLabel('0');number.setMinimumWidth(52);number.setAlignment(Qt.AlignRight|Qt.AlignVCenter)
        number.setStyleSheet('color:#bdcbef;font-weight:600')
        top.addWidget(number);v.addLayout(top)
        slider=QSlider(Qt.Horizontal)
        d=20 if step==.05 else 1
        slider.setRange(round(low*d),round(high*d));slider.setSingleStep(max(1,round(step*d)))
        def changed(n):
            if self.rebuilding:return
            target=self.geometry if geom else self.settings
            # The value can also change with keyboard arrows or the mouse wheel.
            # Snapshot these before changes; mouse drags snapshot on sliderPressed.
            if not slider.isSliderDown():self.record_undo()
            target[key]=n/d;number.setText(f'{n/d:.2f}' if d==20 else f'{n/d:.0f}')
            self.schedule()
        slider.valueChanged.connect(changed)
        slider.sliderPressed.connect(self.record_undo)
        v.addWidget(slider)
        self.slider_controls[('geom_' if geom else '')+key]=(slider,number,d)
        return w
    def make_group(self,section):
        w,box=self.page()
        for item in GROUPS[section]:box.addWidget(self.control(*item))
        box.addStretch();return w
    def make_hsl(self):
        w,box=self.page()
        note=QLabel('Adjust eight color ranges without selecting or painting regions.')
        note.setWordWrap(True);note.setObjectName('secondary');box.addWidget(note)
        for band in BANDS:
            group=QGroupBox(band.capitalize());gl=QVBoxLayout(group)
            for suffix,label in [('hue','Hue'),('sat','Saturation'),('lum','Luminance')]:
                gl.addWidget(self.control(f'hsl_{band}_{suffix}',label,-100,100))
            box.addWidget(group)
        box.addStretch();return w
    def make_curves(self):
        w,box=self.page()
        note=QLabel('Five-point luminance curve · 0, 25, 50, 75 and 100% input.')
        note.setWordWrap(True);note.setObjectName('secondary');box.addWidget(note)
        for x in (0,25,50,75,100):
            box.addWidget(self.control(f'curve_{x}',f'Curve input {x}%',0,100))
        reset=QPushButton('Reset curve to linear');reset.clicked.connect(self.reset_curve)
        box.addWidget(reset);box.addStretch();return w
    def make_wheels(self):
        w,box=self.page()
        note=QLabel('Split-tone hue and strength for shadows, midtones, and highlights.')
        note.setWordWrap(True);note.setObjectName('secondary');box.addWidget(note)
        for name in ('shadow','mid','highlight'):
            g=QGroupBox(name.capitalize());v=QVBoxLayout(g)
            v.addWidget(self.control(f'{name}_hue','Hue (degrees)',0,360))
            v.addWidget(self.control(f'{name}_strength','Intensity',0,100))
            box.addWidget(g)
        box.addStretch();return w
    def make_geometry(self):
        w,box=self.page()
        text=QLabel('Move, zoom, or rotate your entire photograph. No perspective corrections or painted adjustments.')
        text.setWordWrap(True);text.setObjectName('secondary');box.addWidget(text)
        for args in [('move_x','Horizontal position (%)',-50,50),
                     ('move_y','Vertical position (%)',-50,50),
                     ('zoom','Zoom (%)',50,200),('rotation','Rotation (°)',-180,180)]:
            box.addWidget(self.control(*args,geom=True))
        b=QPushButton('Reset geometry');b.clicked.connect(self.reset_geometry);box.addWidget(b)
        box.addStretch();return w
    def make_presets(self):
        w,box=self.page()
        text=QLabel('Presets modify only photographs you opened. They contain no textures, stock images, or generated scene content.')
        text.setWordWrap(True);text.setObjectName('secondary');box.addWidget(text)
        search=QLineEdit();search.setPlaceholderText('Search Backrooms and liminal looks…');box.addWidget(search)
        listing=QListWidget();listing.addItems(PRESETS.keys());listing.setMinimumHeight(380)
        listing.itemClicked.connect(lambda item:self.apply_preset(item.text()))
        search.textChanged.connect(lambda q:self.filter_presets(listing,q))
        box.addWidget(listing);box.addStretch();return w
    def filter_presets(self,lst,q):
        for i in range(lst.count()):lst.item(i).setHidden(q.lower() not in lst.item(i).text().lower())
    def make_raw_options(self):
        w,box=self.page()
        note=QLabel('Sensor-stage options appear only for RAW photographs. JPG/PNG can use all other development, color, optical and liminal controls.')
        note.setWordWrap(True);note.setObjectName('secondary');box.addWidget(note)
        title=QLabel('Demosaicing white balance');box.addWidget(title)
        self.wb_combo=QComboBox();self.wb_combo.addItems(['Camera','Auto','Daylight']);box.addWidget(self.wb_combo)
        title2=QLabel('Sensor highlight decoding');box.addWidget(title2)
        self.highlight_combo=QComboBox();self.highlight_combo.addItems(['Blend','Clip','Reconstruct'])
        box.addWidget(self.highlight_combo)
        btn=QPushButton('Re-develop RAW preview');btn.clicked.connect(self.redecode_raw);box.addWidget(btn)
        self.raw_controls=[self.wb_combo,self.highlight_combo,btn]
        box.addStretch();return w
    def reset_curve(self):
        self.record_undo()
        for n in (0,25,50,75,100):self.settings[f'curve_{n}']=float(n)
        self.sync_ui();self.schedule()
    def reset_geometry(self):
        self.record_undo();self.geometry=DEFAULT_GEOMETRY.copy();self.sync_ui();self.schedule()
    def reset_grade(self):
        self.record_undo();self.settings=DEFAULTS.copy();self.sync_ui();self.schedule()
    def apply_preset(self,name):
        if name not in PRESETS:return
        self.record_undo();self.settings=DEFAULTS|PRESETS[name]
        self.sync_ui();self.schedule();self.statusBar().showMessage(f'Look applied · {name}')
    def sync_ui(self):
        self.rebuilding=True
        try:
            for key,(slider,label,d) in self.slider_controls.items():
                val=self.geometry.get(key[5:]) if key.startswith('geom_') else self.settings.get(key)
                if val is None:continue
                slider.setValue(int(round(val*d)))
                label.setText(f'{val:.2f}' if d==20 else f'{val:.0f}')
        finally:self.rebuilding=False
    def open_dialog(self):
        path,_=QFileDialog.getOpenFileName(self,'Open your photograph','',
            'Photographs (*.cr3 *.CR3 *.cr2 *.CR2 *.dng *.DNG *.nef *.NEF *.arw *.ARW *.raf *.RAF *.orf *.ORF *.rw2 *.RW2 *.pef *.PEF *.srw *.SRW *.jpg *.jpeg *.JPG *.png *.PNG *.tif *.tiff *.TIF *.bmp);;All files (*)')
        if path:self.open_path(path)
    def start_job(self,job):
        self.active_jobs.append(job)
        job.finished.connect(lambda j=job:self.finish_job(j))
        job.start()
    def finish_job(self,job):
        if job in self.active_jobs:self.active_jobs.remove(job)
        if not self.active_jobs:self.progress.hide()
        if self._close_pending:self._finish_pending_close()
    def busy(self,text):
        self.progress.setRange(0,0);self.progress.show();self.statusBar().showMessage(text)
    def open_path(self,path,*,preserve_edits=False):
        if not Path(path).is_file():return
        self.load_token+=1
        self.version+=1  # Invalidate previews from the previously opened image.
        self.timer.stop()
        self.filepath=path;self.image_data=None;self.current_preview=None;self.cached_original=None
        self.canvas.clear_picture();self.hist.hists=None;self.hist.update()
        self.export_btn.setEnabled(False)
        for control in self.raw_controls:control.setEnabled(False)
        self.original_visible=False;self.before_btn.setChecked(False)
        self.before_btn.setText('Before / After')
        if not preserve_edits:
            self.settings=DEFAULTS.copy();self.geometry=DEFAULT_GEOMETRY.copy()
            self.sync_ui();self.undo_states.clear();self.redo_states.clear()
        self.filename.setText(Path(path).name);self.busy('Decoding photograph…')
        job=IOJob('open',path,options=self.raw_options,token=self.load_token)
        job.loaded.connect(self.loaded)
        job.error.connect(self.failed)
        self.start_job(job)
    def loaded(self,arr,meta,linear,path,token):
        if token!=self.load_token or path!=self.filepath:return
        self.image_data=arr;self.linear=linear;self.meta=meta
        self.filename.setText(Path(path).name+'  ·  '+meta.get('resolution',''))
        self.bitbadge.setText(meta.get('bit_depth','')+'  ·  '+meta.get('format',''))
        notes=[meta[k] for k in ('input_profile','alpha') if meta.get(k)]
        self.metadata.setText(f"{meta.get('camera','')}   ·   ISO {meta.get('iso','—')}\n{meta.get('resolution','')}" + ''.join(f"\n{note}" for note in notes))
        self.export_btn.setEnabled(True)
        for control in self.raw_controls:control.setEnabled(linear)
        self.cached_original=engine.render(arr,DEFAULTS,DEFAULT_GEOMETRY,
                                           source_linear=linear,out_bits=8,fast=True)
        self.schedule();self.statusBar().showMessage('Loaded · All editing panels available')
    def failed(self,msg,path,token):
        # Ignore errors from superseded openings; retain errors from exports.
        if token and token!=self.load_token:return
        is_export=token==0
        QMessageBox.critical(self,'Export failed' if is_export else 'Photograph could not be opened',msg)
        if not is_export:self.export_btn.setEnabled(False)
        self.statusBar().showMessage('Export error' if is_export else 'File error · Check format and camera compatibility')
    def raw_settings(self):
        return {'white_balance':self.wb_combo.currentText().lower(),
                'highlight_mode':self.highlight_combo.currentText().lower()}
    def redecode_raw(self):
        if not self.filepath or Path(self.filepath).suffix.lower() not in engine.RAW_EXTENSIONS:return
        self.raw_options=self.raw_settings()
        self.open_path(self.filepath,preserve_edits=True)
    def schedule(self):
        if self.image_data is not None:
            self.version+=1
            self.timer.start()
    def render_debounced(self):
        if self.image_data is None or self._close_pending:return
        if self.render_thread is not None and self.render_thread.isRunning():
            self.timer.start(100);return
        self.render_thread=RenderJob(self.image_data,self.settings,self.geometry,self.linear,self.version)
        self.render_thread.ready.connect(self.preview_ready)
        self.render_thread.error.connect(lambda e,v:self.statusBar().showMessage('Render error · '+e) if v==self.version else None)
        self.render_thread.finished.connect(self._finish_pending_close)
        self.render_thread.start()
    def preview_ready(self,arr,version):
        if version!=self.version:return
        self.current_preview=arr
        self.hist.set_image(arr)
        self.show_image(self.cached_original if self.original_visible else arr)
    def show_image(self,arr):
        if arr is None:return
        h,w=arr.shape[:2]
        qimg=QImage(arr.data,w,h,w*3,QImage.Format_RGB888).copy()
        self.canvas.set_picture(qimg)
    def toggle_original(self):
        self.original_visible=not self.original_visible
        self.before_btn.setChecked(self.original_visible)
        self.before_btn.setText('Original Shown' if self.original_visible else 'Before / After')
        self.show_image(self.cached_original if self.original_visible else self.current_preview)
    def export_dialog(self):
        if not self.filepath:return
        suggested=str(Path(self.filepath).with_name(Path(self.filepath).stem+'_elsewhere.tif'))
        path,chosen=QFileDialog.getSaveFileName(self,'Export your edited photograph',suggested,
            '16-bit TIFF (*.tif);;16-bit PNG (*.png);;JPEG 8-bit (*.jpg)')
        if not path:return
        ext=Path(path).suffix.lower()
        if ext not in ('.tif','.tiff','.png','.jpg','.jpeg'):
            path+=('.tif' if 'TIFF' in chosen else '.png' if 'PNG' in chosen else '.jpg')
        if Path(path).resolve()==Path(self.filepath).resolve():
            QMessageBox.warning(self,'Protect original photograph',
                'The export filename matches the original photo. Choose a different filename to preserve the source.')
            return
        self.busy('Exporting full-resolution photograph…')
        job=IOJob('export',path,self.settings,self.geometry,
                  {'source':self.filepath,**self.raw_options})
        job.exported.connect(self.exported)
        job.error.connect(self.failed)
        self.start_job(job)
    def exported(self,path,bits):
        self.statusBar().showMessage(f'Exported · {Path(path).name} · {bits}-bit RGB')
        QMessageBox.information(self,'Export complete',
            f'Photograph exported at {bits}-bit RGB:\n{path}\n\nThe original file was not modified.')
    def save_recipe(self):
        path,_=QFileDialog.getSaveFileName(self,'Save Elsewhere recipe','elsewhere-grade.json','Elsewhere recipe (*.json)')
        if not path:return
        payload={'app':'Elsewhere Studio','version':2,'settings':self.settings,
                 'geometry':self.geometry,'raw_options':self.raw_options}
        try:
            Path(path).write_text(json.dumps(payload,indent=2),encoding='utf-8')
            self.statusBar().showMessage('Recipe saved · '+Path(path).name)
        except OSError as e:
            QMessageBox.critical(self,'Could not save recipe',str(e))
    def load_recipe(self):
        path,_=QFileDialog.getOpenFileName(self,'Open Elsewhere recipe','','Elsewhere recipe (*.json)')
        if not path:return
        try:
            # Validate the entire recipe *before* changing UI/application state.
            if Path(path).stat().st_size>1024*1024:
                raise ValueError('Recipe file is unexpectedly large')
            payload=json.loads(Path(path).read_text(encoding='utf-8'))
            settings,geometry,raw_options=validated_recipe(payload)
            self.record_undo()
            self.settings=settings;self.geometry=geometry
            self.sync_ui()
            self.raw_options=raw_options
            self.wb_combo.setCurrentText(raw_options['white_balance'].capitalize())
            self.highlight_combo.setCurrentText(raw_options['highlight_mode'].capitalize())
            if self.filepath and Path(self.filepath).suffix.lower() in engine.RAW_EXTENSIONS:
                self.open_path(self.filepath,preserve_edits=True)
            else:self.schedule()
            self.statusBar().showMessage('Recipe loaded · '+Path(path).name)
        except Exception as e:QMessageBox.critical(self,'Recipe error',str(e))
    def _finish_pending_close(self):
        if not self._close_pending:return
        if self.active_jobs or (self.render_thread is not None and self.render_thread.isRunning()):
            return
        self._close_pending=False
        self.close()
    def closeEvent(self,event):
        if self.active_jobs or (self.render_thread is not None and self.render_thread.isRunning()):
            event.ignore()
            self._close_pending=True
            self.timer.stop()
            self.statusBar().showMessage('Finishing active photo processing before closing…')
            return
        super().closeEvent(event)


def main():
    app=QApplication(sys.argv);app.setStyle('Fusion');app.setApplicationName(APP_NAME)
    if '--self-test' in sys.argv:
        import rawpy
        import cv2
        test=np.zeros((8,8,3),dtype=np.uint16)
        result=engine.render(test,out_bits=16)
        if result.shape!=(8,8,3) or result.dtype!=np.uint16:
            raise SystemExit(5)
        raise SystemExit(0)
    win=Elsewhere();win.show()
    if len(sys.argv)>1:win.open_path(sys.argv[1])
    sys.exit(app.exec())

if __name__=='__main__':main()
