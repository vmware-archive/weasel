
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

import os
import operator
import parted
import partition
import vmkctl
import util
import consts
import userchoices
import datastore
import time
import fsset
import glob
import esxconf
import shutil

from exception import InstallationError
from singleton import Singleton
from log import log

from precheck import VMDK_OVERHEAD_SIZE

VMKCTL_SCSI_DISK = 0
DEFAULT_COS_IMAGE = 'esxconsole.vmdk'

TMP_MOUNT_PATH = '/mnt/testdir'

PATHID_ADAPTER_NAME = 0
PATHID_CHANNEL = 1
PATHID_TARGET = 2
PATHID_LUN = 3

class InvalidDriveOrder(Exception):
    '''Exception to describe the case when the user specifies a disk
    with the --driveorder flag that doesn't exist (physically)
    '''

class DiskDev:
    # Name of the driver for USB storage.
    DRIVER_USB_STORAGE = "usb-storage"
    
    def __init__(self, name, device=None, path=None, consoleDevicePath=None,
                 vendor=None, model=None, size=0, sectorSize=512, sizeUnit='KB',
                 deviceExists=True, probePartitions=True, driverName=None,
                 pathIds=None, pathStrings=None, vmkLun=None,
                 supportsVmfs=False, local=True):
        '''Disk Device container class for both physical and virtual
           disk devices.

           name                 - name string
           device               - parted device reference
           path                 - path to device (usually under /vmfs)
           consoleDevicePath    - Console OS device path (usually /dev/sdX)
           vendor               - vendor string
           model                - model string
           size                 - size of the disk device (in KB or MB)
           sectorSize           - size of a disk sector in bytes
           sizeUnit             - KB or MB for kilobytes or megabytes
           deviceExists         - used for virtual devices to not probe
                                  the partition table
           probePartitions      - boolean value to search for partitions
           driverName           - name of the driver associated with the
                                  device
           pathIds              -
           pathStrings          - extra data (usually path strings) associated
                                  with the device.  Useful for fibre channel
                                  and iSCSI devices
           vmkLun               -
           supportsVmfs         - device supports vmfs
           local                - device is local (not remote)
        '''
        self.name = name
        self.path = path
        self.consoleDevicePath = consoleDevicePath
        if vendor:
            vendor = vendor.strip()
        self.vendor = vendor
        if model:
            model = model.strip()
        self.model = model
        self.size = size
        self.sectorSize = sectorSize
        self.sizeUnit = sizeUnit
        self.deviceExists = deviceExists
        self.driverName = driverName
        self.pathIds = pathIds
        self.pathStrings = pathStrings
        self.local = local

        self.partedDevice = device
        self.biosBootOrder = None #TODO: This is needed for bootloader.py

        self.vmkLun = vmkLun

        # Determines whether we'll be able to install to this disk.
        self.supportsVmfs = supportsVmfs

        self.partitions = None
        self.requests = None

        # Stable refers to whether or not the device object can change out
        # from under us.
        self.stable = False

        if probePartitions:
            self.probePartitions()

    def __str__(self):
        return "%s (console %s) -- %s (%d MB, %s)" % (
            self.name,
            self.consoleDevicePath,
            self.getVendorModelString(),
            self.getSizeInMegabytes(),
            self.driverName or "no-driver")
        
    def getSizeInMegabytes(self):
        assert self.sizeUnit in ['KB', 'MB']

        if self.sizeUnit == 'MB':
            return self.size
        elif self.sizeUnit == 'KB':
            return util.getValueInMegabytesFromSectors(self.size,
                                                       self.sectorSize)

    # XXX - make this work for MB at some point
    def getSizeInKilobytes(self):
        assert self.sizeUnit == 'KB'
        return util.getValueInKilobytesFromSectors(self.size, self.sectorSize)

    def getFormattedSize(self):
        return util.formatValue(self.getSizeInKilobytes())

    def probePartitions(self):
        # XXX - we should probably raise an exception here
        if not self.deviceExists:
            log.error("Device was probed but doesn't exist yet!")
        else:
            self.partitions = partition.PartitionSet(device=self, scan=True)

    def getPartitionDevicePath(self, partitionNumber):
        '''Return the '/vmfs/devices' path for a given partition number.

        The format for the path can vary somewhat, so it's best to query vmkctl
        for the actual path.  We do this on-demand since the partitions can
        change out from under us.  Also, in the interest of not becoming more
        entangled with vmkctl, this method should really only be used with
        vmfs partitions.
        '''
        #TODO: this open() / close() is being done to "hiccup" the kernel
        #      into acknowledging the existence of this disk.  It should
        #      be removed when the root problem is discovered.
        fp = open(self.path)
        fp.close()
        
        vmkPartitions = self.vmkLun.GetPartitions()
        for vmkPart in vmkPartitions:
            if vmkPart.GetPartition() == partitionNumber:
                return vmkPart.GetDevfsPath()

        assert False, "Could not find partition %d in vmkctl" % partitionNumber

    def getVendorModelString(self):
        """Return a string that contains the vendor and model name of this
        device.

        If the vendor and model are the same generic string, only one is
        returned.
        """
        if self.vendor == self.model:
            retval = self.vendor
        else:
            retval = "%s %s" % (self.vendor, self.model)

        return retval

    def isControllerOnly(self):
        '''Return true if there is no disk attached to the controller.'''

        # See bug # 273709.  The size for the fake cciss disk that represents
        # the controller is one sector, so we check for zero megs.
        return int(self.getSizeInMegabytes()) == 0

    def findFirstPartitionMatching(self,
                                   fsTypes=None,
                                   minimumSize=0,
                                   uuid=None):
        '''Find the first partition on this disk that matches the given set of
        constraints.

        fsTypes - If not-none, a sequence of filesystem names that are
          acceptable for the partition.
        minimumSize - The minimum size of the partition in megabytes.
        uuid - The partition UUID to search for.
        '''
        
        for currentPart in self.partitions:
            if currentPart.getSizeInMegabytes() < max(0,
                minimumSize - partition.PARTITION_FUDGE_SIZE):
                continue
                
            if fsTypes:
                if not currentPart.fsType or \
                        currentPart.fsType.name not in fsTypes:
                    continue

            if uuid:
                if not currentPart.fsType:
                    continue
                
                try:
                    partUuid = currentPart.fsType.getUuid(
                        currentPart.consoleDevicePath)
                except Exception, e:
                    log.warn("could not get UUID for %s" %
                             currentPart.consoleDevicePath)
                    continue
                else:
                    if partUuid != uuid:
                        continue
                    
            return currentPart

        return None

class VirtualDiskDev(DiskDev):
    '''A class for vmdk container'''

    def __init__(self, name, size=5500, imagePath='',
                 imageName='', physicalDeviceName=None,
                 vmfsVolume=None):

        # XXX isinstance(str) is not py3k compliant.
        assert physicalDeviceName is None or isinstance(physicalDeviceName, str)

        DiskDev.__init__(self, name, size=size, deviceExists=False,
                         probePartitions=False, sectorSize=1, sizeUnit='MB')

        self.imagePath = imagePath
        if imageName:
            self.imageName = imageName
        else:
            self.imageName = DEFAULT_COS_IMAGE
        self.physicalDeviceName = physicalDeviceName
        self.vmfsVolume = vmfsVolume

        self.stable = True

        if not self.imagePath:
            # The default vmdk path includes the system UUID so it will be
            # unique on shared storage.
            self.imagePath = \
                fsset.vmfs3FileSystem.systemUniqueName('esxconsole')

            log.info("creating virtualdisk %s/%s" % 
                     (self.imagePath, self.imageName))
        else:
            # XXX - do we want to raise something here if ValueError is
            #       raised?
            pass

    def create(self):
        assert self.vmfsVolume

        path = os.path.join("/vmfs/volumes", self.vmfsVolume, self.imagePath)

        fullPath = os.path.normpath(os.path.join(path, self.imageName))

        # remove any existing vmdk file first
        removeVmdkFile(fullPath)

        if not os.path.exists(path):
            os.makedirs(path)

        args = [ "/usr/sbin/vmkfstools", "-c", "%dM" % (self.size,),
                 fullPath ]

        try:
            util.execWithLog(args[0], args, raiseException=True)
        except Exception, e:
            raise InstallationError("Could not create new COS vmdk.", e)

        '''
        Add a disk database entry that will allow upper layers to know this
        is a cos disk.
        '''
        try:
            fh = open(fullPath, "a")
            fh.write('ddb.consoleOsDisk = "True"\n');
            fh.close();
        except Exception, e:
            raise InstallationError("Could not bless COS vmdk.", e)

    def mount(self):
        path = os.path.join("/vmfs/volumes", self.vmfsVolume, self.imagePath,
                            self.imageName)
        path = os.path.normpath(path)
        args = [ "/usr/sbin/vsd", "-cu", "-f", path ]

        try:
            devicePath = util.execWithCapture(args[0], args,
                                              raiseException=True)
        except Exception, e:
            raise InstallationError("Could not mount COS vmdk file.", e)

        if devicePath.startswith("/dev/"):
            devicePath = devicePath.strip()

            partition.createDeviceNodes()

            self.path = devicePath
            self.consoleDevicePath = devicePath
            self.partedDevice = parted.PedDevice.get(devicePath)
            self.model = self.partedDevice.model.strip()
            self.length = self.partedDevice.length
            self.sectorSize = self.partedDevice.sector_size
            self.deviceExists = True

            self.probePartitions()

        else:
            log.error("Could not mount vmdk! -- %s" % devicePath)

    def getSizeInKilobytes(self):
        raise NotImplementedError, "getSizeInKilobytes() not implemented."

    def getFormattedSize(self):
        raise NotImplementedError, "getFormattedSize() not implemented."

def removeVmdkFile(vmdkPath):
    if os.path.exists(vmdkPath):
        # remove the vmdk file with vmkfstools first and then attempt
        # to remove the directory
        args = [ "/usr/sbin/vmkfstools", "-U", vmdkPath ]

        try:
            util.execWithLog(args[0], args, raiseException=True)
        except Exception, e:
            raise InstallationError("Could not delete old COS vmdk.", e)

        log.debug("Removing %s" % vmdkPath)
        shutil.rmtree(os.path.dirname(vmdkPath))

class DiskSet(Singleton):
    ''' An iterable data structure that represents all the disks on
    the system.

    This is a singleton object. You can re-probe the cached disk list by
    calling the constructor with forceReprobe=True, however this will
    cause the disk list to lose all information about the disks that has
    been contributed by client code.  Particularly 
    PartitionRequestSet.fitPartitionsOnDevice.
    '''
    def _singleton_init(self, forceReprobe=False):
        self.disks = {}

        # XXX temporary workaround for unsupported ide disks, remove later
        self.nonStandardDisks = []

    def __init__(self, forceReprobe=False):
        if forceReprobe or not self.disks:
            self.probeDisks()

    def __getitem__(self, key):
        return self.disks[key]

    def __contains__(self, item):
        return (item in self.disks)

    def items(self):
        return [(lun.name, lun) for lun in self.values()]

    def keys(self):
        return [lun.name for lun in self.values()]

    def values(self):
        unsortedValues = self.disks.values()

        # Annotate the values with the pathIds so we can sort based on the path.
        sortedIdPairs = [
            (diskDev.pathIds, diskDev) for diskDev in unsortedValues]
        sortedIdPairs.sort(lambda x,y: cmp(x[0], y[0]))

        # Strip the pathIds ... we just need the DiskDevs.
        retval = [pair[1] for pair in sortedIdPairs]

        return retval

    def _attachMountPoint(self, uuid, mountPoint):
        '''Find the partition matching the given UUID and set its mountPoint
        field to the given value.'''
        partitionPath = util.uuidToDevicePath(uuid)
        devicePath, _partNum = partition.splitPath(partitionPath)
        device = self.getDiskByPath(devicePath)
        if device:
            for part in device.partitions:
                if part.consoleDevicePath == partitionPath:
                    part.mountPoint = mountPoint
        else:
            log.error("could not find partition with UUID (%s) for "
                      "mount point -- %s" % (uuid, mountPoint))
    
    def _attachUpgradableMounts(self):
        '''Fill out the mountPoint fields for the partitions from the previous
        installation.'''
        if userchoices.getBootUUID():
            self._attachMountPoint(userchoices.getBootUUID()['uuid'],
                                   os.path.join(consts.ESX3_INSTALLATION,
                                                "boot"))
        if userchoices.getRootUUID():
            self._attachMountPoint(userchoices.getRootUUID()['uuid'],
                                   consts.ESX3_INSTALLATION)

    def _adapterSupportsVmfs(self, adapter):
        '''Not all disk/adapter types can support vmfs.'''
        
        return adapter.GetInterfaceType() not in [
            vmkctl.ScsiInterface.SCSI_IFACE_TYPE_USB]
    
    def probeDisks(self, diskList=None):
        self.disks = {} # Need to reset in case of a reprobe.

        if diskList:
            for entry in diskList:
                partedDev = parted.PedDevice.get(entry[1])
                diskDev = DiskDev(name=entry[0], device=partedDev,
                    path=entry[1], model=partedDev.model,
                    size=partedDev.length, sectorSize=partedDev.sector_size)

                self.disks[entry[0]] = diskDev
        else:
            log.debug("Querying disks")

            storage = vmkctl.StorageInfoImpl()
            luns = storage.GetDiskLuns()

            for entry in luns:
                path = entry.GetDevfsPath()

                log.debug(" lun -- %s" % entry.GetName())

                # skip anything which isn't a disk
                # XXX - replace this with the correct constant from vmkctl
                #       if vmkctlpy gets fixed
                if entry.GetLunType() != VMKCTL_SCSI_DISK:
                    log.warn("Lun at %s is not a proper disk. Skipping lun." %
                             (path))
                    continue

                if entry.IsPseudoLun():
                    log.warn("Lun at %s is a pseudo lun.  Skipping lun." %
                             (path))
                    continue

                # XXX - Console Device paths are broken for some USB devices.
                try:
                    consoleDevicePath = entry.GetConsoleDevice()
                except vmkctl.HostCtlException, msg:
                    log.warn("No Console Path for %s.  Skipping lun." % (path))
                    continue

                if not consoleDevicePath.startswith("/dev"):
                    log.warn("Got bogus console path for %s.  Skipping lun" % 
                             (path))
                    continue

                # XXX - check to see if the disk has been initialized
                # we should probably be prompting the user to initialize it 
                if consoleDevicePath:
                    log.debug("  Trying %s" % (consoleDevicePath))
                else:
                    # XXX work around bug 173969 in vmklinux26 that causes
                    # broken luns to be reported
                    log.warn("No Console Path for %s.  Skipping lun." % (path))
                    continue

                # XXX If the mkblkdevs happened in the middle of a scan some of
                # the devices will have been missed so we double check here and
                # run the mkblkdevs on-demand.
                for attempt in range(0, 3):
                    if os.path.exists(consoleDevicePath):
                        break

                    log.debug("console device, '%s', does not exist.  trying "
                              "mkblkdevs again (attempt %d)" %
                              (consoleDevicePath, attempt + 1))
                    time.sleep(3) # wait for things to settle
                    partition.createDeviceNodes()

                if not os.path.exists(consoleDevicePath):
                    log.warn("console device is missing -- %s" %
                             consoleDevicePath)
                    continue
                
                # XXX - this needs to be wrapped in a try/except
                # and display a proper warning if the device can't be
                # accessed
                try:
                    partedDev = parted.PedDevice.get(consoleDevicePath)
                except parted.error, msg:
                    log.warn("Parted couldn't open device %s.  Skipping lun." %
                             (consoleDevicePath))
                    continue

                driverName = None
                supportsVmfs = False

                # Set a default path with a large value so it's at the end of
                # the sorted list.
                pathIds = [ 'z' * 5 ]

                paths = entry.GetPaths()
                pathStrings = []
                if paths:
                    for vmkctlPath in paths:
                        try:
                            transportMap = vmkctlPath.GetTransportMapping()
                            if transportMap:
                                targetString = transportMap.GetTargetString()
                                log.info("Target String: " + targetString)
                                if targetString not in pathStrings:
                                    pathStrings.append(targetString)
                        except vmkctl.HostCtlException, ex:
                            log.warn("Could not get transport mapping -- %s " %
                                     str(ex.GetMessage()))

                    try:
                        adapter = paths[0].GetAdapter()
                        driverName = adapter.GetDriver()
                        pathIds = [
                            util.splitInts(paths[0].GetAdapterName()),
                            paths[0].GetChannelNumber(),
                            paths[0].GetTargetNumber(),
                            paths[0].GetLun()]

                        supportsVmfs = self._adapterSupportsVmfs(adapter)
                    except vmkctl.HostCtlException, ex:
                        ## Should be a problem only until iSCSI driver situation is stabilized.
                        log.warn("Could not get driver for path %s -- %s" %
                                 (consoleDevicePath, str(ex.GetMessage())))
                else:
                    log.warn("Could not get driver name for %s" %
                             consoleDevicePath)

                diskDev = DiskDev(name=entry.GetName(), device=partedDev,
                    path=path, consoleDevicePath=consoleDevicePath,
                    model=entry.GetModel(), vendor=entry.GetVendor(),
                    size=partedDev.length, sectorSize=partedDev.sector_size,
                    driverName=driverName, pathIds=pathIds,
                    pathStrings=pathStrings, vmkLun=entry,
                    supportsVmfs=supportsVmfs, local=entry.IsLocal())

                log.info("Discovered lun -- %s" % str(diskDev))

                self.disks[entry.GetName()] = diskDev

        self._attachUpgradableMounts()

    def getOrderedDrives(self, allowUserOverride=True):
        '''Return a list of drives. The order will be the order that the 
        BIOS puts them in, unless the user has specified a particular device 
        to go first.

        This is primarily used to set up GRUB

        TODO: the scripted install "driveOrder" command  only affects the order 
        of at most one device.  This is how I understand it should work.  If 
        that's the case, maybe we need to change the name from "driveOrder" 
        to something else.
        '''
        allDrives = self.disks.values()
        comparator = operator.attrgetter('biosBootOrder')
        allDrives.sort(key=comparator)

        # XXX - remove this at some point since mixing userchoices here
        #       is bad.
        if allowUserOverride:
            bootOptions = userchoices.getBoot()
            if bootOptions:
                driveOrder = bootOptions['driveOrder']
                if driveOrder:
                    firstDrive = driveOrder[0]
                    if firstDrive not in allDrives:
                        raise InvalidDriveOrder(firstDrive)
                    allDrives.remove(firstDrive)
                    allDrives.insert(0, firstDrive)
                else:
                    log.debug("No drive order specified.  Set to default.")
            else:
                log.debug("Drive order set to default.")
        return allDrives

    def getDiskByName(self, name):
        if self.disks.has_key(name):
            return self.disks[name]
        return None

    def getDiskByPath(self, path, console=True):
        '''Find the disk that exactly matches path.'''
        for disk in self.disks.values():
            if console:
                if disk.consoleDevicePath == path:
                    return disk
            else:
                if disk.path == path:
                    return disk
        return None

    def _buildDisksToSearch(self, searchVirtual=False):
        '''Build a list of disks to search, including non-standard disks and,
        optionally, virtual disks.
        '''
        
        retval = self.disks.values()
        
        # TODO: it's kind of ugly that this has knowledge of userchoices
        #       in the future, this knowledge should be removed.
        if searchVirtual:
            virtualDevices = userchoices.getVirtualDevices()
            for virtualDevice in virtualDevices:
                virtDiskDev = virtualDevice['device']
                retval.append( virtDiskDev )

        retval.extend(self.nonStandardDisks)

        return retval

    def findPartitionContaining(self, path, searchVirtual=False):
        '''Find the partition containing path.  path may have its own
        dedicated partition, or it might be under /.

        Returns None if path's partition can't be found
        
        If /boot is it's own partition:
        >>> p = DiskSet().findPartitionContaining('/boot')
        >>> print p.mountPoint
        /boot

        If /boot doesn't have it's own partition:
        >>> p = DiskSet().findPartitionContaining('/boot')
        >>> print p.mountPoint
        /
        '''
        candidate = None
        disksToSearch = self._buildDisksToSearch(searchVirtual)

        for disk in disksToSearch:
            for currentPart in disk.partitions:
                if not currentPart.mountPoint:
                    continue

                if currentPart.mountPoint == path:
                    return currentPart
                elif path.startswith(currentPart.mountPoint):
                    if not candidate or \
                       len(currentPart.mountPoint) > len(candidate.mountPoint):
                        candidate = currentPart

        return candidate

    def findFirstPartitionMatching(self, fsTypes=(), minimumSize=0, uuid=None):
        '''Find the first partition in this set of disks that matches the given
        set of constraints.'''
        disksToSearch = self._buildDisksToSearch(False)
        
        for disk in disksToSearch:
            match = disk.findFirstPartitionMatching(fsTypes,
                                                    minimumSize,
                                                    uuid)
            if match:
                return (disk, match)

        return None

    def findDiskContainingPartition(self, part, searchVirtual=False):
        '''Find the disk containing part.
        Returns None if part can't be found
        '''
        disksToSearch = self._buildDisksToSearch(searchVirtual)

        for disk in disksToSearch:
            if part in disk.partitions:
                return disk
        return None

def hostActionSetupVmdk(_context):
    virtualDevs = userchoices.getVirtualDevices()
    assert len(virtualDevs) == 1

    virtualDev = virtualDevs[0]['device']

    vmfsVolPath = ""

    dsSet = datastore.DatastoreSet()
    for ds in dsSet:
        if virtualDev.vmfsVolume in (ds.name, ds.uuid):
            vmfsVolPath = ds.consolePath

    assert vmfsVolPath, "no console path for %s" % virtualDev.vmfsVolume

    path = os.path.normpath(
        os.path.join(vmfsVolPath, virtualDev.imagePath, virtualDev.imageName))

    sysInfo = vmkctl.SystemInfoImpl()
    try:
        sysInfo.SetServiceConsoleVmdk(path)
    except vmkctl.HostCtlException, msg:
        log.warn("Couldn't set vmdk path.  The system may not boot correctly.")

def runtimeActionFindMaxVmdkSize():
    '''Look through userchoices settings and determine how large we can allow
       the vmdk to be.
    '''

    datastoreSet = None

    devName = userchoices.getEsxDatastoreDevice()

    # find the free space on an existing datastore
    if not devName:
        volumeName = userchoices.getVmdkDatastore()

        datastoreSet = datastore.DatastoreSet()
        vol = datastoreSet.getEntryByName(volumeName)
        assert vol

        # Max vmdk size is 256 * fileblocksize from
        # File_VMFSSupportsFileSize in filePosix.c

        return min(vol.getFreeSize() / util.SIZE_MB / util.SIZE_MB,
                   vol.blockSize * 256 / util.SIZE_MB)

    else:
        dev = DiskSet()[devName]
        
        # get the physical size of the device
        size = util.getValueInMegabytesFromSectors(dev.size, dev.sectorSize)

        requests = userchoices.getPhysicalPartitionRequests(dev.name)
        assert requests

        # we have to guess how big the vmfs3 partition is going to be, so
        # remove any other partitions on the disk from our total size
        for req in requests:
            if not req.grow and req.fsType.name != 'vmfs3':
                size -= req.minimumSize

        return min(fsset.vmfs3FileSystem.blockSizeMB * 256 * util.SIZE_MB,
                   size - VMDK_OVERHEAD_SIZE)

def runtimeActionFindExistingEsx(devName):
    '''Search through the first partition on a disk to see if it
       contains traces of an ESX Installation.
    '''

    foundEsx = False

    dev = DiskSet()[devName]

    if not os.path.exists(TMP_MOUNT_PATH):
        os.makedirs(TMP_MOUNT_PATH)

    # don't bother looking if there are no partitions or the
    # first partition isn't ext2/3
    if len(dev.partitions) and dev.partitions[0].partitionId == 1 and \
       dev.partitions[0].fsType and \
       dev.partitions[0].fsType.name in ['ext2', 'ext3']:

        dev.partitions[0].fsType.mount(dev.partitions[0].consoleDevicePath,
                                       TMP_MOUNT_PATH)

        if glob.glob(os.path.join(TMP_MOUNT_PATH, '*vmnix*')) or \
           glob.glob(os.path.join(TMP_MOUNT_PATH, '*ESX')) or \
           glob.glob(os.path.join(TMP_MOUNT_PATH, 'boot', '*vmnix*')):
            foundEsx = True

        dev.partitions[0].fsType.umount(TMP_MOUNT_PATH)

    return foundEsx

def runtimeActionFindExistingVmdkSize(existingVmdk):
    if existingVmdk:
        vmdkPath, ext = os.path.splitext(existingVmdk)
        vmdkPath += '-flat' + ext

        if os.path.exists(vmdkPath):
            vmdkSize = os.path.getsize(vmdkPath) / 1024 / 1024
            return vmdkSize

    return 0

if __name__ == "__main__":
    disks = DiskSet()

    print disks['vmhba32:0:0'].partitions

    print disks['vmhba32:0:0'].size
    print disks['vmhba32:0:0'].model
    print disks['vmhba32:0:0'].sectorSize
    print disks['vmhba32:0:0'].path

    #print x.disks['vmhba0:0:0'].partitions
    print len( disks['vmhba32:0:0'].partitions )
    for entry in disks['vmhba32:0:0'].partitions:
        print "%d: start = %d end = %d size=%d" % (entry.partitionId, entry.startSector, entry.endSector, entry.getLength())

