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

'''ESX Location
Where to install ESX.
For basic partitioning, addVirtualPartitions=True (default)
For advanced partitioning, addVirtualPartitions=False
'''

# TODO:  Where do disk choices get registered?

import devices
import partition
import storage_utils
import userchoices
import datastore
from log import log

from textrunner import TextRunner, SubstepTransitionMenu as TransMenu

title = "ESX Storage Device"

esxLocationText = """\
Select a location to install ESX.

Local Storage:
%(storagelist)s

Other action:
 <) Back
 ?) Help

"""

helpText = """\
Select a location to install ESX.

ESX can be installed on a different device from where virtual machines
are stored.

ESX requires at least 1.25 GB.  If the service console is installed on
the same device as ESX, a minimum of 10 GB is required.
"""

diskHeaderText = """\
 # | Device Name                                       |Lun|Trgt|   Size\
"""

SCROLL_LIMIT = 20

class EsxLocationWindow(TextRunner):
    "Determine disk location for ESX."
    # TODO: handle iSCSI

    def __init__(self, partMode="basic"):
        super(EsxLocationWindow, self).__init__()
        self.storList = \
            storage_utils.getStorageList(devices.DiskSet(),
                                         vmfsSupport=(partMode=="basic"),
                                         esxAndCos=(partMode=="basic"))
        self.partMode = partMode    # basic or advanced
        self.driveName = None

        self.start = self.bldStorDisplayList
        self.substep = self.start
        self.scrollable = None

    def bldStorDisplayList(self):
        " build displayable storage list"
        # only repopulate esxlocation if we need to
        if userchoices.getResetEsxLocation():
            self.storList = \
                storage_utils.getStorageList(devices.DiskSet(),
                                             vmfsSupport=(self.partMode=="basic"),
                                             esxAndCos=(self.partMode=="basic"))

        # build storage list
        storListText = []

        storEnumStr = "%2d) %-51s %3s %4s %11s"
        storEnumPath = "        %s"
        storListText.append(diskHeaderText)
        for num, storLine in enumerate(self.storList):
            deviceModel, lunid, disksize, entry, pathString, targetid = storLine
            storListText.append(storEnumStr %
                (num+1, deviceModel, lunid, targetid, disksize) )
            for path in pathString:
                tempEnumPath = storEnumPath % path
                while tempEnumPath:
                    storListText.append(tempEnumPath[:80])
                    tempEnumPath = tempEnumPath[80:]

        self.setScrollEnv(storListText, SCROLL_LIMIT)
        self.setSubstepEnv( {'next': self.scrollDisplay} )

    def scrollDisplay(self):
        "display store list choices"
        self.buildScrollDisplay(self.scrollable, title,
            self.chooseDevice, "<number>: storage", allowStepBack=True)

    def help(self):
        "Emit help text."
        self.helpPushPop(title + ' (Help)', helpText + TransMenu.Back)

    def chooseDevice(self):
        "Choose the device specified by user.  "
        try:
            selected = self.getScrollChoice(maxValue=len(self.storList))
            driveName = self.storList[selected][storage_utils.STORLIST_DISK_ENTRY]
        except (ValueError, IndexError), ex:
            log.error(str(ex))
            driveName = None

        if not driveName:
            msg = "%s\n" % str(ex)
            self.errorPushPop(title +' (Update)', msg + TransMenu.Back)
            return

        self.driveName = driveName
        log.debug("Selected drive %s" % driveName)

        drive = devices.DiskSet()[driveName]

        self.setSubstepEnv( {'next': self.warn } )

    def warn(self):
        """Warn that content will be delete.
        Currently always do this, even if disk has never been used.
        """
        # TODO: push/pop may not be needed; only comes from chooseDevice.

        warnText = storage_utils.getDeviceHasExistingDataText(self.driveName)

        self.pushSubstep()
        ui = {
            'title': title,
            'body': warnText + TransMenu.OkBack,
            'menu': {
                '1': self.addPartRequest,
                '<': self.popSubstep,
            }
        }
        self.setSubstepEnv(ui)


    def addPartRequest(self):
        """Add the default partition request.  May be configured for
        basic or advanced."""

        self.popSubstep()       # kludge, pop state from warn()

        # schedule default partition operation
        request = devices.DiskSet()[self.driveName]
        if self.partMode == 'basic':
            partition.addDefaultPartitionRequests(request)
        else:   # partMode == 'advanced'
            partition.addDefaultPartitionRequests(request,
                addVirtualPartitions=False)

        # If ESX location is changing (or this is first time), tell
        # DataStoreWindow via userchoices so it can clear options.
        if self.driveName != userchoices.getEsxPhysicalDevice():
            userchoices.setResetEsxLocation(True)
        else:
            userchoices.setResetEsxLocation(False)

        self.setSubstepEnv( {'next': self.stepForward } )

# TODO:  possible parameterization EsxLocationWindow 
def BasicEsxLocationWindow():
    "Do basic partitioning."
    return EsxLocationWindow(partMode="basic")
def AdvEsxLocationWindow():
    "Do advanced partitioning."
    return EsxLocationWindow(partMode="advanced")

# vim: set sw=4 tw=80 :
