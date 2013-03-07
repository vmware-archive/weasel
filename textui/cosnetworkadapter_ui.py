#!/usr/bin/env python
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

'''COS Network Adapter
'''

from log import log
import userchoices
import networking
import textengine
from textrunner import TextRunner, SubstepTransitionMenu as TransMenu
import nic_setup
import network_address_setup

titleAdapter = 'COS Network Adapter'
titleSettings = 'COS Network Settings'

selectNetConfigMethodText = """\
Choose how network settings should be configured (DHCP or Static IP).

Current choice: %(currName)s
 1) Keep %(currDescribe)s
 2) Change to %(newDescribe)s
 <) Back
 ?) Help

"""

helpText = """\
A network adapter (sometimes called a network interface or NIC) must be
available for ESX installation.

If no network adapter is available, then the proper driver may not be
loaded or there is a hardware failure.  You must cancel this installation
process and remedy the problem before you can continue.

If a network adapter is available, but not connected, then installation
can continue, but services such as NTP will not be available during
installation.

"""

def buildCancelBackHelp():
    """Build custom version of ExitBackHelp """
    menuList = (TransMenu._exit, TransMenu._back, TransMenu._help)
    menu = '\n' + '\n'.join(menuList) + '\n\n'
    return menu

class CosNetworkAdapterWindow(TextRunner):
    "COS network adapter and address setup."

    def __init__(self):
        super(CosNetworkAdapterWindow, self).__init__()
        networking.init()
        self.substep = self.start
        self.nic = {}   # device, ip, netmask, bootProto, vlanID
        self.net = {}   # gateway, nameserver[12], hostname

    # -------- substeps --------
    def start(self):
        "Fetch initial COS NIC and network from userchoices."

        # userchoices.getCosNICS() returns a list of dicts.
        # It probably should have been a single (possibly empty) dict.
        cosnics = userchoices.getCosNICs()
        if cosnics:
            self.nic = cosnics[0]

        # Get existing COS network from userchoices.
        self.net = userchoices.getCosNetwork()

        self.setSubstepEnv({'next': self.askCosNic })

    # ---- COS NIC ----
    def askCosNic(self):
        "Get COS NIC info; includes device and VLAN ID."
        nicsetup = nic_setup.NicSetup(
            interfaceName=titleAdapter,
            task="system tasks",
            cosnic=self.nic)
        try:
            result = nicsetup.run()
        except (ValueError, RuntimeError), ex:
            # RuntimeError is definitely bad.
            # ValueError is here just in case NicSetup changes.
            log.error(str(ex))
            menu = {
                '<': self.stepBack,
                '?': self.help,
                '!': self.cancel,
            }
            preface = "Cannot configure COS network inteface."
            body = '\n'.join([preface, str(ex), buildCancelBackHelp()])
            ui = { 'title': titleAdapter, 'body': body, 'menu': menu }
            self.setSubstepEnv(ui)
            return

        if result == textengine.DISPATCH_NEXT:
            self.setSubstepEnv( {'next': self.updateCosNic } )
        else:  # assume result == textengine.DISPATCH_BACK:
            self.setSubstepEnv( {'next': self.stepBack } )

    def updateCosNic(self):
        "Register COS NIC in userchoices."

        assert 'device' in self.nic, "COS NIC requires device"
        assert 'vlanID' in self.nic, "COS NIC requires VLAN ID"

        currentNics = userchoices.getCosNICs()
        if currentNics:
            # COS NIC was previously defined in userchoices.
            # get rid of existing one.
            assert len(currentNics) == 1, "should have only one COS NIC."
            userchoices.delCosNIC(currentNics[0])
            # Use previously set self.net.
        else:
            # Prior to network config, set as DHCP.
            self.nic['bootProto'] = userchoices.NIC_BOOT_DHCP
            self.nic['ip'] = None
            self.nic['netmask'] = None
            self.net = { 'gateway': None,
                'nameserver1': None, 'nameserver2': None, 'hostname': None }

        userchoices.addCosNIC(self.nic['device'], self.nic['vlanID'],
                              self.nic['bootProto'],
                              self.nic['ip'], self.nic['netmask'])

        self.setSubstepEnv( {'next': self.selectNetConfigMethod } )

    # ---- Network Config Method ----
    def selectNetConfigMethod(self):

        methods = {
            'dhcp': {
                'name': 'DHCP',
                'describe': 'automatic DHCP settings',
                'substep': self.updateDHCPMethod,
            },
            'staticip': {
                'name': 'static IP',
                'describe': 'static IP network settings',
                'substep': self.askStaticIP,
            },
        }

        # Get existing config method
        self.net = userchoices.getCosNetwork()

        if self.nic['bootProto'] == userchoices.NIC_BOOT_DHCP:
            currMethod = 'dhcp'
            newMethod = 'staticip'
        else:
            currMethod = 'staticip'
            newMethod = 'dhcp'
        textArgs = {
            'currName': methods[currMethod]['name'],
            'currDescribe': methods[currMethod]['describe'],
            'newDescribe': methods[newMethod]['describe'],
        }

        ui = {
            'title': titleSettings,
            'body': selectNetConfigMethodText % textArgs,
            'menu': {
                '1': methods[currMethod]['substep'],
                '2': methods[newMethod]['substep'],
                '<': self.askCosNic,
                '?': self.help,
            }
        }

        self.setSubstepEnv(ui)

    def updateDHCPMethod(self):
        "update network settings using DHCP"
        userchoices.clearCosNetwork()
        nic_0 = userchoices.getCosNICs()[0]   # get old cosnic
        device, vlanID = nic_0['device'], nic_0['vlanID']
        userchoices.delCosNIC(nic_0)    # delete if exists in userchoices
        bootProto = userchoices.NIC_BOOT_DHCP
        userchoices.addCosNIC(device, vlanID, bootProto)   # add new cosnic
        self.setSubstepEnv( {'next': self.done } )

    def help(self):
        "Emit help text."
        self.helpPushPop(titleSettings + ' (Help)', helpText + TransMenu.Back)

    # ---- Static IP ----
    def askStaticIP(self):
        "ask if network should be configured using static IP"
        fields = {
            # NIC fields
            'ip': self.nic.get('ip', None),
            'netmask': self.nic.get('netmask', None),
            # net fields
            'gateway': self.net.get('gateway', None),
            'ns1': self.net.get('nameserver1', None),
            'ns2': self.net.get('nameserver2', None),
            'hostname': self.net.get('hostname', None),
        }

        netsetup = network_address_setup.NetworkAddressSetup(
                clientName="COS Network Configuration",
                task="COS network configuration",
                fields=fields)
        result = netsetup.run()

        assert(len(userchoices.getCosNICs()) == 1)
        nic_0 = userchoices.getCosNICs()[0]   # get old cosnic
        self.nic = {
            'device': nic_0['device'],
            'vlanID': nic_0['vlanID'],
            'bootProto': userchoices.NIC_BOOT_STATIC,
            'ip': fields['ip'],
            'netmask': fields['netmask']
        }
        self.net = {
            'gateway': fields['gateway'],
            'nameserver1': fields['ns1'],
            'nameserver2': fields['ns2'],
            'hostname': fields['hostname'],
        }

        if result == textengine.DISPATCH_NEXT:
            self.setSubstepEnv( {'next': self.configureStaticIP } )
        else:  # assume result == textengine.DISPATCH_BACK:
            self.setSubstepEnv( {'next': self.selectNetConfigMethod } )

    def configureStaticIP(self):
        "do static IP configuration"
        # Retain COS NIC device and VLAN settings, update ip/netmask.
        currentNics = userchoices.getCosNICs()
        assert len(currentNics) == 1, "should have only one COS NIC."
        userchoices.delCosNIC(currentNics[0])
        userchoices.addCosNIC(self.nic['device'], self.nic['vlanID'],
                              self.nic['bootProto'],
                              self.nic['ip'], self.nic['netmask'])

        # Update network params.
        userchoices.setCosNetwork(self.net['gateway'],
                              self.net['nameserver1'], self.net['nameserver2'],
                              self.net['hostname'])

        self.setSubstepEnv( {'next': self.done } )

    def done(self):
        "set up network NOW"
        try:
            networking.cosConnectForInstaller()
        except Exception, ex:
            log.exception(str(ex))
        self.setSubstepEnv( {'next': self.stepForward } )

# vim: set sw=4 tw=80 :
