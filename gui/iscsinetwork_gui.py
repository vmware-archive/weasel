
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
import nic_setup
import iscsi
import network_address_widgets
from consts import DialogResponses
from common_windows import MessageWindow
from log import log

_widgetsPopulated = False

class iSCSINetworkWindow:
    def __init__(self, controlState, xml, parentDialog):
        controlState.displayHeaderBar = 1
        controlState.windowTitle = "Add software iSCSI storage"
        controlState.windowText = "Configure a NIC to handle iSCSI storage"
        self.thisWindow = controlState.gui.getWindow()
        self.xml = xml
        self.parent = parentDialog

        try:
            log.debug('NicSetup ctor: macAddresses = ' + \
                      str(iscsi.getNicMacAddresses()))
            self.nicSetup = nic_setup.NicSetup(
                xml,
                controlState.gui.getWindow(),
                comboBoxName="IscsinetworkComboBox",
                vlanCheckButtonName="IscsinetworkVlanCheckButton",
                vlanEntryName="IscsinetworkVlanIDEntry",
                vlanIDHBoxName="IscsinetworkVlanIDHBox",
                wantedMacAddresses=iscsi.getNicMacAddresses())
            log.debug('NicSetup ctor: succeeded')
        # Two kinds of possible errors: (1) no iSCSI NICs
        #                               (2) can't read iSCSI boot tables
        except RuntimeError, msg:
            log.debug(str(msg))
            MessageWindow(self.thisWindow, 'iSCSI', 'Can not set up iSCSI.')
            raise

        self.handleComboBox(None)
        xml.get_widget("IscsinetworkComboBox").connect('changed',
                                                       self.handleComboBox)

        self.networkAddressWidgets =\
            network_address_widgets.NetworkAddressWidgets(
                xml, controlState.gui.getWindow(),
                "Iscsinetwork",
                ("ip", "netmask", "gateway"),
                "IscsinetworkDHCPRadioButton", "IscsinetworkIPTable")
        self.networkAddressWidgets.forceNoDHCP() # Not supported, yet, for iSCSI

        # First time through, prepopulate by querying VSI nodes.
        if not _widgetsPopulated:
            self.prepopulateWidgets()
            xml.signal_autoconnect({
                                    'clickedNext' : self.getNext,
                                    'clickedCancel' : self.getCancel
                                   })


    def prepopulateWidgets(self):
        global _widgetsPopulated
        iscsiBootTable = iscsi.getIscsiBootTable()

        if iscsiBootTable.nicVlan:
            self.nicSetup.setVlanID(iscsiBootTable.nicVlan)

        self.networkAddressWidgets.setUsingDHCP(iscsiBootTable.nicDhcp)
        if not iscsiBootTable.nicDhcp:
            self.networkAddressWidgets.setIPAddress(iscsiBootTable.nicIP)
            self.networkAddressWidgets.setSubnetMask(
                iscsiBootTable.nicSubnetMask)
            self.networkAddressWidgets.setGateway(iscsiBootTable.nicGateway)

        _widgetsPopulated = True


    def setSettingsSensitivity(self, boolVal):
        """
        Adapter settings and VLAN settings.  If we're selecting the same adapter
        the COS is going to use, we don't want to let the user enter different
        settings.
        """
        assert boolVal==True  or  boolVal==False
        for widgetName in "IscsinetworkVlanTable",\
                          "IscsinetworkAdapterSettingsFrame":
            widget = self.xml.get_widget(widgetName)
            assert(widget)
            widget.set_sensitive(boolVal)


    def handleComboBox(self, *args):
        """
        Set sensitivity of VLAN and network settings widgets according to
        whether NIC is different from the one selected for the COS.
        """
        if self.nicSetup.getDevice() in userchoices.getCosNICDevices():
            self.setSettingsSensitivity(False)
        else:
            self.setSettingsSensitivity(True)


    def getNext(self, *args):
        """Tell userchoices what choices were made on this screen.
        
           You can assign more than one NIC to the COS from scripted install,
           but not from the GUI installer.
        """
        assert len(userchoices.getVmkNICs()) <= 1, \
               "Found more than one Vmk nic in userchoices."

        if userchoices.getVmkNICs():
            userchoices.delVmkNIC(userchoices.getVmkNICs()[0])

        if self.nicSetup.getDevice() in userchoices.getCosNICDevices():
            window = \
                MessageWindow(self.thisWindow, "iSCSI network adapter",
                "You have already assigned this network interface to the\n"
                "management console.  Are you sure you would like to do that?",
                "okcancel")
            if not window.affirmativeResponse:
                return

            cosNIC = userchoices.getCosNICs()[0]
            cosNet = userchoices.getCosNetwork()
            userchoices.setVmkNetwork(cosNet["gateway"])
            userchoices.addVmkNIC(device=cosNIC["device"],
                                  vlanID=cosNIC["vlanID"],
                                  bootProto=cosNIC["bootProto"],
                                  ip=cosNIC["ip"],
                                  netmask=cosNIC["netmask"])
        else:
            try:
                if self.networkAddressWidgets.getUsingDHCP():
                    bootProto = userchoices.NIC_BOOT_DHCP
                    ipSettings = self.networkAddressWidgets.testIPSettings([])
                else:
                    bootProto = userchoices.NIC_BOOT_STATIC
                    tests = ["ip", "netmask", "gateway"]
                    ipSettings = self.networkAddressWidgets.testIPSettings(tests)

                userchoices.setVmkNetwork(ipSettings["gateway"])
                userchoices.addVmkNIC(device=self.nicSetup.getDevice(),
                                      vlanID=self.nicSetup.getVlanID(),
                                      bootProto=bootProto,
                                      ip=ipSettings["ip"],
                                      netmask=ipSettings["netmask"])
            except exception.StayOnScreen:
                self.parent.response(DialogResponses.STAYONSCREEN)
                return

        self.parent.response(DialogResponses.NEXT)


    def getCancel(self, *args):
        """
        Handle cancel button.
        Reset iSCSI network settings to what they were before we entered this
        dialog.  So if this is our first time in this dialog, the result is
        that iSCSI won't be activated.  If it's our second (third,...) time,
        then we won't de-activate iSCSI but rather reset things to what they
        were the last time we pressed "finish" on the second iSCSI dialog.
        """
        iscsi.vmkNicAndNetworkRollerbacker.rollback()
        self.parent.response(DialogResponses.CANCEL)
