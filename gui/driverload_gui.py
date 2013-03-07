
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

# display the window
import os
import gtk
import gobject
import exception
import applychoices
import networking
from common_windows import MessageWindow, ExceptionWindow
import customdrivers


class DriverLoadWindow:
    SCREEN_NAME = 'driverload'
    
    def __init__(self, controlState, xml):
        self.xml = xml
        self.progressBar = xml.get_widget("DriverloadProgressBar")
        self.progressLabel = xml.get_widget("DriverloadProgressLabel")
        self.statusLabel = xml.get_widget("DriverloadStatusLabel")

        controlState.displayHeaderBar = True
        controlState.windowIcon = 'driverloading.png'
        controlState.windowTitle = "Loading Drivers"
        controlState.windowText = "The installation wizard will resume " + \
            "after all necessary drivers are loaded"

        controlState.setNextButtonEnabled(False)
        controlState.setBackButtonEnabled(False)

        self.controlState = controlState
        self.context = applychoices.Context(
            applychoices.ProgressCallback(self))

        gobject.idle_add(self.loadDrivers)

    def getNext(self):
        # remove the driverload step since we can no longer come back
        # to this screen.  we also need to reset our pointer in the step list
        self.controlState.removeStep('driverload')
        self.controlState.setCurrentStep('customdrivers')

    def loadDrivers(self):
        # resize the display label so that the parent window is not resized off
        # the screen
        # XXX This must be done here since the allocation has not been processed
        # within the __init__ method.  We can not query the allocation of a
        # widget and get a valid value at that point.
        hbox = self.xml.get_widget('DriverloadstatusHBox')
        label = self.xml.get_widget('DriverloadLabel')

        height = self.progressLabel.get_allocation().height
        width = hbox.get_allocation().width - label.get_allocation().width
        self.progressLabel.set_size_request(width, height)

        self.progressBar.set_fraction(0)

        try:
            applychoices.doit(self.context, stepListType='loadDrivers')
            self.controlState.setNextButtonEnabled(True, refresh=True)
        except customdrivers.ScriptLoadError, msg:
            MessageWindow(None, "Script Loading Failures", str(msg[0]))
            self.controlState.setNextButtonEnabled(True, refresh=True)
        except customdrivers.CriticalScriptLoadError, msg:
            MessageWindow(None, "Critical Script Loading Failure", str(msg[0]))

        if not self.checkNICsDetected():
            noNicMsg = customdrivers.NO_NIC_MSG
            noNicMsg += '\nThe system must be restarted.'
            exceptionWin = ExceptionWindow(noNicMsg, '')
            exceptionWin.run() # run() may can gtk.main_quit()
            os.system('chvt 1') # the user pressed Debug

        self.controlState.gui.nextButton.grab_focus()

    def _processEvents(self):
        gtk.gdk.flush()
        while gtk.events_pending():
            gtk.main_iteration(False)

    def checkNICsDetected(self):
        networking.init()
        pnics = networking.getPhysicalNics()
        return len(pnics) > 0

    def progressStatusStarted(self, progressCallback):
        '''Delegate method for applychoices.ProgressCallback that updates the
        progressLabel and progressBar.'''
        
        pct = progressCallback.getProgress()

        # GTK gets upsetwhen the fraction is > 1
        if pct > 1.0:
            pct = 1.0

        self.progressBar.set_fraction(pct)

        msg = progressCallback.getLastMessage()
        if msg: # The message will be empty when everything completes.
            msg = " - %s" % msg
        self.progressLabel.set_text("%3d%% Complete%s" % (pct * 100.0, msg))
        self._processEvents()

        if self.controlState.gui.wasCancelled:
            raise exception.InstallCancelled()

    progressStatusFinished = progressStatusStarted

    progressStatusGroupFinished = progressStatusStarted
