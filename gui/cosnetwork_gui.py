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
network settings gui screen
'''
import gtk
import gobject
import networking
import userchoices
import network_address_widgets
from common_windows import MessageWindow, ProgressWindowTaskListener
from exception import StayOnScreen
from signalconnect import connectSignalHandlerByDict
from log import log


#TODO: add a message to the networkBringupFailureMessage to check
#      that Workstation is allowing promiscuous mode.  Probably
#      only during DEBUG=True
networkBringupFailureMessage = '''\
There was a problem bringing up the network.

This is unusual, but harmless.  Installation will continue normally.  \
For your information, here are the details of the problem:

Exception Class: %(exceptionClass)s
Exception Details:
%(exceptionRepr)s
%(exceptionStr)s
'''

networkBringupSuccessMessage = '''\
No problems detected with the network settings.

Note, these settings are now active and any further changes made in \
the network configuration screen will not be activated until the Test \
button is pressed again or until the installation is complete.
'''

class CosNetworkWindow:
    SCREEN_NAME = 'cosnetwork'
    
    def __init__(self, controlState, xml):
        controlState.displayHeaderBar = True
        controlState.windowIcon = 'network_configure.png'
        controlState.windowTitle = "Network Configuration"
        controlState.windowText = "Enter the network configuration information"

        self.controlState = controlState

        self.progressDialog = None

        self.networkAddressWidgets =\
            network_address_widgets.NetworkAddressWidgets(
                xml,
                self.controlState.gui.getWindow(),
                'Cosnetwork',
                ('ip', 'netmask', 'gateway', 'ns1', 'ns2', 'hostname'),
                'CosnetworkDHCPRadioButton', 'CosnetworkIPTable')

        #
        # Fill out "Network Adapter:" label.
        adapter = xml.get_widget("CosnetworkNetworkAdapterLabel")
        assert len(userchoices.getCosNICs()) > 0
        device = userchoices.getCosNICs()[0]['device']
        adapter.set_text(device.name)

        connectSignalHandlerByDict(self, CosNetworkWindow, xml,
          {('activate_button', 'clicked'): 'onActivateButtonClicked',
          })

    def onActivateButtonClicked(self, widget, *args):
        try:
            #saveChoices() will pop up its own warnings / errors
            self.saveChoices()
        except StayOnScreen:
            return
        
        #activateNetwork() will pop up its own warnings / errors
        self.activateNetwork()

    def activateNetwork(self, dialogOnSuccess=True):
        '''Try to activate the network.  If there is a failure,
        pop up a very friendly warning dialog.
        return True if there were no exceptions, otherwise return False
        '''
        self.progressDialog = ProgressWindowTaskListener(
                                self.controlState.gui.getWindow(),
                                'Network Activation',
                                'Connecting to the network',
                                ['network'],
                                execute=False)

        # give the progress dialog a chance to paint before calling
        # long-running functions
        self.progressDialog.nonblockingRun()
        
        gobject.idle_add(self.activateNetwork2, dialogOnSuccess)


    def activateNetwork2(self, dialogOnSuccess=True):
        failMsg = None
        try:
            networking.cosConnectForInstaller()
        except Exception, ex:
            failMsg = networkBringupFailureMessage %\
                      dict(exceptionClass=ex.__class__,
                           exceptionRepr=repr(ex),
                           exceptionStr=str(ex)
                           )
        self.progressDialog.done = True
        
        if failMsg:
            MessageWindow(self.controlState.gui.getWindow(),
                          'Network Bring-up Warning', failMsg )
        elif dialogOnSuccess:
            MessageWindow(self.controlState.gui.getWindow(),
                          'Network Test',
                          networkBringupSuccessMessage)

    def saveChoices(self):
        if self.networkAddressWidgets.getUsingDHCP():
            bootProto = userchoices.NIC_BOOT_DHCP
            ipSettings = self.networkAddressWidgets.testIPSettings([])
            userchoices.clearCosNetwork()
        else:
            bootProto = userchoices.NIC_BOOT_STATIC
            tests = ["ip", "netmask", "gateway", "ns1", "ns2", "hostname"]
            ipSettings = self.networkAddressWidgets.testIPSettings(tests)
            try:
                networking.utils.sanityCheckIPSettings(ipSettings["ip"],
                                                       ipSettings["netmask"],
                                                       ipSettings["gateway"])
            except (ValueError, TypeError), msg:
                MessageWindow(self.controlState.gui.getWindow(),
                              "IP Settings Error",
                              str(msg))
                raise StayOnScreen
            userchoices.setCosNetwork(ipSettings["gateway"], ipSettings["ns1"],
                                      ipSettings["ns2"], ipSettings["hostname"])

        #
        # cosnetworkadapter_gui.py has called userchoices.addCosNIC(), but
        # it didn't know what IP or netmask to associate with the chosen NIC.
        # Now that we do know those things, we make that association (and it's
        # just an implementation detail that we do so by deleting and then re-
        # creating the userchoices.__cosNics element rather than editing it in
        # place).
        #
        assert(len(userchoices.getCosNICs()) == 1)
        nic_0 = userchoices.getCosNICs()[0]
        device, vlanID = nic_0['device'], nic_0['vlanID']
        userchoices.delCosNIC(nic_0)
        userchoices.addCosNIC(device, vlanID, bootProto,
                              ipSettings["ip"], ipSettings["netmask"])

    def getNext(self):
        self.saveChoices()
        if userchoices.getActivateNetwork():
            self.activateNetwork(dialogOnSuccess=False)
