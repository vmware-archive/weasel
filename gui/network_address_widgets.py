
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
import common_windows
import string
import ip_entry

#
# TODO: replace IP_Entry with regular gtk.Entry, but rig them so on bad
# data focus goes back to offending Entry.
#


import networking.utils as net_utils

from log import log
import exception

#
# Module state and accessors
#
_widgetsInitialized = {}   # One entry for each client
_callbacksRegistered = {}  # One entry for each client
def setCallbacksRegistered(clientName, b):
    global _callbacksRegistered
    _callbacksRegistered[clientName] = b
def callbacksAreRegistered(clientName):
    return (clientName in _callbacksRegistered)  \
           and _callbacksRegistered[clientName]
def setWidgetsInitialized(clientName, b):
    global _widgetsInitialized
    _widgetsInitialized[clientName] = b
def widgetsAreInitialized(clientName):
    return (clientName in _widgetsInitialized) \
           and _widgetsInitialized[clientName]

def testDNSIPString(ipString):
    '''The name servers get treated specially since they
    don't necessarily need a value.
    '''
    if ipString == '':
        return
    else:
        return net_utils.sanityCheckIPString(ipString)


_ipTests = {
    "ip" : ("IPAddress", "IP Address Error",
        "The IP address you entered was invalid.",
        net_utils.sanityCheckIPString),
    "netmask" : ("SubnetMask", "Subnet Mask Error",
        "The Subnet Mask you entered was invalid.",
        net_utils.sanityCheckNetmaskString),
    "gateway" : ("Gateway", "Gateway Address Error",
        "The Gateway address you entered was invalid.",
        net_utils.sanityCheckGatewayString),
    "ns1" : ("PrimaryNS", "Primary DNS Error",
        "The Primary DNS address you entered was invalid.",
        testDNSIPString),
    "ns2" : ("SecondaryNS", "Secondary DNS Error",
        "The Secondary DNS address you entered was invalid.",
        testDNSIPString),
    "hostname" : ("HostnameEntry", "Hostname Error", "",
        net_utils.sanityCheckHostname)
}


_ipEntries = {}  # Dict of dicts, e.g. _ipEntries[client][ipfield]
                 # Holds widgets.


class NetworkAddressWidgets:
    ''' Handles gui selection of DHCP/static and (if static) selection of
        IP addresses and hostname.
    '''

    def __init__(self, xml, thisWindow,
                 clientName, relevantIPFields, dhcpRadioButtonName,
                 networkTableName):
        ''' clientName is the prefix (e.g. "Cosnetwork", "Iscsinetwork") of
            distinguished widgets belonging to the screen we've been called
            from.

            relevantIPFields is a tuple containing any subset of 'ip',
            'netmask', 'gateway', 'ns1', 'ns2' and 'hostname'.  This determines
            which widgets will be created (and validated).  These strings should
            be spelled the same way as the keys of _ipTests.

            networkTableName is a string, the name of the box we activate or
            deactivate according to the DHCP radio button's state.
        '''
        self.xml = xml
        self.thisWindow = thisWindow
        self.clientName = clientName
        self.relevantIPFields = relevantIPFields
        self.dhcpRadioButton = xml.get_widget(dhcpRadioButtonName)
        self.networkTable = xml.get_widget(networkTableName)
        assert self.dhcpRadioButton
        assert self.networkTable

        self.initIPEntries()

        if not callbacksAreRegistered(clientName):
            self.dhcpRadioButton.connect('toggled', self.toggleIPTable)
            _ipEntries[clientName]['SubnetMask'].connect(
                'focus-in-event', self.calcSubnetMask)
            _ipEntries[clientName]['Gateway'].connect(
                'focus-in-event', self.calcGatewayNameserver)
            setCallbacksRegistered(clientName, True)


    def forceNoDHCP(self):
        self.setUsingDHCP(False)
        self.dhcpRadioButton.set_sensitive(False)


    def initIPEntries(self):
        ''' Pack IP_Entry custom widgets.  The convention is that the widget
            called XIPEntry is packed into the Hbox (which we get from the
            .glade file) called self.clientName + 'XHbox'.
        '''
        if widgetsAreInitialized(self.clientName):
            return

        if not self.clientName in _ipEntries:
            _ipEntries[self.clientName] = {}

        for ipField in self.relevantIPFields:
            if ipField == 'hostname':
                continue
            baseName = _ipTests[ipField][0]
            hboxName = self.clientName + baseName + 'Hbox'
            _ipEntries[self.clientName][baseName] = entry = ip_entry.IP_Entry()
            entry.set_name(baseName)
            self.xml.get_widget(hboxName).pack_start(entry, expand=False,
                                                     fill=False)
            entry.show()

        setWidgetsInitialized(self.clientName, True)


    def getUsingDHCP(self):
        return self.dhcpRadioButton.get_active()

    def setUsingDHCP(self, val):
        assert val==0 or val==1 # An int, not a bool, because it's an int in
            # the VSI node and turning that to a bool would have added an awkward
            # special case in StorageInfoImpl::GetIscsiBootTables().

        if val:
            self.dhcpRadioButton.set_active(True)
        else:
            # You can't turn an on radiobutton off; you have to turn on the other
            # (currently-off) radiobutton.
            buttGroup = self.dhcpRadioButton.get_group()
            if buttGroup[0] == self.dhcpRadioButton:
                buttGroup[1].set_active(True)
            else:
                buttGroup[0].set_active(True)

    def getIPString(self, name, formatted=1):
        '''Return the contents of an IP_Entry, as is if formatted==0, more
           nicely formatted if formatted==1.
           Arg name needs to be a key in _ipEntries[self.clientName].
        '''
        txt = _ipEntries[self.clientName][name].get_text()
        if not formatted:
            return txt
        else:
            try:
                return net_utils.formatIPString(txt)
            except ValueError:
                return ""


    def setIPString(self, name, ipstr):
        '''Arg name needs to be a key to the _ipEntries
           dictionary.
           Arg ipstr is a string like "10.20.123.36".
        '''
        _ipEntries[self.clientName][name].set_text(ipstr)


    def setIPAddress(self, ipstr):
        self.setIPString('IPAddress', ipstr)

    def setSubnetMask(self, ipstr):
        self.setIPString('SubnetMask', ipstr)

    def setGateway(self, ipstr):
        self.setIPString('Gateway', ipstr)


    def calcSubnetMask(self, widget, *args):
        '''Calculate the netmask if it hasn't been set.'''
        if self.getIPString('SubnetMask'):
            return

        ipAddress = self.getIPString('IPAddress')
        try:
            netmask = net_utils.calculateNetmask(ipAddress)
        except ValueError:
            pass
        else:
            self.setIPString('SubnetMask', netmask)


    def calcGatewayNameserver(self, widget, *args):
        '''Calculate the gateway and primary nameserver, if they haven't
           been set.
           Skip the nameserver, if it's not mentioned in
           self.relevantIPFields.
        '''
        if self.getIPString('Gateway'):
            return

        ipAddress = self.getIPString('IPAddress')
        netmask = self.getIPString('SubnetMask')
        try:
            gateway = net_utils.calculateGateway(ipAddress, netmask)
        except ValueError:
            pass
        else:
            self.setIPString('Gateway', gateway)

        if 'ns1' in self.relevantIPFields:
            try:
                primaryNS = net_utils.calculateNameserver(ipAddress, netmask)
            except ValueError:
                pass
            else:
                self.setIPString('PrimaryNS', primaryNS)


    def getHostnameEntry(self):
        widget = self.xml.get_widget(
            self.clientName + _ipTests['hostname'][0])
        assert widget
        return widget


    def testIPSettings(self, tests=[]):
        '''Test numerous IP settings to make certain they are valid.'''
        for testName in tests:
            assert testName in self.relevantIPFields

        ipSettings = {}

        # construct an empty set of network settings
        for setting in self.relevantIPFields:
            ipSettings[setting] = ""

        for testName in tests:
            if testName not in _ipTests:
                raise ValueError("Improper test %s" % (testName))

            (entry, title, error, testFunc) = _ipTests[testName]

            if testName == "hostname":
                ipSetting = self.getHostnameEntry().get_text()
                if not ipSetting:
                    common_windows.MessageWindow(self.thisWindow, title,
                                                 "Enter a hostname.")
                    raise exception.StayOnScreen
            else:
                ipSetting = self.getIPString(entry, formatted=0)

            try:
                testFunc(ipSetting)
            except (ValueError, TypeError), msg:
                if str(msg):
                    # Use the message from the exception, it should be more
                    # descriptive than the generic error from _ipTests.
                    error = str(msg)
                common_windows.MessageWindow(self.thisWindow, title, error)
                raise exception.StayOnScreen
            else:
                if ipSetting and testName != "hostname":
                    # filter out any leading zeros
                    ipSetting = net_utils.formatIPString(ipSetting)
                    self.setIPString(entry, ipSetting)
                ipSettings[testName] = ipSetting

        return ipSettings


    def toggleIPTable(self, widget, *args):
        self.networkTable.set_sensitive(not widget.get_active())


