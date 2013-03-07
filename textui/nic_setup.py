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
#

'''NIC setup
This module is used for set-up of the COS network adapter and software iSCSI.
'''

from log import log
import util
import networking
from textrunner import TextRunner, SubstepTransitionMenu as TransMenu

askConfirmText = """\
Select an adapter for ESX to use for %(task)s.
(Choose option 2 (Change) to change either the current adapter choice
or the VLAN ID.)

Current choice:
    %(line1)s
    %(line2)s
  VLAN ID: %(vlan)s
"""

nicHelpText = """\
Select the number of the network adapter you want to use for
%(task)s.
"""

vlanAskConfirmText = """\
Does this adapter require a VLAN ID?
(Choose option 2 (No) if you are not sure.)
    Current choice:  %(use)s    ID: %(vlan)s
"""

vlanSelectText = """\
Enter the VLAN ID.  (an integer in the range of 0-4095)

['<': back, '?': help]
"""

vlanHelpText = """\
The VLAN ID (virtual local area network ID) should be specified by
your network administrator.  The value can range from 0 to 4095.
If you are unsure of the VLAN ID, select No.
"""

errEpilog = TransMenu.Back

prologNicSelectText = """\
    Select an adapter for ESX to use for %(task)s.
    Current choice:
        %(line1)s
        %(line2)s
"""

# -------- menu generation function  --------

def buildKeepChangeBackHelpExit():
    """Build custom version of KeepChangeBackHelpExit."""
    menuList = (TransMenu._keep + " %(linkstat)s",
        TransMenu._change, TransMenu._back, TransMenu._help, TransMenu._exit)
    menu = menu = '\n' + '\n'.join(menuList) + '\n\n'
    return menu


# -------- utility functions  --------
def describeNic(nic):
    "Textual description of NIC - two lines"
    if nic.isLinkUp:
        linkstat = "connected"
    else:
        linkstat = "not connected"
    namePart = util.truncateString(nic.humanReadableName, 42)
    line0 = "%s: %s" % (nic.driverName, namePart)
    line1 = "(%s) [%s]" % (nic.macAddress, linkstat)
    return line0, line1

def listNicChoices(nics):
    "Textual description of NICs"
    nicChoices = []
    for num, nic in enumerate(nics):
        lines = describeNic(nic)
        line0 = "%2d. %s" % (num+1, lines[0])
        line1 = "    %s" % lines[1]
        nicChoices.append("%s\n%s" % (line0, line1))
    return nicChoices

# -------- main class --------
class NicSetup(TextRunner):
    """Network interface card selection and setup
    """
    def __init__(self,
                 interfaceName="unknown interface",
                 task="some tasks",
                 cosnic={},     # really should be filled in by caller
                 oldUserChoiceMacAddress = None,
                 wantedMacAddresses = None):
        # Note:  wantedMacAddresses is currently ignored, but will
        # probably be important for iSCSI.

        super(NicSetup, self).__init__()
        self.task = task
        self.interfaceName = interfaceName
        self.cosnic = cosnic
        self.wantedMacAddresses = wantedMacAddresses or ()  # ?? () ??
        self.substep = self.start

        device = self.cosnic.setdefault('device', None)
        if device:
            oldUserChoiceMacAddress = device.macAddress
        else:
            oldUserChoiceMacAddress = None

        # MAC addresses of various NIC alternatives
        self.altMac = {
            'userSelected': None,
            'userchoices': oldUserChoiceMacAddress,
            'suggest': None,
        }

        # VLAN info
        self.vlanID = self.cosnic.setdefault('vlanID', None)

    # -------- substeps --------
    def start(self):

        self.nics = networking.getPhysicalNics()  # all of them
        if not self.nics:
            raise RuntimeError, 'No network adapters detected.'
        try:
            nic = networking.getPluggedInAvailableNIC(self.nics[0])
        except networking.ConnectException, ex:
            # with argument to getPluggedInAvailableNIC(), we should NEVER
            # get here.  If we do, something is seriously wrong.
            raise RuntimeError, 'NIC setup failure.'
        self.altMac['suggest'] = nic.macAddress

        self.setSubstepEnv( {'next': self.askConfirm } )


    def askConfirm(self):

        for alt in ('userSelected', 'userchoices', 'suggest'):
            if self.altMac[alt]:
                nicMac = self.altMac[alt]
                self.device = networking.findPhysicalNicByMacAddress(nicMac)
                break
        assert self.device
        log.debug("nic_setup self.device %s" % self.device)

        line1, line2 = describeNic(self.device)
        if self.device.isLinkUp:
            linkstat = ""
        else:
            linkstat = "(not connected)"
        nicparams = {
            'task': self.task,
            'line1': line1, 'line2': line2,
            'vlan': self.vlanID,
            'linkstat' : linkstat,
        }
        ui = {
            'title': self.interfaceName,
            'body': (askConfirmText + buildKeepChangeBackHelpExit()) \
                % nicparams,
            'menu': {
                '1': self.done,
                '2': self.nicSelectFromList,
                '<': self.stepBack,
                '?': self.nicHelp,
            }
        }
        self.setSubstepEnv(ui)

    def nicSelectFromList(self):
        "Set up list of NICs."
        SCROLL_LIMIT = 8
        scrollable = listNicChoices(self.nics)
        self.setScrollEnv(scrollable, SCROLL_LIMIT)
        self.setSubstepEnv({'next': self.scrollDisplay})
        self.help = self.nicHelp

    def scrollDisplay(self):
        "Display available NICs."
        line1, line2 = describeNic(self.device)
        self.buildScrollDisplay(self.scrollable, self.interfaceName,
            self.nicUpdate, "<number>: adapter choice", allowStepRestart=True,
            prolog=prologNicSelectText % {'task': self.task,
            'line1': line1, 'line2': line2 })

    def nicUpdate(self):
        # check for numeric input
        try:
            selected = self.getScrollChoice()
        except (IndexError, ValueError), msg:
            body = '\n'.join(['Input error', msg[0], errEpilog])
            self.errorPushPop(self.interfaceName +' (Update)', body)
            return

        nic = self.nics[selected]
        self.altMac['userSelected'] = nic.macAddress
        self.setSubstepEnv( {'next': self.vlanAsk } )


    def vlanAsk(self):
        if self.vlanID != None:
            use = "Yes"
        else:
            use = "No"
        vlanparams = { 'use': use, 'vlan': self.vlanID }
        ui = {
            'title': self.interfaceName,
            'body': vlanAskConfirmText%vlanparams + TransMenu.YesNoBackHelp,
            'menu': {
                '1': self.vlanSelect,
                '2': self.vlanSelectNone,
                '<': self.askConfirm,
                '?': self.vlanHelp,
            }
        }
        self.setSubstepEnv(ui)

    def vlanSelect(self):
        ui = {
            'title': self.interfaceName,
            'body': vlanSelectText,
            'menu': {
                '<': self.nicSelectFromList,
                '?': self.vlanHelp,
                '*': self.vlanUpdate,   # process input
            }
        }
        self.setSubstepEnv(ui)

    def vlanSelectNone(self):
        self.vlanID = None
        self.setSubstepEnv( {'next': self.askConfirm} )

    def vlanUpdate(self):
        "Assign VLAN ID from user input. "
        substepTitle = self.interfaceName + ' (Update)'

        vlanID = self.userinput.strip()
        try:
            networking.utils.sanityCheckVlanID(vlanID)
        except ValueError, ex:
            body = "\n".join(["Input error", str(ex), errEpilog])
            self.errorPushPop(substepTitle, body)
            return
        self.vlanID = int(vlanID)

        self.setSubstepEnv( {'next': self.askConfirm} )

    def nicHelp(self):
        "Show help text for NIC selection."
        self.helpPushPop(self.interfaceName + ' (Help)',
            nicHelpText % {'task':self.task} + TransMenu.Back)

    def vlanHelp(self):
        "Show help text for VLAN ID."
        self.helpPushPop(self.interfaceName + ' (Help)',
            vlanHelpText + TransMenu.Back)

    def done(self):
        self.cosnic['device'] = self.device
        self.cosnic['vlanID'] = self.vlanID

        self.setSubstepEnv( {'next': self.stepForward } )

# vim: set sw=4 tw=80 :
