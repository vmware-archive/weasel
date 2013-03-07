
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

import string
import os
import re
import parted
import util
import types
import time
import struct
import workarounds

from consts import HOST_ROOT
from log import log
from exception import InstallationError
from regexlocator import RegexLocator

class FileSystemType:
    deviceArguments = {}
    formattable = False
    labelable = False
    mountable = False
    uuidable = False
    checked = False
    vmdkable = False
    linuxnativefs = False
    vmwarefs = False
    partedFileSystemType = None
    partedFileSystemName = None
    partedPartitionFlags = []
    minSizeMB = 16
    maxSizeMB = 2 * 1024 * 1024
    supported = False
    defaultOptions = "defaults"
    extraFormatArgs = []

    def __init__(self, name=""):
        if name:
            self.name = name

    def mount(self, device, mountPoint, readOnly=False, bindMount=False,
              loopMount=False):

        #if not self.isMountable():
        #    print "Couldn't mount %s" % (device)
        #    return
        
        status = util.mount(device, mountPoint, readOnly, bindMount, loopMount)
        if status:
            raise InstallationError("Could not mount '%s' onto '%s'." % (
                    device, mountPoint))

    def umount(self, mountPoint):
        status = util.umount(mountPoint)
        if status:
            raise InstallationError("Could not unmount '%s'." % mountPoint)

    def formatDevice(self, entry=None, progress=None, chroot='/'):
        if self.isFormattable():
            raise RuntimeError, "formatDevice method not defined"

    def labelDevice(self, entry=None, chroot='/'):
        if self.isLabelable():
            raise RuntimeError, "labelDevice method not defined"

    def uuidDevice(self, entry=None, chroot='/'):
        if self.isUuidable():
            raise RuntimeError, "uuidDevice method not defined"
            
    def isFormattable(self):
        return self.formattable

    def isLabelable(self):
        return self.labelable

    def isUuidable(self):
        return self.uuidable

    def isLinuxNativeFS(self):
        return self.linuxnativefs

    def isVMwareFS(self):
        return self.vmwarefs

    def isMountable(self):
        '''look through each of the reported /proc/filesystems entries
        to make certain the kernel supports a particular file system

        >>> e3fs = ext3FileSystem()
        >>> e3fs.isMountable()
        True
        >>> fst = FileSystemType()
        >>> fst.name = "foo"
        >>> fst.isMountable()
        False
        '''
        try:
            f = open("/proc/filesystems", "r")
            lines = f.readlines()
            for entry in lines:
                fields = string.split(entry)
                if fields[0] == "nodev":
                    if fields[1] == self.name:
                        return True
                elif fields[0] == self.name:
                    return True
            
            return False
        except:
            print "Couldn't open /proc/filesystems"
            raise

    def isSupported(self):
        return self.supported
        
    def isChecked(self):
        return self.checked

    def getPartedFileSystemType(self):
        return self.partedFileSystemType

    def getPartedPartitionFlags(self):
        return self.partedPartitionFlags

    def getMinSizeMB(self):
        return self.minSizeMB

    def getMaxSizeMB(self):
        '''returns the maximum size of a filesystem in megabytes'''
        return self.maxSizeMB

    def getDefaultOptions(self):
        return self.defaultOptions

    def getUuid(self, devicePath):
        # XXX Maybe we should just install the vol_id package...
        log.warn('This FS Type does not have a UUID')
        return None


class extFileSystem(FileSystemType):
    partedFileSystemType = None
    partedFileSystemName = None
    formattable = True
    mountable = True
    checked = True
    linuxnativefs = True
    maxSizeMB = 2 * 1024 * 1024

    def __init__(self, label=None):
        FileSystemType.__init__(self)

        assert label is None or len(label) < 16
        self.label = label

    def formatDevice(self, devicePath="", progress=None, chroot='/'):
        args = ["/usr/sbin/mkfs.ext2"]
        if self.label:
            args += ["-L", self.label]

        args += [devicePath]
        args.extend(self.extraFormatArgs)

        try:
            util.execWithLog(args[0], args, raiseException=True)
        except Exception, e:
            raise InstallationError("Could not format a linux partition.", e)

    def getUuid(self, devicePath):
        return util.getUuid(devicePath)


class ext2FileSystem(extFileSystem):
    name = "ext2"
    partedFileSystemType = parted.file_system_type_get("ext2")
    partedFileSystemName = "ext2"
    supported = True

    def __init__(self, label=None):
        extFileSystem.__init__(self, label)

class ext3FileSystem(extFileSystem):
    name = "ext3"
    #extraFormatArgs = [ "-j", "-F" ]
    extraFormatArgs = [ ]
    partedFileSystemType = parted.file_system_type_get("ext3")
    partedFileSystemName = "ext3"
    vmdkable = True
    supported = True

    def __init__(self, label=None):
        extFileSystem.__init__(self, label)

    def formatDevice(self, devicePath="", progress=None, chroot='/'):
        extFileSystem.formatDevice(self, devicePath, progress, chroot)

        # XXX - crufty hack for ext3
        os.system('touch /etc/mtab')

        # XXX - add back -Odir_index when htree is safe
        args = ["/usr/sbin/tune2fs", "-c0", "-i0", "-j", devicePath]

        try:
            util.execWithLog(args[0], args, raiseException=True)
        except Exception, e:
            raise InstallationError(
                "Could not enable journalling on a linux partition.", e)

class vmfs3FileSystem(FileSystemType):
    partedFileSystemType = parted.file_system_type_get("vmfs3")
    partedFileSystemName = "vmfs3"
    formattable = True
    checked = False
    vmwarefs = True
    linuxnativefs = False
    supported = True
    minSizeMB = 1200
    maxSizeMB = 2 * 1024 * 1024
    name = "vmfs3"
    blockSizeMB = 1

    maxLabelLength = 64 # From lvm_public.h
    maxFilenameLength = 127 # From statvfs of /vmfs

    @staticmethod
    def sanityCheckVolumeLabel(label):
        '''Return True if the given label is valid.

        XXX Not totally sure what all the constraints are for a label.

        >>> vmfs3FileSystem.sanityCheckVolumeLabel('hello')
        >>> vmfs3FileSystem.sanityCheckVolumeLabel('hello/world')
        Traceback (most recent call last):
        ...
        ValueError: vmfs volume label is invalid.
        >>> vmfs3FileSystem.sanityCheckVolumeLabel('hello' * 128)
        Traceback (most recent call last):
        ...
        ValueError: vmfs volume label must be less than 64 characters long.
        '''

        if not label:
            raise ValueError, \
                "Datastore names must contain at least one character."

        if len(label) > vmfs3FileSystem.maxLabelLength:
            raise ValueError, \
                  "Datastore names must be less than %d characters long." % \
                    (vmfs3FileSystem.maxLabelLength,)

        if label[0] in string.whitespace or label[-1] in string.whitespace:
            raise ValueError, "Datastore names must not start or end with " + \
                "spaces."

        if label[0] == '.':
            raise ValueError, "Datastore names must not begin with the '.' " + \
                "character."

        if not re.match('^(' + RegexLocator.vmfsvolume + ')$', label):
            raise ValueError, "Datastore names must not contain the '/' " + \
                "character."

    @classmethod
    def systemUniqueName(cls, prefix):
        '''Given a prefix return a filename that is unique for this installed
        system.'''
        import vmkctl

        uuid = vmkctl.SystemInfoImpl().GetSystemUuid()
        retval = "%s-%s" % (prefix, uuid.uuidStr)
        if len(retval) > cls.maxFilenameLength:
            raise ValueError(
                "name is too long when prepended to UUID "
                "(max %d chars) -- %s" % (cls.maxFilenameLength, retval))
        return retval

    def __init__(self, volumeName=None):
        FileSystemType.__init__(self)
        self.volumeName = volumeName

    def mount(self, device, mountPoint, readOnly=False, bindMount=False,
              loopMount=False):
        pass

    def umount(self, mountPoint=None):
        pass

    def uuidDevice(self):
        pass

    def formatDevice(self, devicePath=None, progress=None):
        assert self.volumeName

        args = ["/usr/sbin/vmkfstools", "-C", self.name,
                "-b", "%dm" % self.blockSizeMB, "-S", self.volumeName,
                devicePath]
        args.extend(self.extraFormatArgs)

        try:
            util.execWithLog(args[0], args, raiseException=True)
        except Exception, e:
            raise InstallationError("Could not format a vmfs volume.", e)

def findVmfsVolumeName():
    """Find a volume name that we can use to install.

       This function is used to find a default vmfs volume name for
       autopartitioning.

       ***It is not shared storage safe.***

       Autopartitioning is not supposed to be done on shared storage since
       /boot can be overwritten by other machines.  If the user wants to put
       the COS on a new vmfs volume on shared storage, they will have to
       specify the volume name manually.  The risk would be minimal anyway
       since this function should be called late when the partition is just
       about to be formatted.
    """
    count = 0

    while True:
        count += 1

        # XXX - put the string somewhere more useful
        volumeName = "datastore%d" % (count)
        volumePath = os.path.join("/vmfs/volumes", volumeName)

        if not os.path.exists(volumePath) and not os.path.islink(volumePath):
            log.debug("  using auto-generated vmfs volume name -- %s" %
                      volumeName)
            return volumeName

        log.debug("  vmfs volume name already exists, trying again -- %s" %
                  volumePath)


def flushVmfsVolumes():
    import vmkctl

    # XXX A side-effect of rescan is that it will flush any volumes that happen
    # to be squirreled away somewhere in a cache.
    vmkctl.StorageInfoImpl().RescanVmfs()
    # XXX The rescan does not seem to be completely synchronous for this
    # purpose, sleep a bit.
    time.sleep(3)

def rescanVmfsVolumes():
    import vmkctl

    # XXX wait for vmfs volumes to settle down, six is the magic number.
    time.sleep(6)
    vmkctl.StorageInfoImpl().RescanVmfs()


class swapFileSystem(FileSystemType):
    partedFileSystemType = parted.file_system_type_get("linux-swap")
    partedFileSystemName = "linux-swap"
    formattable = True
    name = "swap"
    minSizeMB = 16
    maxSizeMB = 1024 * 1024
    linuxnativefs = True
    vmdkable = True
    supported = True

    # Format of the swap partition header.  Used anaconda's isys package as a
    # reference for this.
    headerFmt = "1024xIII16s"
    
    def __init__(self):
        FileSystemType.__init__(self)

    def mount(self, device, mountPoint, readOnly=False, bindMount=False):
        print "Swap On not implemented"

    def umount(self):
        print "Swap Off not implemented"

    def getUuid(self, devicePath):
        header = open(devicePath, 'r').read(struct.calcsize(self.headerFmt))
        (_version, _last_page, _nr_badpages, uuidBits) = \
                   struct.unpack(self.headerFmt, header)

        return util.uuidBitsToString(uuidBits)

    def formatDevice(self, devicePath=None, progress=None):
        args = [ "/usr/sbin/mkswap", "-v1", devicePath ]

        try:
            util.execWithLog(args[0], args, raiseException=True)
        except Exception, e:
            raise InstallationError(
                "Could not format a linux swap partition.", e)

        workarounds.setSwapUUID(devicePath)

class FATFileSystem(FileSystemType):
    partedFileSystemType = parted.file_system_type_get("fat32")
    partedFileSystemName = "fat32"
    formattable = True
    mountable = True
    maxSizeMB = 1024 * 1024
    name = "vfat"
    vmdkable = False
    supported = True

    def __init__(self):
        FileSystemType.__init__(self)

    def formatDevice(self, entry=None, progress=None, chroot='/'):
        raise RuntimeError, "Fat filesystem creation unimplemented."

        devicePath = "/tmp/foobar"
        args = ["/sbin/mkdosfs", devicePath]

        try:
            util.execWithLog(args[0], args, raiseException=True)
        except Exception, e:
            raise InstallationError(
                "Could not format a DOS partition", e)

class FAT16FileSystem(FATFileSystem):
    partedFileSystemType = parted.file_system_type_get("fat16")
    partedFileSystemName = "fat16"
    maxSizeMB = 2 * 1024 * 1024

class vmkCoreDumpFileSystem(FileSystemType):
    partedFileSystemType = parted.file_system_type_get("vmkcore")
    partedFileSystemName = "vmkcore"
    formattable = False
    checked = False
    vmwarefs = True
    linuxnativefs = True
    maxSizeMB = 100 + 10         # add in a fudge factor
    supported = True
    name = "vmkcore"

    partedPartitionFlags = []
    defaultOptions = "defaults"
    migratetofs = None

    def __init__(self):
        FileSystemType.__init__(self)

    def formatDevice(self, entry, progress=None, chroot='/'):
        pass

class ProcFileSystem(FileSystemType):
    name = "proc"
    def __init__(self):
        FileSystemType.__init__(self, name="proc")

class DevptsFileSystem(FileSystemType):
    name = "devpts"
    def __init__(self):
        FileSystemType.__init__(self, name="devpts")

class SysfsFileSystem(FileSystemType):
    name = "sysfs"
    def __init__(self):
        FileSystemType.__init__(self, name="sysfs")

class cdromFileSystem(FileSystemType):
    '''This is more of a meta-filesystem for cd-rom formats and is used for
    generating the fstab.  The individual formats should be broken up into
    separate classes.'''
    name = "udf,iso9660"
    defaultOptions = "noauto,owner,kudzu,ro"
    def __init__(self):
        FileSystemType.__init__(self, name="udf,iso9660")

class autoFileSystem(FileSystemType):
    name = "auto"
    defaultOptions = "noauto,owner,kudzu"
    def __init__(self):
        FileSystemType.__init__(self, name="auto")


class FileSystemSetEntry:
    def __init__(self, device=None, mountPoint=None, fileSystem=None,
                 format=False, order=-1, fsck=-1):
        self.device = device
        self.mountPoint = mountPoint
        self.fileSystem = fileSystem

        if format and not fileSystem.isFormattable():
            raise RuntimeError, ("File system type %s is not formattable "
                "however it has been flagged to be formatted." % \
                (fileSystem.name,))
        self.format = format
        self.mountCount = 0
        self.options = fileSystem.getDefaultOptions()

        if fsck == -1:
            if fileSystem.isChecked():
                self.fsck = 1
            else:
                self.fsck = 0
        else:
            self.fsck = fsck

        if order == -1:
            if mountPoint == '/':
                self.order = 1
            elif fileSystem.isChecked():
                self.order = 2
            else:
                self.order = 0

    def mount(self, chroot='/', readOnly=0, loopMount=0):
        self.fileSystem.mount(self.device, "%s/%s" % (chroot, self.mountPoint),
            readOnly=readOnly, loopMount=loopMount)
        self.mountCount = self.mountCount + 1

    def umount(self, chroot='/'):
        if self.mountCount > 0:
           self.fileSystem.umount("%s/%s" % (chroot, self.mountPoint))
           self.mountCount = self.mountCount - 1
        else:
           raise RuntimeError, ("Trying to umount %s when there are no "
               "more mount points left to umount." % (self.mountPoint,))

    def setFormat(self, format):
        self.format = format

    def getFormat(self):
        return self.format

    def isMounted(self):
        return self.mountCount > 0


class FileSystemSet:
    def __init__(self, addDefault=True):
        self.entries = []
        if addDefault:
            self.addDefaultEntries()

    def __getitem__(self, key):
        return self.entries[key]

    def __len__(self):
        return len(self.entries)

    def __str__(self):
        format = "%-23s %-23s %-7s %-15s %d %d\n"
        buf = ""

        for entry in self.entries:
            buf += format % (entry.device, entry.mountPoint, 
                entry.fileSystem.name, entry.options, entry.fsck,
                entry.order)

        return buf

    def sort(self, sortByMountPoint=False):
        if sortByMountPoint:
            self.entries.sort(lambda x, y: cmp(x.mountPoint, y.mountPoint))
        else:
            self.entries.sort(lambda x, y: cmp(x.device, y.device))

    def reverse(self):
        self.entries.reverse()

    def addDefaultEntries(self):
        self.addEntry(FileSystemSetEntry(None, '/proc', ProcFileSystem()))
        self.addEntry(FileSystemSetEntry(None, '/dev/pts', DevptsFileSystem()))
        self.addEntry(FileSystemSetEntry(None, '/sys', SysfsFileSystem()))
        self.addEntry(FileSystemSetEntry('/dev/cdrom', '/mnt/cdrom',
                                         cdromFileSystem()))
        self.addEntry(FileSystemSetEntry('/dev/fd0', '/mnt/floppy',
                                         autoFileSystem()))

    def addEntry(self, entry):
        self.entries.append(entry)

    def getEntryByMountPoint(self, mountPoint):
        for entry in self:
            if entry.mountPoint == mountPoint:
                return entry
        return None
        

def getSupportedFileSystems(partedKeys=False):
    fsTable = {}
    for className in globals().keys():
        value = globals()[className]
        if type(value) == types.ClassType and issubclass(value, FileSystemType):
            if value.supported:
                if partedKeys:
                    fsTable[value.partedFileSystemName] = value
                else:
                    fsTable[value.name] = value

    return fsTable

def hostActionMountPseudoFS(_context):
    '''Many executables/packages depend on the /proc filesystem to be present.
    For example, mkinitrd depends on /proc.
    This function creates the /proc, /sys, and /dev directories in the instRoot
    and mounts proc and sysfs.
    '''

    for fsdir in ["/proc", "/sys", "/dev"]:
        path = os.path.join(HOST_ROOT, fsdir.lstrip('/'))
        if not os.path.exists(path):
            os.makedirs(path)
    util.execCommand('/usr/bin/mount -t proc /proc %s/proc' % HOST_ROOT)
    util.execCommand('/usr/bin/mount -t sysfs /sys %s/sys' % HOST_ROOT)

def tidyActionUnmountPseudoFS():
    for fsdir in ["proc", "sys"]:
        path = os.path.join(HOST_ROOT, fsdir)
        if os.path.exists(path):
            util.umount(path)
    
if __name__ == "__main__":
    import doctest
    doctest.testmod()
    
    #fsset = FileSystemSet()
    #fsset.addEntry(FileSystemSetEntry("/", "/", ext3FileSystem(), False))
    #fsset.addEntry(FileSystemSetEntry("/boot", "/boot", ext3FileSystem(), False))
    #y = FileSystemSetEntry("/tmp/foobar", "/tmp/foo", vmfs3FileSystem(), False)
    #y.fileSystem.formatDevice()

    #print fsset
    fstypes = getSupportedFileSystems()

    print fstypes.keys()

