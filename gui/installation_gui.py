
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
import gtk
import gobject
import exception
import applychoices
import userchoices
from common_windows import MessageWindow


class InstallationWindow:
    SCREEN_NAME = 'installation'
    
    def __init__(self, controlState, xml):
        self.xml = xml
        self.progressBar = xml.get_widget("InstallationProgressBar")
        self.progressLabel = xml.get_widget("InstallationProgressLabel")
        self.statusLabel = xml.get_widget("InstallationStatusLabel")

        controlState.displayHeaderBar = True
        controlState.windowIcon = 'installing.png'
        controlState.windowTitle = "Installing ESX 4.1"
        controlState.windowText = \
            "ESX 4.1 is being installed; this may take several minutes."

        controlState.setNextButtonEnabled(False)
        controlState.setBackButtonEnabled(False)

        self.controlState = controlState
        self.context = applychoices.Context(
            applychoices.ProgressCallback(self))

        gobject.idle_add(self.installSystem)

    def installSystem(self):
        # resize the display label so that the parent window is not resized off
        # the screen
        # XXX This must be done here since the allocation has not been processed
        # within the __init__ method.  We can not query the allocation of a
        # widget and get a valid value at that point.
        hbox = self.xml.get_widget('InstallstatusHBox')
        label = self.xml.get_widget('InstallationLabel')

        height = self.progressLabel.get_allocation().height
        width = hbox.get_allocation().width - label.get_allocation().width
        self.progressLabel.set_size_request(width, height)

        self.progressBar.set_fraction(0)

        if not userchoices.getClaimedNICDevices():
            MessageWindow( self.controlState.gui.getWindow(), 'the end',
                           'Because you have no usable (to ESX, so far)\n' +
                           'NICs, installation can go no further than this\n' +
                           'point, for now.')
            # TODO: remove when we *can* install NIC-less.
            return

        applychoices.doit(self.context)
        self.controlState.setNextButtonEnabled(True, refresh=True)
        self.controlState.setCancelButtonEnabled(False, refresh=True)
        self.controlState.gui.nextButton.grab_focus()

    def _processEvents(self):
        gtk.gdk.flush()
        while gtk.events_pending():
            gtk.main_iteration(False)

    def progressStatusStarted(self, progressCallback):
        '''Delegate method for applychoices.ProgressCallback that updates the
        progressLabel and progressBar.'''
        
        pct = progressCallback.getProgress()

        # GTK gets upset when the fraction is > 1
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
