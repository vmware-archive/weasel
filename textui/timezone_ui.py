
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

'''Get Timezone selection.

To run just this module, use 'main.py -s Timezone'
'''

import os

from log import log
from timezone import TimezoneList
import userchoices
import textengine
from textrunner import TextRunner

askConfirmText = """\
Which timezone should this computer use?

Current choice:  %s
 1) Keep
 2) Change
 <) Back
 ?) Help

"""

helpText = """\
Select the number of the Timezone you want.

 <) Back

"""

#exceptTextTimezoneNotFound = """\
#Warning:  selected Timezone name not found in standard list.
#Current choice is not changed.
#
# <) Back
#
#"""

listGuide = "[<enter>: forward, '<': back, '?': help]"

# timezone print representations.  (Second form is in enumeration.)
tzDictStrWithCity = "%(offset)s %(tzName)s (%(city)s)"
tzDictStrWithoutCity = "%(offset)s %(tzName)s"
tzEnumStrWithCity = "%2d. %s %s (%s)"
tzEnumStrWithoutCity = "%2d. %s %s %s"

SCROLL_LIMIT = 20

class TimezoneWindow(TextRunner):
    "Determine timezone of the system."

    def __init__(self):
        super(TimezoneWindow, self).__init__()
        self.substep = self.start
        self.timezones = TimezoneList()
        self.userinput = None
        self.uiTitle = 'Timezone'

        if not userchoices.getTimezone():  # not set in userchoices
            # copy default timezone values into userchoices
            dtz = self.timezones.defaultTimezone
            userchoices.setTimezone(dtz.zoneName, dtz.offset, dtz.city)
            dtz.runtimeAction()

        self.scrollable = None

    def start(self):
        self.setSubstepEnv( {'next': self.askConfirm } )

    def askConfirm(self):
        currentTz = userchoices.getTimezone()
        if currentTz['city']:
            formattedTz = tzDictStrWithCity % currentTz
        else:
            formattedTz = tzDictStrWithoutCity % currentTz
        ui = {
            'title': self.uiTitle,
            'body': askConfirmText % formattedTz,
            'menu': {
                '1': self.stepForward,
                '2': self.showTzList,
                '<': self.stepBack,
                '?': self.help,
            }
        }
        self.setSubstepEnv(ui)

    def help(self):
        self.pushSubstep()
        ui = {
            'title': self.uiTitle + ' (Help)',
            'body': helpText,
            'menu': { '*': self.popSubstep }
        }
        self.setSubstepEnv(ui)

    def showTzList(self):
        scrollable = []
        for iName, tz in enumerate(self.timezones.sortedIter()):
            if tz.city:
                format = tzEnumStrWithCity
            else:
                format = tzEnumStrWithoutCity
            # use 1-indexed
            formattedTz = format % (iName+1, tz.offset, tz.zoneName, tz.city)
            scrollable.append(formattedTz)
        self.setScrollEnv(scrollable, SCROLL_LIMIT)
        self.setSubstepEnv( {'next': self.scrollDisplay } )

    def scrollDisplay(self):
        "display timezone choices"
        self.buildScrollDisplay(self.scrollable, self.uiTitle,
            self.update, "<number>: keyboard choice", allowStepRestart=True)

    def update(self):

        # use skeleton below for exceptions
        errorSkeleton = {
            'title': self.uiTitle + ' (Update)',
            'menu': { '*': self.popSubstep },
            # add 'body'
        }

        # check for numeric input
        try:
            selected = int(self.userinput)-1    # revert to 0-indexed
        except ValueError:                      # non-integer input
            tz = None
        else:
            sortedTimezones = list(self.timezones.sortedIter())
            if 0 <= selected < len(sortedTimezones):
                tz = sortedTimezones[selected]
            else:
                tz = None

        if not tz:
            self.pushSubstep()
            errorSkeleton['body'] = helpText
            self.setSubstepEnv(errorSkeleton)
            return

        # register the choice
        userchoices.setTimezone(tz.zoneName, tz.offset, tz.city)
        tz.runtimeAction()
        log.debug('set tz to %s (%s)' % (tz.zoneName, tz.city))

        # choice acepted
        self.setSubstepEnv( {'next': self.askConfirm } )

