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

'''Service Console Virtual Disk Image
'''

from textrunner import TextRunner, SubstepTransitionMenu as TransMenu
import textengine

import re

from log import log
import devices
import partition
import fsset
import storage_utils
import userchoices
import util
import packages
import systemsettings


title = "Service Console Virtual Disk Image"

askConfirmPartitionsText = """\
The service console contains the partitions below.  You can edit them and
also create new partitions.
    volume:  %(vmfsVolume)s
    type    size        mountpoint
%(parts)s

Do you want to change the partition layout?
"""

changePartMenuText = """\
Type of partition change:
 1) Create a new partition
 2) Edit an existing partition
 3) Delete an existing partition
 4) Reset (discard modifications)
 <) Back
 ?) Help

"""

choosePartitionEditText = """\
Choose a partition to edit:"""

choosePartitionDeleteText = """\
Choose a partition to delete:"""

chooseFileSysTypeText = """\
Select the file system type:"""

enterFileSysMountPointText = """\
Enter the new mount point.
(For example: /, /home, /tmp, /usr, /var.  Name must start with "/".)

"""

enterFileSysSizeText = """\
Specify the partition size.  (Max: %(maxsize)s)
For example: 9.0 GB, 256 MB

"""

summarizeFileSysText = """\
Summary
Mount point: %(mountPoint)s
File system type: %(fsTypeName)s
Size: %(minSize)d MB
"""

confirmPartitionDeleteText = """\
Are you sure you want to remove this partition?
"""

confirmResetPartitionsText = """\
Resetting will cause any changes you have made to the Service Console
partitions to be lost.

Are you sure you would like to reset the partitions?
"""

mperrBootReservedText = """\
Mount Point Error
ESX reserves the '/boot' mount point for booting the system.
Choose a different mount point for this partition.
"""

mperrReservedText = """\
Mount Point Error
The '%s' directory can not be on a separate partition.
Choose a different mount point for this partition.
"""

mperrExistsText = """\
Mount Point Error
The mount point you have specified for this partition already exists.
Choose a different mount point.
"""

mperrInvalidText = """\
Mount Point Error
You have specified an invalid mount point.
"""

errInvalidPartitionsText = """\
The following error(s) were detected with the current partition layout:
"""

errInvalidSelectionText = """\
You have made an invalid %(kind)s selection.
%(reason)s
Select a %(kind)s from the list provided.
"""

errInvalidInputText = """\
You have entered an invalid %(kind)s input.
%(reason)s
Try again.
"""

errMaxPartitionsText = """\
You cannot add any more partitions to this disk.
"""

parterrNotEnoughRoomText = """\
Partition Error
There is not enough room to add the requested partition.
"""

helpSetupVmdkText = """\
The service console allows you to access and to configure ESX.  It will
be stored on the datastore that was selected in the previous step.

The service console must have partitions for at least swap and root (/).
You can change the partitions (create, edit, or delete them), or reset
to discard and pending modifications.  """

helpPartitionText = """\
When editing or creating a new partition, only the ext3 and swap
filesystem types are available.  An ext3 partition must be given a name
for its mount point.  Size can be expressed in megabytes (MB), gigabytes
(GB), or terabytes (TB).
"""

sizeValues = [ "MB", "GB", "TB" ]

SCROLL_LIMIT = 20

# other variations on gui/setupvmdk_gui.py
def getVmdkFsNames(fsTypeClasses):
    "Get names of vmdkable file systems from fsTypes."

    names = []
    for fs in fsTypeClasses:
        if fsTypeClasses[fs].vmdkable:
            names.append(fs)
    names.sort()
    return names


class SetupVmdkWindow(TextRunner):
    "service console virtual disk image."

    def __init__(self):
        super(SetupVmdkWindow, self).__init__()
        self.substep = self.start

        self.diskSet = devices.DiskSet()
        self.maxVmdkSize = devices.runtimeActionFindMaxVmdkSize()

        self.requests = None

        # Download the package data so we can figure out the minimum partition
        # sizes
        weaselConfig = systemsettings.WeaselConfig()
        packagesXML = packages.getPackagesXML(weaselConfig.packageGroups)
        packageData = packages.PackageData(packagesXML.fullInstallDepot)

        self.fileSizes = packageData.fileDict

        if not userchoices.getVirtualDevices():
            self.reset()
        else:
            self.setupVirtualDevice()

    def start(self):
        "Initial step."

        self.requestsCopy = None        # need a copy for reset operation
        # somehow, create list of partitions.

        self.setSubstepEnv({'next': self.askConfirmPartitions})

    def askConfirmPartitions(self):
        "Show partition layout; ask keep/change."
        partList = storage_utils.getPartitionsList(self.requests)
        partLines = []
        for part in partList:
            mountPoint, fsType, size, request = part
            if mountPoint == '':
                mountPoint = '(no mount point)'
            line = '    %-8s%-12s%-s' % (fsType, size, mountPoint)
            partLines.append(line)
        partitionsText = '\n'.join(partLines)

        ui = {
            'title': title,
            'body': askConfirmPartitionsText % {
                'vmfsVolume': self.requests.device.vmfsVolume,
                'parts': partitionsText,
                } + TransMenu.KeepChangeBackHelpExit,
            'menu': {
                '1': self.commit,
                '2': self.changePartition,
                '<': self.stepBack,
                '?': self.help,
            }
        }
        self.setSubstepEnv(ui)

    def changePartition(self):
        "Change a partition."
        ui = {
            'title': title,
            'body': changePartMenuText,
            'menu': {
                '1': self.createNewPartition,
                '2': self.editExistingPartition,
                '3': self.deleteExistingPartition,
                '4': self.confirmResetPartitions,
                '<': self.start,
                '?': self.help,
            }
        }
        self.setSubstepEnv(ui)

    def createNewPartition(self):
        "Create a new partition."
        self.dialogMode = "new"
        if len(self.requests) >= partition.MAX_PARTITIONS:
            self.errorPushPop(title + " (Error)", errMaxPartitionsText +
                    TransMenu.Back)
            return
        self.dialogPartition()
        # Next substep already set.

    def dialogPartition(self, partreq=None):
        part = PartitionWindow(self, partreq=partreq, mode=self.dialogMode)
        result = part.run()
        assert result in (textengine.DISPATCH_BACK, textengine.DISPATCH_NEXT)
        if result == textengine.DISPATCH_NEXT:
            self.setSubstepEnv({'next': self.stepForward})
        else:
            self.setSubstepEnv({'next': self.start}) # start of setupvmdk
        # First return to caller, who has some post-processing.
        # Then let caller return to TextRunner.

    def editExistingPartition(self):
        "Edit an existing partition; present choices to user"

        # menu below needs work
        partList = storage_utils.getPartitionsList(self.requests)
        self.partList = partList
        partLines = []
        for num, part in enumerate(partList):
            mountPoint, fsType, size, request = part
            if mountPoint == '':
                mountPoint = '(no mount point)'
            line = '%2d) %-8s%-12s%-s' % (num+1, fsType, size, mountPoint)
            partLines.append(line)

        self.setScrollEnv(partLines, SCROLL_LIMIT)
        self.scrollDisplay = self.scrollEditDisplay
        self.setSubstepEnv( {'next': self.scrollDisplay} )

    def scrollEditDisplay(self):
        "Display list of partitions to edit"
        self.buildScrollDisplay(self.scrollable, title,
            self.selectPartitionEdit, "<number>: partition", allowStepBack=True,
            prolog=choosePartitionEditText)

    def selectPartitionEdit(self):
        "Select the partition to edit; take user input."

        # check for numeric input
        try:
            selected = self.getScrollChoice()
            device = self.partList[selected]
            devPartRequest = device[storage_utils.STORLIST_DISK_ENTRY]
        except (ValueError, IndexError), msg:
            exceptSkeleton = errInvalidSelectionText % {
                    'kind': 'partition', 'reason': msg} + TransMenu.Back
            self.errorPushPop(title + " (Choose Partition)", exceptSkeleton)
            return

        self.dialogMode = "edit"
        self.dialogPartition(partreq=devPartRequest)    # invoke edit dialog

    def deleteExistingPartition(self):
        "Delete an existing partition."

        # menu below needs work
        partList = storage_utils.getPartitionsList(self.requests)
        self.partList = partList
        partLines = []
        for num, part in enumerate(partList):
            mountPoint, fsType, size, request = part
            if mountPoint == '':
                mountPoint = '(no mount point)'
            line = '%2d) %-8s%-12s%-s' % (num+1, fsType, size, mountPoint)
            partLines.append(line)

        self.setScrollEnv(partLines, SCROLL_LIMIT)
        self.scrollDisplay = self.scrollDeleteDisplay
        self.setSubstepEnv( {'next': self.scrollDisplay} )

    def scrollDeleteDisplay(self):
        "Display list of partitions to delete."
        self.buildScrollDisplay(self.scrollable, title + " (Delete)",
            self.selectPartitionDelete, "<number>: partition",
            allowStepBack=True, prolog=choosePartitionDeleteText)

    def selectPartitionDelete(self):
        "Select the partition to delete; take user input."
        try:
            selected = self.getScrollChoice()
            part = self.partList[selected]
        except (ValueError, IndexError), msg:
            exceptSkeleton = errInvalidSelectionText % {
                'kind': 'device', 'reason': msg} + TransMenu.Back
            self.errorPushPop(title + " (Delete)", exceptSkeleton)
            return

        self.deleteThisRequest = part[storage_utils.STORLIST_DISK_ENTRY]

        self.setSubstepEnv({'next': self.confirmPartitionDelete})

    def confirmPartitionDelete(self):
        "Ask user if really want to delete partition."
        ui = {
            'title': title,
            'body': confirmPartitionDeleteText + TransMenu.YesNoBackHelp,
            'menu': {
                '1': self.doPartitionDelete,
                '2': self.start,
                '<': self.start,  # same as '2'
                '?': self.help,
            }
        }
        self.setSubstepEnv(ui)

    def doPartitionDelete(self):
        "This is it.  Once this completes, the partition request is gone."

        self.requests.remove(self.deleteThisRequest)
        self.setSubstepEnv({'next': self.askConfirmPartitions})

    def confirmResetPartitions(self):
        "Ask user if really want to delete partition."
        ui = {
            'title': title,
            'body': confirmResetPartitionsText + TransMenu.YesNoBackHelp,
            'menu': {
                '1': self.reset,
                '2': self.askConfirmPartitions,
                '<': self.askConfirmPartitions,  # same as '2'
                '?': self.help,
            }
        }
        self.setSubstepEnv(ui)

    def reset(self):
        "Restore request to the way it was prior to this step."
        partition.removeOldVirtualDevices()
        # Add the default virtual disk and the requests for it
        partition.addDefaultVirtualDriveAndRequests(
            physicalDeviceName=userchoices.getEsxDatastoreDevice(),
            vmfsVolume=userchoices.getVmdkDatastore())
        self.setupVirtualDevice()
        
        self.setSubstepEnv({'next': self.askConfirmPartitions})

    def commit(self):
        virtualDevs = userchoices.getVirtualDevices()
        assert len(virtualDevs) == 1

        # set the size of the vmdk
        virtualDevs[0]['device'].size = self.requests.getMinimumSize()

        errors = partition.sanityCheckPartitionRequests(checkSizing=True)
        if errors:
            msg = errInvalidPartitionsText + '\n\n'.join(errors)
            self.errorPushPop(title, msg + TransMenu.Back)
            return

        self.setSubstepEnv({'next': self.stepForward})
        
    def help(self):
        "Emit help text."
        self.helpPushPop(title + ' (Help)', helpSetupVmdkText + TransMenu.Back)

    def warnInUse(self):
        ui = {
            'title': title,
            'body': "in use",
            'menu': { '*': self.popSubstep },
        }
        self.setSubstepEnv(ui)

    def warnInvalidDataStore(self):
        ui = {
            'title': title,
            'body': "invalid datastore",
            'menu': { '*': self.popSubstep },
        }
        self.setSubstepEnv(ui)

    def done(self):
        self.setSubstepEnv({'next': self.stepForward})


    # ---- utilities ----

    ## stolen direct from GUI
    def setupVirtualDevice(self):
        # If the virtual device has already been set up before, use the
        # the requests in it, otherwise start with a fresh set
        virtualDevs = userchoices.getVirtualDevices()
        assert len(virtualDevs) == 1

        virtualDev = virtualDevs[0]['device']

        # Update these since they might have been changed by the prev screen.
        virtualDev.physicalDeviceName = userchoices.getEsxDatastoreDevice()
        virtualDev.vmfsVolume = userchoices.getVmdkDatastore()

        self.requests = userchoices.getVirtualPartitionRequests(virtualDev.name)

        # TODO: If the datastore was changed and it is too small to fit the
        # current vmdk partitioning scheme we need to do a reset.

class PartitionWindow(TextRunner):
    """Edit a new or existing partition.
    """

    # TODO: function calls for class-scoped variables considered harmful.
    # See review 14533 comment by sbrown.

    # file system types, VMDK-able file system names

    def __init__(self, parent, partreq=None, mode='new'):
        """Initialize PartitionWindow.
        Doesn't fit the pattern of a dispatchable step; needs parent
        SetupVmdkWindow object.
        """
        super(PartitionWindow, self).__init__()
        self.parent = parent    # SetupVmdkWindow object
        self.mode = mode
        self.title = title + " (Partition Setup)"

        self.newPartInfo = {}   # info for new partition request
        self.substep = self.start
        self.editSize = 0       # size of existing partition being edited

        # constant lists -- used often, generate once
        self.fsTypeClasses = fsset.getSupportedFileSystems()
        self.vmdkFsNames = getVmdkFsNames(self.fsTypeClasses)

        # used to track if we're editing a parition or creating new one
        if partreq:
            self.currentRequest = partreq
        else:
            self.currentRequest = None

    def start(self):
        "Initial step."
        self.setSubstepEnv({'next': self.chooseFileSysType})

    def chooseFileSysType(self):
        "Choose file system type."

        namesList = []
        for num, name in enumerate(self.vmdkFsNames):
            namesList.append("%2d) %-32s" % (num+1, name))

        self.setScrollEnv(namesList, SCROLL_LIMIT)
        self.scrollDisplay = self.scrollFileSysTypeDisplay
        self.setSubstepEnv( {'next': self.scrollDisplay} )

    def scrollFileSysTypeDisplay(self):
        "Display a list of partitions to edit"
        self.buildScrollDisplay(self.scrollable, title, self.inputFileSysType,
            "<number>: type", allowStepBack=True, prolog=chooseFileSysTypeText)

    def inputFileSysType(self):
        "Choose file system type from user input."

        try:
            selected = self.getScrollChoice()
            typeName = self.vmdkFsNames[selected]
            fsType = self.fsTypeClasses[typeName]
            self.newPartInfo['fsTypeName'] = typeName
        except (ValueError, IndexError), msg:
            exceptSkeleton = errInvalidSelectionText % { 'kind': 'file system',
                'reason': msg} + TransMenu.Back
            self.errorPushPop(title + " (Choose File System Type)",
                exceptSkeleton)
            return

        if fsType.mountable:
            self.setSubstepEnv({'next': self.enterFileSysMountPoint})
        else:
            self.newPartInfo['mountPoint'] = '(no mount point)'
            self.setSubstepEnv({'next': self.enterFileSysSize})

    def enterFileSysMountPoint(self):
        "Enter file system mount point."
        ui = {
            'title': self.title,
            'body': enterFileSysMountPointText,
            'menu': {
                '<': self.start,
                '?': self.help,
                '*': self.inputFileSysMountPoint,
            }
        }
        self.setSubstepEnv(ui)

    def inputFileSysMountPoint(self):
        "Set file system mount point from user input."
        mountPoint = self.userinput

        # sanity check mountPoint 
        errMsg = None
        if not mountPoint.startswith('/'):
            errMsg = mperrInvalidText
        elif mountPoint == '/boot':
            errMsg = mperrBootReservedText
        elif mountPoint in partition.INVALID_MOUNTPOINTS:
            errMsg = mperrReservedText % mountPoint

        if errMsg:
            log.warn(errMsg)
            self.errorPushPop(self.title, errMsg + TransMenu.Back)
            return

        # In edit mode, mountPoint can overwrite itself.
        for request in self.parent.requests:
            if request == self.currentRequest:
                continue
            if request.mountPoint == mountPoint:
                errMsg = mperrExistsText
                log.warn(errMsg)
                self.errorPushPop(self.title, errMsg + TransMenu.Back)
                return

        self.newPartInfo['mountPoint'] = mountPoint
        self.setSubstepEnv({'next': self.enterFileSysSize})

    def enterFileSysSize(self):
        "Enter file system size."
        maxsize = self.parent.maxVmdkSize - self.parent.requests.getMinimumSize() \
            + self.editSize
        sizetext = util.formatValue(maxsize * util.SIZE_MB)
        ui = {
            'title': title,
            'body': enterFileSysSizeText % {'maxsize': sizetext },
            'menu': {
                '<': self.start,
                '?': self.help,
                '*': self.inputFileSysSize,
            }
        }
        self.setSubstepEnv(ui)

    def inputFileSysSize(self):
        "Set file system size from user input."

        exceptSkeleton = {
            'title': title,
            'menu': { '*': self.enterFileSysSize },
            # add 'body' below
        }

        userinput = self.userinput.strip()
        try:
            match = re.match(r'(\S+) *([MGT]B)', userinput, re.IGNORECASE)
            if match:
                quantity, units = match.groups()
            else:  # no match
                raise ValueError, "Failed to parse quantity and units."
            units = units.upper()

            try:
                quantity = float(quantity)
            except ValueError:
                raise ValueError, "Postive numeric quanity expected."

            minSize = util.valueInMegabytesFromUnit(quantity, units)
            fsType = self.fsTypeClasses[self.newPartInfo['fsTypeName']]
            if minSize < fsType.minSizeMB:
                raise ValueError, ("You must specify a partition size greater "
                                   "than or equal to %d MB." % fsType.minSizeMB)

        except ValueError, msg:
            errText = msg[0]
            self.pushSubstep()
            exceptSkeleton['body'] = errInvalidInputText % {
                'kind': 'file system size', 'reason': errText} + TransMenu.Back
            self.setSubstepEnv(exceptSkeleton)
            return

        # We should now have valid quantity and units.

        self.newPartInfo['minSize'] = minSize

        self.setSubstepEnv({'next': self.sizeFit})

    def sizeFit(self):
        "determine if new request will fit onto device."

        minSize = self.newPartInfo['minSize']

        # calculate the size of our current requests and subtract the current
        # request if we're editing
        size = self.parent.requests.getMinimumSize()

        if self.currentRequest:
            size -= self.currentRequest.minimumSize

        if size + minSize > self.parent.maxVmdkSize:
            self.errorPushPop(title, parterrNotEnoughRoomText + TransMenu.Back)
            return

        self.setSubstepEnv({'next': self.summarizeFileSys})

    def summarizeFileSys(self):
        "Summarize file system characteristics."
        ui = {
            'title': title,
            'body': summarizeFileSysText % self.newPartInfo + \
                TransMenu.KeepChangeBackHelpExit,
            'menu': {
                '1': self.acceptSummary,
                '2': self.start,
                '<': self.start,
                '?': self.help,
                '*': self.inputFileSysSize,
            }
        }
        self.setSubstepEnv(ui)

    def acceptSummary(self):
        "Add to partition request list."

        fsTypeName = self.newPartInfo['fsTypeName']
        fsType = self.fsTypeClasses[fsTypeName]()
        request = partition.PartitionRequest(mountPoint=self.newPartInfo['mountPoint'],
            minimumSize=self.newPartInfo['minSize'], maximumSize=self.newPartInfo['minSize'],
            grow=False, fsType=fsType)
        if self.currentRequest:
            self.parent.requests.remove(self.currentRequest)
        self.parent.requests.append(request)
        self.parent.requests.sort()

        self.setSubstepEnv({'next': self.stepBack})  # to SetupvmdkWindow
        # self.notifyNotYetImplemented("acceptSummary")


    def help(self):
        "Emit help text."
        self.helpPushPop(title + ' (Help)', helpPartitionText + TransMenu.Back)


# vim: set sw=4 tw=80 :
