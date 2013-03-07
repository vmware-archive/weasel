
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

import esxlicense
import userchoices
from textrunner import TextRunner

title = "License"

askConfirmText = """\
Choose your licensing mode:

Current choice:  %s
 1) Keep
 2) Change
 <) Back
 ?) Help

"""

licenseModeText = """\
Do you want to enter a serial number now or later?

 1) Enter a serial number now
 2) Enter a serial number later and use evaluation mode
 <) Back
 ?) Help

"""

enterSerialNumberText = """\
Enter your serial number (or enter '<' to go back):

"""

licenseHelpText = """\
If you do not enter a serial number now, you can evaluate the product.  Later
on, you can enter a serial number through vCenter Server.  A serial number
consists of five, five character tuples, like so:

    XXXXX-XXXXX-XXXXX-XXXXX-XXXXX

 <) Back

"""

licenseErrorText = """\
%s

 <) Back

"""

class LicenseWindow(TextRunner):

    def __init__(self):
        super(LicenseWindow, self).__init__()
        self.substep = self.start

    def start(self):
        choice = userchoices.getSerialNumber()
        if 'esx' not in choice:
            self.setSubstepEnv({'next': self.askMode})
        else:
            self.setSubstepEnv({'next': self.askConfirm})

    def askConfirm(self):
        choice = userchoices.getSerialNumber()
        choiceText = 'Fully licensed -- %s' % choice['esx']
        ui = {
            'title': title,
            'body': askConfirmText % choiceText,
            'menu': {
                '1': self.stepForward,
                '2': self.askMode,
                '<': self.stepBack,
                '?': self.help
                }
            }
        self.setSubstepEnv(ui)

    def askMode(self):
        ui = {
            'title': title,
            'body': licenseModeText,
            'menu': {
                '1': self.enterSerialNumber,
                '2': self.clearSerialNumber,
                '<': self.stepBack,
                '?': self.help
                }
            }
        self.setSubstepEnv(ui)

    def clearSerialNumber(self):
        userchoices.clearLicense()
        
        self.setSubstepEnv({'next': self.stepForward})

    def enterSerialNumber(self):
        ui = {
            'title': title,
            'body': enterSerialNumberText,
            'menu': {
                '<': self.start,
                '?': self.help,
                '*': self.saveSerialNumber,
                }
            }
        self.setSubstepEnv(ui)

    def saveSerialNumber(self):
        try:
            esxlicense.checkSerialNumber(self.userinput)
        except esxlicense.LicenseException, e:
            self.errorPushPop(title, licenseErrorText % str(e))
            return
        
        userchoices.setSerialNumber(self.userinput)

        self.setSubstepEnv({'next': self.stepForward})

    def help(self):
        self.errorPushPop(title + ' (Help)', licenseHelpText)
