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

'''Storage model utility functions

Currently, this only includes functions to support basic setup.
Advanced setup to follow... someday.
'''

# import os
import devices
import util
import partition
from log import log
from util import truncateString
from devices import PATHID_LUN

STORLIST_DISK_ENTRY = 3         # element 3 of storline tuple, i.e., disk entry
DEVNAME_LENGTH = 28             # same as in gui/storage_widgets.py
VENDMODNAME_LENGTH = 20         # vendor model name length

def getStorageList(diskSet, vmfsSupport=True, esxAndCos=True):
    ''' diskSet can be an instance of devices.DiskSet, or it can be a
    function that, when evaluated, returns a devices.DiskSet.  This is
    to support both static and dynamic usage of this function.
    This is a counterpart to populateStorageModel() in
    gui/storage_widgets.py.
    '''
    try:
        disks = diskSet()
    except TypeError:
        disks = diskSet
    # TODO: may have to handle "remote" later.  Check gui/storage_widgets.py.

    eligible = partition.getEligibleDisks(vmfsSupport=vmfsSupport,
                                          esxAndCos=esxAndCos)

    storageList = []
    for lun in disks.values():
        if lun not in eligible:
            continue

        name = truncateString(lun.name, DEVNAME_LENGTH)
        vendModName = "%s %s" % (lun.vendor, lun.model)
        vendorModel = truncateString(vendModName, VENDMODNAME_LENGTH)
        deviceName = "%s (%s)" % (vendorModel, name)
        try:
            path0 = lun.vmkLun.GetPaths()[0]
            targetid = str(path0.GetTargetNumber())
        except IndexError:
            targetid = "n/a"
        lunid = '0'
        if len(lun.pathIds) == 4:
            lunid = lun.pathIds[PATHID_LUN]
        diskSize = lun.getFormattedSize()
        storageList.append([deviceName, lunid, diskSize, lun.name, lun.pathStrings, targetid])

    return storageList

def getVmfsVolumes(volumes):
    '''Find VMFS volumes in a datastore set (argument "volumes").
    This is a counterpart to populateVmfsVolumesModel() in
    gui/storage_widgets.py.
    '''

    vmfsList = []
    for entry in volumes:
        name = entry.name
        size = util.formatValue(entry.getSize() / util.SIZE_MB)
        freeSpace = util.formatValue(entry.getFreeSize() / util.SIZE_MB)
        vmfsList.append([name, size, freeSpace])

    return vmfsList

def getPartitionsList(requests):
    '''Find partitions within list of requests.
    This is a counterpart to populatePartitioningModel() in
    gui/storage_widgets.py.
    '''
    partList = []
    for request in requests:
        maxSize = ''
        grow = ''

        mountPoint = request.mountPoint
        fsType = request.fsType.name
        size = util.formatValue(request.minimumSize * util.SIZE_MB)
        partList.append([mountPoint, fsType, size, request])

    return partList

def getDeviceHasExistingDataText(deviceName):
    foundEsx = devices.runtimeActionFindExistingEsx(deviceName)

    foundVmfs = False

    for part in devices.DiskSet()[deviceName].partitions:
        if part.nativeType == 0xfb:
            foundVmfs = True
            break

    if foundEsx and foundVmfs:
        warnText = """ARE YOU TRYING TO PERFORM AN UPGRADE?

The selected storage device contains an existing ESX installation and
datastore. Continuing installation on this storage device will RESULT IN
DATA LOSS, causing any ESX settings and virtual machines to be lost.

To UPGRADE the existing installation without incurring data loss, use
the vSphere Host Update Utility installed along with vSphere Client or
use vCenter Update Manager.\n"""
    elif foundEsx:
        warnText = """ARE YOU TRYING TO PERFORM AN UPGRADE?

The selected storage device contains an existing ESX installation.
Continuing installation on this storage device will RESULT IN DATA LOSS,
causing any ESX settings to be lost.

To UPGRADE the existing installation without incurring data loss, use
the vSphere Host Update Utility installed along with vSphere Client or
use vCenter Update Manager.\n"""
    elif foundVmfs:
        warnText = """DATA LOSS WARNING:

The selected storage device contains a datastore that will be erased 
before installing ESX. Continuing installation will cause any virtual
machines on this datastore to be lost. If you want to save this content,
please cancel out and choose another option.\n"""
    else:
        warnText = """DATA LOSS WARNING:

The contents of the selected storage device will be erased before
installing ESX. All existing data will be lost. If you want to save this
content, please cancel out and choose another option.\n"""

    return warnText


# vim: set sw=4 tw=80 :
