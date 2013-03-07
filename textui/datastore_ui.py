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

'''DataStore
'''

from textrunner import TextRunner, SubstepTransitionMenu as TransMenu
import dispatch
from log import log
import devices
import datastore
import partition
import fsset
import userchoices
import storage_utils
import os.path

from datastore import checkForClearedVolume

title = "Datastore"

dataStoreText = """\
Specify a datastore for ESX to use.

A datastore is a vmfs partition that ESX uses to store virtual machines.
(Additional datastores can be created after ESX is installed by using
vSphere Client.)

 1) Create new datastore
 2) Use existing datastore 
 <) Back 
 ?) Help

"""

createNewDataStoreText = """\
Create new datastore:
Create on same device as ESX?
"""

askConfirmVolumeNameText = """\
Volume name: %(volname)s
"""

enterDataStoreNameText = """\
Create new datastore:
Enter name of new datastore:

 ['<': back, '?': help]
"""

chooseExistingDataStoreText = """\
Choose an existing datastore.
    Capacity    Free Space  Volume Name"""

helpText = """\
Select the number of the device on which to create the datastore.
"""

errInvalidSelectionText = """\
The %(kind)s selection is invalid.
%(reason)s
Select a %(kind)s from the list provided.
"""

errNoExistingDataStoreText = """\
There are no existing datastores.  Please create one instead.

 <) Back

"""

warnInUseText = """
DataStore Name Already Used
The specified name is already used by another datastore.
Specify a new name that is unique.

 1) OK

"""

warnInvalidDataStoreText = """\
Invalid Name
The specified datastore name is invalid.  Specify a different name.

 1) OK

"""

warnTooSmallText = """\
Size Error
The size of the selected disk is not large enough to fit the Console
Virtual Disk image.  Select another disk.

 1) OK

"""

# NOTE: These warnErase messages are directly copied from esxlocation_ui.py.
# It is inspired by gui/storage_widgets.py
# It may make sense to combine the common functionality in this module and in
# EsxLocationWindow, and create a new storage_ui module out of it.
# TODO: merge storage_widget-like functionality into a common module.
# Possibly redefine storage_utils.py.

warnEraseVmfsPartitionText = """\
WARNING:  Existing Datastore
The selected storage device contains a datastore which will be
erased before installing ESX.
"""

warnEraseDeviceContentText = """\
WARNING:  Delete Device Contents
The selected storage device will be erased before installing ESX.
"""

helpDataStoreText = """\
A datastore is a vmfs partition that ESX uses to store virtual machines.
The datastore for the ESX Service Console may be on the same storage
device as, or a different one from ESX itself.

Additional datastores can be created after ESX is installed by using
vSphere Client.
"""

helpCreateDataStoreText = """\
Each datastore volume name should be unique, can be up to 64 bytes long,
and cannot contain slash ('/').
"""

helpChooseDataStoreDeviceText = """\
Each storage device is listed with its capacity.  Choose one for creation
of a datastore for use by ESX.  The contents of the device will be
overwritten.
"""

helpChooseDataStoreText = """\
Each datastore is identified by a unique volume name.  Choose one for
use by ESX.
"""

diskHeaderText = """\
 # | Device Name                                       |Lun|Trgt|   Size"""

SCROLL_LIMIT = 20


class DataStoreWindow(TextRunner):
    """COS datastore selection.
    A datastore is a vmfs partition that ESX uses to store virtual
    machines.  The datastore for the COS may be on the same or different
    storage device from ESX.
    """

    def __init__(self):
        super(DataStoreWindow, self).__init__()
        self.substep = self.start

        self.datastoreSet = datastore.DatastoreSet()
        self.esxDeviceName = None       # re-assign in 'start'
        self.clearDrives = None
        self.volumeName = None
        self.deviceName = None

        self.choseCreateNewDatastore = None     # True/False
        self.choseCreateNewDatastoreOnEsxDevice = None # True/False

    def start(self):
        "Initial step."

        # ESX device is previous user choice or location of /boot.
        self.esxDeviceName = userchoices.getEsxPhysicalDevice()
        devs = userchoices.getPhysicalPartitionRequestsDevices()
        for dev in devs:
            request = userchoices.getPhysicalPartitionRequests(dev)
            if request.findRequestByMountPoint('/boot'):
                self.esxDeviceName = dev
        assert self.esxDeviceName

        self.clearDrives = [self.esxDeviceName]

        createNewDataStoreFunc = self.createNewDataStore
        if not devices.DiskSet()[self.esxDeviceName].supportsVmfs:
            createNewDataStoreFunc = self.createNewDataStoreDiffDev
        
        ui = {
            'title': title,
            'body': dataStoreText,
            'menu': {
                '1': createNewDataStoreFunc,
                '2': self.useExistingDataStore,
                '<': self.stepBack,
                '?': self.help,
            }
        }
        self.setSubstepEnv(ui)

    def createNewDataStore(self):
        "Create new datastore."
        ui = {
            'title': title,
            'body': createNewDataStoreText + TransMenu.YesNoBackHelp,
            'menu': {
                '1': self.createNewDataStoreSameDev,
                '2': self.createNewDataStoreDiffDev,
                '<': self.stepBack,
                '?': self.help,
            }
        }
        self.setSubstepEnv(ui)

    def useExistingDataStore(self):
        "Use existing datastore."
        # get list of existing datastores; choose from list
        chooseDS = ChooseDataStore(self)

        if not chooseDS.vmfsList:
            body = errNoExistingDataStoreText
            self.errorPushPop(title + " (Choose Datastore)", body)
            return

        result = chooseDS.run()

        assert result in (dispatch.DISPATCH_BACK, dispatch.DISPATCH_NEXT), \
            "unexpected step result from ChooseDataStore"
        if result != dispatch.DISPATCH_NEXT:
            # User wants to re-think this
            self.setSubstepEnv({'next': self.stepBack})
            return

        # set volumeName and deviceName
        self.volumeName = chooseDS.getSelectedDataStore()
        self.deviceName = chooseDS.getDeviceName()

        self.choseCreateNewDatastore = False
        self.choseCreateNewDatastoreOnEsxDevice = False
        log.debug("datastore_ui.useExistingDataStore")

        self.setSubstepEnv({'next': self.commit})

    def createNewDataStoreSameDev(self):
        "Set datastore to be on same device as ESX."

        self.deviceName = self.esxDeviceName

        # set datastore characteristics
        createDS = CreateDataStore(self.deviceName, self)
        result = createDS.run()
        assert result in ( dispatch.DISPATCH_BACK, dispatch.DISPATCH_NEXT), \
            "bad step result from CreateDataStore in createNewDataStoreSameDev" 
        if result != dispatch.DISPATCH_NEXT:
            # User wants to re-think this
            self.setSubstepEnv({'next': self.stepBack})
            return
        self.volumeName = createDS.getSelectedDataStore()

        # By now, both self.deviceName and self.volumeName have been set.
        self.choseCreateNewDatastore = True
        self.choseCreateNewDatastoreOnEsxDevice = True
        log.debug("datastore_ui.createNewDataStoreSameDev")

        self.setSubstepEnv({'next': self.commit})


    def createNewDataStoreDiffDev(self):
        "Set datastore to be on different device from ESX."

        # Generate a device selection via ChooseDataStoreDevice.
        # It will prune out ESX device, present list, and
        # make selction.
        chooseDSDev = ChooseDataStoreDevice(self)
        result = chooseDSDev.run()
        assert result in ( dispatch.DISPATCH_BACK, dispatch.DISPATCH_NEXT), \
            "bad step result from ChooseDataStoreDevice in " + \
            "createNewDataStoreDiffDev"
        if result != dispatch.DISPATCH_NEXT:
            # User wants to re-think this
            self.setSubstepEnv({'next': self.stepBack})
            return
        self.deviceName = chooseDSDev.getSelectedDeviceName()

        # set datastore characteristics
        createDS = CreateDataStore(self.deviceName, self)
        result = createDS.run()
        assert result in ( dispatch.DISPATCH_BACK, dispatch.DISPATCH_NEXT), \
            "bad step result from CreateDataStore in createNewDataStoreDiffDev"
        if result != dispatch.DISPATCH_NEXT:
            # User wants to re-think this
            self.setSubstepEnv({'next': self.stepBack})
            return
        self.volumeName = createDS.getSelectedDataStore()

        # By now, both self.deviceName and self.volumeName have been set.
        self.choseCreateNewDatastore = True
        self.choseCreateNewDatastoreOnEsxDevice = False
        log.debug("datastore_ui.createNewDataStoreDiffDev")

        self.setSubstepEnv({'next': self.commit})

    def warnInUse(self):
        "Warn that datastore is in use."
        ui = {
            'title': title,
            'body': warnInUseText,
            'menu': { '1': self.start },
        }
        self.setSubstepEnv(ui)

    def warnTooSmall(self):
        "Warn that disk is too small."
        ui = {
            'title': title,
            'body': warnTooSmallText,
            'menu': { '1': self.start },
        }
        self.setSubstepEnv(ui)

    def commit(self):
        """Commit updates.  By the time we get here, we assume:
        * volume name has been sanity checked
        * requested size has been checked
        """

        assert self.deviceName, 'datastore device name not set'
        assert self.volumeName, 'datastore volume name not set'
        log.debug("DataStoreWindow.commit device %s volume %s" %
                (self.deviceName, self.volumeName))

        # Check if drives to clear are in use; if so stop this madness.
        diskSet = devices.DiskSet()
        if self.deviceName == self.esxDeviceName:
            clearDrives = [self.deviceName]
        else:
            clearDrives = [self.deviceName, self.esxDeviceName]
            # presumably self.choseCreateNewDatastoreOnEsxDevice == False

        log.debug("Cleared drives = %s" % (', '.join(clearDrives)))
        volumePath = os.path.join('/vmfs/volumes', self.volumeName)

        if (os.path.exists(volumePath) or os.path.islink(volumePath)) \
           and not checkForClearedVolume(clearDrives, self.datastoreSet,
                                         self.volumeName):
            log.debug("Volume name in use")
            self.setSubstepEnv({'next': self.warnInUse})
            return

        # build partition requests, add to userchoices
        partition.addDefaultPartitionRequests(diskSet[self.esxDeviceName],
                                              False)

        if self.choseCreateNewDatastore:
            physicalRequests = [
                (None, 100, 0, True, fsset.vmfs3FileSystem(self.volumeName)),
            ]
            dev = diskSet[self.deviceName]
            userchoices.addPhysicalPartitionRequests(self.deviceName,
                partition.createPartitionRequestSet(dev, physicalRequests))

            userchoices.setClearPartitions(drives=clearDrives)

            userchoices.setEsxDatastoreDevice(dev.name)
            userchoices.setVmdkDatastore(self.volumeName)
        else:   # use existing datastore
            userchoices.setClearPartitions(drives=[self.esxDeviceName])

            userchoices.clearVirtualDevices()

            userchoices.setEsxDatastoreDevice(None)
            userchoices.setVmdkDatastore(self.volumeName)

        # size check
        size = partition.getRequestsSize(partition.getDefaultVirtualRequests())
        if size > devices.runtimeActionFindMaxVmdkSize():
            self.setSubstepEnv({'next': self.warnTooSmall})
            return
        self.setSubstepEnv({'next': self.stepForward})
        # commit substep is the last before exiting the datastore step.

    def help(self):
        "Emit help text."
        self.helpPushPop(title + ' (Help)', helpDataStoreText + TransMenu.Back)

class CreateDataStore(TextRunner):
    """Given a device, create a datastore on it.
    If on same device as ESX, exclude it (/boot and vmkcore)
    from size computation.
    """

    def __init__(self, deviceName, parent):
        super(CreateDataStore, self).__init__()
        self.substep = self.start = self.askConfirmVolumeName
        self.deviceName = deviceName
        self.parent = parent
        self.datastoreSet = self.parent.datastoreSet

        # TODO: size computation; check if device too small for COS VMDK.

        self.volumeName = self.getDefaultVolumeName()

    def getDefaultVolumeName(self):
        """Generate a default volume name.
        Current implementation (in GUI as well) is to simply use "datastore1".
        """
        label = "datastore1"
        return label

    def askConfirmVolumeName(self):
        "Ask user if current volume name is acceptable."
        ui = {
            'title': title,
            'body': askConfirmVolumeNameText % {'volname': self.volumeName} + \
                TransMenu.KeepChangeBackHelpExit,
            'menu': {
                '1': self.sanityCheckDataStoreName,
                '2': self.enterDataStoreName,
                '<': self.stepBack,
                '?': self.help,
            }
        }
        self.setSubstepEnv(ui)

    def enterDataStoreName(self):
        "Ask user for name of datastore."
        ui = {
            'title': title,
            'body': enterDataStoreNameText,
            'menu': {
                '<': self.stepBack,
                '?': self.help,
                '*': self.checkDataStoreName,
            }
        }
        self.setSubstepEnv(ui)

    def checkDataStoreName(self):
        "Get datastore name from input and validate."
        self.volumeName = self.userinput
        self.volumeName = self.volumeName.strip()
        self.setSubstepEnv({'next': self.sanityCheckDataStoreName})

    def sanityCheckDataStoreName(self):
        "sanity check and set volume name for new vmfs partition"
        # may get here either from user input or from askConfirm.
        try:
            fsset.vmfs3FileSystem.sanityCheckVolumeLabel(self.volumeName)
        except ValueError:
            self.setSubstepEnv({'next': self.warnInvalidDataStore})
            return

        self.setSubstepEnv({'next': self.stepForward})
        # We're done; return to caller in DataStoreWindow.

    def getSelectedDataStore(self):
        "Get volume name from DataStoreWindow."
        return self.volumeName

    def warnInvalidDataStore(self):
        "Warn of invalid datastore."
        ui = {
            'title': title,
            'body': warnInvalidDataStoreText,
            'menu': { '1': self.enterDataStoreName },
        }
        self.setSubstepEnv(ui)

    def help(self):
        "Emit help text."
        # TODO: uses generic helpText now; need to specialize.
        self.helpPushPop(title + ' (Help)',
                         helpCreateDataStoreText + TransMenu.Back)


class ChooseDataStoreDevice(TextRunner):
    """Choose a device on which to create a datastore.
    In general, this is a different device from the one used by ESX;
    so typically this device is skipped.  (Of course, storage device
    and datastore are not the same thing.)
    Get result via getSelectedDevice() or getSelectedDeviceName().
    """

    def __init__(self, parent, skipEsxDevice=True):
        """Initialize using parent's environment.
        Generates self.storDevList - list of allowable storage devices.
        """
        super(ChooseDataStoreDevice, self).__init__()
        self.substep = self.start = self.showDevices
        self.scrollable = None

        self.parent = parent
        self.selectedDevice = None

        if skipEsxDevice:
            allowedDiskSet = pruneDiskSet(devices.DiskSet(),
                [self.parent.esxDeviceName])
        else:
            allowedDiskSet = devices.DiskSet()
        self.storDevList = storage_utils.getStorageList(allowedDiskSet,
                                                        esxAndCos=not skipEsxDevice)

    def getSelectedDevice(self):
        """Get the selected device from outside this class, when all the
        local fun and games are done.
        """
        assert self.selectedDevice, "selectedDevice not yet set"
        return self.selectedDevice

    def getSelectedDeviceName(self):
        "Just get the name."
        return self.getSelectedDevice()[storage_utils.STORLIST_DISK_ENTRY]

    def showDevices(self):
        "Create list of drives, and display."
        # TODO:  Very similar to ESXLocationWindow.start.  Factorable?
        # TODO: prune for disks which are too small for COS VMDK.
        # TODO: handle iSCSI

        storDevListText = []

        storDevEnumStr = "%2d) %-51s %3s %4s %11s"
        storDevEnumPath = "        %s"
        storDevListText.append(diskHeaderText)
        for num, storLine in enumerate(self.storDevList):
            deviceName, lunid, disksize, entry, pathString, targetid = storLine
            storDevListText.append(storDevEnumStr %
                (num+1, deviceName, lunid, targetid, disksize) )
            for path in pathString:
                tempEnumPath = storDevEnumPath % path
                while tempEnumPath:
                    storDevListText.append(tempEnumPath[:80])
                    tempEnumPath = tempEnumPath[80:]

        self.setScrollEnv(storDevListText, SCROLL_LIMIT)
        self.setSubstepEnv( {'next': self.scrollDisplay} )

    def scrollDisplay(self):
        "display store dev list choices"
        self.buildScrollDisplay(self.scrollable, title,
            self.chooseDevice, "<number>: storage device", allowStepBack=True)

    def chooseDevice(self):
        "Apply user choice to select an existing datastore."
        try:
            selected = self.getScrollChoice(maxValue=len(self.storDevList))
            device = self.storDevList[selected]
        except (ValueError, IndexError), ex:
            log.error(str(ex))
            device = None

        if not device:
            msg = "%s\n" % str(ex)
            self.errorPushPop(title +' (Update)', msg + TransMenu.Back)
            return

        self.selectedDevice = device
        driveName = self.selectedDevice[storage_utils.STORLIST_DISK_ENTRY]
        warnText = storage_utils.getDeviceHasExistingDataText(driveName)

        self.pushSubstep()
        ui = {
            'title': title,
            'body': warnText + TransMenu.OkBack,
            'menu': {
                '1': self.stepForward, # return to caller in DataStoreWindow
                '<': self.popSubstep,
            }
        }
        self.setSubstepEnv(ui)

    def help(self):
        "Emit help text."
        # TODO: uses generic helpText now; need to specialize.
        self.helpPushPop(title + ' (Help)',
                         helpChooseDataStoreDeviceText + TransMenu.Back)


class ChooseDataStore(TextRunner):
    """Select from existing datastores.
    Datastore must be on different device from ESX since that
    device is going to be wiped out.
    """

    def __init__(self, parent):
        super(ChooseDataStore, self).__init__()
        self.parent = parent
        self.substep = self.start = self.showDataStores
        self.datastoreSet = datastore.DatastoreSet()
        self.dataStoreName = None       # set in chooseExistingDataStore()
        self.deviceName = None          # set in chooseExistingDataStore()

        # eliminate volumes that reside on ESX device
        # TODO: prune for disks which are too small for COS VMDK.
        deviceName = self.parent.esxDeviceName
        prunedDsSet = pruneDatastoreSet(self.datastoreSet, [deviceName])
        self.vmfsList = storage_utils.getVmfsVolumes(prunedDsSet)

    def showDataStores(self):
        """Show choices of existing datastores.
        Exclude volumes in ESX device.
        """

        # build datastore list
        vmfsListText = []
        for num, vmfsLine in enumerate(self.vmfsList):
            name, size, freeSpace = vmfsLine
            # nn) Capacity    Free Space  Volume Name
            vmfsListText.append("%2d) %10s  %10s  %-48s" %
                (num+1, size, freeSpace, name))

        self.setScrollEnv(vmfsListText, SCROLL_LIMIT)
        self.scrollDisplay = self.scrollDataStoreDisplay
        self.setSubstepEnv( {'next': self.scrollDisplay} )

    def scrollDataStoreDisplay(self):
        self.buildScrollDisplay(self.scrollable, title,
                self.chooseExistingDataStore, "<number>: datastore",
                allowStepBack=True, prolog=chooseExistingDataStoreText)

    def chooseExistingDataStore(self):
        "Apply user choice to select an existing datastore."

        # check for numeric input
        try:
            selected = self.getScrollChoice()
            vmfs = self.vmfsList[selected]
        except (ValueError, IndexError), msg:
            body = errInvalidSelectionText % {
                'kind': 'datastore', 'reason': msg} + TransMenu.Back
            self.errorPushPop(title + " (Choose Datastore)", body)
            return

        self.dataStoreName = vmfs[0]    # name field
        ds = self.datastoreSet.getEntryByName(self.dataStoreName)
        self.deviceName = ds.driveName

        self.setSubstepEnv({'next': self.stepForward})
        # We're done; return to caller in DataStoreWindow.

    def getSelectedDataStore(self):
        "Get datastore (volume) name."
        return self.dataStoreName

    def getDeviceName(self):
        "Get drive (device) name."
        return self.deviceName

    def help(self):
        "Emit help text."
        self.helpPushPop(title + ' (Help)',
                         helpChooseDataStoreText + TransMenu.Back)


# ----------------------------------------------------------------
# Functions below extracted from gui/datastore_gui.py
# TODO:  move these functions to devices.py or datastore.py
# These may need to folded into existing classes.
# (See reviewboard #15941.)
# Renamings:
#  buildDiskSet() -> pruneDiskSet()
#  buildDatastoreSet() -> pruneDatastoreSet()

def pruneDiskSet(disks, skipList):
    '''Builds a set of disks which do not contain anything from skipList'''
    diskSet = {}

    for dev in disks.keys():
        if dev in skipList:
            continue
        diskSet[dev] = disks[dev]

    return diskSet

def pruneDatastoreSet(datastoreSet, skipList):
    '''Builds a set of datastores'''
    datastoreCopy = datastore.DatastoreSet(scan=False)
    for ds in datastoreSet:
        if ds.driveName not in skipList:
            datastoreCopy.append(ds)

    return datastoreCopy

