#!/usr/bin/env python
"""
utilities for XRF display
"""
import copy
from functools import partial

import wx
import wx.lib.colourselect  as csel

from wxutils import (SimpleText, FloatCtrl, Choice, Font, pack, Button,
                     Check, HyperText, HLine, GridPanel, CEN, LEFT, RIGHT)

from wxmplot.colors import hexcolor

import larch

larch.use_plugin_path('xrf')

from xrf_bgr import xrf_background
from xrf_calib import xrf_calib_fitrois, xrf_calib_compute, xrf_calib_apply

class CalibrationFrame(wx.Frame):
    def __init__(self, parent, mca, larch=None, size=(500, 300)):
        self.mca = mca
        self.larch = larch
        wx.Frame.__init__(self, parent, -1, 'Calibrate MCA',
                          size=size, style=wx.DEFAULT_FRAME_STYLE)

        self.SetFont(Font(8))
        panel = GridPanel(self)
        self.calib_updated = False
        panel.AddText("Calibrate MCA Energy (Energies in eV)",
                      colour='#880000', dcol=7)
        panel.AddText("ROI", newrow=True)
        panel.AddText("Predicted")
        panel.AddText("Current Energies", dcol=3, style=CEN)
        panel.AddText("Refined Energies", dcol=3, style=CEN)
        panel.AddText("Use?")

        panel.AddText("Name", newrow=True)
        panel.AddText("Energy")
        panel.AddText("Center")
        panel.AddText("Difference")
        panel.AddText("FWHM")
        panel.AddText("Center")
        panel.AddText("Difference")
        panel.AddText("FWHM")

        panel.Add(HLine(panel, size=(900, 3)),  dcol=9, newrow=True)
        self.wids = []

        # find ROI peak positions
        xrf_calib_fitrois(mca, _larch=self.larch)

        for roi in self.mca.rois:
            eknown, ecen, fwhm, amp, fit = mca.init_calib[roi.name]
            diff = ecen - eknown
            name = ('   ' + roi.name+' '*10)[:10]
            opts = {'style': CEN, 'size':(100, -1)}
            w_name = SimpleText(panel, name,   **opts)
            w_pred = SimpleText(panel, "% .1f" % (1000*eknown), **opts)
            w_ccen = SimpleText(panel, "% .1f" % (1000*ecen),   **opts)
            w_cdif = SimpleText(panel, "% .1f" % (1000*diff),   **opts)
            w_cwid = SimpleText(panel, "% .1f" % (1000*fwhm),   **opts)
            w_ncen = SimpleText(panel, "-----",         **opts)
            w_ndif = SimpleText(panel, "-----",         **opts)
            w_nwid = SimpleText(panel, "-----",         **opts)
            w_use  = Check(panel)

            panel.Add(w_name, style=LEFT, newrow=True)
            panel.AddMany((w_pred, w_ccen, w_cdif, w_cwid,
                           w_ncen, w_ndif, w_nwid, w_use))

            self.wids.append((roi.name, eknown, ecen, w_ncen, w_ndif, w_nwid, w_use))

        panel.Add(HLine(panel, size=(900, 3)),  dcol=9, newrow=True)
        offset = 1000.0*self.mca.offset
        slope  = 1000.0*self.mca.slope
        panel.AddText("Current Calibration:",   dcol=2, newrow=True)
        panel.AddText("offset(eV):")
        panel.AddText("%.3f" % (offset), dcol=1, style=RIGHT)
        panel.AddText("slope(eV/chan):")
        panel.AddText("%.3f" % (slope),  dcol=1, style=RIGHT)

        panel.AddText("Refined Calibration:", dcol=2, newrow=True)
        self.new_offset = FloatCtrl(panel, value=offset, precision=3,
                                   size=(80, -1))
        self.new_slope = FloatCtrl(panel, value=slope,  precision=3,
                                   size=(80, -1))
        panel.AddText("offset(eV):")
        panel.Add(self.new_offset,    dcol=1, style=RIGHT)
        panel.AddText("slope(eV/chan):")
        panel.Add(self.new_slope,     dcol=1, style=RIGHT)

        panel.Add(Button(panel, 'Compute Calibration',
                         size=(160, -1), action=self.onCalibrate),
                  dcol=2, newrow=True)

        panel.Add(Button(panel, 'Use New Calibration',
                         size=(160, -1), action=self.onUseCalib),
                  dcol=2, style=RIGHT)

        panel.Add(Button(panel, 'Done',
                         size=(160, -1), action=self.onClose),
                  dcol=2, style=RIGHT)

        panel.pack()
        self.SetSize((950, 450))
        self.Show()
        self.Raise()

    def onCalibrate(self, event=None):
        x, y = [], []
        mca = self.mca
        # save old calib
        old_calib  =  mca.offset, mca.slope
        init_calib =  copy.deepcopy(mca.init_calib)
        for roiname, eknown, ecen, w_ncen, w_ndif, w_nwid, w_use in self.wids:
            if not w_use.IsChecked():
                mca.init_calib.pop(roiname)

        xrf_calib_compute(mca, apply=True, _larch=self.larch)
        offset, slope = mca.new_calib
        self.calib_updated = True
        self.new_offset.SetValue("% .3f" % (1000*offset))
        self.new_slope.SetValue("% .3f" % (1000*slope))

        # find ROI peak positions using this new calibration
        xrf_calib_fitrois(mca, _larch=self.larch)
        for roi in self.mca.rois:
            eknown, ecen, fwhm, amp, fit = mca.init_calib[roi.name]
            diff  = ecen - eknown
            for roiname, eknown, ocen, w_ncen, w_ndif, w_nwid, w_use in self.wids:
                if roiname == roi.name:
                    w_ncen.SetLabel("%.1f" % (1000*ecen))
                    w_ndif.SetLabel("% .1f" % (1000*diff))
                    w_nwid.SetLabel("%.1f" % (1000*fwhm))
                    break

        # restore calibration to old values until new values are accepted
        xrf_calib_apply(mca, offset=old_calib[0], slope=old_calib[1],
                        _larch=self.larch)
        mca.init_calib = init_calib

        tsize = self.GetSize()
        self.SetSize((tsize[0]+1, tsize[1]))
        self.SetSize((tsize[0], tsize[1]))

    def onUseCalib(self, event=None):
        mca = self.mca
        if hasattr(mca, 'new_calib'):
            xrf_calib_apply(mca, _larch=self.larch)
        self.Destroy()

    def onClose(self, event=None):
        self.Destroy()


class ColorsFrame(wx.Frame):
    """settings frame for XRFDisplay"""
    def __init__(self, parent, size=(400, 300), **kws):
        self.parent = parent
        conf = parent.conf
        kws['style'] = wx.DEFAULT_FRAME_STYLE
        wx.Frame.__init__(self, parent, -1, size=size,
                          title='XRF Color Settings', **kws)

        panel = GridPanel(self)
        panel.SetFont(Font(11))
        def add_color(panel, name):
            cval = hexcolor(getattr(conf, name))
            c = csel.ColourSelect(panel,  -1, "", cval, size=(35, 25))
            c.Bind(csel.EVT_COLOURSELECT, partial(self.onColor, item=name))
            return c

        SX = 130
        def scolor(txt, attr, **kws):
            panel.AddText(txt, size=(SX, -1), style=LEFT, font=Font(11), **kws)
            panel.Add(add_color(panel, attr),  style=LEFT)

        panel.AddText('    XRF Display Colors', dcol=4, colour='#880000')

        panel.Add(HLine(panel, size=(400, 3)),  dcol=4, newrow=True)
        scolor(' Main Spectra:',        'spectra_color', newrow=True)
        scolor(' Background Spectra:',      'spectra2_color')
        scolor(' ROIs:',                'roi_color',     newrow=True)
        scolor(' ROI Fill:',            'roi_fillcolor')
        scolor(' Cursor:',              'marker_color',  newrow=True)
        scolor(' XRF Background:',      'bgr_color')
        scolor(' Major X-ray Lines:',   'major_elinecolor', newrow=True)
        scolor(' Minor X-ray Lines:',   'minor_elinecolor')
        scolor(' Selected X-ray Line:', 'emph_elinecolor', newrow=True)

        panel.Add(HLine(panel, size=(400, 3)),  dcol=4, newrow=True)
        panel.Add(Button(panel, 'Done', size=(80, -1), action=self.onDone),
                  dcol=2, newrow=True)

        panel.pack()
        self.SetMinSize(panel.GetBestSize())
        self.Show()
        self.Raise()

    def onColor(self, event=None, item=None):
        color = hexcolor(event.GetValue())
        setattr(self.parent.conf, item, color)
        if item == 'spectra_color':
            self.parent.panel.conf.set_trace_color(color, trace=0)
        elif item == 'roi_color':
            self.parent.panel.conf.set_trace_color(color, trace=1)
        elif item == 'marker_color':
            for lmark in self.parent.cursor_markers:
                if lmark is not None:
                    lmark.set_color(color)

        elif item == 'roi_fillcolor' and self.parent.roi_patch is not None:
            self.parent.roi_patch.set_color(color)
        elif item == 'major_elinecolor':
            for l in self.parent.major_markers:
                l.set_color(color)
        elif item == 'minor_elinecolor':
            for l in self.parent.minor_markers:
                l.set_color(color)
        self.parent.panel.canvas.draw()
        self.parent.panel.Refresh()

    def onDone(self, event=None):
        self.Destroy()

class XrayLinesFrame(wx.Frame):
    """settings frame for XRFDisplay"""

    k1lines = ['Ka1', 'Ka2', 'Kb1']
    k2lines = ['Kb2', 'Kb3']
    l1lines = ['La1', 'Lb1', 'Lb3', 'Lb4']
    l2lines = ['La2', 'Ll', 'Ln', 'Lb2,15']
    l3lines = ['Lg1', 'Lg2', 'Lg3']
    mlines  = ['Ma', 'Mb', 'Mg', 'Mz']

    def __init__(self, parent, size=(500, 300), **kws):
        self.parent = parent
        conf  = parent.conf
        kws['style'] = wx.DEFAULT_FRAME_STYLE
        wx.Frame.__init__(self, parent, -1, size=size,
                          title='XRF Line Selection', **kws)
        panel = GridPanel(self)
        self.checkbox = {}
        def add_elines(panel, lines, checked, action):
            for i in lines:
                cb = Check(panel, '%s ' % i, default = i in checked,
                           action=partial(action, label=i))
                self.checkbox[i] = cb
                panel.Add(cb, style=LEFT)

        hopts = {'size': (125, -1), 'bgcolour': (250, 250, 200),
                 'action': self.ToggleLines}
        labopts = {'newrow': True, 'style': LEFT}
        self.linedata = {'Major K Lines:': self.k1lines,
                         'Minor K Lines:': self.k2lines,
                         'Major L Lines:': self.l1lines,
                         'Minor L Lines:': self.l2lines+self.l3lines,
                         'Major M Lines:': self.mlines}
        panel.AddText(' Select X-ray Emission Lines', dcol=4, colour='#880000')
        panel.Add(HLine(panel, size=(450, 3)),  dcol=5, newrow=True)

        panel.Add(HyperText(panel, 'Major K Lines:', **hopts), **labopts)
        add_elines(panel, self.k1lines, conf.K_major, self.onKMajor)

        panel.Add(HyperText(panel, 'Minor K Lines:',  **hopts), **labopts)
        add_elines(panel, self.k2lines, conf.K_minor, self.onKMinor)

        panel.Add(HyperText(panel, 'Major L Lines:', **hopts), **labopts)
        add_elines(panel, self.l1lines, conf.L_major, self.onLMajor)

        panel.Add(HyperText(panel, 'Minor L Lines:', **hopts), **labopts)
        add_elines(panel, self.l2lines, conf.L_minor, self.onLMinor)

        panel.AddText(' ', **labopts)
        add_elines(panel, self.l3lines, conf.L_minor, self.onLMinor)

        panel.Add(HyperText(panel, 'Major M Lines:', **hopts), **labopts)
        add_elines(panel, self.mlines,  conf.M_major, self.onMMajor)

        panel.AddText('Energy Range (keV): ', **labopts)
        fopts = {'minval':0, 'maxval':1000, 'precision':2, 'size':(75, -1)}
        panel.Add(FloatCtrl(panel, value=conf.e_min,
                            action=partial(self.onErange, is_max=False),
                            **fopts),  dcol=2, style=LEFT)

        panel.AddText(' : ')
        panel.Add(FloatCtrl(panel, value=conf.e_max,
                            action=partial(self.onErange, is_max=True),
                            **fopts), dcol=2, style=LEFT)

        panel.Add(HLine(panel, size=(450, 3)),  dcol=5, newrow=True)
        panel.Add(Button(panel, 'Done', size=(80, -1), action=self.onDone),
                  newrow=True, style=LEFT)
        panel.pack()
        cx, cy = panel.GetBestSize()
        panel.SetSize((cx+5, cy+5))
        self.Show()
        self.Raise()

    def ToggleLines(self, label=None, event=None, **kws):
        if not event.leftIsDown:
            for line in self.linedata.get(label, []):
                checked = self.checkbox[line].IsChecked()
                self.checkbox[line].SetValue({True: 1, False:0}[not checked])

    def onKMajor(self, event=None, label=None):
        self.onLine(label, event.IsChecked(), self.parent.conf.K_major)

    def onKMinor(self, event=None, label=None):
        self.onLine(label, event.IsChecked(), self.parent.conf.K_minor)

    def onLMajor(self, event=None, label=None):
        self.onLine(label, event.IsChecked(), self.parent.conf.L_major)

    def onLMinor(self, event=None, label=None):
        self.onLine(label, event.IsChecked(), self.parent.conf.L_minor)

    def onMMajor(self, event=None, label=None):
        self.onLine(label, event.IsChecked(), self.parent.conf.M_major)

    def onErange(self, event=None, value=None, is_max=True):
        en = self.parent.conf.e_min
        if is_max: en = self.parent.conf.e_max
        en = float(value)

    def onLine(self, label, checked, plist):
        if label in plist and not checked:
            plist.remove(label)
        elif label not in plist and checked:
            plist.append(label)
        if self.parent.selected_elem is not None:
            self.parent.onShowLines(elem=self.parent.selected_elem)

    def onDone(self, event=None):
        self.Destroy()

class XRFDisplayConfig:
    emph_elinecolor  = '#444444'
    major_elinecolor = '#DAD8CA'
    minor_elinecolor = '#F4DAC0'
    marker_color     = '#77BB99'
    roi_fillcolor    = '#F8F0BA'
    roi_color        = '#AA0000'
    spectra_color    = '#0000AA'
    spectra2_color   = '#00DD00'
    bgr_color        = '#000000'

    K_major = ['Ka1', 'Ka2', 'Kb1']
    K_minor = ['Kb3', 'Kb2']
    K_minor = []
    L_major = ['La1', 'Lb1', 'Lb3', 'Lb4']
    L_minor = ['Ln', 'Ll', 'Lb2,15', 'Lg2', 'Lg3', 'Lg1', 'La2']
    L_minor = []
    M_major = ['Ma', 'Mb', 'Mg', 'Mz']
    e_min   = 1.00
    e_max   = 30.0