
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

"""Get time and date.
"""

import sys
from datetime import datetime
import socket
import re
import userchoices
import timedate
import networking
import textengine
from log import log
from textrunner import TextRunner, SubstepTransitionMenu as TransMenu

askMethodText = """\
Time/Date
How do you want to configure the time and date for ESX?

 1) Automatically by NTP server
 2) Manually
 <) Back
 ?) Help

"""

askServerChangeText = """
Time/Date (Automatic)

The current NTP server is:  %(ntpServer)s
Do you want to change it?
"""

askServerText = """\
Time/Date (Automatic)
Specify the NTP server.

['<': back, '?': help]
"""

askManualChangeText = """
Time/Date (Manual)

The current time is:  %(now)s
Do you want to change it?
"""

askDateTimeText = """\
Time/Date (Manual)

Specify the local system date and time as:
    YYYY-MM-DD HH:MM:SS
where:
    YYYY-MM-DD are year, month, and day
    HH:MM:SS are hour (0-23), minute, and second
After you press <enter>, the installer will immediately attempt to
update the date and time.

['<': back, '?': help]
"""

askTimeText = """\
Time/Date (Manual)

Specify the local hour, minute, and second as HH:MM:SS
(24-hour format):

['<': back, '?': help]
"""

helpText = """\
Choose the present date and time.
Local date and time are specified in the following numeric formats:
    Date:  YYYY-MM-DD
    Time:  HH:MM:SS

Time may be derived from a server via NTP (Network Time Protocol),
or from the system's local real-time clock.
"""

verifyText = """
The system clock has been updated.  The current time is:
%(now)s

 1) OK
 <) Back

"""

title = 'Time/Date Settings'

# -------- classes --------

class TimedateWindow(TextRunner):
    """Determine the method of setting date and time (NTP server or manual),
    and set time accordingly.
    """
    # TODO:  need to set userchoice for NTP stuff.
    # manual method will need to clean userchoice.

    def __init__(self):
        super(TimedateWindow, self).__init__()
        self.substep = self.start
        self.uiTitle = title

        #now = datetime.now()
        #print now
        self.date = None        # [year, month, day]
        self.time = None        # [hours, mins, secs]
        self.timeref = None     # ntp server, local clock
        self.ntpServer = None

    def start(self):
        "Start here.  if date and time set, confirm; else get values."
        self.setSubstepEnv( {'next': self.askMethod } )

    def askMethod(self):
        "Ask user how to configure - by NTP server or manually."
        ui = {
            'title': self.uiTitle,
            'body': askMethodText,
            'menu': {
                '1': self.askServerChange, # start of server dialog
                '2': self.askManualChange, # start of manual dialog
                '<': self.stepBack,     # back to previous step
                '?': self.help,
            }
        }
        self.setSubstepEnv(ui)

    def askServerChange(self):
        "Show the current NTP server, Ask if the user wants to change it"
        choice = userchoices.getTimedate()
        if not choice or not choice['ntpServer']:
            self.setSubstepEnv({'next': self.askServer})
            return

        ntpServer = choice['ntpServer']
        ui = {
            'title': self.uiTitle,
            'body': askServerChangeText % {'ntpServer':ntpServer} + \
                TransMenu.KeepChangeBackHelpExit,
            'menu': {
                '1': self.stepForward,
                '2': self.askServer,
                '<': self.start,
                '?': self.help,
            }
        }
        self.setSubstepEnv(ui)

    def askServer(self):
        "Ask for NTP server name."
        ui = {
            'title': self.uiTitle,
            'body': askServerText,
            'menu': {
                '<': self.start,
                '?': self.help,
                '*': self.parseServer,
            }
        }
        self.setSubstepEnv(ui)

    def parseServer(self):
        "Parse user input for NTP server name."
        userinput = self.userinput.strip()
        try:
            networking.utils.sanityCheckIPorHostname(userinput)
        except ValueError:
            msg = 'Bad server address or name.\n' + TransMenu.Back
            self.errorPushPop(self.uiTitle, msg)
            return
        self.ntpServer = userinput

        self.setSubstepEnv({'next': self.attemptSynchronize})

    def attemptSynchronize(self):
        "Contact NTP server, synchronize time."

        errMsg = None
        try:
            # Note:  ntpQueryStart() may get error 107: ENOTCONN
            # It seems to be harmless but results in console message.
            if not networking.connected():
                print 'Connecting to the network...'
                networking.cosConnectForInstaller()
            timedate.ntpQueryStart(self.ntpServer)
            textengine.render_status('Attempting to contact server.')
            for _attempt in range(timedate.NTP_TIMEOUT):
                if timedate.ntpReady():
                    break
                textengine.render_status('.')
            textengine.render_status('\n')
            if timedate.ntpReady(timeout=0):
                year, month, day, hours, mins, secs = timedate.ntpQueryFinish()
            else:
                raise timedate.NTPError("Timeout: Destination is unreachable")
        except timedate.NTPError, ex:
            errMsg = 'Got an NTP error (%s)' % str(ex)
        except (socket.error, socket.gaierror), ex:
            errMsg = 'Got a socket error (%s)' % str(ex)
        except Exception, ex:
            # cast a wide exception net here because network errors should
            # not prevent the user from installing.
            errMsg = 'Got an exception (%s)' % str(ex)

        if errMsg:
            log.error(errMsg)
            self.errorPushPop(self.uiTitle +' (Update)',
                    '%s\n%s' % (errMsg, TransMenu.Back))
            return

        userchoices.setTimedate(self.ntpServer)
        self.date = (year, month, day)
        self.time = (hours, mins, secs)
        self.setSubstepEnv({'next': self.commit})

    def askManualChange(self):
        "Show current time, ask if user wants to change it."
        now = datetime.now()
        ui = {
            'title': self.uiTitle,
            'body': askManualChangeText % {'now': now} + \
                TransMenu.KeepChangeBackHelpExit,
            'menu': {
                '1': self.stepForward,
                '2': self.askDateTime,
                '<': self.start,
                '?': self.help,
            }
        }
        self.setSubstepEnv(ui)

    def askDateTime(self):
        """Ask for date and time in YYYY-MM-DD HH:MM:SS format.
        Start of manual dialog.
        """
        ui = {
            'title': self.uiTitle,
            'body': askDateTimeText,
            'menu': {
                '<': self.start,
                '?': self.help,
                '*': self.parseDateTime,
            }
        }
        self.setSubstepEnv(ui)

    def parseDateTime(self):
        "Parse user input for date."
        datetimestr = self.userinput.strip()
        # TODO: watch out for multiple intervening spaces.  May need to do a
        # safer split, or come the date and time regex stuff in one expression.

        # extract date fields
        try:
            try:
                datestr, timestr = datetimestr.split(' ')
            except ValueError:
                raise ValueError('The input could not be parsed into ' + \
                    'time and date.')
            ymd = re.match(r'(\d\d\d\d)-(\d\d?)-(\d\d?)', datestr)
            if not ymd:
                raise ValueError('The date could not be parsed into ' + \
                    'year, month, and day.')
            year, month, day = [int(value) for value in ymd.groups()]
            if not (1000 <= year <= 9999 and 1 <= month <= 12 and 1 <= day <= 31):
                raise ValueError('A date value (year, month, or day) ' + \
                    'is out of bounds.')
        except ValueError, msg:
            body = '\n'.join([msg[0], TransMenu.Back])
            self.errorPushPop(self.uiTitle, body)
            return

        self.date = (year, month, day)

        # extract time fields
        try:
            hms = re.match(r'(\d\d?):(\d\d?):(\d\d?)', timestr)
            if not hms:
                raise ValueError('The time could not be parsed into ' + \
                    'hours, minutes, and seconds.')
            hours, mins, secs = [int(value) for value in timestr.split(':')]
            if not (0 <= hours <= 23 and 0 <= mins <= 59 and 0 <= secs <= 59):
                raise ValueError('A time value (hour, minute, or second) ' + \
                    'is out of bounds.')
        except ValueError, msg:
            body = msg[0] + '\n' + TransMenu.Back
            self.errorPushPop(self.uiTitle, body)
            return

        self.time = (hours, mins, secs)
        self.setSubstepEnv({'next': self.commit})

    def help(self):
        "Emit help text."
        self.helpPushPop(self.uiTitle+' (Help)', helpText + TransMenu.Back)

    def commit(self):
        "Set the time."
        year, month, day = self.date
        hours, mins, secs = self.time

        timedate.runtimeAction(year, month, day, hours, mins, secs)

        self.setSubstepEnv({'next': self.verify})

    def verify(self):
        "Retrieve time after setting."
        now = datetime.now()
        ui = {
            'title': self.uiTitle,
            'body': verifyText % {'now': now},
            'menu': {
                '1': self.stepForward,
                '<': self.start,
                '?': self.help,
            }
        }
        self.setSubstepEnv(ui)


