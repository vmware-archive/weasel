
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
import userchoices
import networking
import iscsi
import ip_entry
from consts import DialogResponses
from common_windows import MessageWindow

_ipEntryCreated = False
_ipEntry = None
_needsPrepopulating = True
def setIpEntry(widget):
    global _ipEntry
    _ipEntry = widget
def setIpEntryCreated(b):
    global _ipEntryCreated
    _ipEntryCreated = b
def setNeedsPrepopulating(b):
    global _needsPrepopulating
    _needsPrepopulating = b


class iSCSISetupWindow:
    def __init__(self, controlState, xml, parentDialog):
        controlState.setDisplayHeaderBar(True)
        controlState.windowTitle = "Add software iSCSI storage"
        controlState.windowText = "Specify iSCSI settings"

        self.xml = xml
        self.parent = parentDialog
        self.thisWindow = controlState.gui.getWindow()

        if not _ipEntryCreated:
            setIpEntry(ip_entry.IP_Entry())
            # Eventually we'll replace this gtk.Entry with some kind of custom
            # widget, and that's why I'm creating even Entry programmatically,
            # rather than bringing it in from the .glade file.
            xml.get_widget("IscsisetupTargetIPAddressHbox"
                           ).pack_start(_ipEntry,
                                        expand=False, fill=False)
            _ipEntry.show()
            setIpEntryCreated(True)

        # First time through, prepopulate by querying VSI nodes.
        if _needsPrepopulating:
            self.prepopulateWidgets()
            self.deEditableizeAllChildren()
            xml.signal_autoconnect({'clickedBack' : self.getBack,
                                    'clickedFinish' : self.getFinish,
                                    'clickedCancel' : self.getCancel})


    def deEditableizeAllChildren(self):
        """
        Since everything in this screen has to come from the NIC option ROM,
        it makes no sense to let the user edit here.  However, if he tries to
        edit anything, a warning pops up instructing him to register his wishes
        with the NIC's option ROM.
        """

        # Collect all Entry widgets, in a list.
        def gatherChildEntries(widget, children):
            if(isinstance(widget, gtk.Entry) or
               isinstance(widget, ip_entry.IP_Entry)):
                children.append(widget)
            else:
                try:
                    for child in widget.get_children():
                        gatherChildEntries(child, children)
                except AttributeError:
                    pass
        children = []
        gatherChildEntries(self.parent, children)
        def notEditableWarning(unused1,unused2):
            MessageWindow(self.thisWindow, 'iSCSI',
              "To change this entry, reconfigure the NIC's option ROM",
              'warning')
        for child in children:
            child.set_editable(False)
            child.connect('key-press-event', notEditableWarning)


    def prepopulateWidgets(self):
        iscsiBootTable = iscsi.getIscsiBootTable()
        # TODO: When (and if) we support more than one iSCSI-capable NIC,
        #       revisit this code.

        _ipEntry.set_text(iscsiBootTable.targetIP)
        for pair in (
              ('IscsisetupInitiatorIQNEntry', iscsiBootTable.initiatorName),
              ('IscsisetupInitiatorAliasEntry', iscsiBootTable.initiatorAlias),
              ('IscsisetupTargetIQNEntry', iscsiBootTable.targetName),
              ('IscsisetupPortEntry', iscsiBootTable.targetPort),
              ('IscsisetupUserNameEntry', iscsiBootTable.chapName),
              ('IscsisetupPassword1Entry', iscsiBootTable.chapPwd),
              ('IscsisetupPassword2Entry', iscsiBootTable.chapPwd)):
            self.xml.get_widget(pair[0]).set_text(str(pair[1]))

        setNeedsPrepopulating(False)


    def getFinish(self, *args):
        initiatorIQN = self.xml.get_widget('IscsisetupInitiatorIQNEntry')
        initiatorAlias = self.xml.get_widget('IscsisetupInitiatorAliasEntry')
        targetIQN = self.xml.get_widget('IscsisetupTargetIQNEntry')
        targetIP = _ipEntry
        port = self.xml.get_widget('IscsisetupPortEntry')
        username = self.xml.get_widget('IscsisetupUserNameEntry')
        password1 = self.xml.get_widget('IscsisetupPassword1Entry')

        try:
            iscsi.validateIQN(initiatorIQN.get_text())
            iscsi.validateIQN(targetIQN.get_text())
            self._validateNameAndPwd()
            networking.utils.sanityCheckIPString(targetIP.get_text())
        except ValueError, msg:
            MessageWindow(self.thisWindow, 'iSCSI', str(msg), 'warning')
            self.parent.response(DialogResponses.STAYONSCREEN)
            return

        userchoices.setIscsiInitiatorAndTarget(
            initiatorIQN.get_text(),
            initiatorAlias.get_text(),
            targetIQN.get_text(),
            _ipEntry.get_text(),
            port.get_text(),
            username.get_text(),
            password1.get_text())

        try:
            iscsi.activate(userchoices.getVmkNICs()[0]['bootProto'] ==
                           userchoices.NIC_BOOT_DHCP,
                           userchoices.getVmkNICs()[0]['ip'],
                           userchoices.getVmkNICs()[0]['netmask'],
                           userchoices.getVmkNetwork()['gateway'],
                           iscsi.getNicMacAddresses()[0])
        except Exception, ex:
            MessageWindow(self.thisWindow,
                          'iSCSI network setup failure', str(ex) )
            # TODO: what else do we need to do here?
           
        iscsi.vmkNicAndNetworkRollerbacker.backup()
        self.parent.response(DialogResponses.FINISH)


    def getBack(self, *args):
        self.parent.response(DialogResponses.BACK)


    def getCancel(self, *args):
        """
        Handle "cancel" button.
        We're on the second of the two iSCSI screens here, but even so the
        "cancel" button undoes even settings changed in the first screen.
        """
        iscsi.vmkNicAndNetworkRollerbacker.rollback()
        self.parent.response(DialogResponses.CANCEL)


    def _validateNameAndPwd(self):
        """
        User name is optional.  But if one is provided, a password is required,
        and the password must be 12-16 bytes long (with no other restrictions).
        """
        userName = self.xml.get_widget("IscsisetupUserNameEntry")
        if not userName.get_text().strip():
            return
            
        passwd1 = self.xml.get_widget("IscsisetupPassword1Entry").get_text()
        passwd2 = self.xml.get_widget("IscsisetupPassword2Entry").get_text()
        iscsi.validateCHAPPassword(passwd1)

        if passwd1 != passwd2:
            raise ValueError, "The two passwords entered did not match."
