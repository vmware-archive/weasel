
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

'''
Scripted User Interface
'''
import sys
import logging
import exception
import readline # needed for raw_input to work on tty6

import media
import networking
import applychoices
import userchoices
from consts import ExitCodes
from log import log, formatterForHuman, LOGLEVEL_HUMAN

tty6Handler = None

class MountMediaDelegate:
    def mountMediaNoDrive(self):
        raw_input("error: The CD drive was not detected on boot up and "
                  "you have selected CD-based installation.\n"
                  "Press <enter> to reboot...")
        
    def mountMediaNoPackages(self):
        raw_input("Insert the ESX Installation media.\n"
                  "Press <enter> when ready...")
        
media.MOUNT_MEDIA_DELEGATE = MountMediaDelegate()

class Scui:
    '''Class used to do a scripted install.'''

    def __init__(self, script):
        # Setup error handling stuff first so any errors during driver loading
        # or the main bits gets handled correctly.
        
        global tty6Handler

        sys.excepthook = lambda type, value, tb: \
                         exception.handleException(self, (type, value, tb),
                                                   traceInDetails=False)
        
        try:
            # The scui uses logging to write out user-visible output so we need
            # another logger for tty6 (which stdout is redirected to by
            # weasel.py).
            tty6Handler = logging.StreamHandler(sys.stdout)
            tty6Handler.setFormatter(formatterForHuman)
            tty6Handler.setLevel(LOGLEVEL_HUMAN)
            log.addHandler(tty6Handler)
        except IOError:
            #Could not open for writing.  Probably not the root user
            pass
        
        self._execute(script)

    @applychoices.ensureDriversAreLoaded
    def _execute(self, script):
        from preparser import ScriptedInstallPreparser
        from scriptedinstallutil import Result

        errors = None
        installCompleted = False

        try:
            self.sip = ScriptedInstallPreparser(script)

            (result, errors, warnings) = self.sip.parseAndValidate()
            if warnings:
                log.warn("\n".join(warnings))
            if errors:
                log.error("\n".join(errors))
                userchoices.setReboot(False)
            if result != Result.FAIL:
                # Bring up whatever is needed for the install to happen.  For
                # example, get the network going for non-local installs.
                errors, warnings = self._runtimeActions()

                if warnings:
                    log.warn("\n".join(warnings))
                if errors:
                    log.error("\n".join(errors))
                    userchoices.setReboot(False)
                
                if not errors:
                    if userchoices.getDebug():
                        log.info(userchoices.dumpToString())

                    if userchoices.getDryrun():
                        log.log(LOGLEVEL_HUMAN, "dry run specified, stopping.")
                    else:
                        context = applychoices.Context(
                            applychoices.ProgressCallback(
                                applychoices.StdoutProgressDelegate()))
                        applychoices.doit(context)
                        installCompleted = True

                media.runtimeActionEjectMedia()
        except IOError, e:
            log.error("error: cannot open file -- %s\n" % str(e))

        if not installCompleted:
            log.error("installation aborted")
        
        if not installCompleted or not userchoices.getReboot():
            msg = "Press <enter> to reboot..."
            if userchoices.getUpgrade():
                msg = "The machine will reboot automatically or\n" \
                    "press <enter> to reboot immediately..."
            raw_input(msg)

    def exceptionWindow(self, desc, details):
        log.error("") # Just a separator from the other output.
        if details:
            log.error(details)
        log.error(desc)
        log.error("See /var/log/esx_install.log for more information.")

        raw_input("Press <enter> to reboot...")

        sys.exit(ExitCodes.IMMEDIATELY_REBOOT)

    def _runtimeActions(self):
        errors = []
        warnings = []

        if userchoices.getActivateNetwork() and userchoices.getCosNICs() and \
           not networking.connected() and not userchoices.getUpgrade():
            try:
                networking.cosConnectForInstaller()
            except Exception, ex:
                log.exception(str(ex))
                warnings.append("warning: could not bring up network -- %s\n" %
                                str(ex))

        return (errors, warnings)
