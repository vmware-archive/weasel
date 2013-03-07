#! /usr/bin/env python

###############################################################################
# Copyright (c) 2008-2009 VMware, Inc.
#
# This file is part of Weasel.
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
timedate module docstring goes here
'''

import os
import time
import socket
import select
import struct
import userchoices
import task_progress
import vmkctl
from util import execCommand
from log import log
from consts import HOST_ROOT

ntp_conf_content = '''\
# ---- ntp.conf ----
# Created by Weasel (ESX Installer)

# Permit time synchronization with our time source, but do not
# permit the source to query or modify the service on this system.
restrict default kod nomodify notrap nopeer noquery
restrict -6 default kod nomodify notrap nopeer noquery
restrict 127.0.0.1

server %(ntpServer)s
driftfile /var/lib/ntp/drift
'''

adjtime_content = '''\
0.0 0 0.0
0
UTC
'''

NTP_PORT = 123
# this is the magical value that is an ntp query. 
# simply send \x1b followed by 47 null bytes to an ntp server and it
# should respond to you.  See RFC 958 for details
NTP_ASK_MSG = '\x1b' + '\0'*47

NTP_TIMEOUT = 15 # seconds

_openSocket = None

class NTPError(Exception):
    '''Exception to be used for errors when talking to NTP servers'''

def getTimezoneName():
    choice = userchoices.getTimezone()
    if not choice:
        return os.environ.get('TZ', '')
    else:
        return choice['tzName']

def systemClockIsUTC():
    choice = userchoices.getTimezone()
    if not choice:
        return True #System clock assumed UTC by default
    else:
        return choice['isUTC']

def checkActionSaneTimedate():
    if time.time() < 0:
        runtimeAction(2008, 1, 1, 0, 0, 0)

def setHardwareClock(timeTuple):
    '''Set the hardware clock on the machine.

    timeTuple - A tuple containing the date to set in the clock.  The tuple
      should be made up of (year, month, day, hour, min, sec).
    '''
    sysinfo = vmkctl.SystemInfoImpl()
    dt = sysinfo.GetDateTime() #get a writable vmkctl DateTime object
    dt.year, dt.month, dt.day, dt.hour, dt.min, dt.sec = timeTuple
    sysinfo.SetDateTime(dt)
    
def hostActionTimedate(_context):
    '''If the ntp server is set, just write to /mnt/sysimage/etc/ntp.conf
    otherwise, use vmkctl to set the hardware clock.
    '''
    fp = open(os.path.join(HOST_ROOT, 'etc/adjtime'), 'w')
    fp.write(adjtime_content)
    fp.close()

    choice = userchoices.getTimedate()
    if not choice or not choice['ntpServer']:
        # If the system clock was changed manually or by the checkAction we
        # need to update it.
        if systemClockIsUTC():
            timeFn = time.gmtime
        else:
            timeFn = time.localtime
        timeTuple = timeFn()[:6]
        setHardwareClock(timeTuple)
        return

    fp = open(os.path.join(HOST_ROOT, 'etc/ntp.conf'), 'w')
    fp.write(ntp_conf_content % choice)
    fp.close()

def runtimeAction(year, month, day, hour, minute, seconds):
    '''This will set the system clock.'''
    try:
        year    = int(year)
        month   = int(month)
        day     = int(day)
        hour    = int(hour)
        minute  = int(minute)
        seconds = int(seconds)
    except ValueError, ex:
        raise ValueError('time/date must be set with integer arguments')
    # this is the format that works with busybox
    tzName = getTimezoneName()
    execCommand('TZ="%s" date -s "%02d%02d%02d%02d%d.%02d"' %
                (tzName, month, day, hour, minute, year, seconds))


def carefullyCloseSocket():
    global _openSocket
    if _openSocket:
        try:
            _openSocket.shutdown(socket.SHUT_RDWR)
            _openSocket.close()
        except (EnvironmentError, socket.error), ex:
            log.info('Error while shuting down / closing socket')
            log.info('Error details: ' + str(ex))

def ntpQueryStart(server):
    global _openSocket
    task_progress.taskStarted('ntp')
    carefullyCloseSocket()
    _openSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    task_progress.taskProgress('ntp')
    try:
        _openSocket.connect((server, NTP_PORT))
        _openSocket.send(NTP_ASK_MSG)
    except (socket.error, socket.gaierror), ex:
        log.info('Socket error sending to NTP server ' + str(ex))
        raise NTPError('Socket error '+ str(ex))
    
    return _openSocket

def ntpReady(timeout=1.0):
    """Block until the ntp socket is ready for reading or the timeout fires.

    Returns true if the socket is ready to be read by ntpQueryFinish.
    """
    task_progress.taskProgress('ntp')
    
    iready, _oready, _eready = \
        select.select([_openSocket], [], [], timeout)

    return iready != []

def ntpQueryFinish():
    global _openSocket
    task_progress.taskProgress('ntp')
    try:
        rawData = _openSocket.recv(1024)
    except (socket.error, socket.gaierror), ex:
        log.info('Socket error receiving from NTP server ' + str(ex))
        task_progress.taskFinish('ntp')
        raise NTPError('Socket error '+ str(ex))
    carefullyCloseSocket()
    if not rawData:
        log.warn('NTP server did not respond with any data')
        task_progress.taskFinish('ntp')
        raise NTPError('No data received')

    task_progress.taskFinish('ntp')

    twelveBigEndianUnsignedInts = '!12I'
    try:
        dataTuple = struct.unpack(twelveBigEndianUnsignedInts, rawData)
    except struct.error, ex:
        raise NTPError('Error unpacking NTP server response (%s)' % str(ex))
    if dataTuple == 0:
        raise NTPError('NTP server response was 0')

    serverTime = dataTuple[8]
    epochOffset = 2208988800L
    timeTuple = time.localtime(serverTime - epochOffset)
    year, month, day, hours, mins, secs = timeTuple[:6]
    return year, month, day, hours, mins, secs


