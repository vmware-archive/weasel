
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

import userchoices
import util
import cdutil
from log import log
from time import sleep
from consts import MEDIA_DEVICE_MOUNT_POINT

def _tidySteps():
    import firewall
    import script
    import boot_cmdline
    import fsset
    import partition
    import remote_files
    import media
    from log import tidyActionCloseLog

    retval = [
        ('turn off firewall', firewall.tidyAction),
        ('turn off udevd', script.tidyAction),
        ('boot cmdline', boot_cmdline.tidyAction),
        ('umount remote-media nfs mounts', remote_files.tidyAction),
        ('umount pseudo file systems', fsset.tidyActionUnmountPseudoFS),
        ('close out log file', tidyActionCloseLog),
        ('umount file systems', partition.tidyActionUnmount),
        ('umount media', media.runtimeActionUnmountMedia),
        ('eject cdrom', media.runtimeActionEjectMedia),
        ]
    
    return retval

def doit():
    steps = _tidySteps()
    
    for desc, step in steps:
        try:
            log.debug("tidying: %s" % desc)
            step()
        except:
            # This is best effort, just log the exception.
            log.exception("non-fatal exception while tidying: %s" % desc)

