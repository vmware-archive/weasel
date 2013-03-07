#! /usr/bin/python

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
import os

import util
import userchoices
import exception
import networking
from common_windows import MessageWindow
from log import log

class NicSetup:
    """
    Selects a NIC and, optionally, sets a VLAN ID.
    Used by cosnetworkadapter_gui.py and iscsinetwork_gui.py.

    Makes strong assumptions about the layout of things in the glade file:
    there's got to be a ComboBox; a CheckButton and an Entry and an HBox
    surrounding the CheckButton and the Entry.

    If wantedMacAddresses is not None, then it's a list of the only NICs that
    should show up in the combobox.  (If it's empty, then we list all NICs.)

    If queryCurrentFn is set, it should be a function that returns the
    NIC *device* that is currently selected.
    """
    def __init__(self, xml, thisWindow,
                 comboBoxName, vlanCheckButtonName, vlanEntryName,
                 vlanIDHBoxName,
                 wantedMacAddresses=None,
                 queryCurrentFn=None):
        self.xml = xml
        self.thisWindow = thisWindow
        self.comboBox = xml.get_widget(comboBoxName)
        self.vlanCheckButton = xml.get_widget(vlanCheckButtonName)
        self.vlanEntry = xml.get_widget(vlanEntryName)
        self.vlanIDHBox = xml.get_widget(vlanIDHBoxName)
        self.wantedMacAddresses = wantedMacAddresses or ()
        self.queryCurrentFn = queryCurrentFn or (lambda: None)

        # TODO: vlanEntry needs a handler to reject non-numeric characters
        # the moment they're typed.

        self.connectivityPixbufs = \
            {'connected': gtk.gdk.pixbuf_new_from_file(
                              os.path.join(os.path.dirname(__file__),
                              'images/connected.png')),
             'disconnected': gtk.gdk.pixbuf_new_from_file(
                              os.path.join(os.path.dirname(__file__),
                              'images/disconnected.png'))}

        self.populateComboBox()
        self.vlanCheckButton.connect('toggled', self._handleVlanCheckButton)
        self.comboBox.connect('realize', self._comboRealized)


    def _comboRealized(self, widget):
        # The root window is the GDK Window that pops up when a user clicks
        # on the comboBox widget.  It doesn't exist until the comboBox is
        # realized, so we have to set the cursor in this special function.
        rootWin = self.comboBox.get_root_window()
        rootWin.set_cursor(gtk.gdk.Cursor(gtk.gdk.LEFT_PTR))


    def populateComboBox(self):
        self.comboBox.clear()

        # Find available NICs and put them in the liststore
        nics = networking.getPhysicalNics()
        if not nics:
            raise RuntimeError, 'No network interfaces detected'
        if self.wantedMacAddresses:
            nics = [nic for nic in nics
                    if nic.macAddress in self.wantedMacAddresses]
            if not nics:
                log.error('No NICs passed MAC address filter')
                raise RuntimeError, 'No appropriate NICs detected'
        nics.sort(lambda x,y: cmp(y.isLinkUp, x.isLinkUp))

        liststore = gtk.ListStore(object, str, bool)
        for nic in nics:
            namePart = util.truncateString(nic.humanReadableName, 24)
            identifier = '%s (MAC: %s)' % (namePart, nic.macAddress)
            liststore.append([nic, identifier, nic.isLinkUp])
        self.comboBox.set_model(liststore)

        # Three cells: nic name, toggle, connected/disconnected
        nicNameCell = gtk.CellRendererText()
        self.comboBox.pack_start(nicNameCell, expand=True)
        self.comboBox.add_attribute(nicNameCell, 'text', 1)

        crp = gtk.CellRendererPixbuf()
        self.comboBox.pack_start(crp, expand=False)
        self.comboBox.set_cell_data_func(crp,
                                         self._connectedPixmapGenerator)

        connectedTextCell = gtk.CellRendererText()
        connectedTextCell.set_property('family', 'monospace')
        connectedTextCell.set_property('width-chars', 15)
        self.comboBox.pack_start(connectedTextCell, expand=False)
        self.comboBox.set_cell_data_func(connectedTextCell,
                                         self._connectedTextGenerator)

        # Now figure out which row should be active
        currentNic = self.queryCurrentFn()
        if currentNic:
            # If there's one that has already been selected, activate that
            for i, nic in enumerate(nics):
                if nic == currentNic:
                    self.comboBox.set_active(i)
                    break
        else:
            # Set-active the first NIC that hasn't been claimed already (e.g. 
            # we might be configuring iSCSI, having already configured COS 
            # networking) and which is connected ("isLinkUp").
            claimedNics = userchoices.getClaimedNICDevices()
            suggestedNic = None
            for i, nic in enumerate(nics):
                if nic not in claimedNics and nic.isLinkUp:
                    suggestedNic = i
                    self.comboBox.set_active(suggestedNic)
                    break
            if suggestedNic == None:
                if claimedNics:
                    MessageWindow(self.thisWindow, 'NICs',
                                  ('All the connected network adapters are'
                                   'claimed. Proceed with caution.'),
                                  'warning')
                self.comboBox.set_active(0)


    def _connectedTextGenerator(self, column, cellRenderer, treeModel,
                                iterator):
        if treeModel.get_value(iterator,2):
            cellRenderer.set_property('text', '-Connected')
        else:
            cellRenderer.set_property('text', '-Disconnected')


    def _connectedPixmapGenerator(self, column, cellRenderer, treeModel,
                                  iterator):
        if treeModel.get_value(iterator,2):
            cellRenderer.set_property('pixbuf',
                                      self.connectivityPixbufs['connected'])
        else:
            cellRenderer.set_property('pixbuf',
                                      self.connectivityPixbufs['disconnected'])


    def _handleVlanCheckButton(self, widget):
        self.vlanIDHBox.set_sensitive(widget.get_active())


    def getDevice(self):
        """ Return the NIC selected in the ComboBox. """
        activeIter = self.comboBox.get_active_iter()
        nic = self.comboBox.get_model().get_value(activeIter, 0)
        return nic


    def getVlanID(self):
        """ Return the ID or, if the VLAN checkbox isn't checked, None """
        vlanID = None
        if self.vlanCheckButton.get_active():
            vlanID = self.vlanEntry.get_text().strip()
            try:
                networking.utils.sanityCheckVlanID(vlanID)
            except ValueError, message:
                MessageWindow(self.thisWindow, 'Vlan ID', str(message),
                              'warning')
                raise exception.StayOnScreen
        return vlanID


    def setVlanID(self, vlanID):
        self.vlanCheckButton.set_active(True)
        self.vlanEntry.set_text(str(vlanID))
