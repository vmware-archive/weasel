#!/usr/bin/env python
#-*- coding: utf-8 -*-

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

'''Installation
'''

import re, textwrap

import applychoices
import userchoices
import customdrivers

from log import log, stdoutHandler, LOGLEVEL_HUMAN

from textrunner import TextRunner

title = "Installation"

installingText = """\
Please wait while the installation wizard installs ESX.
This may take a few minutes.

"""

errContinueCancel = "\n 1) Continue\n !) Cancel\n\n"

_THROTTLE = True        # throttle down for human-readable content

def refmt(textin):
    """Text reformatter."""
    splitter = re.compile(r"[\r\n]*")
    textout = []
    for fragment in splitter.split(textin):
        if fragment:
            textout += textwrap.wrap(fragment, 75)
        else:
            textout.append('')  # retain blank line spacing
    return '\n'.join(textout)


class InstallationWindow(TextRunner):
    """Load and install RPMs.
    """

    def __init__(self):
        super(InstallationWindow, self).__init__()
        self.context = applychoices.Context(
            applychoices.ProgressCallback(
                applychoices.StdoutProgressDelegate()))
        self.substep = self.apply

    def apply(self):
        "Apply choices using default 'install' step list"
        previousLevel = stdoutHandler.level
        if _THROTTLE:
            stdoutHandler.setLevel(LOGLEVEL_HUMAN)
        applychoices.doit(self.context)
        stdoutHandler.setLevel(previousLevel)

        self.setSubstepEnv( {'next':self.stepForward} )

    def apply2(self, stepListType):
        "Apply choices using variant step list"
        previousLevel = stdoutHandler.level
        if _THROTTLE:
            stdoutHandler.setLevel(LOGLEVEL_HUMAN)
        applychoices.doit(self.context, stepListType)
        stdoutHandler.setLevel(previousLevel)

        self.setSubstepEnv( {'next':self.stepForward} )

    def applyDrivers(self):
        "Apply choices using 'loadDrivers' step list"
        previousLevel = stdoutHandler.level
        if _THROTTLE:
            stdoutHandler.setLevel(LOGLEVEL_HUMAN)
        try:
            applychoices.doit(self.context, stepListType="loadDrivers")
        except customdrivers.ScriptLoadError, msg:
            ui = {
                'title': "Non-critical Script Loading Failures",
                'body':  "%s\n%s" % ( refmt(msg[0]), errContinueCancel),
                'menu': {
                    '1': self.continueForward,
                    '!': self.cancel,
                }
            }
            self.setSubstepEnv(ui)
            return

        stdoutHandler.setLevel(previousLevel)
        self._removeCustomDriversSteps()

        self.setSubstepEnv( {'next':self.stepForward} )

    def continueForward(self):
        self._removeCustomDriversSteps()
        self.stepForward()

    def _removeCustomDriversSteps(self):
        self.dispatch.remove('customdrivers')
        self.dispatch.remove('driverload')
        # XXX Need to go back twice since we removed two screens and the
        # index in the dispatcher wasn't updated.
        self.dispatch.goBack()
        self.dispatch.goBack()

        

# Special cases of InstallationWindow
# ... right now, only one.
def DriverLoadWindow():
    "load custom drivers"
    iw = InstallationWindow()
    iw.substep = iw.applyDrivers
    return iw

# vim: set sw=4 tw=80 :
