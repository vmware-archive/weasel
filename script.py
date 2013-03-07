
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
import time
import signal
import userchoices

from log import log, LOGLEVEL_HUMAN
from consts import HOST_ROOT, ExitCodes
from exception import InstallationError

class Script:
    def __init__(self, script, interp, inChroot, timeoutInSecs, ignoreFailure):
        self.script = script
        self.interp = interp
        self.inChroot = inChroot
        self.timeoutInSecs = timeoutInSecs
        self.ignoreFailure = ignoreFailure

    def run(self, chroot="/"):
        path = "tmp/ks-script"

        openPath = os.path.join(chroot, path)
        if self.inChroot:
            execPath = os.path.join('/', path)
        else:
            execPath = openPath
        
        f = open(openPath, "w")
        f.write(self.script)
        f.close()
        os.chmod(openPath, 0700)

        cmd = [self.interp, execPath]

        if self.inChroot:
            execRoot = chroot
        else:
            execRoot = '/'

        try:
            rc = util.execWithLog(cmd[0], cmd,
                                  level=LOGLEVEL_HUMAN,
                                  root=execRoot,
                                  timeoutInSecs=self.timeoutInSecs,
                                  raiseException=(not self.ignoreFailure))
        except Exception, e:
            raise InstallationError("User-supplied script failed.", e)
        
        os.unlink(openPath)
        return rc

    def __eq__(self, rhs):
        return (self.script == rhs.script and
                self.interp == rhs.interp and
                self.inChroot == rhs.inChroot and
                self.timeoutInSecs == rhs.timeoutInSecs and
                self.ignoreFailure == rhs.ignoreFailure)

    def __repr__(self):
        return repr(self.__dict__)


def hostActionPostScript(context):
    postScripts = userchoices.getPostScripts()
    if not postScripts:
        return

    # Setup /dev in the installed system.
    # XXX There still might be a few other things in rc.sysinit we'll need to
    # do.
    util.execCommand('/sbin/start_udev', root=HOST_ROOT)

    for postScript in postScripts:
        postScript['script'].run(HOST_ROOT)

def tidyAction():
    # Kill the udevd process since it has files open in the installed system.
    args = ["/mnt/sysimage/sbin/pidof", "-x", "udevd"]
    if os.path.exists(args[0]):
        out = util.execWithCapture(args[0], args)
        try:
            pid = int(out)
            os.kill(pid, signal.SIGTERM)
            time.sleep(1)
        except ValueError:
            # not running
            pass
        except OSError:
            # kill failed, oh well...
            pass

