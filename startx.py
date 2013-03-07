
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

#import xsetup
import rhpl.keyboard as keyboard
import time
import sys
import util

from consts import ExitCodes
from log import log

import pciidlib

# Not only are we going to set the resolution to RUNRES, we're also going to
# force the refresh rate to REFRESH.
RUNRES = '800x600'
REFRESH = '60'

miniwm_pid = None

skelConfig = """\
Section "ServerLayout"
    Identifier  "Weasel"
    Screen      0 "Screen0" 0 0
EndSection

Section "Device"
    Identifier  "Card0"
    Driver      "%(driver)s"
EndSection

Section "Screen"
    Identifier  "Screen0"
    Device      "Card0"
    SubSection  "Display"
        Modes   "%(res)s"
    EndSubSection
EndSection\
"""

BAD_CARDS = {
    '0x102b 0x0530' : 'vesa',  # matrox loads incorrectly on local console
    '0x102b 0x0532' : 'vesa',  # matrox loads incorrectly on local console
}

def startX(videoDriver=''):
    pciDevices = pciidlib.PciDeviceSet(scanSystem=True)

    if not videoDriver:
        for card in BAD_CARDS.keys():
            if card in pciDevices.devices:
                videoDriver = BAD_CARDS[card]
                break

    try:
        startServer(videoDriver)
    except (OSError, RuntimeError), msg:
        if videoDriver == 'vesa':
            log.warn("Couldn't start Graphical UI;  trying text mode.")
            return False

        try:
            log.warn("Couldn't start Graphical UI;  trying vesa driver.")
            startServer('vesa')
        except (OSError, RuntimeError), msg:
            log.warn("Couldn't start Graphical UI;  trying text mode.")
            return False

    return True


def startServer(videoDriver=''):
    Xargs = ["Xorg", "-br", "-logfile", "/tmp/X.log", ":1", "vt6", "-s", "1440",
            "-ac", "-nolisten", "tcp", "-dpi", "96"]

    if videoDriver:
        xConfig = open("/tmp/xorg.conf", "w")
        xConfig.write(skelConfig % {'driver': videoDriver, 'res': RUNRES })
        xConfig.close()
        Xargs.extend(["-config", xConfig.name])

    # Careful when debugging around here.. If an OSError pops up, be sure that
    # it gets set back to its previous handler before going any further.
    try:
        try:
            import signal
            import subprocess

            def sigchld_handler(num, frame):
                raise OSError

            def sigusr1_handler(num, frame):
                pass

            def preexec_fn():
                signal.signal(signal.SIGUSR1, signal.SIG_IGN)

            old_sigusr1 = signal.signal(signal.SIGUSR1, sigusr1_handler)
            old_sigchld = signal.signal(signal.SIGCHLD, sigchld_handler)
            xout = open("/dev/tty5", "w")

            proc = subprocess.Popen(Xargs, close_fds=True, stdout=xout, stderr=xout,
                                    preexec_fn=preexec_fn)

            time.sleep(3)

            os.environ["DISPLAY"] = ":1"

            doStartupX11Actions()
        except ImportError, e:
            log.error("Problems importing: %s." % str(e))
        except RuntimeError:
            log.warn("Starting X failed")
            pass
    finally:
        signal.signal(signal.SIGUSR1, old_sigusr1)
        signal.signal(signal.SIGCHLD, old_sigchld)


def startMiniWM(root='/'):
    (rd, wr) = os.pipe()
    childpid = os.fork()
    if not childpid:
        if os.access("./mini-wm", os.X_OK):
            cmd = "./mini-wm"
        elif os.access(root + "/usr/bin/mini-wm", os.X_OK):
            cmd = root + "/usr/bin/mini-wm"
        else:
            return None

        os.dup2(wr, 1)
        os.close(wr)

        args = [cmd, '--display', ':1']
        os.execv(args[0], args)
        sys.exit(ExitCodes.WAIT_THEN_REBOOT)
    else:
        # We need to make sure that mini-wm is the first client to
        # connect to the X server (see bug #108777).  Wait for mini-wm
        # to write back an acknowledge token.
        os.read(rd, 1)

    log.info("We've started miniWM with PID %s" % childpid)
    return childpid


def doStartupX11Actions():
    global miniwm_pid

    f = open("/tmp/mylog", "w")

    # now start up mini-wm
    try:
        miniwm_pid = startMiniWM()
        print "Started mini-wm"
        f.write(" * Started mini-wm\n")
        f.write("miniwm_pid=%s\n" % (miniwm_pid))
    except:
        miniwm_pid = None
        print "Unable to start mini-wm"


    # test to setup dpi
    # cant do this if miniwm didnt run because otherwise when
    # we open and close an X connection in the xutils calls
    # the X server will exit since this is the first X
    # connection (if miniwm isnt running)

    if miniwm_pid is not None:
        # try to start up xrandr
        try:
            argv = ["/usr/bin/xrandr", "-s", RUNRES, "-r", REFRESH]
            util.execWithRedirect(argv[0], argv, searchPath=1,
                                  stdout="/dev/tty5", stderr="/dev/tty5")
        # We expect an OSError at this point, the child completed successfully.
        except OSError, e:
            if str(e):
                log.error("Exception when running xrandr: %s" % str(e))
            else:
                pass
        except Exception, e:
            log.error("Exception when running xrandr: %s" % str(e))

        import xutils

        f.write("imported xutils\n")
        f.close()

        try:
            if xutils.screenWidth() > 640:
                dpi = "96"
            else:
                dpi = "75"

            xutils.setRootResource('Xcursor.size', '24')
            xutils.setRootResource('Xft.antialias', '1')
            xutils.setRootResource('Xft.dpi', dpi)
            xutils.setRootResource('Xft.hinting', '1')
            xutils.setRootResource('Xft.hintstyle', 'hintslight')
        except:
            sys.stderr.write("X SERVER STARTED, THEN FAILED");
            raise RuntimeError, "X server failed to start"


def doShutdownX11Actions():
    global miniwm_pid

    if miniwm_pid is not None:
        try:
            os.kill(miniwm_pid, 15)
            os.waitpid(miniwm_pid, 0)
        except:
            pass


if __name__ == "__main__":
    startX()
