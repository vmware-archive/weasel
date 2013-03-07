
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

# Weasel modules
from log import log
from common_windows import MessageWindow
from exception import StayOnScreen
import networking
import userchoices
import nic_setup



class CosNetworkAdapterWindow:
    SCREEN_NAME = 'cosnetworkadapter'
    
    def __init__(self, controlState, xml):
        controlState.displayHeaderBar = True
        controlState.windowIcon = 'networkadapter.png'
        controlState.windowTitle = "Network Configuration"
        controlState.windowText = "Select an adapter for ESX"

        self.controlState = controlState
        self.thisWindow = controlState.gui.getWindow()
        self.xml = xml

        networking.init()

        def queryCurrentCosNic():
            cosNics = userchoices.getCosNICs()
            if not cosNics:
                return None
            return cosNics[0]['device']

        try:
            self.nicSetup = nic_setup.NicSetup(
                xml,
                controlState.gui.getWindow(),
                comboBoxName="CosnetworkadapterComboBox",
                vlanCheckButtonName="CosnetworkadapterVlanCheckButton",
                vlanEntryName="CosnetworkadapterVlanIDEntry",
                vlanIDHBoxName="CosnetworkadapterVlanIDHBox",
                queryCurrentFn=queryCurrentCosNic)
        except RuntimeError, msg:
            self.desensitizeEverything()
            self.noNicHandlerID = self.thisWindow.connect('enter-notify-event',
                                                          self.showNoNicError)
            # We do it like this, rather than call MessageWindow right here,
            # so as to give this screen a chance to render itself.  (If not,
            # we see the MessageWindow on top of a totally blank, grey, window.)
            self.nicSetup = None


    def desensitizeEverything(self):
        for widget in 'CosnetworkadapterVlanCheckButton', \
                      'CosnetworkadapterComboBox':
            self.xml.get_widget(widget).set_sensitive(False)


    def showNoNicError(self, unused1, unused2):
        """
        See justification for this, under the except clause in the contructor.
        """
        # We should never get here because we detect nics immediately after
        # driver loading.
        msg = 'No NICs detected'
        MessageWindow(self.thisWindow, msg.title(), msg)
        self.thisWindow.disconnect(self.noNicHandlerID)
        # If we don't disconnect, the popup will keep rearing its ugly head, to
        # the point the user will never get a chance to click on "cancel" or
        # "back"!


    def getNext(self):
        """Tell userchoices what choices were made on this screen.
        
           We don't know bootProto, ip or netmask yet.  They're set in the
           next screen.
        
           You can assign more than one NIC to the COS from scripted install,
           but not from the GUI installer.
        """
        # Case of no NICs found. Driver loading window should prevent this.
        if not self.nicSetup:
            msg = 'No NICs detected'
            MessageWindow(self.thisWindow, msg.title(), msg)
            raise StayOnScreen()

        chosenNics = userchoices.getCosNICs()

        if chosenNics:
            assert len(chosenNics) == 1, "Found more than one console NIC."
            userchoices.delCosNIC(chosenNics[0])

        physicalNic = self.nicSetup.getDevice()
        userchoices.addCosNIC(device=physicalNic,
                              vlanID=self.nicSetup.getVlanID(),
                              bootProto=None,
                              ip=None, netmask=None)

