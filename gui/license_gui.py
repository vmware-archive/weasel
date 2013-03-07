
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

import gtk
import pango
import gobject

import esxlicense
import exception
import userchoices

from log import log
from common_windows import MessageWindow

from signalconnect import connectSignalHandlerByDict

class LicenseWindow:
    SCREEN_NAME = 'license'
    
    def __init__(self, controlState, xml):
        controlState.displayHeaderBar = True
        controlState.windowIcon = 'license.png'
        controlState.windowTitle = "License"
        controlState.windowText = "Enter license serial number"

        self.controlState = controlState
        
        self.serialRadio = xml.get_widget('serial_radio')
        self.serialParent = xml.get_widget('serial_hbox')

        ## TODO: revisit focus setting, backed out for beta1 (PR #290671)
        ## causes keystroke in serial number to lose focus to radio
        # controlState.initialFocus = self.serialRadio

        # Using a monospace font might make it easier to read.
        monoFont = pango.FontDescription("monospace")
        
        self.entries = []
        for entryNumber in range(esxlicense.SERIAL_NUM_COMPONENT_COUNT):
            entry = xml.get_widget('serialnum%d' % entryNumber)
            entry.modify_font(monoFont)
            self.entries.append(entry)

        connectSignalHandlerByDict(self, LicenseWindow, xml, {
                ('serial_radio', 'toggled') : 'onSerialToggled',
                ('serialnum0', 'changed') : 'onSerialnumChangedTabForward',
                ('serialnum1', 'changed') : 'onSerialnumChangedTabForward',
                ('serialnum2', 'changed') : 'onSerialnumChangedTabForward',
                ('serialnum3', 'changed') : 'onSerialnumChangedTabForward',
#                ('serialnum4', 'changed') : 'onSerialnumChanged',
                })

        self.onSerialToggled(self.serialRadio)

    def onSerialToggled(self, *_args):
        self.serialParent.set_sensitive(self.serialRadio.get_active())
#        self.onSerialnumChanged()

    def onSerialnumChangedTabForward(self, widget, *args):
        if len(widget.get_text()) == esxlicense.SERIAL_NUM_COMPONENT_SIZE:
            # Send a tab to move to the next widget.
            parent = widget.get_parent()
            while parent.get_parent():
                parent = parent.get_parent()
            parent.child_focus(gtk.DIR_TAB_FORWARD)
            
#        self.onSerialnumChanged(widget, *args)


# XXX - don't change the sensitivity of the Next button for now as it
#       causes problems with the default focus.
#    def onSerialnumChanged(self, *_args):
#        if self.serialRadio.get_active():
#            incompleteEntries = [entry for entry in self.entries
#                                 if len(entry.get_text()) != \
#                                     esxlicense.SERIAL_NUM_COMPONENT_SIZE]
#
#            sensitive = not incompleteEntries
#        else:
#            sensitive = True
#            
#        self.controlState.setNextButtonEnabled(sensitive, refresh=True)
        
    def getNext(self):
        if not self.serialRadio.get_active():
            userchoices.clearLicense()
            return

        serialNumber = '-'.join([entry.get_text() for entry in self.entries])
        try:
            esxlicense.checkSerialNumber(serialNumber)
        except esxlicense.LicenseException, e:
            MessageWindow(None, 'Invalid Serial Number', str(e))
            raise exception.StayOnScreen

        userchoices.setSerialNumber(serialNumber)

