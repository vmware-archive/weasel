
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

import getopt
import sys
import os
import util
import traceback
import logging
import timedate

import vmkctl

import tidy
import exception
import userchoices
from log import log, stdoutHandler
from consts import ExitCodes, MEDIA_DEVICE_MOUNT_POINT
from boot_cmdline import translateBootCmdLine

sys.path.append("scriptedinstall")

def dumpExceptionInfo(ex):
    log.debug('An exceptional situation was encountered.'
              ' Weasel does not know how to handle this.'
              ' Terminating.')
    log.debug('The class of the exception was: %s' % str(ex.__class__))
    log.debug('The exception was: %s' % str(ex))
    log.debug('Dumping userchoices')
    log.debug(userchoices.dumpToString())
    log.debug('\n************* UNHANDLED WEASEL EXCEPTION **************')
    log.debug(traceback.format_exc())
    log.debug('**************************************************\n')

def parseArgsToUserChoices(argv):
    try:
        (opts, _args) = getopt.getopt(argv[1:], "htds:p:",
                          ['help', 'text', 'debug', 'nox', 'askmedia',
                           'noeject', 'mediacheck', 'script=', 'url=',
                           'debugpatch=', 'videodriver='])
    except getopt.error, e:
        sys.stderr.write("error: %s\n" % str(e))
        sys.exit(ExitCodes.WAIT_THEN_REBOOT)

    # replace the default exception hook with a friendlier one.  This
    # is just for parsing the boot cmdline, as GUI, Text, and Scripted
    # install methods will replace the sys.excepthook with their own
    sys.excepthook = lambda type, value, tb: \
            exception.handleException(None, (type, value, tb),
                                      traceInDetails=False)

    # To make testing easier, pull from environment first.
    # It's either in $BOOT_CMDLINE or the /proc/cmdline file
    cmdlineFile = open('/proc/cmdline', 'r')
    bootCmdLine = os.environ.get('BOOT_CMDLINE', cmdlineFile.read())
    opts.extend(translateBootCmdLine(bootCmdLine))

    log.debug('command line options: %s' % str(opts))

    for opt, arg in opts:
        if (opt == '-t' or opt == '--text'):
            userchoices.setRunMode(userchoices.RUNMODE_TEXT)
        elif (opt == '-d' or opt == '--debug'):
            userchoices.setDebug(True)
        elif (opt == '--nox'):
            userchoices.setStartX(False)
        elif (opt == '-s' or opt == '--script'):
            userchoices.setRunMode(userchoices.RUNMODE_SCRIPTED)
            userchoices.setRootScriptLocation(arg)
        elif (opt == '--url'):
            userchoices.setMediaLocation(arg)
        elif (opt == '--debugpatch'):
            userchoices.setDebugPatchLocation(arg)
        elif (opt == '--askmedia'):
            userchoices.setShowInstallMethod(True)
        elif (opt == '--noeject'):
            userchoices.setNoEject(True)
        elif (opt == '--mediacheck'):
            userchoices.setMediaCheck(True)
        elif (opt == '--videodriver'):
            userchoices.setVideoDriver(arg)
        elif (opt == '--serial'):
            userchoices.setWeaselTTY('/dev/console')
            

def main(argv):
    try:
        timedate.checkActionSaneTimedate()
    
        parseArgsToUserChoices(argv)

        if userchoices.getDebug():
            # Only import debugging if specified 
            # We want to ensure that the debugging module has minimal impact
            # because debug mode is not a supported installation method
            import debugging
            debugging.init()
            patchLocChoice = userchoices.getDebugPatchLocation()
            if patchLocChoice:
                log.info('using the super-secret live install patching')
                patchLoc = patchLocChoice['debugPatchLocation']
                debugging.livePatch(patchLoc)

        if userchoices.getShowInstallMethod():
            # User wants to select the media themselves.  So, we unmount the
            # media set up by the init scripts since the UI will remount it
            # later.
            util.umount(MEDIA_DEVICE_MOUNT_POINT)
        
        runModeChoice = userchoices.getRunMode()

        # if we didn't boot via CD, make sure we prompt for the media
        if runModeChoice != userchoices.RUNMODE_SCRIPTED and \
           not os.path.exists(
              os.path.join(MEDIA_DEVICE_MOUNT_POINT, 'packages.xml')) and \
           not userchoices.getMediaLocation():
            userchoices.setShowInstallMethod(True)

        if not runModeChoice:
            log.warn("User has not chosen a Weasel run mode.")
            log.info("Weasel run mode defaulting to GUI.")
            runMode = userchoices.RUNMODE_GUI
        else:
            runMode = runModeChoice['runMode']

        if runMode != userchoices.RUNMODE_GUI:
            switchTty()

        stdoutHandler.setLevel(logging.DEBUG)
        if runMode == userchoices.RUNMODE_GUI:
            startGui = True

            if userchoices.getStartX():
                import startx
                startGui = startx.startX(userchoices.getVideoDriver())

            if startGui:
                try:
                    import gui
                    gui.Gui()
                except RuntimeError, msg:
                    # gtk looks like it's having problems
                    import pciidlib
                    devs = pciidlib.PciDeviceSet()
                    devs.scanSystem(pciidlib.PCI_CLASS_VIDEO)

                    if len(devs) < 1:
                        log.warn("Didn't find a video chipset")
                    else:
                        log.warn("X failed for chipset %s" % 
                            devs.keys()[0])
                    startGui = False

            if not startGui:
                switchTty()

                from textui.main import TextUI
                t = TextUI([])
                t.run()

        elif runMode == userchoices.RUNMODE_TEXT:
            from textui.main import TextUI

            t = TextUI([])
            t.run()

        elif runMode == userchoices.RUNMODE_SCRIPTED:
            import scui
            locDict = userchoices.getRootScriptLocation()
            if not locDict:
                log.error('Script location has not been set.')
            s = scui.Scui(locDict['rootScriptLocation'])

        else:
            log.error("Weasel run mode set to invalid value (%s)" % runMode)

    except SystemExit:
        raise # pass it on
    except (vmkctl.HostCtlException, Exception), ex:
        dumpExceptionInfo(ex)
        log.error("installation aborted")
        raise

    try:
        tidy.doit() # Always cleanup our mess.
    except Exception, ex:
        log.debug('An non-fatal exception was encountered while cleaning up')
        log.debug(traceback.format_exc())

    if userchoices.getDebug():
        sys.exit(ExitCodes.DO_NOTHING)

    return 0

def switchTty():
    try:
        ttyName = userchoices.getWeaselTTY()
        if not ttyName:
            ttyName = "/dev/tty6"
            os.system("chvt 6")
        tty = open(ttyName, "r+")
        sys.stdin = tty
        sys.stdout = tty
        tty.write("\033[H\033[J");
    except IOError:
        pass


if __name__ == "__main__":
    sys.exit(main(sys.argv))
