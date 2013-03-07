'''Utility functions for CD install.'''

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

# TODO: Rename file to cdmedia.py

import os
import media
import util
from log import log
from consts import CDROM_DEVICE_PATH

def cdromDevicePaths():
    try:
        for line in open("/proc/sys/dev/cdrom/info"):
            if line.startswith("drive name:"):
                _key, value = line.split(':', 1)
                return [("/dev/%s" % devName) for devName in value.split()]
    except IOError, e:
        log.exception("cannot get list of cd-rom devices")
        
    return []

def findCdMedia(showAll=False):
    """Scan the cd-rom drives for installation media.

    If showAll is True, all CD devices are returned even if they do not contain
    any installation media.
    """
    
    retval = []
    for devicePath in cdromDevicePaths():
        cdDesc = media.MediaDescriptor(
            partPath=devicePath, partFsName="iso9660")
        if cdDesc.probeForPackages() or showAll:
            retval.append(cdDesc)

    return retval

def ejectCdrom():
    if not os.path.exists(CDROM_DEVICE_PATH):
        # The drive is empty.
        return

    cmd = ["/usr/bin/eject"]
    util.execWithCapture(cmd[0], cmd, timeoutInSecs=10)
