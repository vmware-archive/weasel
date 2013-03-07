
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

# display the bootloader window
import devices
import datastore
import storage_widgets
import exception
import partition
import fsset
import os.path

from log import log
from common_windows import MessageWindow
from common_windows import CommonWindow

from storage_widgets import getSelectionFromView
from storage_widgets import STORAGEVIEW_DISK_ENTRY

from signalconnect import connectSignalHandlerByDict
from datastore import checkForClearedVolume

from installlocation_gui import VMFS_OVERHEAD

import userchoices

_deviceName = ''
_vmfsVolume = ''

_createDSHandlersInitialized = False
_selectDSHandlersInitialized = False

class DataStoreWindow:
    SCREEN_NAME = 'datastore'
    
    def __init__(self, controlState, xml):
        controlState.displayHeaderBar = True
        controlState.windowIcon = 'datastore.png'
        controlState.windowTitle = "Datastore"
        controlState.windowText = "Specify a datastore for ESX"

        self.xml = xml

        self.diskSet = devices.DiskSet()
        self.datastoreSet = datastore.DatastoreSet()

        self.datastoreExistTable = xml.get_widget("DatastoreexistingTable")
        self.datastoreCreateTable = xml.get_widget("DatastorecreateTable")

        connectSignalHandlerByDict(self, DataStoreWindow, self.xml,
          { ('DatastoredeviceButton', 'clicked'): 'createNewDatastore',
            ('DatastorepartitionButton', 'clicked'): 'selectDatastore',
            ('DatastorecreateRadioButton', 'toggled'): 'toggleDatastoreChoice',
            ('DatastoreCheckButton', 'toggled'): 'toggleSameDevice',
          })

        self.defaultDeviceName = userchoices.getEsxPhysicalDevice()

        # set up the aux. helper windows
        self.createDataStoreWindow = \
            CreateDataStoreWindow(self.xml, self.diskSet, self)
        self.selectDataStoreWindow = \
            SelectDataStoreWindow(self.xml, self.datastoreSet, self)

        # find the existing vmdk size that we're going to remove
        vmdkPath = userchoices.getExistingVmdkLocation().get('vmdkLocation')
        self.vmdkSize = devices.runtimeActionFindExistingVmdkSize(vmdkPath)

        self.preserveVmfs = bool(userchoices.getPartitionMountRequests())

        if userchoices.getResetEsxLocation():
            self.setup()
            userchoices.setResetEsxLocation(False)

    def setup(self):
        self.xml.get_widget('DatastorecreateRadioButton').set_active(True)

        # If /boot is on an unsupported disk (IDE), we won't be able put a
        # vmfs datastore on it.
        checkButton = self.xml.get_widget('DatastoreCheckButton')
        dsPart = self.xml.get_widget("DatastorepartitionEntry")

        supportedDisk = self.diskSet[self.defaultDeviceName].supportsVmfs
        checkButton.set_active(supportedDisk)
        checkButton.set_sensitive(supportedDisk)

        if len(self.diskSet.keys()) == 1:
            checkButton.set_sensitive(False)

        skipList = [self.defaultDeviceName]

        radioButton = self.xml.get_widget('DatastoreexistingRadioButton')

        # don't skip the datastore with the vmfs partition if we're
        # preserving it
        if self.preserveVmfs:
            radioButton.set_active(True)
            checkButton.set_active(False)
            checkButton.set_sensitive(False)
            skipList = []

            drive = userchoices.getEsxPhysicalDevice()
            datastores = self.datastoreSet.getEntriesByDriveName(drive)

            assert len(datastores) > 0

            # remove the size of the vmdk so that it shows up correctly
            # in the datastore pop-up window
            log.debug("Block size = %d" % (datastores[0].blockSize))
            datastores[0].blocksUsed -= self.vmdkSize

            dsPart.set_text(datastores[0].name)

            global _vmfsVolume
            _vmfsVolume = datastores[0].name
        else:
            checkButton.set_sensitive(True)

        vols = buildDatastoreSet(self.datastoreSet, skipList)

        if vols:
            radioButton.set_sensitive(True)
        else:
            radioButton.set_sensitive(False)

    def _setDatastoreDeviceText(self, device):
        """Set the vendor / model name for the Device entry widget."""
        devModel = "%s %s" % (device.vendor, device.model)
        self.xml.get_widget("DatastoredeviceEntry").set_text(devModel)

    def _toggleDatastoreDevice(self, active):
        global _deviceName
        for name in ["Label", "Entry", "Button"]:
            deviceWidget = self.xml.get_widget("Datastoredevice%s" % (name))
            deviceWidget.set_sensitive(active)

        # Set the widget to the default device if it's selected, otherwise
        # return it to whatever the user set it to
        if active:
            try:
                _deviceName = \
                    getSelectionFromView(self.createDataStoreWindow.view,
                                         column=STORAGEVIEW_DISK_ENTRY)
                self._setDatastoreDeviceText(self.diskSet[_deviceName])
            except KeyError:
                pass
        else:
            self.xml.get_widget("DatastoredeviceEntry").set_text('')
            _deviceName = ''


    def toggleSameDevice(self, widget, *args):
        """Toggle the Datastoredevice[Label|Entry|Button] widgets on/off"""
        self._toggleDatastoreDevice(not widget.get_active())

    def toggleDatastoreChoice(self, widget, *args):
        self.datastoreExistTable.set_sensitive(not widget.get_active())
        self.datastoreCreateTable.set_sensitive(widget.get_active())

    def createNewDatastore(self, *args):
        self.createDataStoreWindow.show()

    def selectDatastore(self, *args):
        self.selectDataStoreWindow.show()

    def updateCreateDatastore(self, deviceName):
        global _deviceName
        log.debug("Update create datastore")
        self._setDatastoreDeviceText(self.diskSet[deviceName])
        _deviceName = deviceName

    def getNext(self):
        global _deviceName, _vmfsVolume

        if self.xml.get_widget('DatastorecreateRadioButton').get_active():
            if self.xml.get_widget('DatastoreCheckButton').get_active():
                deviceName = self.defaultDeviceName
            else:
                deviceName = _deviceName

            if not deviceName:
                MessageWindow(None, 'Invalid Datastore Device',
                    'Specify a device for creating the datastore.')
                raise exception.StayOnScreen

            # Set the volume name for the new vmfs partition
            volumeName = self.xml.get_widget("DatastorenameEntry").get_text()
            try:
                fsset.vmfs3FileSystem.sanityCheckVolumeLabel(volumeName)
            except ValueError, msg:
                MessageWindow(None, "Datastore Name Invalid", msg[0])
                raise exception.StayOnScreen

            # if we're using the same disk for the datastore that we're
            # using for installing esx, only clear one disk, otherwise
            # clear both

            if deviceName == self.defaultDeviceName or self.preserveVmfs:
                clearDrives = [deviceName]
            else:
                clearDrives = [deviceName, self.defaultDeviceName]

            volumePath = os.path.join('/vmfs/volumes', volumeName)

            if (os.path.exists(volumePath) or os.path.islink(volumePath)) \
               and not checkForClearedVolume(clearDrives, self.datastoreSet,
                                             volumeName):
                MessageWindow(None, "Datastore Name Already Used",
                    "The specified name is already used by another datastore. "
                    "Specify a new name that is unique.")
                raise exception.StayOnScreen

            # if we're preserving the vmfs partition on a different drive
            # then we don't need the full set of partitions.
            if not self.preserveVmfs:
                partition.addDefaultPartitionRequests(
                    self.diskSet[self.defaultDeviceName], False)

            physicalRequests = [
                (None, 100, 0, True, fsset.vmfs3FileSystem(volumeName)),
            ]

            dev = self.diskSet[deviceName]
            userchoices.addPhysicalPartitionRequests(dev.name,
                partition.createPartitionRequestSet(dev, physicalRequests))
            
            userchoices.setClearPartitions(drives=clearDrives)

            userchoices.setEsxDatastoreDevice(dev.name)
            userchoices.setVmdkDatastore(volumeName)
        else:
            if not _vmfsVolume:
                MessageWindow(None, "Invalid Datastore",
                    "No datastore has been selected. "
                    "Select a datatore for ESX to use.")
                raise exception.StayOnScreen 

            if not self.preserveVmfs:
                partition.addDefaultPartitionRequests(
                    self.diskSet[self.defaultDeviceName], False)

                userchoices.setClearPartitions(drives=[self.defaultDeviceName])
            
            userchoices.setEsxDatastoreDevice(None)
            userchoices.setVmdkDatastore(_vmfsVolume)

        # find the size of the virtual partitions and then remove the
        # size of any existing COS since it can be removed to free up space
        size = partition.getRequestsSize(partition.getDefaultVirtualRequests())
        size += VMFS_OVERHEAD

        if self.vmdkSize > 0:
            size -= self.vmdkSize

        if size > devices.runtimeActionFindMaxVmdkSize():
            MessageWindow(None, "No Free Space",
                storage_widgets.COSVMDK_TOTALLY_FULL)
            raise exception.StayOnScreen

        #print "Max vmdk = %d" % devices.runtimeActionFindMaxVmdkSize()


class CreateDataStoreWindow(CommonWindow):
    def __init__(self, xml, diskSet, parent):
        CommonWindow.__init__(self)

        self.dialog = xml.get_widget("createdatastore")
        self.diskSet = diskSet
        self.xml = xml
        self.parent = parent

        global _createDSHandlersInitialized
        if not _createDSHandlersInitialized:
            self.xml.signal_autoconnect({
                'on_createdatastore_ok_clicked' : self.okClicked,
                'on_createdatastore_cancel_clicked' : self.cancelClicked,
            })
            _createDSHandlersInitialized = True

        self.view = xml.get_widget("CreatedatastoreTreeView")
        self.scrolled = xml.get_widget("CreatedatastoreScrolledWindow")
        storage_widgets.setupStorageView(self.view)

        prunedDiskSet = buildDiskSet(self.diskSet,
                                     [self.parent.defaultDeviceName])

        storage_widgets.populateStorageModel(self.view, self.scrolled,
                                             prunedDiskSet,
                                             esxAndCos=False)

        self.addFrameToWindow()

    def okClicked(self, *args):
        createDatastore = False
        name = getSelectionFromView(self.view, column=STORAGEVIEW_DISK_ENTRY)
        assert not name or name in self.diskSet.keys()
        if not name:
            MessageWindow(None,
                "Storage Selection Error",
                "Select a place to create the new datastore.")
        else:
            # check and prompt if there is already a vmfs partition on the
            # device
            createDatastore = \
                storage_widgets.promptDeviceHasExistingData(name, False)

            # update the 'Device:' textentry with the appropriate drive name
            if createDatastore == storage_widgets.EXISTING_DATA_CLEAR_DRIVE:
                self.parent.updateCreateDatastore(name)
                self.hide()

    def cancelClicked(self, *args):
        self.hide()

    def show(self):
        self.dialog.show_all()

    def hide(self):
        self.dialog.hide_all()


def buildDiskSet(disks, skipList):
    '''Builds a set of disks which do not contain anything from skipList'''
    diskSet = {}

    for dev in disks.keys():
        if dev in skipList:
            continue
        diskSet[dev] = disks[dev]

    return diskSet

def buildDatastoreSet(datastoreSet, skipList):
    '''Builds a set of datastores'''
    datastoreCopy = datastore.DatastoreSet(scan=False)
    for ds in datastoreSet:
        if ds.driveName not in skipList:
            datastoreCopy.append(ds)

    return datastoreCopy

class SelectDataStoreWindow(CommonWindow):
    def __init__(self, xml, datastoreSet, parent):
        CommonWindow.__init__(self)

        self.dialog = xml.get_widget("selectdatastore")
        self.datastoreSet = datastoreSet

        self.xml = xml
        self.parent = parent

        global _selectDSHandlersInitialized
        if not _selectDSHandlersInitialized:
            self.xml.signal_autoconnect({
                'on_selectdatastore_ok_clicked' : self.okClicked,
                'on_selectdatastore_cancel_clicked' : self.cancelClicked,
            })
            _selectDSHandlersInitialized = True

        self.view = xml.get_widget("SelectdatastoreTreeView")
        self.scrolled = xml.get_widget("SelectdatastoreScrolledWindow")

        deviceName = userchoices.getEsxPhysicalDevice()
        skipList = [deviceName]

        if userchoices.getPartitionMountRequests():
            skipList = []

        prunedDatastore = buildDatastoreSet(self.datastoreSet, skipList)

        storage_widgets.setupVmfsVolumesView(self.view)
        storage_widgets.populateVmfsVolumesModel(self.view, self.scrolled,
                                                 prunedDatastore)

        self.addFrameToWindow()

    def okClicked(self, *args):
        vmfsName = getSelectionFromView(self.view)
        if not vmfsName or vmfsName == "Datastores":
            MessageWindow(None,
                "Storage Selection Error",
                "A valid existing datastore must be selected.")
        else:
            setPartEntry = False

            # TODO: at some point it might be nice to allow the user to change
            #       the name of the vmdk file
            entry = self.datastoreSet.getEntryByName(vmfsName)
            assert entry
            if entry:
                vmdkPath = os.path.normpath(
                    os.path.join(entry.consolePath,
                        fsset.vmfs3FileSystem.systemUniqueName('esxconsole'),
                        devices.DEFAULT_COS_IMAGE))

                # This is extremely unlikely to ever be executed given
                # that the UUID should be unique, however we still need
                # to nuke it if it does exist.
                if os.path.exists(vmdkPath):
                    rc = MessageWindow(None, "Existing Service Console",
                            "There is an existing service console at the "
                            "specified location. "
                            "Overwrite it?", type="yesno")
                    if rc.affirmativeResponse:
                        setPartEntry = True
                else:
                    setPartEntry = True

                if setPartEntry:
                    dsPart = \
                        self.xml.get_widget("DatastorepartitionEntry")
                    dsPart.set_text(vmfsName)
                    global _vmfsVolume
                    _vmfsVolume = vmfsName
                    self.hide()
            else:
                # should never be able to get here
                MessageWindow(None, "Error",
                    "The selected datastore does not exist. "
                    "Choose a different datastore.")

    def cancelClicked(self, *args):
        self.hide()

    def show(self):
        self.dialog.show_all()

    def hide(self):
        self.dialog.hide_all()

