
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

class DialogResponses:
    #
    # Dialog responses not covered by the gtk.RESPONSE_* family.
    #
    BACK           = 1001
    NEXT           = 1002
    CANCEL         = 1003
    FINISH         = 1004
    STAYONSCREEN   = 1005

class ExitCodes:
    '''Exit codes used to signal the weasel script created by vmk-initrd.sh'''
    IMMEDIATELY_REBOOT = 0
    WAIT_THEN_REBOOT = 1
    DO_NOTHING = 2

# HOST_ROOT
# The "host" environment is the system as it will be post-install,
# as opposed to the "install environment".  So the HOST_ROOT is the
# the filesystem that will be located at / ("root") when the host
# environment is running.  But it is /mnt/sysimage/ when the installer
# is running.
HOST_ROOT = '/mnt/sysimage/'

VMDK_MINSIZE = 2500

# Label for the root partition.  Useful for cases where using the UUID would be
# inconvenient, see pr 230869.
ESX_ROOT_LABEL = 'esx-root'

CDROM_DEVICE_PATH = '/dev/cdrom'
MEDIA_DEVICE_MOUNT_POINT = '/mnt/source'

# XXX Need to handle different upgrade versions.
ESX3_INSTALLATION = "/esx3-installation"

HV_DISABLED_TEXT = \
"""This host has VT (Virtualization Technology) support, however
VT has not been enabled.   VT will increase the performance of
virtual machines.

To enable VT, verify the BIOS/firmware settings.  You may need
to update the BIOS/firmware to the latest version.
"""

