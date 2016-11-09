#!/usr/bin/env python
"""
Scan Data File Viewer
"""
import os
import sys
import time
import numpy as np
np.seterr(all='ignore')

from functools import partial

import wx
import wx.lib.agw.flatnotebook as flat_nb
import wx.lib.scrolledpanel as scrolled
import wx.lib.mixins.inspection

from wx.richtext import RichTextCtrl

is_wxPhoenix = 'phoenix' in wx.PlatformInfo

from wxutils import (SimpleText, FloatCtrl, pack, Button, HLine,
                     Choice,  Check, MenuItem, GUIColors,
                     CEN, RCEN, LCEN, FRAMESTYLE, Font)

import lmfit.models as lm_models

from larch import Interpreter, isParameter, Group
from larch.larchlib import read_workdir, save_workdir
from larch.wxlib import (larchframe, EditColumnFrame, ReportFrame,
                         BitmapButton, FileCheckList)

from larch.fitting import fit_report

from larch_plugins.std import group2dict
from larch_plugins.math import fit_peak, index_of
from larch_plugins.math.smoothing import (savitzky_golay, smooth, boxcar)

from larch_plugins.wx.plotter import _newplot, _plot, _getDisplay
from larch_plugins.wx.icons import get_icon

from larch_plugins.io import (read_ascii, read_xdi, read_gsexdi,
                              gsescan_group, fix_varname)

from larch_plugins.xafs import pre_edge

CEN |=  wx.ALL
FILE_WILDCARDS = "Scan Data Files(*.0*,*.dat,*.xdi)|*.0*;*.dat;*.xdi|All files (*.*)|*.*"
FNB_STYLE = flat_nb.FNB_NO_X_BUTTON|flat_nb.FNB_NODRAG|flat_nb.FNB_NO_NAV_BUTTONS


PLOTOPTS_1 = dict(style='solid', linewidth=3, marker='None', markersize=4)
PLOTOPTS_2 = dict(style='short dashed', linewidth=2, zorder=-5,
                  marker='None', markersize=4)
PLOTOPTS_D = dict(style='solid', linewidth=2, zorder=-5,
                  side='right',  marker='None', markersize=4)

ICON_FILE = 'larch.ico'

SMOOTH_OPS = ('None', 'Boxcar', 'Savitzky-Golay', 'Convolution')
CONV_OPS  = ('Lorenztian', 'Gaussian')


def assign_gsescan_groups(group):
    labels = group.array_labels
    labels = []
    for i, name in enumerate(group.pos_desc):
        name = fix_varname(name.lower())
        labels.append(name)
        setattr(group, name, group.pos[i, :])

    for i, name in enumerate(group.sums_names):
        name = fix_varname(name.lower())
        labels.append(name)
        setattr(group, name, group.sums_corr[i, :])

    for i, name in enumerate(group.det_desc):
        name = fix_varname(name.lower())
        labels.append(name)
        setattr(group, name, group.det_corr[i, :])

    group.array_labels = labels



StepChoices = ('Linear', 'Arctan', 'ErrorFunction', 'Logistic')

ModelChoices = ('Gaussian', 'Lorentzian', 'Voigt', 'PseudoVoigt', 'Pearson7',
               'StudentsT', 'SkewedGaussian', 'Constant', 'Linear',
               'Quadratic', 'Exponential', 'PowerLaw', 'Rectangle',
               'DampedOscillator', 'Lognormal', 'BreitWigner', 'Donaich')


XASOPChoices=('Raw Data', 'Normalized', 'Derivative',
              'Normalized + Derivative',
              'Pre-edge subtracted',
              'Raw Data + Pre-edge/Post-edge')

class ProcessPanel(wx.Panel):
    def __init__(self, parent=None, main=None, **kws):
        wx.Panel.__init__(self, parent, -1, **kws)

        self.parent = parent
        self.main  = main
        self.larch = None

        self.needs_update = False

        self.needs_update = False
        self.proc_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.onProcessTimer, self.proc_timer)
        self.proc_timer.Start(500)
        self.build_display()

    def fill(self, dgroup):

        predefs = dict(e0=0, pre1=-200, pre2=-30, norm1=50, edge_step=0,
                       norm2=-10, nnorm=3, nvict=2, auto_step=True,
                       auto_e0=True, show_e0=True, xas_op=0)

        if hasattr(dgroup, 'proc_opts'):
            predefs.update(group2dict(dgroup.proc_opts))

        self.xshift.SetVale(predefs['xshift'])
        self.yshift.SetVale(predefs['yshift'])
        self.xscale.SetVale(predefs['xscale'])
        self.yscale.SetVale(predefs['yscale'])

        self.smooth_op.SetStringSelection(predefs['smooth_op'])
        self.smooth_conv.SetStringSelection(predefs['smooth_conv'])
        self.smooth_c0.SetValue(predefs['smooth_c0'])
        self.smooth_c1.SetValue(predefs['smooth_c1'])
        self.smooth_sig.SetValue(predefs['smooth_sig'])


        if dgroup.datatype == 'xas':
            self.xas_op.SetSelection(predefs['xas_op'])
            self.xas_e0.SetValue(predefs['e0'])
            self.xas_step.SetValue(predefs['edge_step'])
            self.xas_pre1.SetValue(predefs['pre1'])
            self.xas_pre2.SetValue(predefs['pre2'])
            self.xas_nor1.SetValue(predefs['norm1'])
            self.xas_nor2.SetValue(predefs['norm2'])
            self.xas_vict.SetSelection(predefs['nvict'])
            self.xas_nnor.SetSelection(predefs['nnorm'])

            self.xas_showe0.SetValue(predefs['show_e0'])
            self.xas_autoe0.SetValue(predefs['auto_e0'])
            self.xas_autostep.SetValue(predefs['auto_step'])

    def build_display(self):

        self.SetFont(Font(11))

        titleopts = dict(font=Font(12), colour='#AA0000')

        xas = self.xaspanel = wx.Panel(self)
        gen = self.genpanel = wx.Panel(self)
        self.btns = {}
        #gen
        opts  = dict(action=self.UpdatePlot, size=(100, -1))

        self.xshift = FloatCtrl(gen, value=0.0, precision=4, **opts)
        self.xscale = FloatCtrl(gen, value=1.0, precision=4, **opts)

        self.yshift = FloatCtrl(gen, value=0.0, precision=4, **opts)
        self.yscale = FloatCtrl(gen, value=1.0, precision=4, **opts)

        self.btns['xshift'] = BitmapButton(gen, get_icon('plus'),
                                           action=partial(self.on_selpoint, opt='xshift'),
                                           tooltip='use last point selected from plot')
        self.btns['yshift'] = BitmapButton(gen, get_icon('plus'),
                                           action=partial(self.on_selpoint, opt='yshift'),
                                           tooltip='use last point selected from plot')

        opts  = dict(action=self.onSmoothChoice, size=(30, -1))
        sm_row1 = wx.Panel(gen)
        sm_row2 = wx.Panel(gen)
        sm_siz1= wx.BoxSizer(wx.HORIZONTAL)
        sm_siz2= wx.BoxSizer(wx.HORIZONTAL)

        self.smooth_c0 = FloatCtrl(sm_row1, value=2, precision=0, **opts)
        self.smooth_c1 = FloatCtrl(sm_row1, value=1, precision=0, **opts)
        opts['size'] =  (75, -1)
        self.smooth_sig = FloatCtrl(sm_row2, value=1, precision=4, **opts)

        opts['size'] =  (120, -1)
        self.smooth_op = Choice(sm_row1, choices=SMOOTH_OPS, **opts)
        self.smooth_op.SetSelection(0)

        self.smooth_conv = Choice(sm_row2, choices=CONV_OPS, **opts)

        self.smooth_c0.Disable()
        self.smooth_c1.Disable()
        self.smooth_sig.Disable()
        self.smooth_conv.SetSelection(0)
        self.smooth_conv.Disable()

        sm_siz1.Add(self.smooth_op,  0, LCEN, 1)
        sm_siz1.Add(SimpleText(sm_row1, ' n ='), 0, LCEN, 1)
        sm_siz1.Add(self.smooth_c0,  0, LCEN, 1)
        sm_siz1.Add(SimpleText(sm_row1, ' order ='), 0, LCEN, 1)
        sm_siz1.Add(self.smooth_c1,  0, LCEN, 1)

        sm_siz2.Add(SimpleText(sm_row2, ' form ='), 0, LCEN, 1)
        sm_siz2.Add(self.smooth_conv,  0, LCEN, 1)
        sm_siz2.Add(SimpleText(sm_row2, ' sigma ='), 0, LCEN, 1)
        sm_siz2.Add(self.smooth_sig,  0, LCEN, 1)
        pack(sm_row1, sm_siz1)
        pack(sm_row2, sm_siz2)

        sizer = wx.GridBagSizer(5, 5)

        ir = 0
        sizer.Add(SimpleText(gen, ' General Data Processing', **titleopts),
                  (ir, 0), (1, 8), LCEN, 5)

        ir += 1
        sizer.Add(SimpleText(gen, ' X shift:'),  (ir, 0), (1, 1), LCEN, 0)
        sizer.Add(self.btns['xshift'],           (ir, 1), (1, 1), LCEN, 0)
        sizer.Add(self.xshift,                   (ir, 2), (1, 2), LCEN, 0)
        sizer.Add(SimpleText(gen, ' X scale:'),  (ir, 4), (1, 1), LCEN, 0)
        sizer.Add(self.xscale,                   (ir, 5), (1, 2), LCEN, 0)

        ir += 1
        sizer.Add(SimpleText(gen, ' Y shift:'),  (ir, 0), (1, 1), LCEN, 0)
        sizer.Add(self.btns['yshift'],           (ir, 1), (1, 1), LCEN, 0)
        sizer.Add(self.yshift,                   (ir, 2), (1, 2), LCEN, 0)
        sizer.Add(SimpleText(gen, ' Y scale:'),  (ir, 4), (1, 1), LCEN, 0)
        sizer.Add(self.yscale,                   (ir, 5), (1, 2), LCEN, 0)


        ir += 1
        sizer.Add(SimpleText(gen, ' Smoothing:'), (ir, 0), (1, 1), LCEN, 0)
        sizer.Add(sm_row1, (ir,   1), (1, 7), LCEN)
        sizer.Add(sm_row2, (ir+1, 1), (1, 7), LCEN)

        pack(gen, sizer)

        #xas
        opts = {'action': self.UpdatePlot}
        self.xas_autoe0   = Check(xas, default=True, label='auto?', **opts)
        self.xas_showe0   = Check(xas, default=True, label='show?', **opts)
        self.xas_autostep = Check(xas, default=True, label='auto?', **opts)
        opts['size'] = (300, -1)
        self.xas_op  = Choice(xas, choices=XASOPChoices,  **opts)

        for name in ('e0', 'pre1', 'pre2', 'nor1', 'nor2'):
            bb = BitmapButton(xas, get_icon('plus'),
                              action=partial(self.on_selpoint, opt=name),
                              tooltip='use last point selected from plot')
            self.btns[name] = bb

        opts = {'size': (85, -1), 'precision': 3,
                'action': self.UpdatePlot}

        self.xas_e0   = FloatCtrl(xas, value  = 0, **opts)
        self.xas_step = FloatCtrl(xas, value  = 0, **opts)
        opts['precision'] = 1
        self.xas_pre1 = FloatCtrl(xas, value=-200, **opts)
        self.xas_pre2 = FloatCtrl(xas, value= -30, **opts)
        self.xas_nor1 = FloatCtrl(xas, value=  50, **opts)
        self.xas_nor2 = FloatCtrl(xas, value= -50, **opts)

        opts = {'size': (50, -1),
                'choices': ('0', '1', '2', '3'),
                'action': self.UpdatePlot}
        self.xas_vict = Choice(xas, **opts)
        self.xas_nnor = Choice(xas, **opts)
        self.xas_vict.SetSelection(1)
        self.xas_nnor.SetSelection(2)
        sizer = wx.GridBagSizer(5, 5)


        ir = 0
        sizer.Add(SimpleText(xas, ' XAS Data Processing', **titleopts),
                  (ir, 0), (1, 7), LCEN, 0)

        ir += 1
        sizer.Add(SimpleText(xas, 'Arrays to Plot: '),  (ir, 0), (1, 1), LCEN)
        sizer.Add(self.xas_op,                           (ir, 1), (1, 7), LCEN)

        ir += 1
        sizer.Add(SimpleText(xas, 'E0 : '),   (ir, 0), (1, 1), LCEN)
        sizer.Add(self.btns['e0'],             (ir, 1), (1, 1), LCEN)
        sizer.Add(self.xas_e0,                 (ir, 2), (1, 1), LCEN)
        sizer.Add(self.xas_autoe0,             (ir, 3), (1, 2), LCEN)
        sizer.Add(self.xas_showe0,             (ir, 5), (1, 2), LCEN)


        ir += 1
        sizer.Add(SimpleText(xas, 'Edge Step: '),  (ir, 0), (1, 1), LCEN)
        sizer.Add(self.xas_step,               (ir, 2), (1, 1), LCEN)
        sizer.Add(self.xas_autostep,           (ir, 3), (1, 3), LCEN)

        ir += 1
        sizer.Add(SimpleText(xas, 'Pre-edge range: '),  (ir, 0), (1, 1), LCEN)
        sizer.Add(self.btns['pre1'],           (ir, 1), (1, 1), LCEN)
        sizer.Add(self.xas_pre1,               (ir, 2), (1, 1), LCEN)
        sizer.Add(SimpleText(xas, ':'),       (ir, 3), (1, 1), LCEN)
        sizer.Add(self.btns['pre2'],           (ir, 4), (1, 1), LCEN)
        sizer.Add(self.xas_pre2,               (ir, 5), (1, 1), LCEN)
        sizer.Add(SimpleText(xas, 'Victoreen:'), (ir, 6), (1, 1), LCEN)
        sizer.Add(self.xas_vict,               (ir, 7), (1, 1), LCEN)

        ir += 1
        sizer.Add(SimpleText(xas, 'Normalization range: '), (ir, 0), (1, 1), LCEN)
        sizer.Add(self.btns['nor1'],           (ir, 1), (1, 1), LCEN)
        sizer.Add(self.xas_nor1,               (ir, 2), (1, 1), LCEN)
        sizer.Add(SimpleText(xas, ':'),          (ir, 3), (1, 1), LCEN)
        sizer.Add(self.btns['nor2'],           (ir, 4), (1, 1), LCEN)
        sizer.Add(self.xas_nor2,               (ir, 5), (1, 1), LCEN)
        sizer.Add(SimpleText(xas, 'PolyOrder:'), (ir, 6), (1, 1), LCEN)
        sizer.Add(self.xas_nnor,               (ir, 7), (1, 1), LCEN)
        ir +=1

        pack(xas, sizer)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.AddMany([((10,10), 0, LCEN, 0),
                       (gen,  0, LCEN, 10),
                       ((10,10), 0, LCEN, 0),
                       (HLine(self, size=(550, 2)), 0, LCEN, 10),
                       ((10,10), 0, LCEN, 0),
                       (xas,  1, LCEN|wx.GROW, 10)])

        xas.Disable()

        pack(self, sizer)

    def onSmoothChoice(self, evt=None, value=1):
        try:
            choice = self.smooth_op.GetStringSelection().lower()
            conv  = self.smooth_conv.GetStringSelection()
            self.smooth_c0.Disable()
            self.smooth_c1.Disable()
            self.smooth_conv.Disable()
            self.smooth_sig.Disable()

            if choice.startswith('box'):
                self.smooth_c0.Enable()
            elif choice.startswith('savi'):
                self.smooth_c0.Enable()
                self.smooth_c1.Enable()
            elif choice.startswith('conv'):
                self.smooth_conv.Enable()
                self.smooth_sig.Enable()
            self.needs_update = True
        except AttributeError:
            pass


    def onProcessTimer(self, evt=None):
        if self.main.groupname is not None and self.needs_update:
            self.process(self.main.groupname)
            self.main.plot_group(self.main.groupname, new=True)
            self.needs_update = False

    def UpdatePlot(self, evt=None, **kws):
        self.needs_update = True

    def on_selpoint(self, evt=None, opt='e0'):
        xval = None
        if self.larch is None:
            self.larch = self.main.larch
        try:
            xval = self.larch.symtable._plotter.plot1_x
            yval = self.larch.symtable._plotter.plot1_y
        except:
            pass
        if xval is None:
            return

        e0 = self.xas_e0.GetValue()
        if opt == 'e0':
            self.xas_e0.SetValue(xval)
            self.xas_autoe0.SetValue(0)
        elif opt == 'pre1':
            self.xas_pre1.SetValue(xval-e0)
        elif opt == 'pre2':
            self.xas_pre2.SetValue(xval-e0)
        elif opt == 'nor1':
            self.xas_nor1.SetValue(xval-e0)
        elif opt == 'nor2':
            self.xas_nor2.SetValue(xval-e0)
        elif opt == 'xshift':
            self.xshift.SetValue(xval)
        elif opt == 'yshift':
            self.yshift.SetValue(yval)


    def process(self, gname, new_mu=False, **kws):
        """ process (pre-edge/normalize) XAS data from XAS form, overwriting
        larch group '_y1_' attribute to be plotted
        """
        if self.larch is None:
            self.larch = self.main.larch
        dgroup = getattr(self.larch.symtable, gname)
        if not hasattr(dgroup, 'proc_opts'):
            dgroup.proc_opts = Group(datatype='xas')
        if not hasattr(dgroup, 'plot_opts'):
            dgroup.plot_opts = Group(datatype='xas')
        proc_opts = dgroup.proc_opts
        plot_opts = dgroup.plot_opts

        proc_opts.xshift = self.xshift.GetValue()
        proc_opts.yshift = self.yshift.GetValue()
        proc_opts.xscale = self.xscale.GetValue()
        proc_opts.yscale = self.yscale.GetValue()

        dgroup.x = proc_opts.xscale*(dgroup.xdat - proc_opts.xshift)
        dgroup.y = proc_opts.yscale*(dgroup.ydat - proc_opts.yshift)

        # apply smoothhing here
        proc_opts.smooth_op = self.smooth_op.GetStringSelection()
        proc_opts.smooth_c0 = int(self.smooth_c0.GetValue())
        proc_opts.smooth_c1 = int(self.smooth_c1.GetValue())
        proc_opts.smooth_sig = float(self.smooth_sig.GetValue())
        proc_opts.smooth_conv = self.smooth_conv.GetStringSelection()

        smop = proc_opts.smooth_op.lower()
        cform = str(proc_opts.smooth_conv.lower())
        if smop.startswith('box'):
            dgroup.y = boxcar(dgroup.y, proc_opts.smooth_c0)
        elif smop.startswith('savit'):
            winsize = 2*proc_opts.smooth_c0 + 1
            dgroup.y = savitzky_golay(dgroup.y, winsize, proc_opts.smooth_c1)
        elif smop.startswith('conv'):
            dgroup.y = smooth(dgroup.x, dgroup.y,
                              sigma=proc_opts.smooth_sig, form=cvform)

        if dgroup.datatype.startswith('xas'):
            dgroup.energy = dgroup.x
            dgroup.mu = dgroup.y

            e0 = None
            if not self.xas_autoe0.IsChecked():
                _e0 = self.xas_e0.GetValue()
                if _e0 < max(dgroup.energy) and _e0 > min(dgroup.energy):
                    e0 = float(_e0)

            preopts = {'e0': e0}
            if not self.xas_autostep.IsChecked():
                preopts['step'] = self.xas_step.GetValue()
            preopts['pre1']  = self.xas_pre1.GetValue()
            preopts['pre2']  = self.xas_pre2.GetValue()
            preopts['norm1'] = self.xas_nor1.GetValue()
            preopts['norm2'] = self.xas_nor2.GetValue()
            preopts['nvict'] = self.xas_vict.GetSelection()
            preopts['nnorm'] = self.xas_nnor.GetSelection()
            preopts['make_flat'] = False
            preopts['_larch'] = self.larch

            pre_edge(dgroup, **preopts)

            for attr in  ('e0', 'edge_step'):
                setattr(proc_opts, attr, getattr(dgroup, attr))
            for attr in  ('pre1', 'pre2', 'norm1', 'norm2'):
                setattr(proc_opts, attr, getattr(dgroup.pre_edge_details, attr))

            proc_opts.auto_e0 = self.xas_autoe0.IsChecked()
            proc_opts.show_e0 = self.xas_showe0.IsChecked()
            proc_opts.auto_step = self.xas_autostep.IsChecked()
            proc_opts.nnorm = int(self.xas_nnor.GetSelection())
            proc_opts.nvict = int(self.xas_vict.GetSelection())
            proc_opts.xas_opt = self.xas_op.GetSelection()

            if self.xas_autoe0.IsChecked():
                self.xas_e0.SetValue(dgroup.e0)
            if self.xas_autostep.IsChecked():
                self.xas_step.SetValue(dgroup.edge_step)

            self.xas_pre1.SetValue(proc_opts.pre1)
            self.xas_pre2.SetValue(proc_opts.pre2)
            self.xas_nor1.SetValue(proc_opts.norm1)
            self.xas_nor2.SetValue(proc_opts.norm2)

            dgroup.orig_ylabel = dgroup.plot_ylabel
            dgroup.plot_ylabel = '$\mu$'
            dgroup.plot_y2label = None
            dgroup.plot_xlabel = '$E \,\mathrm{(eV)}$'
            dgroup.plot_yarrays = [(dgroup.mu, PLOTOPTS_1, dgroup.plot_ylabel)]
            y4e0 = dgroup.mu

            out = self.xas_op.GetStringSelection().lower() # raw, pre, norm, flat
            if out.startswith('raw data + pre'):
                dgroup.plot_yarrays = [(dgroup.mu,        PLOTOPTS_1, '$\mu$'),
                                       (dgroup.pre_edge,  PLOTOPTS_2, 'pre edge'),
                                       (dgroup.post_edge, PLOTOPTS_2, 'post edge')]
            elif out.startswith('pre'):
                dgroup.pre_edge_sub = dgroup.norm * dgroup.edge_step
                dgroup.plot_yarrays = [(dgroup.pre_edge_sub, PLOTOPTS_1,
                                        'pre-edge subtracted $\mu$')]
                y4e0 = dgroup.pre_edge_sub
                dgroup.plot_ylabel = 'pre-edge subtracted $\mu$'
            elif 'norm' in out and 'deriv' in out:
                dgroup.plot_yarrays = [(dgroup.norm, PLOTOPTS_1, 'normalized $\mu$'),
                                       (dgroup.dmude, PLOTOPTS_D, '$d\mu/dE$')]
                y4e0 = dgroup.norm
                dgroup.plot_ylabel = 'normalized $\mu$'
                dgroup.plot_y2label = '$d\mu/dE$'
                dgroup.y = dgroup.norm

            elif out.startswith('norm'):
                dgroup.plot_yarrays = [(dgroup.norm, PLOTOPTS_1, 'normalized $\mu$')]
                y4e0 = dgroup.norm
                dgroup.plot_ylabel = 'normalized $\mu$'
                dgroup.y = dgroup.norm

            elif out.startswith('deriv'):
                dgroup.plot_yarrays = [(dgroup.dmude, PLOTOPTS_1, '$d\mu/dE$')]
                y4e0 = dgroup.dmude
                dgroup.plot_ylabel = '$d\mu/dE$'
                dgroup.y = dgroup.dmude

            dgroup.plot_ymarkers = []
            if self.xas_showe0.IsChecked():
                ie0 = index_of(dgroup.xdat, dgroup.e0)
                dgroup.plot_ymarkers = [(dgroup.e0, y4e0[ie0], {'label': 'e0'})]


class FitPanel(wx.Panel):
    def __init__(self, parent=None, main=None, **kws):

        wx.Panel.__init__(self, parent, -1, **kws)

        self.parent = parent
        self.main  = main
        self.fit_components = []
        self.sizer = wx.GridBagSizer(10, 6)
        self.build_display()

    def build_display(self):

        self.modelpanel = scrolled.ScrolledPanel(self, style=wx.GROW|wx.TAB_TRAVERSAL)
        self.modelsizer = wx.BoxSizer(wx.VERTICAL)

        pack(self.modelpanel, self.modelsizer)
        self.modelpanel.SetupScrolling()

        top = wx.Panel(self)

        models = Choice(top, size=(150, -1), choices=ModelChoices,
                        action=self.addModel)
        steps = Choice(top, size=(150, -1), choices=StepChoices,
                       action=partial(self.addModel, is_step=True))

        row   = wx.Panel(top)
        rsizer = wx.BoxSizer(wx.HORIZONTAL)

        fit_btn  = Button(row, 'Do Fit', size=(100, -1), action=self.onRunFit)
        save_btn = Button(row, 'Save Fit', size=(100, -1), action=self.onSaveFit)

        self.xmin_sel = BitmapButton(row, get_icon('plus'),
                                     action=partial(self.on_selpoint, opt='xmin'),
                                     tooltip='use last point selected from plot')
        self.xmax_sel = BitmapButton(row, get_icon('plus'),
                                     action=partial(self.on_selpoint, opt='xmax'),
                                     tooltip='use last point selected from plot')

        opts = {'size': (90, -1), 'precision': 3}
        self.xmin = FloatCtrl(row, value=0, **opts)
        self.xmax = FloatCtrl(row, value=0, **opts)

        rsizer.Add(SimpleText(row, 'Fit Range: [ '), 0, LCEN, 3)
        rsizer.Add(self.xmin_sel, 0, LCEN, 3)
        rsizer.Add(self.xmin,     0, LCEN, 3)
        rsizer.Add(SimpleText(row, ' : '),  0, LCEN, 3)
        rsizer.Add(self.xmax_sel, 0, LCEN, 3)
        rsizer.Add(self.xmax,     0, LCEN, 3)
        rsizer.Add(SimpleText(row, ' ]  '), 0, LCEN, 3)
        rsizer.Add(fit_btn,       0, LCEN, 3)
        rsizer.Add(save_btn,      0, LCEN, 3)

        pack(row, rsizer)

        sizer = wx.GridBagSizer(5, 5)
        ir = 0
        sizer.Add(HLine(self, size=(550, 2)), (ir, 0), (1, 8), LCEN)

        ir += 1
        sizer.Add(row, (ir, 0), (1, 6), LCEN)

        ir += 1
        sizer.Add(SimpleText(top, ' Add Model: '),      (ir, 0), (1, 1), LCEN)
        sizer.Add(models,                     (ir, 1), (1, 2), LCEN)
        sizer.Add(SimpleText(top, ' Add Step Model: '), (ir, 3), (1, 1), LCEN)
        sizer.Add(steps,                      (ir, 4), (1, 2), LCEN)

        pack(top, sizer)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.AddMany([((10,10), 0, LCEN, 0),
                       (top,  0, LCEN, 10),
                       ((10,10), 0, LCEN, 0),
                       (HLine(self, size=(550, 2)), 0, LCEN, 10),
                       ((10,10), 0, LCEN, 0),
                       (self.modelpanel,  1, LCEN|wx.GROW, 10)])

        pack(self, sizer)

    def addModel(self, event=None, model=None, is_step=False):
        if model is None and event is not None:
            model = event.GetString()
        if model is None:
            return

        def Label(t): return SimpleText(self.modelpanel, t)

        title = model
        if is_step:
            title = "Step(%s)" % model
            form = model.lower()
            if form.startswith('err'): form = 'erf'
            mclass = lm_models.StepModel
            minst = mclass(form=form)
        else:
            mclass = getattr(lm_models, model+'Model')
            minst = mclass()

        imod = len(self.fit_components) + 1

        prefix = "p%i" % imod

        print("Add Model ", model, mclass, minst.param_names)

        mpanel = self.modelpanel

        modbox = wx.StaticBox(mpanel, -1, "Component %i: %s" % (imod, title))

        sizer = wx.GridBagSizer(3, 3)

        mname  = wx.TextCtrl(modbox, -1, prefix, size=(80, -1))
        usebox = Check(modbox, default=True, label='Use in Model', size=(100, -1))
        delbtn = Button(modbox, 'Delete', size=(80, -1),
                        action=partial(self.onDeleteComponent, comp=imod))

        pick3btn = Button(modbox, 'Pick 3 Points', size=(80, -1),
                          action=partial(self.onPick3Points, comp=imod))
        pick3msg = SimpleText(modbox, "    ", size=(100, -1))

        sizer.Add(SimpleText(modbox, "Name"), (0, 0), (1, 1), LCEN, 2)
        sizer.Add(mname,     (0, 1), (1, 1), LCEN, 2)
        sizer.Add(usebox,    (0, 2), (1, 1), LCEN, 2)
        sizer.Add(pick3btn,  (0, 3), (1, 1), LCEN, 2)
        sizer.Add(pick3msg,  (0, 4), (1, 1), LCEN, 2)
        sizer.Add(delbtn,    (0, 5), (1, 1), LCEN, 2)

        t2 = SimpleText(modbox, "%s" % repr(minst.param_names))
        sizer.Add(t2,        (1, 1), (1, 3), LCEN|wx.GROW, 2)

        self.fit_components.append((imod, modbox, mpanel, mname, usebox, delbtn, pick3btn, pick3msg))

        pack(modbox, sizer)


        self.modelsizer.Add(modbox, 0, LCEN|wx.GROW, 2)
        pack(self.modelpanel, self.modelsizer)


    def onDeleteComponent(self, evt=None, comp=-1):
        pass

    def onPick3Points(self, evt=None, comp=-1):
        pass

    def onSaveFit(self, event=None):
        pass

    def on_selpoint(self, evt=None, opt='xmin'):
        xval = None
        try:
            xval = self.main.larch.symtable._plotter.plot1_x
        except:
            xval = None
        if xval is not None:
            if opt == 'xmin':
                self.xmin.SetValue(xval)
            elif opt == 'xmax':
                self.xmax.SetValue(xval)

    def onRunFit(self, event=None):
        gname = self.main.groupname

        dtext = []
        model = self.fit_model.GetStringSelection().lower()
        dtext.append('Fit Model: %s' % model)
        bkg =  self.fit_bkg.GetStringSelection()
        if bkg == 'None':
            bkg = None
        if bkg is None:
            dtext.append('No Background')
        else:
            dtext.append('Background: %s' % bkg)

        step = self.fit_step.GetStringSelection().lower()
        if model in ('step', 'rectangle'):
            dtext.append('Step form: %s' % step)

        try:
            lgroup =  getattr(self.main.larch.symtable, gname)
            x = lgroup.xdat
            y = lgroup.ydat
        except AttributeError:
            self.main.write_message('need data to fit!')
            return
        if step.startswith('error'):
            step = 'erf'
        elif step.startswith('arctan'):
            step = 'atan'

        pgroup = fit_peak(x, y, model, background=bkg, step=step,
                          _larch=self.larch)

        dtext = '\n'.join(dtext)
        dtext = '%s\n%s\n' % (dtext, fit_report(pgroup.params, min_correl=0.25,
                                                _larch=self.larch))

        self.main.show_subframe('fitreport', ReportFrame)
        self.main.subframes['fitreport'].set_text(dtext)

        if not hasattr(lgroup, 'fits'):
            lgroup.fits = []

        lgroup.fits.append((model, bkg, step, dtext))

        lgroup.plot_yarrays = [(lgroup.y, PLOTOPTS_1, lgroup.plot_ylabel)]
        if bkg is None:
            lgroup._fit = pgroup.fit[:]
            lgroup.plot_yarrays.append((lgroup._fit, PLOTOPTS_2, 'fit'))
        else:
            lgroup._fit     = pgroup.fit[:]
            lgroup._fit_bgr = pgroup.bkg[:]
            lgroup.plot_yarrays.append((lgroup._fit,    PLOTOPTS_2, 'fit'))
            lgroup.plot_yarrays.append((lgroup._fit_bgr, PLOTOPTS_2, 'background'))
        self.main.plot_group(gname, new=True)


class ScanViewerFrame(wx.Frame):
    _about = """Scan 2D Plotter
  Matt Newville <newville @ cars.uchicago.edu>
  """
    def __init__(self, parent=None, size=(850, 650), _larch=None, **kws):
        wx.Frame.__init__(self, parent, -1, size=size, style=FRAMESTYLE)
        self.file_groups = {}
        self.last_array_sel = {}
        title = "Column Data File Viewer"
        self.larch = _larch
        self.larch_buffer = None
        self.subframes = {}
        self.plotframe = None
        self.groupname = None
        self.SetTitle(title)
        self.SetSize(size)
        self.SetFont(Font(10))

        self.config = {'chdir_on_fileopen': True}

        self.createMainPanel()
        self.createMenus()
        self.statusbar = self.CreateStatusBar(2, 0)
        self.statusbar.SetStatusWidths([-3, -1])
        statusbar_fields = ["Initializing....", " "]
        for i in range(len(statusbar_fields)):
            self.statusbar.SetStatusText(statusbar_fields[i], i)
        # read_workdir('scanviewer.dat')

    def createMainPanel(self):
        splitter  = wx.SplitterWindow(self, style=wx.SP_LIVE_UPDATE)
        splitter.SetMinimumPaneSize(225)

        leftpanel = wx.Panel(splitter)
        ltop = wx.Panel(leftpanel)

        plot_one = Button(ltop, 'Plot One',
                          size=(100, 40),
                          action=self.onPlotOne)
        plot_sel = Button(ltop, 'Plot Selected',
                          size=(100, 40),
                          action=self.onPlotSel)
        plot_one.SetFont(Font(12))
        plot_sel.SetFont(Font(12))
        self.filelist = FileCheckList(leftpanel, main=self,
                                      select_action=self.ShowFile)
        self.filelist.SetBackgroundColour(wx.Colour(255, 255, 255))

        tsizer = wx.GridBagSizer(5, 5)
        tsizer.Add(plot_one, (0, 0), (1, 1), LCEN, 2)
        tsizer.Add(plot_sel, (0, 1), (1, 1), LCEN, 2)

        pack(ltop, tsizer)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(ltop, 0, LCEN|wx.GROW, 1)
        sizer.Add(self.filelist, 1, LCEN|wx.GROW|wx.ALL, 1)

        pack(leftpanel, sizer)

        # right hand side
        panel = wx.Panel(splitter)
        sizer = wx.BoxSizer(wx.VERTICAL)

        self.title = SimpleText(panel, 'initializing...')
        self.title.SetFont(Font(10))

        ir = 0
        sizer.Add(self.title, 0, LCEN|wx.GROW|wx.ALL, 1)

        self.nb = flat_nb.FlatNotebook(panel, -1, agwStyle=FNB_STYLE)

        self.nb.SetTabAreaColour(wx.Colour(250,250,250))
        self.nb.SetActiveTabColour(wx.Colour(254,254,195))

        self.nb.SetNonActiveTabTextColour(wx.Colour(10,10,128))
        self.nb.SetActiveTabTextColour(wx.Colour(128,0,0))

        self.proc_panel = ProcessPanel(parent=self.nb, main=self)
        self.fit_panel =  FitPanel(parent=self.nb, main=self)

        self.nb.AddPage(self.proc_panel, ' Data Processing ',   True)
        self.nb.AddPage(self.fit_panel,  ' Curve Fitting ',  True)

        sizer.Add(self.nb, 1, LCEN|wx.EXPAND, 2)
        self.nb.SetSelection(0)

        pack(panel, sizer)

        splitter.SplitVertically(leftpanel, panel, 1)
        wx.CallAfter(self.init_larch)


    def init_larch(self):
        t0 = time.time()
        if self.larch is None:
            self.larch = Interpreter()
        self.larch.symtable.set_symbol('_sys.wx.wxapp', wx.GetApp())
        self.larch.symtable.set_symbol('_sys.wx.parent', self)

        self.SetStatusText('ready')
        self.title.SetLabel('')

        # self.fit_panel.larch = self.larch
        larchdir = self.larch.symtable._sys.config.larchdir
        fico = os.path.join(larchdir, 'icons', ICON_FILE)
        if os.path.exists(fico):
            self.SetIcon(wx.Icon(fico, wx.BITMAP_TYPE_ICO))

        plotframe = self.larch.symtable._plotter.get_display(
            wintitle='DataViewer Plot Window')
        xpos, ypos = self.GetPosition()
        xsiz, ysiz = self.GetSize()
        plotframe.SetPosition((xpos+xsiz, ypos))
        self.Raise()

    def write_message(self, s, panel=0):
        """write a message to the Status Bar"""
        self.SetStatusText(s, panel)


    def onPlotOne(self, evt=None, groupname=None):
        if groupname is None:
            groupname = self.groupname

        dgroup = getattr(self.larch.symtable, groupname, None)
        if dgroup is None:
            return
        self.groupname = groupname
        if (dgroup.datatype == 'xas' and
            (getattr(dgroup, 'plot_yarrays', None) is None or
             getattr(dgroup, 'energy', None) is None or
             getattr(dgroup, 'mu', None) is None)):
            self.proc_panel.xaspanel.Enable()
            self.proc_panel.process(groupname)
        self.plot_group(groupname, new=True)

    def onPlotSel(self, evt=None):
        newplot = True
        group_ids = self.filelist.GetCheckedStrings()
        for checked in group_ids:
            groupname = self.file_groups[str(checked)]
            dgroup = getattr(self.larch.symtable, groupname, None)
            if dgroup is None:
                continue
            dgroup.plot_yarrays = [(dgroup.y, PLOTOPTS_1,
                                    dgroup.filename)]

            if dgroup.datatype == 'xas':
                if ((getattr(dgroup, 'plot_yarrays', None) is None or
                     getattr(dgroup, 'energy', None) is None or
                     getattr(dgroup, 'mu', None) is None)):
                    self.proc_panel.process(groupname)

                dgroup.plot_ylabel = 'normalized $\mu$'
                dgroup.plot_xlabel = '$E\,\mathrm{(eV)}$'
                dgroup.plot_ymarkers = []

            self.plot_group(groupname, title='', new=newplot)
            newplot=False

    def plot_group(self, groupname, title=None, new=True):
        oplot = self.larch.symtable._plotter.plot
        newplot = self.larch.symtable._plotter.newplot
        getdisplay = self.larch.symtable._plotter.get_display

        plotcmd = oplot
        if new:
            plotcmd = newplot

        dgroup = getattr(self.larch.symtable, groupname, None)
        if not hasattr(dgroup, 'xdat'):
            print("Cannot plot group ", groupname)

        if not hasattr(dgroup, 'x'):
            dgroup.x = dgroup.xdat[:]
        if not hasattr(dgroup, 'y'):
            dgroup.y = dgroup.ydat[:]


        if hasattr(dgroup, 'plot_yarrays'):
            plot_yarrays = dgroup.plot_yarrays
        else:
            plot_yarrays = [(dgroup.y, {}, None)]
        # print("Plt Group ", groupname, hasattr(dgroup,'plot_yarrays'))

        popts = {}
        path, fname = os.path.split(dgroup.filename)
        popts['label'] = "%s: %s" % (fname, dgroup.plot_ylabel)
        popts['xlabel'] = dgroup.plot_xlabel
        popts['ylabel'] = dgroup.plot_ylabel
        if getattr(dgroup, 'plot_y2label', None) is not None:
            popts['y2label'] = dgroup.plot_y2label

        if plotcmd == newplot and title is None:
            title = fname

        popts['title'] = title
        popts['wintitle'] = 'DataViewer Plot Window'
        for yarr in plot_yarrays:
            popts.update(yarr[1])
            if yarr[2] is not None:
                popts['label'] = yarr[2]
            plotcmd(dgroup.x, yarr[0], **popts)
            plotcmd = oplot # self.plotpanel.oplot

        ppanel = getdisplay(_larch=self.larch).panel
        if hasattr(dgroup, 'plot_ymarkers'):
            axes = ppanel.axes
            for x, y, opts in dgroup.plot_ymarkers:
                popts = {'marker': 'o', 'markersize': 4,
                         'markerfacecolor': 'red',
                         'markeredgecolor': 'black'}
                popts.update(opts)
                axes.plot([x], [y], **popts)
        ppanel.canvas.draw()
        self.Raise()


    def onShowLarchBuffer(self, evt=None):
        if self.larch_buffer is None:
            self.larch_buffer = larchframe.LarchFrame(parent=self,
                                                      _larch=self.larch)

        self.larch_buffer.Show()
        self.larch_buffer.Raise()

    def ShowFile(self, evt=None, groupname=None, **kws):
        if groupname is None and evt is not None:
            groupname = self.file_groups[str(evt.GetString())]

        if not hasattr(self.larch.symtable, groupname):
            print( 'Error reading file ', groupname)
            return

        self.groupname = groupname
        self.dgroup = getattr(self.larch.symtable, groupname, None)

        self.nb.SetSelection(0)
        if self.dgroup.datatype == 'xas':
            self.proc_panel.xaspanel.Enable()
            self.proc_panel.fill(self.dgroup)
        else:
            self.proc_panel.xaspanel.Disable()

        self.title.SetLabel(str(evt.GetString()))


    def createMenus(self):
        # ppnl = self.plotpanel
        self.menubar = wx.MenuBar()
        #
        fmenu = wx.Menu()
        MenuItem(self, fmenu, "&Open Data File\tCtrl+O",
                 "Read Scan File",  self.onReadDialog)

        MenuItem(self, fmenu, "Show Larch Buffer\tCtrl+L",
                  "Show Larch Programming Buffer",
                  self.onShowLarchBuffer)


        MenuItem(self, fmenu, "Re-select Data Columns\tCtrl+R",
                 "Change which data columns used for this file",
                 self.onEditColumns)

        fmenu.AppendSeparator()
        MenuItem(self, fmenu, "debug wx", "debug", self.showInspectionTool)
        MenuItem(self, fmenu, "&Quit\tCtrl+Q", "Quit program", self.onClose)


        self.menubar.Append(fmenu, "&File")

        omenu = wx.Menu()
        self.menubar.Append(omenu, "Options")

        self.SetMenuBar(self.menubar)
        self.Bind(wx.EVT_CLOSE,  self.onClose)

    def showInspectionTool(self, event=None):
        app = wx.GetApp()
        app.ShowInspectionTool()

    def onAbout(self,evt):
        dlg = wx.MessageDialog(self, self._about,"About ScanViewer",
                               wx.OK | wx.ICON_INFORMATION)
        dlg.ShowModal()
        dlg.Destroy()

    def onClose(self, evt):
        save_workdir('scanviewer.dat')
        sys.stderr.write("SAVED scanviewer.dat\n")
        self.proc_panel.proc_timer.Stop()

        if self.larch_buffer is not None:
            try:
                self.larch_buffer.onClose()
            except:
                pass

        for nam in dir(self.larch.symtable._plotter):
            obj = getattr(self.larch.symtable._plotter, nam)
            try:
                obj.Destroy()
            except:
                pass
        for nam in dir(self.larch.symtable._sys.wx):
            obj = getattr(self.larch.symtable._sys.wx, nam)
            del obj

        self.Destroy()

    def show_subframe(self, name, frameclass, **opts):
        shown = False
        if name in self.subframes:
            try:
                self.subframes[name].Raise()
                shown = True
            except:
                del self.subframes[name]
        if not shown:
            self.subframes[name] = frameclass(self, **opts)

    def onEditColumns(self, evt=None):
        self.show_subframe('coledit', EditColumnFrame,
                           group=self.dgroup.raw,
                           last_array_sel=self.last_array_sel,
                           _larch=self.larch,
                           read_ok_cb=partial(self.onRead_OK,
                                              overwrite=True))

    def onReadDialog(self, evt=None):
        dlg = wx.FileDialog(self, message="Load Column Data File",
                            defaultDir=os.getcwd(),
                            wildcard=FILE_WILDCARDS, style=wx.FD_OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            path = path.replace('\\', '/')

            self.onRead(path)
        dlg.Destroy()

    def onRead(self, path):
        if path in self.file_groups:
            if wx.ID_YES != popup(self, "Re-read file '%s'?" % path,
                                  'Re-read file?'):
                return
        filedir, filename = os.path.split(path)
        pref= fix_varname(filename.replace('.', '_'))
        if len(pref) > 15:
            pref = pref[:15]
        groupname = pref
        count, maxcount = 0, 999
        while hasattr(self.larch.symtable, groupname) and count < maxcount:
            count += 1
            groupname = '%s_%2.2i' % (pref, count)

        if self.config['chdir_on_fileopen']:
            os.chdir(filedir)

        fh = open(path, 'r')
        line1 = fh.readline().lower()
        fh.close()

        reader = read_ascii
        if 'epics stepscan file' in line1:
            reader = read_gsexdi
        elif 'epics scan' in line1:
            reader = gsescan_group
        elif 'xdi' in line1:
            reader = read_xdi

        dgroup = reader(str(path), _larch=self.larch)
        if reader == gsescan_group:
            assign_gsescan_groups(dgroup)
        dgroup.path = path
        dgroup.filename = filename
        dgroup.groupname = groupname
        self.show_subframe('coledit', EditColumnFrame, group=dgroup,
                           last_array_sel=self.last_array_sel,
                           _larch=self.larch,
                           read_ok_cb=partial(self.onRead_OK,
                                              overwrite=False))

    def onRead_OK(self, datagroup, array_sel, overwrite=False):
        """ called when column data has been selected and is ready to be used
        overwrite: whether to overwrite the current datagroup, as when editing a datagroup

        """
        self.last_array_sel = array_sel
        filename = datagroup.filename
        groupname= datagroup.groupname
        # print("READ SCAN  storing datagroup ", datagroup, groupname, filename)
        # file /group may already exist in list
        if filename in self.file_groups and not overwrite:
            for i in range(1, 101):
                ftest = "%s (%i)"  % (filename, i)
                if ftest not in self.file_groups:
                    filename = ftest
                    break

        if filename not in self.file_groups:
            self.filelist.Append(filename)
            self.file_groups[filename] = groupname

        setattr(self.larch.symtable, groupname, datagroup)
        if datagroup.datatype == 'xas':
            self.proc_panel.fill(datagroup)
        self.nb.SetSelection(0)
        self.onPlotOne(groupname=groupname)

class ScanViewer(wx.App, wx.lib.mixins.inspection.InspectionMixin):
    def __init__(self, **kws):
        wx.App.__init__(self, **kws)

    def run(self):
        self.MainLoop()

    def createApp(self):
        frame = ScanViewerFrame()
        frame.Show()
        self.SetTopWindow(frame)

    def OnInit(self):
        self.createApp()
        return True

class DebugScanViewer(ScanViewer, wx.lib.mixins.inspection.InspectionMixin):
    def __init__(self, **kws):
        ScanViewer.__init__(self, **kws)

    def OnInit(self):
        self.Init()
        self.createApp()
        self.ShowInspectionTool()
        return True

def initializeLarchPlugin(_larch=None):
    """add ScanFrameViewer to _sys.gui_apps """
    if _larch is not None:
        _sys = _larch.symtable._sys
        if not hasattr(_sys, 'gui_apps'):
            _sys.gui_apps = {}
        _sys.gui_apps['scanviewer'] = ('Scan Viewer', ScanViewerFrame)

def registerLarchPlugin():
    return ('_wx', {})

if __name__ == "__main__":
    ScanViewer().run()
