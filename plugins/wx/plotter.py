'''
   Plotting functions for Larch, wrapping the mplot plotting
   widgets which use matplotlib

Exposed functions here are
   plot:  display 2D line plot to an enhanced,
            configurable Plot Frame
   oplot: overplot a 2D line plot on an existing Plot Frame
   imshow: display a false-color map from array data on
           a configurable Image Display Frame.
'''
import time
import wx
import  wx.lib.newevent
from wxmplot import PlotFrame, ImageFrame
import thread

(CursorEvent, EVT_PLOT_CURSOR) = wx.lib.newevent.NewEvent()

IMG_DISPLAYS = {}
PLOT_DISPLAYS = {}
MODNAME = '_plotter'

def ensuremod(larch):
    if larch is not None:
        symtable = larch.symtable
        if not symtable.has_group(MODNAME):
            symtable.newgroup(MODNAME)
        return symtable

class CursorThread:
    def __init__(self, parent, plotwin):
        self.parent = parent
        self.plotwin = plotwin

    def Start(self):
        self.keepGoing = self.running = True
        thread.start_new_thread(self.Run, ())

    def Stop(self):
        self.keepGoing = False

    def Run(self):
        self.running = True
        while self.keepGoing:
            wx.PostEvent(self.parent, CursorEvent(win=self.plotwin))
            time.sleep(0.1)
        self.running = False

class CursorFrame(wx.MiniFrame):
    """hidden wx frame that simply waits for cursor to be set
    """
    def __init__(self, parent, larch=None, win=None, plotter=None, **kws):
        wx.MiniFrame.__init__(self, parent, -1, '')
        self.Show(False)
        self.plotter = plotter
        self.symtable = ensuremod(larch)
        self.xval = '%s.plot%i_x' % (MODNAME, win)
        self.yval = '%s.plot%i_y' % (MODNAME, win)
        if self.symtable.has_symbol(self.xval):
            self.symtable.del_symbol(self.xval)

        self.has_cursor = False
        self.Bind(EVT_PLOT_CURSOR, self.onUpdate)
        self.Bind(wx.EVT_CLOSE, self.onClose)
        self.thread = CursorThread(self, win)
        self.thread.Start()
        
    def onClose(self, evt=None):
        wx.Yield()
        self.thread.Stop()
        while self.thread.running:
            time.sleep(0.1)
        
    def onUpdate(self, evt=None):
        self.has_cursor = self.symtable.has_symbol(self.xval) 
        
    def wait_for_cursor(self, timeout=60.0):
        """wait for and return most recent cursor position"""
        self.has_cursor = False
        t0 = time.time()
        if self.symtable.has_symbol(self.xval):
            self.symtable.del_symbol(self.xval)

        app = wx.GetApp()
        # note that evtloop.Dispatch() seems to be very
        # important for allowing other windows to update!
        evtloop = wx.EventLoop()
        while (not self.has_cursor and
               time.time() - t0 < timeout):
            time.sleep(0.1)
            wx.Yield()
            app.ProcessIdle()
            while evtloop.Pending():
                evtloop.Dispatch()
        self.thread.Stop()

        
class PlotDisplay(PlotFrame):
    def __init__(self, wxparent=None, window=1, larch=None, **kws):
        PlotFrame.__init__(self, parent=wxparent,
                                 exit_callback=self.onExit, **kws)
        self.Show()
        self.Raise()
        self.cursor_pos = None
        self.panel.cursor_callback = self.onCursor
        self.window = int(window)
        self.larch = larch
        self.symname = '%s.plot%i' % (MODNAME, self.window)
        symtable = ensuremod(self.larch)

        if symtable is not None:
            symtable.set_symbol(self.symname, self)
        if window not in PLOT_DISPLAYS:
            PLOT_DISPLAYS[window] = self

    def onExit(self, o, **kw):
        try:
            symtable = self.larch.symtable
            if symtable.has_group(MODNAME):
                symtable.del_symbol(self.symname)
        except:
            pass
        if self.window in PLOT_DISPLAYS:
            PLOT_DISPLAYS.pop(self.window)

        self.Destroy()

    def onCursor(self, x=None, y=None, **kw):
        symtable = ensuremod(self.larch)
        if symtable is None:
            return
        symtable.set_symbol('%s_x'  % self.symname, x)
        symtable.set_symbol('%s_y'  % self.symname, y)
        self.cursor_pos = (x, y)

    def get_cursor(self):
        """return most recent cursor position"""
        return self.cursor_pos

class ImageDisplay(ImageFrame):
    def __init__(self, wxparent=None, window=1, larch=None, **kws):
        ImageFrame.__init__(self, parent=wxparent,
                                  exit_callback=self.onExit, **kws)
        self.Show()
        self.Raise()
        self.cursor_pos = []
        self.panel.cursor_callback = self.onCursor
        self.window = int(window)
        self.symname = '%s.img%i' % (MODNAME, self.window)
        self.larch = larch
        symtable = ensuremod(self.larch)
        if symtable is not None:
            symtable.set_symbol(self.symname, self)
        if self.window not in IMG_DISPLAYS:
            IMG_DISPLAYS[self.window] = self

    def onExit(self, o, **kw):
        #print 'ImageDisplay Exit ', self.symname, o, kw
        #for k, v in IMG_DISPLAYS.items():
        #    print 'IMG DISP: ',  k, v
        try:
            symtable = self.larch.symtable
            symtable.has_group(MODNAME), self.symname
            if symtable.has_group(MODNAME):
                symtable.del_symbol(self.symname)
        except:
            pass
        if self.window in IMG_DISPLAYS:
            IMG_DISPLAYS.pop(self.window)
        self.Destroy()

    def onCursor(self,x=None, y=None, ix=None, iy=None,
                 val=None, **kw):
        symtable = ensuremod(self.larch)
        if symtable is None:
            return
        set = symtable.set_symbol
        if x is not None:   set('%s_x' % self.symname, x)
        if y is not None:   set('%s_y' % self.symname, y)
        if ix is not None:  set('%s_ix' % self.symname, ix)
        if iy is not None:  set('%s_iy' % self.symname, iy)
        if val is not None: set('%s_val' % self.symname, val)

def _getDisplay(win=1, larch=None, wxparent=None, image=False):
    """make a plotter"""
    # global PLOT_DISPLAYS, IMG_DISPlAYS
    if larch is None:
        #print("Could not find larch?")
        return
    win = max(1, int(abs(win)))
    title   = 'Plot Window %i' % win
    symname = '%s.plot%i' % (MODNAME, win)
    creator = PlotDisplay
    display_dict = PLOT_DISPLAYS
    if image:
        creator = ImageDisplay
        display_dict = IMG_DISPLAYS
        title   = 'Image Window %i' % win
        symname = '%s.img%i' % (MODNAME, win)

    if win in display_dict:
        display = display_dict[win]
    else:
        display = larch.symtable.get_symbol(symname, create=True)

    if display is None:
        display = creator(window=win, wxparent=wxparent, larch=larch)
        larch.symtable.set_symbol(symname, display)

    if display is not None:
        display.SetTitle(title)
    return display

def _plot(x,y, win=1, new=False, larch=None, wxparent=None, **kws):
    """plot(x, y[, win=1], options])

    Plot 2-D trace of x, y arrays in a Plot Frame, clearing any plot currently in the Plot Frame.

    Parameters:
    --------------
        x :  array of ordinate values
        y :  array of abscissa values (x and y must be same size!)

        win: index of Plot Frame (0, 1, etc).  May create a new Plot Frame.
        new: flag (True/False, default False) for whether to start a new plot.
        label: label for trace
        title:  title for Plot
        xlabel: x-axis label
        ylabel: y-axis label
        ylog_scale: whether to show y-axis as log-scale (True or False)
        grid: whether to draw background grid (True or False)

        color: color for trace (name such as 'red', or '#RRGGBB' hex string)
        style: trace linestyle (one of 'solid', 'dashed', 'dotted', 'dot-dash')
        linewidth:  integer width of line
        marker:  symbol to draw at eac point ('+', 'o', 'x', 'square', etc)
        markersize: integer size of marker

        drawstyle: ?

        dy: array for error bars in y (must be same size as y!)
        yaxis='left'??
        use_dates

    See Also: oplot, newplot
    """
    plotter = _getDisplay(wxparent=wxparent, win=win, larch=larch)
    if plotter is None:
        larch.raise_exception(msg='No Plotter defined')
    wx.CallAfter(plotter.Raise)

    if new:
        plotter.plot(x, y, **kws)
    else:
        plotter.oplot(x, y, **kws)

def _oplot(x, y, win=1, larch=None, wxparent=None, **kws):
    """oplot(x, y[, win=1[, options]])

    Plot 2-D trace of x, y arrays in a Plot Frame, over-plotting any
    plot currently in the Plot Frame.

    This is equivalent to
    plot(x, y[, win=1[, new=False[, options]]])

    See Also: plot, newplot
    """
    _plot(x, y, win=win, new=False, larch=larch, wxparent=wxparent, **kws)

def _newplot(x, y, win=1, larch=None, wxparent=None, **kws):
    """newplot(x, y[, win=1[, options]])

    Plot 2-D trace of x, y arrays in a Plot Frame, clearing any
    plot currently in the Plot Frame.

    This is equivalent to
    plot(x, y[, win=1[, new=True[, options]]])

    See Also: plot, oplot
    """
    _plot(x, y, win=win, new=True, larch=larch, wxparent=wxparent, **kws)


def _getcursor(win=1, timeout=10, larch=None, wxparent=None, **kws):
    """get_cursor(win=1, timeout=60)

    waits (up to timeout) for cursor click in selected plot window, and returns
    x, y position of cursor.
    """
    plotter = _getDisplay(wxparent=wxparent, win=win, larch=larch)
    symtable = ensuremod(larch)
    xval = '%s.plot%i_x' % (MODNAME, win)
    yval = '%s.plot%i_y' % (MODNAME, win)

    cframe =CursorFrame(wxparent, larch=larch, win=win,
                         plotter=plotter)
    cframe.wait_for_cursor(timeout=timeout)
    cframe.Close()
    cframe.Destroy()

    try:
        return (symtable.get_symbol(xval), symtable.get_symbol(yval))
    except:
        return None

def _imshow(map, win=1, larch=None, wxparent=None, **kws):
    """imshow(map[, options])

    Display an image for a 2-D array, as a map

    map: 2-dimensional array for map
    """
    img = _getDisplay(wxparent=wxparent, win=win, larch=larch, image=True)
    if img is not None:
        img.display(map, **kws)

def registerLarchPlugin():
    return (MODNAME, {'plot':_plot,
                      'newplot':_newplot,
                      'oplot': _oplot,
                      'get_cursor': _getcursor,
                      'imshow':_imshow} )
