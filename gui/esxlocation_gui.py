
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

# display the partitioning window
from common_windows import MessageWindow

import devices
import exception
import partition
import storage_widgets
import iscsi_detour
import userchoices

from log import log

from storage_widgets import STORAGEVIEW_DISK_ENTRY, SUPPORTED_DISK_ENTRY
from signalconnect import connectSignalHandlerByDict

from installlocation_gui import GenericLocationWindow

_handlersInitialized = False

class EsxLocationWindow(GenericLocationWindow):
    SCREEN_NAME = 'esxlocation'

    def __init__(self, controlState, xml):
        controlState.displayHeaderBar = True 
        controlState.windowTitle = "ESX Storage Device"
        controlState.windowText = "Select a location to install ESX"
        controlState.windowIcon = "drive.png"

        self.xml = xml

        self.controlState = controlState

        self.view = xml.get_widget("EsxlocationView")
        self.scrolled = xml.get_widget("EsxlocationScrolled")

        storage_widgets.setupStorageView(self.view)

        # only repopulate the esxlocation if we need to
        if userchoices.getResetEsxLocation():
            model = \
                storage_widgets.populateStorageModel(self.view, self.scrolled,
                                                     devices.DiskSet(),
                                                     vmfsSupport=False)
            storage_widgets.findFirstSelectableRow(model,
                                                   self.view,
                                                   SUPPORTED_DISK_ENTRY)

        connectSignalHandlerByDict(self, EsxLocationWindow, self.xml,
          { ('EsxlocationDetailsButton', 'clicked'): 'showDetails',
          })


