
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
from common_windows import CommonWindow
import gtk
import devices
import exception
import partition
import storage_widgets
import datastore
import iscsi_detour
import userchoices
import esxconf
import os.path
from storage_widgets import STORAGEVIEW_DISK_ENTRY, SUPPORTED_DISK_ENTRY
from storage_widgets import StorageDetailsWindow
from storage_widgets import PreserveCosVmdkWindow
from signalconnect import connectSignalHandlerByDict

from log import log

VMFS_OVERHEAD = 20


_handlersInitialized = False
_resetInstallLocation = True

class GenericLocationWindow:
    def __init__(self, controlState, xml):
        pass

    def getNext(self):
        haveMountPoint = bool(userchoices.getPartitionMountRequests())

        userchoices.clearPhysicalPartitionRequests()
        userchoices.clearPartitionMountRequests()
        userchoices.clearExistingVmdkLocation()

        (model, diskIter) = self.view.get_selection().get_selected()
        if diskIter and model.get(diskIter, STORAGEVIEW_DISK_ENTRY)[0]:
            drive = model.get(diskIter, STORAGEVIEW_DISK_ENTRY)[0]

            log.debug("Selected drive %s" % (drive))

            diskSet = devices.DiskSet()
            datastoreSet = datastore.DatastoreSet()

            rc = storage_widgets.promptDeviceHasExistingData(drive)

            if rc == storage_widgets.EXISTING_DATA_STAY_ON_SCREEN:
                raise exception.StayOnScreen
            elif rc == storage_widgets.EXISTING_DATA_PRESERVE_VMFS:
                vmdkPath = \
                    esxconf.runtimeActionExtractVmdkPathFromInitrd(drive)
                vmdkSize = \
                    devices.runtimeActionFindExistingVmdkSize(vmdkPath)

                log.debug("VMDK Size = %d Path = %s" % (vmdkSize, vmdkPath))

                if vmdkSize > 0:
                    vmdkCheckBox = True

                    # only turn off the preserveVmdk check button if
                    # we're on the install location screen since the user
                    # can choose to put the vmdk on a different datastore
                    # on the esxlocation screen

                    if self.SCREEN_NAME == 'installlocation':
                        ds = datastoreSet.getEntriesByDriveName(drive)[0]
                        freeSize = ds.getFreeSize() / 1024 / 1024
                        requestSize = partition.getRequestsSize(
                                          partition.getDefaultVirtualRequests())

                        if freeSize + vmdkSize <= requestSize + VMFS_OVERHEAD:
                            MessageWindow(None, "No Free Space",
                                storage_widgets.COSVMDK_TOTALLY_FULL)
                            raise exception.StayOnScreen

                        elif freeSize < requestSize:
                            vmdkCheckBox = False

                    preserveVmdk = PreserveCosVmdkWindow(vmdkCheckBox).run()
                    if preserveVmdk == -1:
                        raise exception.StayOnScreen
                    elif preserveVmdk == 1:
                        pass
                    else:
                        userchoices.setExistingVmdkLocation(vmdkPath)

                # Set up virtual disk and settings
                datastore.preserveDatastoreOnDrive(drive)

                if self.SCREEN_NAME == 'esxlocation':
                    userchoices.setEsxPhysicalDevice(drive)
                    userchoices.setResetEsxLocation(True)

            elif rc == storage_widgets.EXISTING_DATA_CLEAR_DRIVE:
                if self.SCREEN_NAME == 'installlocation':
                    partition.addDefaultPartitionRequests(diskSet[drive])

                else:
                    # clear out the datastore options if the user has changed
                    # their mind about which drive to use -- this will get
                    # changed back to false on the next screen
                    if drive != userchoices.getEsxPhysicalDevice() or \
                       haveMountPoint:
                        userchoices.setResetEsxLocation(True)
                    else:
                        userchoices.setResetEsxLocation(False)

                    userchoices.setEsxPhysicalDevice(drive)
            else:
                raise ValueError, "Got unexpected return code"

        else:
            MessageWindow(self.controlState.gui.getWindow(),
                "Storage Selection Error",
                "You must select a place to install ESX.")
            raise exception.StayOnScreen

    def showDetails(self, *args):
        (model, diskIter) = self.view.get_selection().get_selected()
        if diskIter and model.get(diskIter, STORAGEVIEW_DISK_ENTRY)[0]:
            drive = model.get(diskIter, STORAGEVIEW_DISK_ENTRY)[0]
            StorageDetailsWindow(drive).run()


class InstallLocationWindow(GenericLocationWindow):
    SCREEN_NAME = 'installlocation'
    
    def __init__(self, controlState, xml):
        controlState.displayHeaderBar = True
        controlState.windowTitle = "ESX Storage Device"
        controlState.windowText = "Select a location to install ESX"
        controlState.windowIcon = "drive.png"

        self.controlState = controlState
        self.xml = xml

        self.view = xml.get_widget("InstalllocationView")
        self.scrolled = xml.get_widget("InstalllocationScrolled")

        storage_widgets.setupStorageView(self.view)

        model = storage_widgets.populateStorageModel(
            self.view, self.scrolled, devices.DiskSet())

        storage_widgets.findFirstSelectableRow(model,
            self.view, SUPPORTED_DISK_ENTRY)

        connectSignalHandlerByDict(self, InstallLocationWindow, self.xml,
          { ('InstalllocationDetailsButton', 'clicked'): 'showDetails',
          })


