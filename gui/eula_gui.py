
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

# display the welcome window
from log import log
import gtk
import string

import userchoices

from signalconnect import connectSignalHandlerByDict


class EulaWindow:
    SCREEN_NAME = 'eula'
    
    def __init__(self, controlState, xml):
        controlState.displayHeaderBar = True
        controlState.windowIcon = 'eula.png'
        controlState.windowTitle = "End User License Agreement"
        controlState.windowText = "To continue with the installation, " + \
            "please read and accept the end user license agreement."
        controlState.nextButtonEnabled = False

        self.checked = xml.get_widget("EulaCheckButton")
        controlState.initialFocus = self.checked

        self.controlState = controlState

        self.xml = xml

        self.setupEula()

        connectSignalHandlerByDict(self, EulaWindow, self.xml,
          { ('EulaCheckButton', 'clicked') : 'acceptedEula',
          })

        self.setupEulaAccepted()
	
    def acceptedEula(self, *args):
        widget = args[0]
        if widget.get_active():
            self.controlState.setNextButtonEnabled(True, refresh=True)
        else:
            self.controlState.setNextButtonEnabled(False, refresh=True)

    def setupEulaAccepted(self):
        self.acceptedEula(self.checked)

    def setupEula(self, fn='eula.txt'):
        try:
            eulafile = open(fn, "r")
        except:
            try:
                eulafile = open("/mnt/runtime/etc/" + fn, "r")
            except:
                log.error("Couldn't load eula")
                return ""

        text = string.join(eulafile.readlines(), '')
        eulafile.close()

        buf = gtk.TextBuffer(None)
        buf.set_text(text)

        textview = self.xml.get_widget("EulaTextView")
        textview.set_buffer(buf)

    def getNext(self):
        userchoices.setAcceptEULA(True)

