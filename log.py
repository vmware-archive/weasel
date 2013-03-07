
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

import os
import re
import shutil
import logging
import sys

from grubupdate import UPGRADE_DIR
from consts import HOST_ROOT

LOGLEVEL_HUMAN = 25
LOG_PATH = "/var/log/weasel.log"
ESX_LOG_PATH = "/var/log/esx_install.log"

logging.addLevelName(LOGLEVEL_HUMAN, "HUMAN")

log = logging.Logger('weasel')
formatterForLog = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
formatterForHuman = logging.Formatter('%(message)s')
stdoutHandler = None
fileHandler = None

class URLPasswordFilter(logging.Filter):
    '''Filter used to censor passwords in URLs.'''
    def filter(self, record):
        record.msg = re.sub(r'(://.*?:).*?@', r'\1XXXXXX@', str(record.msg))
        return True

def addStdoutHandler():
    global stdoutHandler
    
    stdoutHandler = logging.StreamHandler(sys.stdout)
    stdoutHandler.setFormatter(formatterForHuman)
    stdoutHandler.setLevel(logging.INFO)
    log.addHandler(stdoutHandler)

def addLogFileHandler():
    global fileHandler
    
    try:
        fileHandler = logging.FileHandler(LOG_PATH)
        fileHandler.setFormatter(formatterForLog)
        log.addHandler(fileHandler)

        #users like "esx_install.log" over "weasel.log"
        if not os.path.exists(ESX_LOG_PATH):
            os.symlink(LOG_PATH, ESX_LOG_PATH)
    except IOError:
        #Could not open for writing.  Probably not the root user
        pass

log.addFilter(URLPasswordFilter())
addStdoutHandler()
addLogFileHandler()

installHandler = None
upgradeHandler = None

try:
    # dump messages to /proc/vmware/log (aka serial port).  
    handler3 = logging.StreamHandler(open('/proc/vmware/log', "w"))
    handler3.setFormatter(formatterForLog)
    log.addHandler(handler3)
except IOError:
    #Could not open for writing.  Probably not the root user
    pass

log.setLevel(logging.DEBUG)

def hostActionCopyLogs(_context):
    global installHandler
    
    '''Copy the log to the installed system.'''
    instPath = os.path.join(HOST_ROOT, LOG_PATH.lstrip('/'))
    instDir = os.path.dirname(instPath)
    if not os.path.exists(instDir):
        os.makedirs(instDir)
    shutil.copy(LOG_PATH, instPath)
    #users like "esx_install.log" over "weasel.log"
    nicePath = os.path.join(HOST_ROOT, ESX_LOG_PATH.lstrip('/'))
    os.symlink(LOG_PATH, nicePath)

    # Add another handler so any log messages after this point make it into the
    # new log file.
    installHandler = logging.FileHandler(instPath)
    installHandler.setFormatter(formatterForLog)
    log.addHandler(installHandler)

def hostActionAddUpgradeLogs(_context):
    '''Copy the log to the old cos during an upgrade.'''
    import userchoices
    import util

    global upgradeHandler
    
    rootUUID = userchoices.getRootUUID()['uuid']
    mountPath = util.mountByUuid(rootUUID)
    if not mountPath:
        return

    upPathDir = os.path.join(mountPath, UPGRADE_DIR.lstrip('/'))
    if not os.path.exists(upPathDir):
        os.makedirs(upPathDir)
    upPath = os.path.join(upPathDir, "esx_upgrade.log")
    logFile = open(LOG_PATH, 'r')
    upLogFile = open(upPath, 'a')
    while True:
        chunk = logFile.read(1024)
        if not chunk:
            break
        upLogFile.write(chunk)

    upgradeHandler = logging.FileHandler(upPath)
    upgradeHandler.setFormatter(formatterForLog)
    log.addHandler(upgradeHandler)

def tidyActionCloseLog():
    global installHandler, upgradeHandler
    
    if installHandler:
        log.removeHandler(installHandler)
        installHandler.close()
        installHandler = None
    if upgradeHandler:
        log.removeHandler(upgradeHandler)
        upgradeHandler.close()
        upgradeHandler = None
