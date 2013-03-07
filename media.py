
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
import sys
import util
import devices
import packages
import userchoices

from log import log
from consts import MEDIA_DEVICE_MOUNT_POINT, CDROM_DEVICE_PATH, ExitCodes
from customdrivers import INIT_WRAPPER

from util import execCommand
import brandiso

MEDIA_PATH = "/mnt/media"
MOUNT_MEDIA_DELEGATE = None
CDROM_MOUNT_SCRIPT = "11.85.mount-cdrom"
MEDIA_CHECKED = False

class MediaDescriptor:
    def __init__(self, diskName=None, partPath=None, partFsName=None,
                 isoPath=None):
        self.diskName = diskName
        self.partPath = partPath
        self.partFsName = partFsName
        self.isoPath = isoPath
        self.version = '(no install media found)'
        self.hasPackages = False
        self.isMounted = False

    def _mountMediaAsTheDepot(self):
        if util.mount(self.partPath,
                      MEDIA_DEVICE_MOUNT_POINT,
                      loopMount=self.partPath.endswith(".iso"),
                      fsTypeName=self.partFsName) != 0:
            raise Exception("Could not mount media device -- %s" %
                            self.partPath)
        self.isMounted = True

    def mount(self):
        if self.isMounted:
            return
        
        if not self.isoPath:
            # The disk itself is the install media.
            self._mountMediaAsTheDepot()
            return
        
        # The disk contains an ISO that is the media.
        if self.partPath and util.mount(self.partPath,
                                        MEDIA_PATH,
                                        fsTypeName=self.partFsName) != 0:
            raise Exception("could not mount partition containing ISO -- %s" %
                            self.partPath)
        
        if os.path.isabs(self.isoPath):
            absIsoPath = self.isoPath
        else:
            absIsoPath = os.path.join(MEDIA_PATH, self.isoPath)
        if util.mount(absIsoPath,
                      MEDIA_DEVICE_MOUNT_POINT,
                      loopMount=self.isoPath.endswith(".iso"),
                      # Be explicit with the mount type in case the file name
                      # has a colon in it, which might make mount think it is an
                      # nfs mount.  See bug 249366.
                      fsTypeName="iso9660") != 0:
            raise Exception("could not mount ISO -- %s" % self.isoPath)

        self.isMounted = True

    def umount(self):
        if not self.isMounted:
            return
        
        util.umount(MEDIA_DEVICE_MOUNT_POINT)
        
        if self.partPath:
            util.umount(MEDIA_PATH)

        self.isMounted = False

    def eject(self):
        retval = True
        if self.partPath and self.partPath.startswith("/dev/"):
            retval = (os.system("/usr/bin/eject %s" % self.partPath) == 0)

        return retval

    def probeForPackages(self):
        """Probe the media for the installation packages, if the packages are
        found the version field will be filled out and True is returned.
        """
        retval = False
        
        try:
            self.mount()
            try:
                packagesPath = os.path.join(
                    MEDIA_DEVICE_MOUNT_POINT, "packages.xml")
                xml = packages.PackagesXML(None, fullPath=packagesPath)
                self.version = "%s %s (%s)" % (
                    xml.name, xml.esxVersion, xml.release)
                retval = True
            finally:
                self.umount()
        except Exception, e:
            log.exception("could not read packages.xml")

        self.hasPackages = retval
        
        return retval
        
    def getName(self):
        """Get a descriptive name for this installation media."""
        
        if self.diskName:
            diskSet = devices.DiskSet()
            return diskSet[self.diskName].getVendorModelString()
        else:
            return self.partPath

    def __str__(self):
        if self.diskName:
            diskStr = "%s:" % self.diskName
        else:
            diskStr = ""
        if self.isoPath:
            isoStr = os.path.join('/', self.isoPath)
        else:
            isoStr = ""
        return "%s%s(%s)%s version %s" % (
            diskStr,
            self.partPath,
            self.partFsName,
            isoStr,
            self.version)
        
# The default descriptor represents the cd found by the init scripts.
DEFAULT_MEDIA = MediaDescriptor(partPath=CDROM_DEVICE_PATH,
                                partFsName="iso9660")

def isInstallMediaMounted():
    return os.path.exists(os.path.join(MEDIA_DEVICE_MOUNT_POINT,
                                       'packages.xml'))

def runtimeActionMountMedia(uiDelegate=None):
    """Mounts the installation media."""

    if not uiDelegate:
        uiDelegate = MOUNT_MEDIA_DELEGATE

    log.info("attempting to mount install media")

    if userchoices.getMediaLocation():
        log.info("  remote media in use, nothing to mount...")
        return

    while True:
        media = userchoices.getMediaDescriptor()

        if not media:
            # Check for the default media setup by the init scripts.
            media = DEFAULT_MEDIA
            media.isMounted = isInstallMediaMounted()
            if not os.path.exists(media.partPath):
                # attempt to remount the cd-rom since it may have been a SCSI
                # CD-ROM drive
                rc, stdout, stderr = \
                    execCommand("cd / && INSTALLER=1 %s %s" % (INIT_WRAPPER,
                                CDROM_MOUNT_SCRIPT))
                if rc:
                    log.critical("%s was not created" % media.partPath)
                    uiDelegate.mountMediaNoDrive()
                    sys.exit(ExitCodes.IMMEDIATELY_REBOOT)
                else:
                    media.isMounted = True

        # Make sure the media is mounted up.
        try:
            media.mount()
            if isInstallMediaMounted():
                return
            media.umount()
        except Exception, e:
            log.error(str(e))
        media.eject()
        uiDelegate.mountMediaNoPackages()

def runtimeActionUnmountMedia():
    if userchoices.getMediaLocation():
        return
    
    media = userchoices.getMediaDescriptor() or DEFAULT_MEDIA
    media.umount()

def runtimeActionEjectMedia():
    if userchoices.getMediaLocation():
        # Non-CD install, don't bother.
        return
    
    if userchoices.getNoEject():
        return

    media = userchoices.getMediaDescriptor() or DEFAULT_MEDIA
    return media.eject()

def needsToBeChecked():
    return (not MEDIA_CHECKED and userchoices.getMediaCheck())

def runtimeActionMediaCheck(uiDelegate=None):
    global MEDIA_CHECKED
    
    log.info("checking the MD5 of the installation media")

    if not uiDelegate:
        uiDelegate = MOUNT_MEDIA_DELEGATE

    media = userchoices.getMediaDescriptor() or DEFAULT_MEDIA

    def verify():
        try:
            d1, d2, _id = brandiso.extract_iso_checksums(media.partPath)
            return d1 == d2
        except brandiso.BrandISOException, inst:
            log.warn(inst)
            return None
        except IOError, e:
            log.warn(e)
            return None

    if isInstallMediaMounted():
        runtimeActionUnmountMedia()
        retval = verify()
        runtimeActionMountMedia()
    else:
        retval = verify()

    if not retval:
        uiDelegate.mountMediaCheckFailed()
        sys.exit(ExitCodes.IMMEDIATELY_REBOOT)
    else:
        uiDelegate.mountMediaCheckSuccess()

    MEDIA_CHECKED = True

    return retval

