
###############################################################################
# Copyright (c) 2008-2009 VMware, Inc.
#
# This file is part of Weasel.
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
import sys
import traceback
import os
import signal
import util

DEBUG = False

class InstallationError(Exception):
    def __init__(self, actionMsg, innerException=None):
        Exception.__init__(self, str(innerException))

        self.actionMsg = actionMsg
        self.innerException = innerException
        if innerException:
            self.innerTrace = sys.exc_traceback

def handleException(installMethod, (exceptType, value, trace),
                    traceInDetails=True):

    sys.excepthook = sys.__excepthook__

    details = ''
    if exceptType == InstallationError:
        desc = value.actionMsg

        if value.innerException:
            exceptType = type(value.innerException)
            trace = value.innerTrace
            value = value.innerException
    else:
        desc = str(value)

    if hasattr(value, "getDetails"):
        details = value.getDetails()
    if traceInDetails:
        details += "\n" + string.join(traceback.format_exception(
                exceptType, value, trace, 50))

    if hasattr(installMethod, "exceptionWindow"):
        if installMethod.exceptionWindow(desc, details):
            return

        # change to the text terminal
        os.system("chvt 1")

    print "Weasel Exception\n\n" + details

    # clean up ui
    if hasattr(installMethod, "__del__"):
        installMethod.__del__()

    if DEBUG:
        f = open("/tmp/weasel.dump", "w")
        f.write(trace)
        f.close()

    import pdb
    pdb.pm()
    #pdb.post_mortem(trace)

    os.kill(os.getpid(), signal.SIGKILL)

class StayOnScreen(Exception):
    def __init__(self):
        self.args = ()

class InstallCancelled(Exception):
    pass
