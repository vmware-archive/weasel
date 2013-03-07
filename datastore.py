
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

import vmkctl
import partition
import devices

# Location of uuid in "/vmfs/volumes/<uuid>"
VOLUME_UUID = 3

class Datastore:
    def __init__(self, name, uuid=None, consolePath=None, driveName="",
                 majorVersion=0, minorVersion=0, totalBlocks=0,
                 blockSize=0, blocksUsed=0):
        self.name = name
        self.uuid = uuid
        self.consolePath = consolePath
        self.driveName = driveName
        self.majorVersion = majorVersion
        self.minorVersion = minorVersion
        self.totalBlocks = totalBlocks
        self.blockSize = blockSize
        self.blocksUsed = blocksUsed

    def getFreeBlocks(self):
        return self.totalBlocks - self.blocksUsed

    def getFreeSize(self):
        return self.getFreeBlocks() * self.blockSize

    def getSize(self):
        return self.totalBlocks * self.blockSize


class DatastoreSet:
    '''A class to store vmfs volumes'''
    def __init__(self, scan=True):
        self.entries = []

        if scan:
            self.scanVmfsVolumes()

    def scanVmfsVolumes(self):
        storage = vmkctl.StorageInfoImpl()
        volumes = storage.GetVmfsFileSystems()

        for vol in volumes:
            # XXX - need to deal with vmfs extents properly
            extents = vol.GetExtents()
            assert len(extents) > 0

            # device name = 'vml.XXXXX'
            driveName = extents[0].GetDeviceName()

            self.append(Datastore(
                name=vol.GetVolumeName(),
                uuid=vol.GetUuid(),
                consolePath=vol.GetConsolePath(),
                driveName=driveName,
                majorVersion=vol.GetMajorVersion(),
                minorVersion=vol.GetMinorVersion(),
                totalBlocks=vol.GetTotalBlocks(), blockSize=vol.GetBlockSize(),
                blocksUsed=vol.GetBlocksUsed()))

    def getEntryByName(self, name):
        for entry in self.entries:
            if entry.name == name or entry.uuid == name:
                return entry
        return None

    def getEntriesByDriveName(self, driveName):
        foundEntries = []
        for entry in self.entries:
            if entry.driveName == driveName:
                foundEntries.append(entry)
        return foundEntries

    def append(self, entry):
        self.entries.append(entry)

    def remove(self, entry):
        self.entries.remove(entry)

    def __getitem__(self, key):
        return self.entries[key]

    def __len__(self):
        return len(self.entries)

    def __bool__(self):
        return len(self.entries) > 0

def checkForClearedVolume(driveList, datastoreSet, volumeName):
    '''Check to see if a given datastore has been cleared'''

    vol = datastoreSet.getEntryByName(volumeName)
    if vol and vol.driveName in driveList:
        return True
    return False

def runtimeActionFindExistingDatastore(deviceName):
    '''Check to see if an existing datastore is on a device'''

    datastoreSet = DatastoreSet()
    if datastoreSet.getEntriesByDriveName(deviceName):
        return True

    return False

def preserveDatastoreOnDrive(driveName):
    import userchoices

    diskSet = devices.DiskSet()
    datastoreSet = DatastoreSet()

    # find the /boot partition
    disk = diskSet[driveName]
    part = disk.findFirstPartitionMatching(
        fsTypes=('ext2', 'ext3'),
        minimumSize=partition.BOOT_MINIMUM_SIZE)

    assert part

    # wipe the partition
    part.mountPoint = "/boot"
    req = partition.PartitionRequest(mountPoint=part.mountPoint,
        minimumSize=part.getSizeInMegabytes(),
        fsType=part.fsType,
        consoleDevicePath=part.consoleDevicePath,
        clearContents=True)

    # get the datastores for a given drive
    datastores = datastoreSet.getEntriesByDriveName(driveName)

    userchoices.addPartitionMountRequest(req)
    userchoices.clearVirtualDevices()

    # XXX - assuming there is only one datastore on the drive
    partition.addDefaultVirtualDriveAndRequests(driveName,
        vmfsVolume=datastores[0].name)

