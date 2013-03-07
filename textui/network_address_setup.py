# python
#-*- coding: utf-8 -*-

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

'''Network address setup
This module is used for set-up of the COS network adapter and software iSCSI.
'''

import sys

from log import log
import networking.utils as net_utils
import textengine
from textrunner import TextRunner


askConfirmText = """\
%(label)s
Current choice: %(value)s
 1) Keep
 2) Change
 <) Back
 ?) Help

"""

askConfirmSummaryText = """\
Current choices:
IP Address:     %(ip)s
Subnet Mask:    %(netmask)s
Gateway:        %(gateway)s
Primary DNS:    %(ns1)s
Secondary DNS:  %(ns2)s
Hostname:       %(hostname)s

 1) Keep
 2) Change
 <) Back
 ?) Help

"""

fieldEnterText = """\
Enter the %(label)s
Current choice: %(value)s

['<': back, '?': help]
"""

sipHelpText = """\
Enter static IP settings for ESX.
Use "dotted-decimal" notation for IP addresses, for example, "192.168.1.123".
Hostname should be the fully qualified domain name (FQDN) of the system.

 <) Back

"""
errEpilog = """\

 <) Back

"""

# -------- utility functions and data structures --------

# testDNSIPString() stolen from gui/network_address_widgets.py.
def testDNSIPString(ipString):
    '''The name servers get treated specially since they
    don't necessarily need a value.
    '''
    if ipString == '':
        return
    else:
        return net_utils.sanityCheckIPString(ipString)

# _ipTests is inspired by gui/network_address_widgets.py _ipTests

class IpTestsBuilder:
    def __init__(self, label, errHead, errText, sanityFunc,
        defaultValueFunc, defaultValueParams, mandatory):
        self.__dict__.update(locals())
        del self.__dict__['self']

_ipTests = {
    "ip" : IpTestsBuilder("IP Address", "IP Address Error",
        "The IP address you entered was invalid.",
        net_utils.sanityCheckIPString,
        None, None,
        True),
    "netmask" : IpTestsBuilder("Subnet Mask", "Subnet Mask Error",
        "The Subnet Mask you entered was invalid.",
        net_utils.sanityCheckNetmaskString,
        net_utils.calculateNetmask, ["ip",],
        True),
    "gateway" : IpTestsBuilder("Gateway", "Gateway Address Error",
        "The Gateway address you entered was invalid.",
        net_utils.sanityCheckGatewayString,
        net_utils.calculateGateway, ["ip", "netmask"],
        True),
    "ns1" : IpTestsBuilder("Primary DNS", "Primary DNS Error",
        "The Primary DNS address you entered was invalid.",
        testDNSIPString,
        net_utils.calculateNameserver, ["ip", "netmask"],
        False),
    "ns2" : IpTestsBuilder("Secondary DNS", "Secondary DNS Error",
        "The Secondary DNS address you entered was invalid.",
        testDNSIPString,
        None, ["ip", "netmask"],
        False),
    "hostname" : IpTestsBuilder("Hostname", "Hostname Error", "",
        net_utils.sanityCheckHostname,
        None, None,
        True),
}

# query fields in this order:
_fieldQueue = ["ip", "netmask", "gateway", "ns1", "ns2", "hostname"]

# -------- main class --------
class NetworkAddressSetup(TextRunner):
    """IP setup
    """
    # TODO: use calcSubnetMask() and calcGatewayNameServer()
    # to compute default values before user input.

    def __init__(self, clientName="unknown client",
            task="some tasks", fields={}):
        super(NetworkAddressSetup, self).__init__()
        self.task = task
        self.clientName = clientName
        self.fields = fields
        self.substep = self.start
        self.confirmed = []
        self.fqx = iter(_fieldQueue)

    # -------- utilities --------
    def getFieldParams(self, fieldName):
        props = _ipTests[fieldName]

        params = {}
        params['name'] = fieldName
        params['label'] = props.label

        if fieldName in self.fields and self.fields[fieldName]:
            params['value'] = self.fields[fieldName]
        elif fieldName not in self.fields:   # not yet set
            params['value'] = self.getDefaultValue(fieldName)
        elif props.mandatory:
            params['value'] = self.getDefaultValue(fieldName)
        else: # optional field
            params['value'] = None
        return params

    def getDefaultValue(self, fieldName):
        params = []
        defaultFunc = _ipTests[fieldName].defaultValueFunc
        defaultParams = _ipTests[fieldName].defaultValueParams
        if not defaultFunc:
            return None  # no default value
        for p in defaultParams:
            if p not in self.fields:
                return None  # incomplete list of parameters
        # Build argument list for function, and invoke.
        args = [self.fields[name] for name in defaultParams]
        value = defaultFunc(*args)
        return value

    # -------- substeps --------
    def start(self):
        if 'hostname' in self.fields and self.fields['hostname']:
            # fields previous populated
            self.setSubstepEnv( {'next': self.askConfirmSummary } )
        else:
            # first iteration to populate fields
            self.setSubstepEnv( {'next': self.iterate } )

    def iterate(self):
        try:
            fieldName = self.fieldName = self.fqx.next()
            if (fieldName not in self.fields) or (not self.fields[fieldName]):
                # no existing value, attempt default
                params = self.getFieldParams(fieldName)
                if params and params['value']:
                    self.fields[fieldName] = params['value']

            if (fieldName in self.fields) and self.fields[fieldName]:
                # value exists already
                self.setSubstepEnv( {'next': self.askConfirm } )
            else:
                # value doesn't exist yet
                self.setSubstepEnv( {'next': self.enterField } )
        except StopIteration:
            self.setSubstepEnv( {'next': self.askConfirmSummary } )
            self.fqx = iter(_fieldQueue)
        return

    def askConfirm(self):
        params = self.getFieldParams(self.fieldName)
        ui = {
            'title': self.clientName,
            'body': askConfirmText % params,
            'menu': {
                '1': self.iterate,
                '2': self.enterField,
                '<': self.stepBack,
                '?': self.help,
            }
        }
        self.setSubstepEnv(ui)

    def enterField(self):
        params = self.getFieldParams(self.fieldName)
        ui = {
            'title': self.clientName,
            'body': fieldEnterText % params,
            'menu': {
                '<': self.stepBack,
                '?': self.help,
                '*': self.checkField,
            }
        }
        self.setSubstepEnv(ui)

    def checkField(self):
        sanitytest = _ipTests[self.fieldName].sanityFunc
        try:
            result = sanitytest(self.userinput)
            if self.userinput:
                if self.fieldName != 'hostname':
                    # get normalized octets
                    self.fields[self.fieldName] = \
                        net_utils.formatIPString(self.userinput)
                else:
                    # hostname: use userinput directly
                    self.fields[self.fieldName] = self.userinput
            else:
                self.fields[self.fieldName] = None

            if self.fieldName == 'ns2':
                if not self.fields.get('ns2'):
                    pass        # empty ns1 okay
                elif not self.fields.get('ns1'):
                    # non-empty ns2 requires non-empty ns1
                    raise ValueError("Primary DNS not yet set.")
                elif self.fields['ns1'] == self.fields['ns2']:
                    raise ValueError("Primary and secondary DNS cannot be identical.")
        except ValueError, msg:
            body = '\n'.join([str(msg), errEpilog])
            self.errorPushPop(self.clientName, body)
            return
        self.setSubstepEnv( {'next': self.askConfirm } )

    def askConfirmSummary(self):
        "Produce displayed summary for confirmation."
        displayedFields = {}
        for fieldName, fieldValue in self.fields.items():
            if fieldValue:
                displayedFields[fieldName] = fieldValue
            else:
                displayedFields[fieldName] = "(Not assigned)"
        ui = {
            'title': self.clientName,
            'body': askConfirmSummaryText % displayedFields,
            'menu': {
                '1': self.done,
                '2': self.iterate,
                '<': self.stepBack,
                '?': self.help,
            }
        }
        self.setSubstepEnv(ui)

    def help(self):
        "help for static IP"
        self.pushSubstep()
        ui = {
            'title': self.clientName + ' (Help)',
            'body': sipHelpText,
            'menu': { '*': self.popSubstep }
        }
        self.setSubstepEnv(ui)

    def done(self):
        "fini."
        try:
            net_utils.sanityCheckIPSettings(self.fields["ip"],
                                            self.fields["netmask"],
                                            self.fields["gateway"])
        except ValueError, msg:
            body = '\n'.join([str(msg), errEpilog])
            self.errorPushPop(self.clientName, body)
            return
        self.setSubstepEnv( {'next': self.stepForward} )

# vim: set sw=4 tw=80 :
