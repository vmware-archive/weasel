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

'''bootloader
'''

import getpass
import userchoices
import bootloader
from log import log
import textengine
from textrunner import TextRunner, SubstepTransitionMenu as TransMenu

title = "Bootloader Options"

askWantKernelParamsText = """\
Do you want to specify kernel arguments for the GRUB bootloader?
"""

installLocText = """\
Where do you want to install GRUB?  (Select 1 (Master Boot Record)
if you are unsure.)

 1) Master Boot Record
 2) First partition of the disk
 <) Back
 ?) Help

"""

kernelArgsText = """\
Specify any kernel arguments for the GRUB bootloader

Kernel Arguments:
"""

askWantBootPasswordText = """\
Do you want to provide a bootloader password for your system?
"""

passwordText = """\
Set the bootloader password (or enter '<' to go back).
"""

helpText = """\
Kernel arguments are appended to the GRUB bootloader command line when
ESX is booted.

You can provide a GRUB password so that the computer can only be booted
when the password is provided.
"""

errNotMatch = "The two passwords entered do not match."

# TODO:  when going backwards, user should see options already entered.
# check local stuff and userchoices.
# This is potentially a bug.

class BootloaderWindow(TextRunner):
    def __init__(self, fname=None):
        super(BootloaderWindow, self).__init__()

        self.kernelParams = None
        self.location = None
        self.password = None

        self.start = self.askWantKernelParams
        self.substep = self.start


    def askWantKernelParams(self):
        """Ask if the user wants to set kernel arguments."""
        ui = {
            'title': title,
            'body': askWantKernelParamsText + TransMenu.YesNoBackHelp,
            'menu': {
                '1': self.enterKernelParams,
                '2': self.askWantBootPassword,
                '<': self.stepBack,
                '?': self.help,
            }
        }
        self.setSubstepEnv(ui)


    def enterKernelParams(self):
        """Ask for kernel boot parmeters."""
        ui = {
            'title': title,
            'body': kernelArgsText,
            'menu': {
                '?': self.help,
                '<': self.start,
                '*': self.saveKernelParams,
            }
        }
        self.setSubstepEnv(ui)

    def saveKernelParams(self):
        """Save kernel boot parameters."""
        self.kernelParams = self.userinput.strip()
        self.setSubstepEnv( {'next': self.askWantBootPassword } )

    def askWantBootPassword(self):
        """Ask if the user wants a password for the GRUB bootloader. """
        ui = {
            'title': title,
            'body': askWantBootPasswordText + TransMenu.YesNoBackHelp,
            'menu': {
                '1': self.enterPassword,
                '2': self.stepForward,
                '<': self.start,
                '?': self.help,
            }
        }
        self.setSubstepEnv(ui)

    def enterPassword(self):
        ui = {
            'title': title,
            'body': passwordText,
            'menu': {
                '<': self.start,
                '*': self.savePassword, },
            'input': 'passwords',
            'short': ['<', '?']
        }
        self.setSubstepEnv(ui)

    def savePassword(self):
        """Validate password entries, save."""

        # extract input
        trial1, trial2 = self.userinput

        if len(trial1) + len(trial2) > 0:
            # non-empty password
            try:
                if trial1 != trial2:
                    raise ValueError, errNotMatch
                bootloader.validateGrubPassword(trial1)
            except ValueError, ex:
                msg = "Password Input Error:\n%s\n" % str(ex)
                self.errorPushPop(title +' (Update)', msg + TransMenu.Back)
                return

            self.password = trial1
        else:
            # empty password
            self.password = ''

        self.setSubstepEnv({'next': self.enterLocation})

    def enterLocation(self):
        "Ask for boot location."
        ui = {
            'title': title,
            'body': installLocText,
            'menu': {
                '1': self.saveLocation,
                '2': self.saveLocation,
                '<': self.start,
                '?': self.help,
            }
        }
        self.setSubstepEnv(ui)

    def saveLocation(self):
        "Save boot location."
        if self.userinput == '1':
            self.location = userchoices.BOOT_LOC_MBR
        else:  # '2'
            self.location = userchoices.BOOT_LOC_PARTITION
        self.setSubstepEnv({'next': self.applyChoices})

    def applyChoices(self):
        userchoices.setBoot(False,
                location=self.location,
                kernelParams=self.kernelParams,
                password=self.password)
        bootloader.runtimeAction()

        self.setSubstepEnv({'next': self.stepForward})

    def help(self):
        "Emit help text."
        self.helpPushPop(title + ' (Help)', helpText + TransMenu.Back)

