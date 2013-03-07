
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

import re
import fsset
import parted
import util
import devices
import os
import shutil
import packages
import userchoices
import systemsettings
import consts
import vmkctl

from copy import copy
from log import log

from precheck import \
    DEFAULT_ROOT_SIZE, \
    DEFAULT_LOG_SIZE, \
    getDefaultSwapSize

PRIMARY = 0
LOGICAL = 1
EXTENDED = 2
FREESPACE = 4
METADATA = 8
PROTECTED = 16

MAX_PRIMARY_PARTITIONS = 4
MAX_PARTITIONS = 13

DEFAULT_PHYSICAL_REQUESTS = [
    ("/boot", 1100, 0, False, fsset.ext3FileSystem()),
    (None, 110, 0, False, fsset.vmkCoreDumpFileSystem()),
]

INVALID_MOUNTPOINTS = [
    '/etc',
    '/boot/grub',
    '/proc',
    '/sys',
    '/dev',
    '/sbin',
    '/lib',
    '/lib64',
    '/bin'
    ]

REQUEST_MOUNTPOINT = 0
REQUEST_SIZE = 1
REQUEST_GROW = 2
REQUEST_FSTYPE = 3

# In case we're reusing an existing partition, the size might not be exactly
# as originally requested, so we'll need to add a fudge factor in some places.
PARTITION_FUDGE_SIZE = 10

BOOT_MINIMUM_SIZE = 100

def getDefaultDiskType():
    return parted.disk_type_get("msdos")

def createDeviceNodes():
    """Get the OS to create all new device nodes.""" 
    os.system("echo mkblkdevs | nash --force")

def splitPath(path):
    '''Split a /dev device path into the path for the whole device and the
    partition number.

    >>> splitPath("/dev/sda10")
    ('/dev/sda', 10)
    >>> splitPath("/dev/cciss/c0d0p1")
    ('/dev/cciss/c0d0', 1)
    >>> splitPath("/dev/sx8/0p2")
    ('/dev/sx8/0', 2)
    '''

    m = re.match(r'(/dev/(?:cciss|rd|sx8|ida)/[^p]+|'
                 # The part above ^^^ matches the device path up to the
                 # partition number when the path has an intervening directory
                 # (e.g. cciss).
                 r'/dev/[^\d]+)' # Match 'normal' devices.
                 r'p?(\d+)', # Finally, capture the partition number.
                 path)
    assert m
    assert len(m.groups()) == 2
    
    return (m.group(1), int(m.group(2)))

def joinPath(devicePath, partitionNum):
    '''Join a path for a whole device with a partition number.

    >>> joinPath("/dev/sda", 1)
    '/dev/sda1'
    '''
    if (devicePath.startswith("/dev/sd") or
        devicePath.startswith("/dev/hd")):
        retval = "%s%d" % (devicePath, partitionNum)
    elif (devicePath.startswith("/dev/cciss") or 
          devicePath.startswith("/dev/rd")):
        retval = "%sp%d" % (devicePath, partitionNum)
    else:
        raise ValueError, "Got unexpected console device: %s" % (devicePath)

    return retval

class NotEnoughSpaceException(Exception):
    def __init__(self, msg):
        Exception.__init__(self, msg)
        self.msg = msg

class Partition:
    def __init__(self, name="", fsType=None, partitionType=PRIMARY,
                 startSector=-1, endSector=-1, partitionId=-1, mountPoint=None,
                 format=False, consoleDevicePath=None, nativeType=-1):
        '''Basic Partition class.

           name                 - name related to the partition (usually blank)
           fsType               - file system class (from fsset)
           partitionType        - type of partition can be PRIMARY, EXTENDED
                                  LOGICAL
           partitionId          - id of the partition on disk.  -1 is free
                                  space.  1-4 are primary partitions (or 1
                                  extended partition)
           mountPoint           - absolute path to real mount point (place
                                  where the directory would normally be
                                  mounted)
           format               - boolean value to format the partition
           consoleDevicePath    - device node for how to access the partition
           nativeType           - native id type for the filesystem
                                  (ie. linux is 0x83, linux-swap is 0x82,
                                       vmfs is 0xfb, vmkcore is 0xfc)
        '''
        assert fsType is None or isinstance(fsType, fsset.FileSystemType)
        
        self.name = name
        self.fsType = fsType
        self.startSector = long(startSector)
        self.endSector = long(endSector)
        self.partitionId = partitionId
        self.mountPoint = mountPoint
        self.consoleDevicePath = consoleDevicePath
        self.nativeType = nativeType

        if partitionType == PRIMARY or partitionType == LOGICAL or \
           partitionType == EXTENDED or partitionType == FREESPACE or \
           partitionType == LOGICAL + FREESPACE:
            self.partitionType = partitionType
        else:
           raise ValueError, ("Partition type must be set to PRIMARY, "
               "LOGICAL or EXTENDED.")

        if format and not fsType.formattable:
            raise RuntimeError, ("File system type %s is not formattable "
                "however it has been flagged to be formatted." % \
                (fsType.name,))
        self.format = format

    def getName(self):
        return self.name

    def getStartSector(self):
        return self.startSector

    def getEndSector(self):
        return self.endSector

    def getLength(self):
        return long(self.endSector - self.startSector + 1)

    def getSizeInMegabytes(self):
        return util.getValueInMegabytesFromSectors(self.getLength())

    def getFileSystem(self):
        return self.fsType

    def getId(self):
        return self.partitionId

    def getMountPoint(self):
        return self.mountPoint

    def getPartitionType(self):
        return self.partitionType

    def setFormat(self, format):
        self.format = format

    def getFormat(self):
        return self.format

    def getFsTypeName(self):
        if self.fsType:
            retval = self.fsType.name
        else:
            retval = None

        return retval

    def isPrimary(self):
        return self.partitionType == PRIMARY

    def getPartitionEntry(self, device=""):
        """Returns a formatted list of options for the partitioning screen"""

        entry = []
        fsType = ""

        if self.getId() == -1:
            entry.append("Free space")
        else:
            entry.append("%s:%d" % (device, self.getId()))
        entry.append(self.getMountPoint())

        if self.fsType:
            entry.append(self.fsType.name)
        elif self.partitionType == EXTENDED:
            entry.append("Extended")
        elif self.partitionType & FREESPACE:
            entry.append("")
        else:
            entry.append("Unknown")

        # CPD - We should append a checkmark or something like that here
        if self.getFormat():
            entry.append("*")
        else:
            entry.append("")

        entry.append(util.formatValue(self.getLength() / 2))
        #entry.append(util.formatValueInMegabytes(self.getStartSector() / 2))
        #entry.append(util.formatValueInMegabytes(self.getEndSector() / 2))

        return entry



class PartitionSet:
    """Container object for a set of partitions"""

    def __init__(self, partitions=None, device=None, scan=False):
        if partitions == None:
            self.partitions = []
        else:
            self.partitions = partitions

        # XXX - if a disk label isn't initialized, go ahead and initialize it
        # this could cause some ramifications if we detect a disk with a disk
        # label that parted doesn't understand which we may want to prompt
        # for.  Ideally we should warn the user here that the disk they're
        # trying to partition can not be used.

        if device:
            self.partedDevice = device.partedDevice
            try:
                self.partedDisk = parted.PedDisk.new(self.partedDevice)
            except parted.error:
                try:
                    self.partedDisk = self.partedDevice.disk_new_fresh(
                        parted.disk_type_get("msdos"))
                    self.partedDisk.commit()
                except parted.error, msg:
                    log.error("Couldn't initialize %s: %s." % (device.path, msg))
                    return

        self.device = device

        if scan:
            self.scanPartitionsOnDevice()

    def __len__(self):
        return len(self.partitions)

    def __getitem__(self, key):
        return self.partitions[key]

    def append(self, partition):
        self.partitions.append(partition)

    def __str__(self):
        buf = ""
        for entry in self.partitions:
            length = entry.getLength()

            buf += "%d: pos=%d start=%d end=%d size=%d (%d MB)\n" % \
            (entry.partitionType, entry.partitionId, entry.startSector,
             entry.endSector, length,
             util.getValueInMegabytesFromSectors(length))
        return buf

    def clear(self):
        self.partedDisk.delete_all()

        # re-init the disk in case the partition table is corrupt
        self.partedDisk = self.partedDevice.disk_new_fresh(
            parted.disk_type_get("msdos"))
        self.partedDisk.commit()

        self.partitions = []
        self.scanPartitionsOnDevice()

    def getPartitions(self, showFreeSpace=False, showUsedSpace=True):
        """Return a PartitionSet with a Free or Used Space"""
        if showFreeSpace and showUsedSpace:
            # XXX - this should probably return a copy
            return self
        else:
            partitions = PartitionSet(device=self.device)
            for partition in self.partitions:
                if showFreeSpace and partition.getPartitionType() & FREESPACE:
                    partitions.append(partition)
                elif showUsedSpace and \
                     not partition.getPartitionType() & FREESPACE:
                    partitions.append(partition)
            return partitions

    def scanPartitionsOnDevice(self, device=None, partedDev=None,
                               partedDisk=None, requests=None):
        """Walk through each of the partitions on a given disk"""
        if not device:
            device = self.device

        if not partedDev:
            partedDev = self.partedDevice
        if not partedDisk:
            partedDisk = self.partedDisk

        self.partitions = []

        fsTable = fsset.getSupportedFileSystems(partedKeys=True)

        partition = partedDisk.next_partition()

        while partition:
            if partition.num > 0:
                # MSDOS disk labels don't have names for partitions, however
                # GPT tables may, even if we don't support them yet.
                try:
                    name = partition.get_name()
                except:
                    name = ""

                mountPoint = None
                consoleDevicePath = None
                format = False

                nativeType = partition.native_type

                if requests:
                    request = requests.findRequestByPartitionID(partition.num)
                    if request:
                        mountPoint = request.mountPoint
                        consoleDevicePath = request.consoleDevicePath
                        # if we have a request, format every partition possible
                        if request.fsType.formattable:
                            format = True
                elif partedDisk.type.name == "loop":
                    # The "loop" type means there is no partition table, for
                    # example, if the whole disk is formatted as FAT.
                    consoleDevicePath = partedDev.path
                else:
                    consoleDevicePath = joinPath(partedDev.path, partition.num)
                
                # XXX - we need to be able to figure out what filesystem
                #       type we've found instead of setting it to None
                if partition.type & EXTENDED:
                    fsType = None
                elif partition.fs_type and \
                   fsTable.has_key(partition.fs_type.name):
                    fsClass = fsTable[partition.fs_type.name]
                    fsType = fsClass()
                else:
                    partedFsTypeName = "unknown"
                    if partition.fs_type:
                        partedFsTypeName = partition.fs_type.name
                    log.debug("Unknown parted file system type ('%s') for "
                              "partition: %s%d" %
                              (partedFsTypeName,
                               device.consoleDevicePath,
                               partition.num))
                    fsType = None
                    format = False # XXX

                self.partitions.append(Partition(name, fsType, partition.type,
                    partition.geom.start, partition.geom.end, partition.num,
                    mountPoint, format, consoleDevicePath, nativeType))
            else:
                if partition.type and partition.type & FREESPACE:
                    name = ""
                    self.partitions.append(Partition(name, None,
                        partition.type, partition.geom.start,
                        partition.geom.end, partition.num))

            partition = partedDisk.next_partition(partition)


    def removeNonVmfsPartitions(self):
        extended_part = None
        new_parts = []
        logical = 0

        self.sort_partitions_by_position() #TODO: wtf is this?!?!

        # pass 1
        # wipe out any non-vmfs partitions
        for entry in self.getPartitions():
            if entry.type == 'extended':
                logical = 1
                extended_part = entry

            elif entry[0] == 'vmfs':
                if logical and extended_part:
                    new_parts.append(extended_part)
                    extended_part = None

                new_parts.append(entry)

    def getDevice(self):
        return self.device


class PartitionRequest(Partition):
    def __init__(self, mountPoint=None, fsType=None, drive=None,
                 minimumSize=0, maximumSize=0, grow=False,
                 primaryPartition=False, badBlocks=False,
                 consoleDevicePath="", clearContents=False):
        # XXX - don't call this or the nosetests will fail
        #assert fsType is None or isinstance(fsType, fsset.FileSystemType)
        
        self.mountPoint = mountPoint
        self.fsType = fsType
        if self.mountPoint == "/":
            self.fsType.label = consts.ESX_ROOT_LABEL
        
        self.apparentSize = 0
        self.minimumSize = minimumSize
        self.maximumSize = maximumSize
        self.grow = grow
        self.consoleDevicePath = consoleDevicePath
        self.partitionId = 0

        self.clearContents = clearContents

        # XXX - check to see if there is enough space for another primary
        # partition here
        self.primaryPartition = primaryPartition
        self.badBlocks = badBlocks

    def __repr__(self):
        return repr(self.__dict__)

class PartitionRequestSet:
    """Container object for holding PartitionRequests"""

    def __init__(self, deviceName=None, deviceObj=None):
        self.deviceName = deviceName
        self._deviceObj = deviceObj
        self.requests = []

    def __getitem__(self, key):
        return self.requests[key]

    def __len__(self):
        return len(self.requests)

    def __add__(self, oldSet):
        """Add two request sets together.  This is useful for determining
           the mount order of each of the partitions, however the device will
           be invalid for the entire set so you will not be able to partition
           after combining two sets.
        """
        newSet = PartitionRequestSet()
        newSet.requests = self.requests + oldSet.requests

        # set the device to the old one although it's possible this could
        # be invalid
        newSet.deviceName = oldSet.deviceName
        newSet._deviceObj = oldSet._deviceObj

        return newSet

    def _getDevice(self):
        if self._deviceObj or self.deviceName:
            return self._deviceObj or devices.DiskSet()[self.deviceName]
        else:
            return None
    device = property(_getDevice)

    def getMinimumSize(self):
        # Need to add some padding for the mbr, partition boot records and
        # whatever else...
        size = 1
        for request in self.requests:
            size += request.minimumSize + 1
        return size

    def sort(self, sortByMountPoint=False):
        '''Sort the partition requests.  The default sorting order is based on
        the partition size and whether it is set to grow (see _cmpRequests).
        The default ordering is used when creating the partitions.
        Alternatively, you can sort by mountpoint, which is useful for
        determining a mounting order that will work correctly since the parent
        directories have to be mounted before the children.

        >>> from devices import DiskSet
        >>> ds = DiskSet()
        >>> prs = PartitionRequestSet(ds.values()[0])
        >>> prs.append(PartitionRequest("/boot", minimumSize=100))
        >>> prs.append(PartitionRequest("/", minimumSize=50, grow=True))
        >>> prs.append(PartitionRequest("/var/log",
        ...                             minimumSize=50,
        ...                             maximumSize=200,
        ...                             grow=True))
        >>> prs.sort()
        >>> for pr in prs:
        ...     print pr.mountPoint
        /boot
        /var/log
        /
        >>> prs.sort(True)
        >>> for pr in prs:
        ...     print pr.mountPoint
        /
        /boot
        /var/log
        '''
        
        if sortByMountPoint:
            # sort the requests by mount point so we will mount parent
            # directories before their children.
            self.requests.sort(lambda x, y: cmp(x.mountPoint, y.mountPoint))
        else:
            self.requests.sort(self._cmpRequests)

    def append(self, request):
        self.requests.append(request)

    def remove(self, request):
        self.requests.remove(request)

    def reverse(self):
        self.requests.reverse()

    def _cmpRequests(self, request1, request2):
        """Sort requests in the following order:
                First precedence:  /boot
                Second precedence: fixed partitioning
                Third precedence:  grow partitioning with max size
                Fourth precedence: grow partitioning with no max size
        """

        def requestPrecedence(request):
            if request.mountPoint and request.mountPoint == '/boot':
                return 0
            if request.minimumSize and not request.grow:
                return 1
            elif request.minimumSize and request.maximumSize and request.grow:
                return 2
            else:
                return 3

        return cmp(requestPrecedence(request1), requestPrecedence(request2))

    def findRequestByMountPoint(self, mountPoint):
        for request in self.requests:
            if request.mountPoint == mountPoint:
                return request
        return None

    def findRequestByPartitionID(self, partID):
        for part in self.requests:
            if part.partitionId == partID:
                return part
        return None

    def _findFreeSpace(self, rescan=False):
        return self.device.partitions.getPartitions(showFreeSpace=True,
                                                    showUsedSpace=False)

    def _addPartition(self, partitionType, fsType, startSector, endSector,
                      partReq):
        partitionSet = self.device.partitions
        newPartition = partitionSet.partedDisk.partition_new(partitionType, 
                           fsType, startSector, endSector)

        # XXX - set the boot partition as bootable for IBM Nahalem servers
        if partReq.mountPoint == '/boot':
            newPartition.set_flag(parted.PARTITION_BOOT, 1)

        newConstraint = partitionSet.partedDevice.constraint_any()
        partitionSet.partedDisk.add_partition(newPartition, newConstraint)

        partReq.consoleDevicePath = joinPath(partitionSet.partedDevice.path,
                                             newPartition.num)

        log.debug("New partition console path:%s" % (partReq.consoleDevicePath))

        # save the new partition id so we can reference requests with it later
        partReq.partitionId = newPartition.num

    # XXX - It may be possible to merge fitRequestsOnDevice() and
    #       fitPartitionsOnDevice() at some point.  They do similar but
    #       different things right now.  It may be worth running
    #       fitRequestsOnDevice() and then added physical partitions
    #       afterward.

    def fitRequestsOnDevice(self):
        '''Try to fit the partition requests into the available size of
           the device that it's on.  This differs from fitPartitionsOnDevice()
           in that it doesn't try to create physical partitions but show
           how the disk would logically look to the user.
        '''

        totalRemainingSize = self.device.getSizeInMegabytes()
        growToMax = 0
        minSize = 0

        for entry in self.requests:
            minSize += entry.minimumSize
            if entry.grow and not entry.maximumSize:
                growToMax += 1

        if minSize > totalRemainingSize:
            raise NotEnoughSpaceException, \
                "Not enough space for requested partitions."

        for entry in self.requests:
            if not entry.grow:
                entry.apparentSize = entry.minimumSize
            elif entry.grow and entry.maximumSize:
                if entry.maximumSize > totalRemainingSize:
                    entry.apparentSize = totalRemainingSize
                else:
                    entry.apparentSize = entry.maximumSize
            else:
                entry.apparentSize = totalRemainingSize / growToMax
                growToMax -= 1

            totalRemainingSize -= entry.apparentSize

    def fitPartitionsOnDevice(self):
        '''Try to fit partition requests on to a given disk.'''
        growToMax = 0
        primaryPartitions = 0
        primaryRequests = 0
        extendedPartition = 0

        # only count non-freespace partitions in our total
        totalPartitions = len(self.device.partitions.getPartitions())

        # look through real paritions on the device
        for entry in self.device.partitions:
            if entry.partitionType == PRIMARY:
                primaryPartitions += 1
            elif entry.partitionType == EXTENDED:
                extendedPartition += 1

        if extendedPartition > 1:
            raise OSError, "Found more than one extended partition on a device"

        if totalPartitions >= 4 and not extendedPartition and \
           len(self.requests) > 0:
            raise ValueError, "Can't add extended partition to handle requests"

        # look through new requests
        for entry in self.requests:
            if entry.grow and not entry.maximumSize:
                growToMax += 1
            if entry.primaryPartition:
                primaryRequests += 1

        if primaryPartitions + primaryRequests > MAX_PRIMARY_PARTITIONS:
            raise ValueError, "Can't have more than %d primary partitions" % \
                MAX_PRIMARY_PARTITIONS

        if totalPartitions + len(self.requests) > MAX_PARTITIONS:
            raise ValueError, "Can't have more than %d total partitions" % \
                MAX_PARTITIONS

        for entry in self.requests:
            length = util.getValueInSectorsFromMegabyes(entry.minimumSize)
            startSector = -1

            log.debug("Free Space")
            freeSpace = self._findFreeSpace()
            log.debug(freeSpace)

            if len(freeSpace) < 1 or freeSpace[0].getLength() < length:
                raise ValueError, ("Not enough free space, cannot "
                                   "create partition.")

            # create the extended partition if we need one
            log.debug("Primary = %d" % (primaryPartitions))
            if not extendedPartition and not entry.primaryPartition and \
               primaryPartitions >= 2:
                partitionType = EXTENDED
                extendedPartition += 1
                primaryPartitions += 1

                if len(freeSpace) == 1:
                    startSector = freeSpace[0].startSector
                    endSector = freeSpace[0].endSector

                    self._addPartition(partitionType, None, startSector,
                                       endSector, entry)

                    # reset freespace since we added an extended partition
                    freeSpace = self._findFreeSpace()

                else:
                    raise ValueError, "FIXME: Gaps in the freespace"

            foundSpot = False
            # look for a spot on the disk
            for space in freeSpace:
                if length <= space.getLength():
                    foundSpot = True
                    log.debug("Found a spot:  %d" % (space.startSector))
                    startSector = space.startSector
                    endSector = space.endSector

                    if entry.primaryPartition or not extendedPartition:
                        partitionType = PRIMARY
                        primaryPartitions += 1
                    else:
                        partitionType = LOGICAL

                    # fixed partition size
                    if entry.minimumSize and not entry.grow:
                        space.startSector = space.startSector + length

                    # growable partition w/ max size
                    elif entry.minimumSize and entry.maximumSize and entry.grow:
                        maxLength = util.getValueInSectorsFromMegabyes(
                                        entry.maximumSize)

                        # check to see if the partition is too big
                        if maxLength > space.getLength():
                            length = space.getLength()
                        else:
                            length = maxLength

                        space.startSector = space.startSector + length

                    # growable partition w/ no max size
                    else:
                        log.debug("no max size")
                        length = space.getLength() / growToMax
                        space.startSector = space.startSector + length
                        growToMax -= 1

            if not foundSpot:
                raise ValueError, ("Couldn't find a spot for the " + \
                                   "requested partition.")

            # only create the partition if we found a spot
            if startSector != -1:
                totalPartitions += 1

                fsType = entry.fsType.partedFileSystemType
                self._addPartition(partitionType, fsType, startSector,
                                       startSector + length-1, entry)
            else:
                log.debug("Couldn't find a spot!")

        self.device.partitions.scanPartitionsOnDevice(requests=self)
        log.debug('partitions are: ' + str(self.device.partitions))

    def savePartitions(self):
        if self.device.partitions.partedDisk:
            self.device.partitions.partedDisk.commit()

    def findMinimumRequestSizes(self, sizeDict):
        '''Create a dictionary which contains a list of minimum sizes for
           any given system directory.

           sizeDict - dictionary which contains a list of directories and their
                      corresponding total file sizes (in bytes)

           minSizeDict - constructed list of the minimum sizes for each
                         given partition request (in megabytes)
        '''

        sizeDict = sizeDict.copy()

        minSizeDict = {}
        mountPoints = []
        for req in self.requests:
            if req.mountPoint and req.mountPoint.startswith('/'):
                mountPoints.append(req.mountPoint)

        # sort each of the mountPoints and then reverse their order since
        # we need to remove directories further down the directory tree first
        mountPoints.sort()
        mountPoints.reverse()

        # iterate through each of the directories in our directory tree and
        # remove each directory and sum the contents

        for mountPoint in mountPoints:
            size = 0
            for dirName in sizeDict.keys():
                if dirName == mountPoint or \
                   dirName.startswith(mountPoint + '/') or \
                   mountPoint == '/':
                    size += sizeDict[dirName]
                    del sizeDict[dirName]

            # add 20% overhead just to make sure we're going to fit
            minSizeDict[mountPoint] = int(size / 1024 / 1024 * 1.20)

        return minSizeDict


def createPartitionRequestSet(device, requestList):
    """This is a convenience function for creating a partition request
       set from a list of tuples.

       Expected tuple format: 
       ( mountPoint (absolute path),
         minimumSize (in MB),
         maximumSize (in MB),
         growable,
         fileSystem (filesystem class))
    """

    if device.stable:
        partitionRequests = PartitionRequestSet(deviceObj=device)
    else:
        partitionRequests = PartitionRequestSet(deviceName=device.name)

    for part in requestList:
        request = PartitionRequest(mountPoint=part[0],
            minimumSize=part[1], maximumSize=part[2], grow=part[3],
            fsType=part[4])
        partitionRequests.append(request)

    partitionRequests.sort()

    return partitionRequests

def addDefaultPartitionRequests(drive, addVirtualPartitions=True):
    '''Add the default partition configuration for the given drive to
    userchoices under the given name.

    >>> ds = devices.DiskSet()
    >>> name = ds.keys()[0]
    >>> addDefaultPartitionRequests(ds[name])
    >>> reqs = userchoices.getPhysicalPartitionRequests(name)
    >>> len(reqs)
    3
    >>> reqs[0].mountPoint
    '/boot'
    '''

    name = drive.name
    userchoices.setClearPartitions(drives=[drive.name])
    userchoices.clearPhysicalPartitionRequests()

    if addVirtualPartitions:
        removeOldVirtualDevices()

        addDefaultPhysicalRequests(drive, True)
        addDefaultVirtualDriveAndRequests(drive.name)
    else:
        addDefaultPhysicalRequests(drive, False)

    assert userchoices.checkPhysicalPartitionRequestsHasDevice(name)

def addDefaultPhysicalRequests(physicalDisk, addVmfsPartition=True):
    physicalRequests = copy(DEFAULT_PHYSICAL_REQUESTS)
    if addVmfsPartition:
        # Set the min size of the vmfs partition to the size of the default
        # virtual requests.
        virtualRequests = getDefaultVirtualRequests()
        vmfsSize = getRequestsSize(virtualRequests) + devices.VMDK_OVERHEAD_SIZE
        physicalRequests.append((None,
                                 vmfsSize,
                                 0,
                                 True,
                                 fsset.vmfs3FileSystem()))

    userchoices.setPhysicalPartitionRequests(physicalDisk.name,
        createPartitionRequestSet(physicalDisk, physicalRequests))

# XXX - this is really similar to getMinimumSize in the partitionRequestSet
#       we should probably change the tuples for the default partitions
#       to be in a PartitionRequestSet object and then remove this
#       function
def getRequestsSize(requests):
    size = 1

    for req in requests:
        size += req[REQUEST_SIZE] + 1

    return size

def getDefaultVirtualRequests():
    # Query vmkctl for the current amount of memory reserved for the cos.  In
    # the case of installs, this will be the default value in vmkctl.  For
    # upgrades, though, it will be the size in the previous install.
    cosMemSize = vmkctl.MemoryInfoImpl().GetServiceConsoleReservedMem()
    physMemSize = vmkctl.MemoryInfoImpl().GetPhysicalMemory() / 1024 / 1024
    retval = [
        ("/", DEFAULT_ROOT_SIZE, 0, True, fsset.ext3FileSystem()),
        ("", getDefaultSwapSize(cosMemSize, physMemSize), 0, False, fsset.swapFileSystem()),
        ("/var/log", DEFAULT_LOG_SIZE, 0, False, fsset.ext3FileSystem()),
        ]

    return retval

def addDefaultVirtualDriveAndRequests(physicalDeviceName,
                                      virtualDiskName="esxconsole",
                                      vmfsVolume="(auto-generated)",
                                      extraVirtualDiskSpace=0,
                                      imagePath=None,
                                      imageName=None):

    # don't add a new virtual device if one has already been configured
    #for virtualDev in userchoices.getVirtualDevices():
    #    if virtualDev['device'].name == virtualDiskName:
    #        return

    virtualRequests = getDefaultVirtualRequests()
    
    # figure out the size of the vmdk from our partitions
    size = getRequestsSize(virtualRequests) + extraVirtualDiskSpace

    virtualDisk = devices.VirtualDiskDev(name=virtualDiskName, size=size,
                                         physicalDeviceName=physicalDeviceName,
                                         vmfsVolume=vmfsVolume,
                                         imagePath=imagePath,
                                         imageName=imageName)

    userchoices.setVirtualPartitionRequests(virtualDisk.name,
        createPartitionRequestSet(virtualDisk, virtualRequests))

    userchoices.addVirtualDevice(virtualDisk)


def removeOldVirtualDevices():
    for oldVirtDevice in userchoices.getVirtualPartitionRequestsDevices():
        userchoices.delVirtualPartitionRequests(oldVirtDevice)

    for oldVirtualDevice in userchoices.getVirtualDevices():
        userchoices.delVirtualDevice(oldVirtualDevice)
    

def _allUserPartitionRequestSets():
    '''Return all the PartitionRequestSets in userchoices in a list.'''
    retval = []

    for physDevice in userchoices.getPhysicalPartitionRequestsDevices():
        retval.append(userchoices.getPhysicalPartitionRequests(physDevice))
    
    for virtDevice in userchoices.getVirtualPartitionRequestsDevices():
        if not userchoices.checkVirtualPartitionRequestsHasDevice(
            virtDevice):
            # no partitions on the vmdk
            continue
        
        retval.append(userchoices.getVirtualPartitionRequests(virtDevice))

    # Only add the partition mount requests if there are any, otherwise there
    # appears to be user partition requests when there really aren't.
    if userchoices.getPartitionMountRequests():
        mountSet = PartitionRequestSet()
        mountSet.requests = userchoices.getPartitionMountRequests()
        retval.append(mountSet)
    
    return retval

def allUserPartitionRequests():
    '''Return all the PartitionRequests in userchoices in a single
    PartitionRequestSet.'''
    reqSets = _allUserPartitionRequestSets()

    retval = PartitionRequestSet()
    for reqSet in reqSets:
        retval += reqSet

    return retval

def getEligibleDisks(disks=None, vmfsSupport=True, esxAndCos=True):
    '''Return a list of DiskDevs that are supported and large enough to
    support the default installation.'''

    if disks is None:
        disks = devices.DiskSet()

    defaultRequests = list(DEFAULT_PHYSICAL_REQUESTS)
    if vmfsSupport and esxAndCos:
        minSizeInMB = getRequestsSize(defaultRequests + getDefaultVirtualRequests()) + \
                      devices.VMDK_OVERHEAD_SIZE
    elif vmfsSupport and not esxAndCos:
        minSizeInMB = getRequestsSize(getDefaultVirtualRequests()) + \
                      devices.VMDK_OVERHEAD_SIZE
    else:
        minSizeInMB = getRequestsSize(defaultRequests)

    maxSizeInMB = 2 * 1024 * 1024 # 2 TB

    retval = []
    for disk in disks.values():
        log.debug("checking disk for install eligibility -- %s" % str(disk))

        if vmfsSupport and not disk.supportsVmfs:
            log.debug("  vmfs not supported")
            continue

        if disk.getSizeInMegabytes() < minSizeInMB:
            log.debug("  too small")
            continue

        if disk.getSizeInMegabytes() >= maxSizeInMB: # XXX bug #290262
            log.debug("  too big")
            continue

        if disk.name in userchoices.getDrivesInUse():
            log.debug("  already in use")
            continue

        log.debug("  disk is eligible")
        retval.append(disk)
    
    return retval      

def sanityCheckPartitionRequests(partRequestSetList=None, checkSizing=False):
    '''Check the partition requests to make sure the expected requests (e.g.
    "/boot" and "/") are there.

    The given list of PartitionRequestSets is checked against the following
    constraints:
      * There is a "/boot" partition that is on a physical partition and is
        greater than or equal to 100MB in size.
      * There is a "/" partition and it greater than or equal to 100MB in size.

    The return value is a pair containing any error messages and warnings.

    >>> from devices import DiskSet
    >>> ds = DiskSet()
    >>> prs = PartitionRequestSet(ds.values()[0])
    >>> prs.append(PartitionRequest("/boot", minimumSize=100))
    >>> # There is no root partition, we should get an error.
    ... sanityCheckPartitionRequests([prs])
    (['no root partition found.'], [])
    >>> prs.append(PartitionRequest("/", minimumSize=100))
    >>> sanityCheckPartitionRequests([prs])
    ([], [])
    '''

    if partRequestSetList is None:
        partRequestSetList = _allUserPartitionRequestSets()

    errors = []
    
    bootRequest = None
    rootRequest = None

    if checkSizing and partRequestSetList:
        # Download the package data so we can figure out the minimum partition
        # sizes
        weaselConfig = systemsettings.WeaselConfig()
        packagesXML = packages.getPackagesXML(weaselConfig.packageGroups)
        packageData = packages.PackageData(packagesXML.fullInstallDepot)
    
        fileSizes = packageData.fileDict
    else:
        fileSizes = {}

    swapSize = 0
    for reqSet in partRequestSetList:
        clearChoice = userchoices.getClearPartitions()
        if reqSet.device and reqSet.device.deviceExists and \
                reqSet.deviceName not in clearChoice.get('drives', []):
            errors.append(
                '%s needs to have its partitions cleared before it can be '
                'repartitioned.' % reqSet.device.name)
        
        minSize = reqSet.getMinimumSize()
        if reqSet.device and minSize > reqSet.device.getSizeInMegabytes():
            errors.append(
                'partition sizes for %s are too large (%d MB > %d MB).' % (
                    reqSet.device.name,
                    minSize,
                    reqSet.device.getSizeInMegabytes()))

        sizeDict = reqSet.findMinimumRequestSizes(fileSizes)
        for req in reqSet:
            if isinstance(req.fsType, fsset.swapFileSystem):
                swapSize += req.minimumSize
                continue
            
            if not req.mountPoint:
                continue

            if req.mountPoint.startswith('/') and \
                    req.minimumSize < sizeDict[req.mountPoint]:
                errors.append('The "%s" partition needs to be at least %d '
                              'megabytes in size.' % (
                        req.mountPoint, sizeDict[req.mountPoint]))
            
            if (not isinstance(reqSet.device, devices.VirtualDiskDev) and
                req.mountPoint == '/boot'):
                bootRequest = req
                
            if req.mountPoint == '/':
                rootRequest = req

            # TODO: Check for anything starting with '/etc' or '/boot'.
            if req.mountPoint in INVALID_MOUNTPOINTS:
                errors.append('%s cannot be on a separate partition.' %
                              req.mountPoint)

    if swapSize == 0:
        errors.append('A swap partition is required to use ESX.')
    elif swapSize < 256:
        errors.append('Swap space must be at least 256MB in size.')
    
    if userchoices.getUpgrade():
        if not userchoices.getBootUUID():
            # TODO: deal with no boot partition, everything in root...
            errors.append('no "/boot" partition specified for upgrade.')
    elif not bootRequest:
        errors.append('no "/boot" partition found.')
    elif bootRequest.minimumSize < (BOOT_MINIMUM_SIZE - PARTITION_FUDGE_SIZE):
        errors.append('"/boot" partition must be at least %dMB in size.' %
                      BOOT_MINIMUM_SIZE)

    if not rootRequest:
        errors.append("A '/' (root) partition was not specified for the "
                      "Service Console virtual disk.  The Service Console "
                      "can not boot without a '/' partition.")

    return errors


# Host-actions are below, these functions are called by the applychoices
# module in order to act on the data in userchoices.

def hostActionClearPartitions(context):
    clearParts = userchoices.getClearPartitions()
    if 'drives' in clearParts and 'whichParts' in clearParts:
        # XXX A side-effect of getting the list of vmfs volumes in DatastoreSet
        # is that any existing vmfs volumes will get put into a cache in the
        # kernel.  While in this cache, some SCSI handles are left open which
        # prevent us from clearing the partition table completely.
        #
        # See pr 237236 for more information.
        fsset.flushVmfsVolumes()
        
        context.cb.pushStatusGroup(len(clearParts['drives']))
        for deviceName in clearParts['drives']:
            device = devices.DiskSet()[deviceName]
            if device.name in userchoices.getDrivesInUse():
                log.info("skipping clearing drive -- %s" % device.name)
                continue
            
            context.cb.pushStatus("Clearing Partition %s (%s)" % (
                device.name, device.path))
            if clearParts['whichParts'] == userchoices.CLEAR_PARTS_ALL:
                device.partitions.clear()
            else:
                #TODO: finish this for the other options.
                assert False, "clearPartitions not completely implemented"
            device.partitions.partedDisk.commit() # XXX
            context.cb.popStatus()
        context.cb.popStatusGroup()

        # rescan the vmfs volumes in case we need to disconnect any since
        # we have a new partition table
        fsset.rescanVmfsVolumes()
        

def hostActionPartitionPhysicalDevices(context):
    requestDevices = userchoices.getPhysicalPartitionRequestsDevices()
    context.cb.pushStatusGroup(len(requestDevices))

    for deviceName in requestDevices:
        virtualDevs = \
            userchoices.getVirtualDevicesByPhysicalDeviceName(deviceName)

        requests = userchoices.getPhysicalPartitionRequests(deviceName)
        context.cb.pushStatus("Partitioning %s (%s)" % (
            requests.device.name, requests.device.path))
        
        requests.sort()
        requests.fitPartitionsOnDevice()
        requests.savePartitions()

        # TODO: check for badblocks?
        
        createDeviceNodes()

        context.cb.pushStatusGroup(len(requests))
        for request in requests:
            if request.fsType.formattable:
                if request.fsType.name == "vmfs3":
                    path = requests.device.getPartitionDevicePath(
                        request.partitionId)
                    volumeName = request.fsType.volumeName

                    # If we don't have a name for the vmfs volume and
                    # we have a virtual device, then we need to set
                    # the volume name for autopartitioning.

                    # XXX - we're assuming that we only have one vmfs device
                    # per volume right now

                    if virtualDevs and not volumeName:
                        volumeName = fsset.findVmfsVolumeName()
                        request.fsType.volumeName = volumeName

                        assert len(virtualDevs) == 1

                        virtualDevs[0]['device'].vmfsVolume = volumeName
                else:
                    path = request.consoleDevicePath
                
                context.cb.pushStatus("Formatting %s" % path)
                request.fsType.formatDevice(path)
                context.cb.popStatus()
        context.cb.popStatusGroup()
        context.cb.popStatus()
    context.cb.popStatusGroup()

def hostActionPartitionVirtualDevices(context):
    virtualDevs = userchoices.getVirtualDevices()
    assert len(virtualDevs) == 1 or len(virtualDevs) == 0

    if not virtualDevs:
        return

    # There's two steps for each dev, partitioning it and formatting the parts. 
    context.cb.pushStatusGroup(len(virtualDevs) * 2)
    # XXX - we only care about one virtual device for now
    virtualDevs[0]['device'].create()
    virtualDevs[0]['device'].mount()
    
    deviceName = virtualDevs[0]['device'].name

    context.cb.pushStatus("Partitioning %s" % deviceName)
    if userchoices.checkVirtualPartitionRequestsHasDevice(deviceName):
        requests = userchoices.getVirtualPartitionRequests(deviceName)
        requests.device = virtualDevs[0]['device']
        requests.sort()
        requests.fitPartitionsOnDevice()
        requests.savePartitions()
    else:
        # The virtualdisk does not have any partitions (can happen in scripted
        # install...)
        requests = []
    context.cb.popStatus()
    
    createDeviceNodes()

    context.cb.pushStatus("Formatting Virtual Devices")
    context.cb.pushStatusGroup(len(requests))
    for request in requests:
        if request.fsType.formattable:
            context.cb.pushStatus("Formatting %s" % request.consoleDevicePath)
            request.fsType.formatDevice(request.consoleDevicePath)
            context.cb.popStatus()
    context.cb.popStatusGroup()
    context.cb.popStatus()
    context.cb.popStatusGroup()

def hostActionMountFileSystems(context):
    # XXX - we only use one virtual device for now
    virtualDevs = userchoices.getVirtualDevices()
    assert len(virtualDevs) == 1 or len(virtualDevs) == 0

    requests = allUserPartitionRequests()
    requests.sort(sortByMountPoint=True)
    
    for request in requests:
        # skip vmfs partitions since they can't be mounted
        if not request.mountPoint:
            continue

        mountPoint = os.path.normpath(consts.HOST_ROOT +
                                      request.mountPoint)

        if not os.path.exists(mountPoint):
            os.makedirs(mountPoint)
        
        log.debug("Mounting %s -> %s" % \
                  (request.consoleDevicePath, mountPoint))
        request.fsType.mount(request.consoleDevicePath, mountPoint)

        if request.clearContents:
            # Clear out the contents of the drive.  Removing the files might be
            # preferable to a reformat since we preserve the UUID.
            for name in os.listdir(mountPoint):
                path = os.path.join(mountPoint, name)
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                
    if userchoices.getUpgrade():
        upgradeMounts = [
            (consts.ESX3_INSTALLATION, userchoices.getRootUUID()['uuid'])
            ]

        if userchoices.isCombinedBootAndRootForUpgrade():
            log.debug("Linking boot")
            # No /boot partition, need to create a link to the old one.
            os.symlink(os.path.join(consts.ESX3_INSTALLATION.lstrip('/'),
                                    "boot"),
                       os.path.join(consts.HOST_ROOT, "boot"))
        else:
            upgradeMounts.append(
                ("/boot", userchoices.getBootUUID()['uuid']))

        for partMountPoint, uuid in upgradeMounts:
            mountPoint = os.path.normpath(consts.HOST_ROOT + partMountPoint)
            if not os.path.exists(mountPoint):
                os.makedirs(mountPoint)

            log.debug("Mounting %s -> %s" % (uuid, mountPoint))
            rc = util.mount(uuid, mountPoint, isUUID=True)
            assert rc == 0 # TODO: handle errors

def tidyActionUnmount():
    requests = allUserPartitionRequests()
    requests.sort(sortByMountPoint=True)
    requests.reverse()

    for request in requests:
        if not request.mountPoint:
            continue

        mountPoint = os.path.normpath(consts.HOST_ROOT + request.mountPoint)
        if os.path.exists(mountPoint):
            log.debug("Unmounting %s" % (mountPoint))
            util.umount(mountPoint)


if __name__ == "__main__":
    import doctest
    doctest.testmod()
    
    diskSet = devices.DiskSet()
    disks = diskSet.keys()
    disks.sort()

#    for entry in diskSet["vmhba32:0:0"].partitions:
#        print "%d: start=%d end=%d size=%d" % (entry.partitionId, entry.startSector, entry.endSector, entry.getLength())


    requests = PartitionRequestSet(deviceName="vmhba32:0:0")

    #requests.append(PartitionRequest(minimumSize=100, maximumSize=100))
    #requests.append(PartitionRequest(minimumSize=256, maximumSize=256))
    #requests.append(PartitionRequest(minimumSize=3000, maximumSize=3000))

    requests.append(PartitionRequest(minimumSize=100, grow=True))
    requests.append(PartitionRequest(minimumSize=100, maximumSize=100))
    requests.append(PartitionRequest(minimumSize=400, maximumSize=3000, grow=True))
    #requests.append(PartitionRequest(minimumSize=400, maximumSize=3000, grow=True))

    requests.sort()
    print "Sort"
    for myEntry in requests:
        print "min = %d max = %d grow = %s" % (myEntry.minimumSize, myEntry.maximumSize, myEntry.grow)

    requests.fitPartitionsOnDevice()
    #requests.savePartitions()


