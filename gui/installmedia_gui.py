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

import exception
import userchoices
from common_windows import MessageWindow

class InstallMediaWindow:
    SCREEN_NAME = 'installmedia'
    
    def __init__(self, controlState, xml):
        controlState.displayHeaderBar = True
        controlState.windowTitle = "Install Media"
        controlState.windowText = "Select the source for this ESX installation"
        controlState.windowIcon = "mediaselect.png"

        self.controlState = controlState
        self.xml = xml

    def getNext(self):

        stepDict = { 'InstallHttpRadioButton' : 'httpmedia',
                     'InstallFtpRadioButton' : 'ftpmedia',
                     'InstallUsbRadioButton' : 'usbmedia',
                     'InstallNfsRadioButton' : 'nfsmedia' }

        for step in stepDict.values():
            if step in self.controlState.gui.dispatch:
                self.controlState.removeStep(step)

        for step in stepDict.keys():
            if self.xml.get_widget(step).get_active():
                self.controlState.insertStep(stepDict[step], 'setupchoice')
                break

        # if the media requires a network connection, check that the ethernet
        # cable is plugged in
        if stepDict[step] in ['httpmedia', 'ftpmedia', 'nfsmedia']:
            chosenNics = userchoices.getCosNICs()
            assert len(chosenNics) == 1
            physicalNic = chosenNics[0]['device']
            if not physicalNic.isLinkUp:
                MessageWindow(None, 'Network Adapter Error',
                              'The network adapter must be connected to '
                              'access FTP, HTTP, or NFS sources.')
                raise exception.StayOnScreen()
