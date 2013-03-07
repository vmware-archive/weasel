
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
import glob

import util
import media
import devices

from log import log

USB_MEDIA_PATH = "/mnt/usbmedia"

def _tryDevice(disk, part):
    devicePath = part.consoleDevicePath
    
    log.info("looking for installation data on %s" % devicePath)

    # Either the USB storage is the media itself or it might contain an ISO file
    # that is the installation media.
    usbDesc = media.MediaDescriptor(disk.name, devicePath, part.getFsTypeName())
    if usbDesc.probeForPackages():
        log.info("  found installation media...")
        return [usbDesc]
    
    # Be explicit about fsTypeName since long file names work if we mount it as
    # "vfat", but not when the auto-detection thinks it's "msdos".
    if util.mount(devicePath,
                  USB_MEDIA_PATH,
                  fsTypeName=part.getFsTypeName()) != 0:
        return []

    retval = []
    for iso in glob.glob(os.path.join(USB_MEDIA_PATH, "*.iso")):
        isoDesc = media.MediaDescriptor(
            disk.name,
            devicePath, part.getFsTypeName(),
            os.path.basename(iso))
        if isoDesc.probeForPackages():
            log.info("  found iso, %s, with installation media..." % iso)
            retval.append(isoDesc)

    util.umount(USB_MEDIA_PATH)
    
    return retval

def findUSBMedia(showAll=False):
    """Scan attached USB devices for installation media.

    If showAll is True, all CD devices are returned even if they do not contain
    any installation media.
    """
    
    diskSet = devices.DiskSet(forceReprobe=True)

    retval = []
    
    util.umount(USB_MEDIA_PATH)
    for disk in diskSet.values():
        if disk.driverName != devices.DiskDev.DRIVER_USB_STORAGE:
            log.debug("skipping non-usb device -- %s" % disk.name)
            continue

        diskMedia = []
        for part in disk.partitions:
            if not part.consoleDevicePath:
                continue
            
            diskMedia += _tryDevice(disk, part)

        if not diskMedia and showAll:
            # No installation media was found on the device, but the caller
            # wants the list of potential media devices, so add that in.
            diskMedia = [media.MediaDescriptor(disk.name)]
            
        retval += diskMedia

    return retval
