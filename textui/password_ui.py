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

'''Adminstrator password
'''

import getpass
import userchoices
import users
import textengine
from textrunner import TextRunner, SubstepTransitionMenu as TransMenu

title = "Administrator Password"

instructionText = """\
Set the administrator (root) password for ESX
(or enter '<' to go back).

Passwords must be at least 6 characters long.

"""

helpText = """\
The administrator (root) password for ESX must be at least 6 characters
long, less than 64 characters long, and can only contain ascii characters.
"""

errNotMatch = "The two passwords entered do not match."

class PasswordWindow(TextRunner):

    def __init__(self):
        super(PasswordWindow, self).__init__()
        self.substep = self.start

    def start(self):
        ui = {
            'title': title,
            'body': instructionText,
            'menu': {
                '?': self.help,
                '<': self.stepBack,
                '*': self.validate, },
            'input': 'passwords',
            'short': ['<','?']
        }
        self.setSubstepEnv(ui)

    def validate(self):
        # extract input
        try:
            trial1, trial2 = self.userinput
        except ValueError, ex:
            if len(self.userinput) == 1:
                # may come here if pop substepStack, e.g., exit()
                self.setSubstepEnv({'next': self.start})
                return
            else:
                raise

        try:
            if trial1 != trial2:
                raise ValueError(errNotMatch)
            users.sanityCheckPassword(trial1)
        except ValueError, ex:
            msg = "%s\n" % str(ex)
            self.errorPushPop(title, msg + TransMenu.Back)
            return

        userchoices.setRootPassword(users.cryptPassword(trial1),
            userchoices.ROOTPASSWORD_TYPE_MD5)
        self.setSubstepEnv( {'next': self.stepForward} )

    def help(self):
        ui = {
            'title': title,
            'body': helpText,
            'menu': {
                '<': self.start,
                '*': self.start,
            }
        }
        self.setSubstepEnv(ui)

