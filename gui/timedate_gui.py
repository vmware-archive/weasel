#! /usr/bin/env python

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
time / date screen
'''

import time
import socket
import gobject

import timedate
import networking
import userchoices
from log import log
from exception import StayOnScreen
from singleton import Singleton
from signalconnect import connectSignalHandlerByDict
from common_windows import ProgressWindowTaskListener, MessageWindow

TEN_SECONDS  = 10000
ONE_SECOND   = 1000
TENTH_SECOND = 100

#-----------------------------------------------------------------------------
# This needs to be a singleton because the window can still have pending 
# callbacks fired after the user hits Next or Back
class TimedateWindow(Singleton):
    SCREEN_NAME = 'timedate'
    
    def _singleton_init(self, controlState, xml):
        self.controlState = controlState
        self.done = False

        self.ntpWidgetsParent = xml.get_widget('automatically_alignment')
        self.manualWidgetsParent = xml.get_widget('manually_alignment')
        self.ntpServerEntry = xml.get_widget('ntpserver_entry')
        self.ntpSyncButton = xml.get_widget('ntpserver_sync')
        self.ntpError = xml.get_widget('ntpserver_error')
        self.calendarWidget = xml.get_widget('calendar')
        self.clockEntry = xml.get_widget('clock_entry')
        self.manualRadioButton = xml.get_widget('TimedateManuallyRadioButton')

        self.ntpError.hide()

        connectSignalHandlerByDict(self, TimedateWindow, xml,
          { ('TimedateManuallyRadioButton', 'toggled'): 'onMethodToggled',
            ('ntpserver_entry', 'changed'): 'onNTPServerChanged',
            ('ntpserver_sync', 'clicked'): 'attemptSynchronize',
            ('calendar', 'focus_out_event'): 'onCalendarFocusOut',
            ('clock_entry', 'changed'): 'onClockChanged',
            ('clock_entry', 'focus_in_event'): 'onClockFocusIn',
            ('clock_entry', 'focus_out_event'): 'onClockFocusOut',
          })

        self.pendingSyncTimeoutID = None
        self.pendingTickID = None

        choices = userchoices.getTimedate()
        if not choices:
            # first time through: nothing set yet.
            choices['ntpServer'] = None
            # set it to blank, just so that it's set
            log.info('Setting default time/date user choice: no NTP')
            userchoices.setTimedate(**choices)
            self.manualRadioButton.set_active(True)
        elif choices['ntpServer']:
            self.ntpServerEntry.set_text(choices['ntpServer'])

    def __init__(self, controlState, xml):
        controlState.displayHeaderBar = 1
        controlState.windowIcon = 'timedate.png'
        controlState.windowTitle = "Date and Time"
        controlState.windowText = "Specify the date and time for ESX"

        self.done = False
        self.clockToSystemTime()
        self.ensureClockTicking()

    def onMethodToggled(self, widget, *args):
        isManual = widget.get_active()
        if not isManual and self.hasBadHoursMinsSecs():
            # wipe the clock widget
            self.clockToSystemTime()
            self.ensureClockTicking()

        self.ntpWidgetsParent.set_sensitive(not isManual)
        self.manualWidgetsParent.set_sensitive(isManual)

    def getHoursMinsSecs(self):
        text = self.clockEntry.get_text()
        try:
            hours, mins, secs = [int(i) for i in text.split(':')]
            if not (0 <= hours <= 23 and
                    0 <= mins <= 59 and
                    0 <= secs <= 59):
                raise ValueError('Clock value out of bounds')
        except ValueError, ex:
            log.warn('Bad hours, mins, or secs (%s). Exception: %s'
                     % (text, str(ex)))
            raise
        return hours, mins, secs

    def hasBadHoursMinsSecs(self):
        try:
            self.getHoursMinsSecs()
            return False
        except ValueError:
            return True

    def clockTick(self):
        self.pendingTickID = None

        # if the current value in the widget is bogus, give the user
        # time to see the error and correct it manually
        if self.hasBadHoursMinsSecs():
            return

        self.clockToSystemTime()
        self.ensureClockTicking()

    def ensureClockTicking(self):
        if self.done:
            return
        self.pendingTickID = gobject.timeout_add(ONE_SECOND, self.clockTick)

        
    def ntpServerValidationProblem(self):
        '''If the contents of the NTP server textentry don't validate,
        return the Exception object.  If there are no validation problems,
        return None.
        '''
        problem = None
        ipOrHostname = self.ntpServerEntry.get_text()
        ipOrHostname = ipOrHostname.strip()
        try:
            networking.utils.sanityCheckIPorHostname(ipOrHostname)
        except ValueError, ex:
            problem = ex
        return problem
    
    def onNTPServerChanged(self, widget, *args):
        self.ntpError.hide()
        self.ntpSyncButton.set_sensitive(not self.ntpServerValidationProblem())

    def attemptSynchronize(self, widget, *args):
        '''attempt to synchronize the time with the NTP server.
        Getting a response from the NTP server takes time, so this function
        splits up the work and the error cases over several other methods
        of this class.
        '''
        self.ntpError.hide()
        self.ntpSyncButton.set_sensitive(False)
        self.progressDialog = ProgressWindowTaskListener(
                                self.controlState.gui.getWindow(),
                                'NTP Synchronization',
                                'Connecting to the network',
                                ['network', 'ntp'],
                                execute=False)

        self.progressDialog.nonblockingRun()

        if not networking.connected():
            try:
                networking.cosConnectForInstaller()
            except Exception, ex:
                log.warn('Timedate Window could not connect to the network')
                log.warn('Exception was: %s' % str(ex))
                self.ntpError.show()
                self.progressDialog.finish()
                return

        self.progressDialog.setText('Asking the server for the time')

        # if the ntp server takes longer than 10 seconds to respond, just
        # give up.  latency is bad user experience. it's probably dead anyway.
        self.pendingSyncTimeoutID = gobject.timeout_add(TEN_SECONDS,
                                                        self.onSynchronizeError)

        server = self.ntpServerEntry.get_text().strip()
        try:
            sock = timedate.ntpQueryStart(server)
        except (socket.gaierror, timedate.NTPError), ex:
            self.onSynchronizeError()
            return

        # TODO: find a good way to test these...
        gobject.io_add_watch(sock, gobject.IO_IN, self.onSynchronizeResponse)
        gobject.io_add_watch(sock, gobject.IO_PRI, self.onSynchronizeResponse)

    def onSynchronizeResponse(self, ntpSocket, ioCondition):
        log.info('got a ntp server response')
        gobject.source_remove(self.pendingSyncTimeoutID)
        self.ntpSyncButton.set_sensitive(not self.ntpServerValidationProblem())
        self.progressDialog.finish()

        try:
            year, month, day, hour, mins, secs = timedate.ntpQueryFinish()
        except timedate.NTPError, ex:
            log.error('Timedate Window got NTPError (%s)' % str(ex))
        except socket.gaierror, ex:
            log.error('Timedate Window got socket error (%s)' % str(ex))
        else:
            timedate.runtimeAction(year, month, day, hour, mins, secs)
            self.calendarToSystemTime()
            self.clockToSystemTime()

        # called by io_add_watch - so tell it we're done
        return False

    def onSynchronizeError(self, ntpSocket=None, ioCondition=None):
        log.info('got a ntp server error')
        gobject.source_remove(self.pendingSyncTimeoutID)
        self.ntpError.show()
        self.ntpSyncButton.set_sensitive(not self.ntpServerValidationProblem())
        self.progressDialog.finish()

        # called by timeout_add - so tell it we're done
        return False
        
    def onCalendarFocusOut(self, widget, *args):
        self.setSystemTime()

    def onClockFocusIn(self, widget, *args):
        log.debug('Clock focus in.  Removing clocktick from the timeout')
        if self.pendingTickID != None:
            gobject.source_remove(self.pendingTickID)

    def onClockFocusOut(self, widget, *args):
        log.debug('Clock focus out.  Putting clocktick back in the timeout')
        self.ensureClockTicking()
        self.setSystemTime()

    def onClockChanged(self, widget, *args):
        pass
        # We don't need do anything here, but when debugging, the following
        # commented-out code is useful:
        #if self.hasBadHoursMinsSecs():
            #log.debug('Clock changed to invalid value')

    def clockToSystemTime(self):
        newText = time.strftime('%H:%M:%S', time.localtime())
        self.clockEntry.set_text(newText)

    def calendarToSystemTime(self):
        year, month, day = time.localtime()[:3]
        month -= 1 #gtk calendar widget has months 0-11, localtime gives 1-12
        self.calendarWidget.select_month(month, year)
        self.calendarWidget.select_day(day)

    def setSystemTime(self):
        try:
            hours, mins, secs = self.getHoursMinsSecs()
        except ValueError, ex:
            log.error('Could not set system time')
            log.error(str(ex))
            return
        year, month, day = self.calendarWidget.get_date()
        month += 1 #gtk calendar widget has months 0-11, we want 1-12
        timedate.runtimeAction(year, month, day, hours, mins, secs)

    def getBack(self):
        self.done = True

    def getNext(self):
        if self.hasBadHoursMinsSecs():
            errWin = MessageWindow(None, 'Invalid Time',
                                   'The time must be in hh:mm:ss format')
            raise StayOnScreen()
        if self.manualRadioButton.get_active():
            log.info('Setting time/date user choice to Manual')
            userchoices.setTimedate(None)
        else:
            problem = self.ntpServerValidationProblem()
            if problem:
                MessageWindow(None, 'Invalid NTP Server',
                              'The NTP server must be a valid IP Address '
                              'or host name. (%s)' % str(problem))
                raise StayOnScreen()
            log.info('Setting time/date user choice to use NTP')
            ntpServer = self.ntpServerEntry.get_text().strip()
            userchoices.setTimedate(ntpServer)
        self.done = True
