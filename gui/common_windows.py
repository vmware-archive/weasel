#! /usr/bin/env python

###############################################################################
# Copyright (c) 2008-2009 VMware, Inc.
#
# This file is part of Weasel.
#
# Weasel is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free
# Software Foundation version 2 and no later version.
#
# Weasel is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License
# version 2 for more details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc., 51
# Franklin St, Fifth Floor, Boston, MA 02110-1301 USA.
#

'''
This module contains modal dialog (pop-up) windows that can be used
in many of the GUI screens.
'''

import os
import gtk
import time
import gobject
import task_progress
from log import log

TENTH_SECOND = 100 #units are miliseconds

class CommonWindow:
    def __init__(self):
        self.isMoving = False
        self.deltaX = 0
        self.deltaY = 0
        self.buttonEvent = None
        self.dialog = None
        self.affirmativeResponse = None

    def run(self):
        raise NotImplementedError, "CommonWindow can not be run directly"

    def moveDialog(self, widget, event):
        if self.isMoving:
            assert self.dialog

            # stop the dialog from moving off top and left of the screen
            targetX = max(0, int(event.x_root) - self.deltaX)
            targetY = max(0, int(event.y_root) - self.deltaY)

            width, height = self.dialog.get_size()

            # stop the dialog from moving off bottom and right of the screen
            targetX = min(gtk.gdk.screen_width() - width, targetX)
            targetY = min(gtk.gdk.screen_height() - height, targetY)

            self.dialog.move(targetX, targetY)

    def grabDialog(self, widget, event):
        if event.type & gtk.gdk.BUTTON_PRESS and event.button == 1:
            self.isMoving = True
            self.buttonEvent = event.button

            # XXX - these will be slightly off due to the size of the frame 
            # we're packed in vs where the event box starts.  this will cause
            # the window to "shudder" slightly when you start to move it.
 
            self.deltaX = int(event.x)
            self.deltaY = int(event.y)

    def releaseDialog(self, widget, event):
        if self.isMoving and self.buttonEvent == event.button:
            self.isMoving = False
            self.deltaX = 0
            self.deltaY = 0
            self.buttonEvent = None

    def addFrameToWindow(self, title=""):
        '''Adds a "Frame" to a given dialog or window.

           TODO: We may want to glade-a-fy this at some point.
        '''

        contents = self.dialog.get_children()[0]

        # if we've already added a frame to the widget don't add another
        if contents.get_name() == 'common-window':
            return

        self.dialog.remove(contents)
        frame = gtk.Frame()
        frame.set_name('common-window')
        frame.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        frame.set_border_width(0)
        frame.connect('realize', self._onRealize)
        box = gtk.VBox()

        eventBox = titleBox(title)
        eventBox.connect("button-press-event", self.grabDialog)
        eventBox.connect("button-release-event", self.releaseDialog)
        eventBox.connect("motion-notify-event", self.moveDialog)

        eventBox.show_all()
        box.pack_start(eventBox, False, False)

        innerFrame = gtk.Frame()
        innerFrame.set_shadow_type(gtk.SHADOW_NONE)
        innerFrame.set_border_width(4)
        innerFrame.add(contents)
        box.pack_start(innerFrame, True, True, padding=5)

        frame.add(box)
        frame.show_all()

        self.dialog.add(frame)
        self.dialog.set_property('border-width', 0)

    def _onRealize(self, _widget):
        self.setCursor()
        
    def setCursor(self, cursor=None):
        if cursor is None:
            cursor = gtk.gdk.Cursor(gtk.gdk.LEFT_PTR)
        if not self.dialog.window:
            raise RuntimeError('Setting cursor: dialog.window is None. '
                               'Perhaps setCursor() was called before show()?')
        self.dialog.window.set_cursor(cursor)


def titleBox(title=""):
    '''Returns an eventbox with a title bar.

       TODO: We may want to glade-a-fy this at some point.
    '''

    eventBox = gtk.EventBox()

    titleBox = gtk.HBox(False, 5)
    eventBox.add(titleBox)

    # use the "selected" colour to fill the background
    eventBox.modify_bg(gtk.STATE_NORMAL,
                       eventBox.rc_get_style().bg[gtk.STATE_SELECTED])

    titleLabel = gtk.Label()
    titleLabel.set_markup("<b>%s</b>" % (title,))
    titleLabel.modify_fg(gtk.STATE_NORMAL, eventBox.rc_get_style().fg[gtk.STATE_SELECTED])
    titleBox.pack_start(titleLabel, padding=10)

    return eventBox

class MessageWindow(CommonWindow):
    def __init__(self, window, title, text, type='ok', execute=True,
                 useMarkup=False):
        CommonWindow.__init__(self)

        buttonTypes = {
		'ok' : (gtk.BUTTONS_OK, gtk.MESSAGE_INFO),
		'warning' : (gtk.BUTTONS_OK, gtk.MESSAGE_WARNING),
                'error' : (gtk.BUTTONS_OK, gtk.MESSAGE_ERROR),
		'okcancel' : (gtk.BUTTONS_OK_CANCEL, gtk.MESSAGE_WARNING),
                'yesno' : (gtk.BUTTONS_YES_NO, gtk.MESSAGE_QUESTION),
        }

        if buttonTypes.has_key(type):
            (buttons, style) = buttonTypes[type]
        else:
            raise AttributeError, "Missing/bad button type"

        self.dialog = gtk.MessageDialog(window, 0, style, buttons)
        if useMarkup:
            # Note: I wasn't able to use dialog.set_property('use-markup'...)
            # because in my attempts it would sometimes require repeated 
            # main_iteration()s before it seemed to take effect.
            self.dialog = gtk.MessageDialog(window, 0, style, buttons)
            self.dialog.set_markup(text)
        else:
            self.dialog = gtk.MessageDialog(window, 0, style, buttons, text)

        self.dialog.set_position(gtk.WIN_POS_CENTER)
        self.addFrameToWindow(title)

        if execute:
            self.run()

    def run(self):
        self.dialog.show_all()

        self.rc = self.dialog.run()

        response = {
            gtk.RESPONSE_OK : True,
            gtk.RESPONSE_YES : True,
            gtk.RESPONSE_CANCEL : False,
            gtk.RESPONSE_NO : False,
            gtk.RESPONSE_CLOSE : False,
            gtk.RESPONSE_DELETE_EVENT : False,
        }

        # this should raise a key error if we don't have a proper response
        self.affirmativeResponse = response[self.rc]

        self.dialog.destroy()
        self.dialog = None

        return self.rc

class ProgressWindow(CommonWindow):
    '''The ProgressWindow is similar to the MessageWindow, but it
    adds a progress bar that pulses until finish() is called.

    Instead of MessageWindow's run() method, ProgressWindow provides
    a nonblockingRun() method.

    The cancelCallback argument can be used to activate the Cancel button
    of the dialog.  When the Cancel button is pressed, it will call the
    cancelCallback, which is expected to correctly cancel and clean up
    the operation in progress.
    '''
    def __init__(self, window, title, text, execute=True):
        CommonWindow.__init__(self)
        fpath = os.path.join(os.path.dirname(__file__),
                             "glade/progress_dialog.glade")
        self.xml = gtk.glade.XML(fpath)
        self.dialog = self.xml.get_widget("progress_dialog")

        self.cancelCallback = None

        self.dialog.set_position(gtk.WIN_POS_CENTER)
        self.addFrameToWindow(title)

        self.progressBar = self.xml.get_widget("progressbar1")
        self.cancelButton = self.xml.get_widget('cancel_button')
        self.labelText = self.xml.get_widget('progress_label')
        self.labelText.set_text(text)

        if not self.cancelCallback:
            self.cancelButton.set_sensitive(False)

        if execute:
            self.nonblockingRun()
            
    def finish(self):
        if self.dialog:
            #self.dialog.hide()
            self.dialog.destroy()
            self.dialog = None

    def setText(self, newText):
        self.labelText.set_text(newText)

    def setCancelCallback(self, newCancelCallback):
        if not self.cancelCallback:
            self.cancelButton.set_sensitive(True)
        self.cancelCallback = newCancelCallback

    def pulse(self):
        '''Pulses the GUI progress bar'''
        self.progressBar.pulse()
        gtk.gdk.flush()
        while gtk.events_pending():
            gtk.main_iteration(False)

    def setFraction(self, fraction):
        self.progressBar.set_fraction(fraction)
        gtk.gdk.flush()
        while gtk.events_pending():
            gtk.main_iteration(False)

    def run(self):
        # callers would expect run() to block
        raise RuntimeError('ProgressWindow instances do not have run methods')

    def handleResponse(self, widget, responseID):
        if responseID == gtk.RESPONSE_CANCEL:
            if self.cancelCallback:
                self.cancelCallback()
            else:
                log.error('ProgressWindow canceled, but no cancel handler')

        if self.dialog:
            self.finish()

    def nonblockingRun(self):
        self.dialog.show_all()
        gtk.gdk.flush()
        while gtk.events_pending():
            gtk.main_iteration(False)

        self.setCursor()

        if not self.dialog:
            return False

        self.dialog.connect('response', self.handleResponse)


class ProgressWindowTaskListener(ProgressWindow):
    def __init__(self, window, title, text, watchedTasks, execute=True):
        ProgressWindow.__init__(self, window, title, text, execute)
        self.watchedTasks = watchedTasks
        self.tasksToFinish = set(watchedTasks)
        task_progress.addNotificationListener(self)
        # we don't want to pulse more often than once every 1/10 of a second
        self.hyperactivityThreshold = 0.1
        self.lastPulse = 0

    def _pulseIfWatching(self, taskTitle):
        if time.time() - self.lastPulse < self.hyperactivityThreshold:
            return
        if taskTitle not in self.watchedTasks:
            return
        self.lastPulse = time.time()
        remaining = task_progress.getPercentageOfWorkRemaining(taskTitle)
        if remaining == 1.0:
            self.pulse()
        else:
            self.setFraction(1.0 - remaining)

    def notifyTaskStarted(self, taskTitle):
        self._pulseIfWatching(taskTitle)

    def notifyTaskProgress(self, taskTitle, amountCompleted):
        self._pulseIfWatching(taskTitle)

    def notifyTaskFinish(self, taskTitle):
        if taskTitle in self.tasksToFinish:
            self.tasksToFinish.remove(taskTitle)
        if self.tasksToFinish:
            self._pulseIfWatching(taskTitle)
        else:
            self.finish()


class FileChooser(CommonWindow):
    def __init__(self, parent, title):
        CommonWindow.__init__(self)

        self.dialog = gtk.FileChooserDialog(title,
                                            action=gtk.FILE_CHOOSER_ACTION_OPEN,
                                            buttons=(gtk.STOCK_CANCEL,
                                                     gtk.RESPONSE_CANCEL,
                                                     gtk.STOCK_OPEN,
                                                     gtk.RESPONSE_OK))
        self.dialog.set_position(gtk.WIN_POS_CENTER)
        self.dialog.resize(600, 300)
        self.addFrameToWindow(title)

class ExceptionWindow(CommonWindow):
    '''Show a window to inform the user about an exceptional situation,
    usually an error.
    The constructor takes 'desc', a summary of the error, and 'details',
    which can be a longer message and is initially obscured behind a
    GTK Expander.  If 'details' is empty, the Expander will not be shown.
    '''
    def __init__(self, desc, details):
        CommonWindow.__init__(self)
        self.xml = gtk.glade.XML(os.path.join(os.path.dirname(__file__),
                                 "glade/exception.glade"))

        self.dialog = self.xml.get_widget("exception")
        self.expander = self.xml.get_widget("exceptionExpander")

        if details:
            self.expander.connect("activate", self._expanderActivated)
        else:
            self.expander.set_child_visible(False)

        descLabel = self.xml.get_widget("ExceptionDescription")
        descLabel.set_text(desc)

        buf = gtk.TextBuffer()
        buf.set_text(details)
        textview = self.xml.get_widget("ExceptionTextView")
        textview.set_buffer(buf)

        self.dialog.set_position(gtk.WIN_POS_CENTER)
        self.addFrameToWindow("Installation Error")

        self.xml.get_widget('ExceptionDebugButton').grab_focus()

    def _expanderActivated(self, *_args):
        # XXX Need to 'not' the get_expanded() value since it has not been
        # updated at this point.
        self.dialog.set_resizable(not self.expander.get_expanded())
  
    def run(self):
        self.dialog.show_all()

        rc = self.dialog.run()
        self.dialog.destroy()

        if rc == 1:
            gtk.main_quit()
            return True

        return False

def populateViewColumns(view, columns, **columnArgs):
    '''Populate a view with columns and sizes.
    '''

    renderer = gtk.CellRendererText()

    for count, col in enumerate(columns):
        column = gtk.TreeViewColumn(col[0], renderer, text=count, **columnArgs)
        if col[1]:
            column.set_min_width(col[1])
        view.append_column(column)

class MountMediaDelegate:
    '''Implements the delegate functions required by the
    media.runtimeActionMountMedia function.'''
    
    def mountMediaNoDrive(self):
        MessageWindow(None, "No CD-ROM Detected",
                      "The CD drive was not detected on boot up and "
                      "you have selected CD-based installation.\n\n"
                      "Click 'Ok' to reboot.",
                      type='error')

    def mountMediaNoPackages(self):
        MessageWindow(None, "CD-ROM Missing",
                      "Insert the ESX Installation media.")

    def mountMediaCheckFailed(self):
        MessageWindow(None, "Verification Failed",
                      "The ESX Installation media contains errors.\n\n"
                      "Click 'Ok' to reboot.",
                      type='error')

    def mountMediaCheckSuccess(self):
        MessageWindow(None, "Verification Success",
                      "No errors were found on the ESX installation media.\n\n")

