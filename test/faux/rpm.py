
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

'''A mock rpm module.

Provides enough mock classes to make it through a weasel installation.  As part
of this, it also overrides the os.open() function in order to fake the
TransactionSet.hdrFromFdno() method.
'''

RPM_FILE_ROOTS = []

import os
import fauxroot

from types import DictType

RPM_FILES = {}

# List of package names that are "corrupted", i.e. they cause a CPIO error to
# occur during installation.
CORRUPTED_PACKAGES = []

def reset():
    global CORRUPTED_PACKAGES
    
    CORRUPTED_PACKAGES = []

old_os_open = os.open

def rpm_open(filename, flags, mode = 0777):
    '''Wrapper for the os.open function that is used to implement
    TransactionSet.hdrFromFdno.  It works by capturing attempts to open files
    with a given prefix (e.g. /mnt/source/VMware/RPMS) and returns a "header"
    tuple instead of a file descriptor.  When the returned value is passed to
    TransactionSet.hdrFromFdno, it will be returned as the header value.

    XXX This should be replaced with something more sensible...
    '''
    
    filename = os.path.basename(filename)
    
    if filename in RPM_FILES:
        return RPM_FILES[filename]

    return old_os_open(filename, flags, mode)

os.open = rpm_open


old_os_close = os.close

def rpm_close(fileDescriptorOrRpmOpenDict):
    '''Wrapper for os.close function that deals with tuple objects generated
    by the os.open wrapper above.'''
    
    if type(fileDescriptorOrRpmOpenDict) is DictType:
        return

    return old_os_close(fileDescriptorOrRpmOpenDict)

os.close = rpm_close


(RPMTAG_NAME, RPMTAG_SIZE, RPMTAG_REQUIRENAME, RPMTAG_CONFLICTNAME) =\
('name', 'size', 'requires', 'conflicts')

(RPMCALLBACK_INST_OPEN_FILE,
 RPMCALLBACK_INST_CLOSE_FILE,
 RPMCALLBACK_INST_START,
 RPMCALLBACK_INST_PROGRESS,
 RPMCALLBACK_TRANS_PROGRESS,
 RPMCALLBACK_TRANS_START,
 RPMCALLBACK_TRANS_STOP,
 RPMCALLBACK_UNPACK_ERROR,
 RPMCALLBACK_CPIO_ERROR,
 RPMCALLBACK_UNKNOWN) = range(10)

(RPMVSB_NORSA, RPMVSB_NODSA) = range(2)

(RPMPROB_FILTER_NONE, RPMPROB_FILTER_IGNOREARCH) = range(2)

RPMVSF_NORSA = 1 << RPMVSB_NORSA
RPMVSF_NODSA = 1 << RPMVSB_NODSA

def addMacro(name, value):
    return

def setLogFile(logFile):
    if logFile:
        logFile.write("faux rpm reporting for duty")
        logFile.close()

class RpmPackage:

    def __init__(self, rpmHeader, cbArgs):
        self.cbArgs = cbArgs
        self.rpmHeader = rpmHeader
        self.name = self.rpmHeader['name']
        self.size = self.rpmHeader['size']
        self.requires = self.rpmHeader['requires']
        self.conflicts = self.rpmHeader['conflicts']

    def N(self):
        return self.name

    def V(self):
        return 1

    def R(self):
        return 1

    def A(self):
        return "x86_64" # XXX return a more realistic value

class TransactionSet:

    def __init__(self, root):
        self.root = root
        self.vsflags = 0
        self.packages = []
        self.filt = RPMPROB_FILTER_NONE
        self.color = 0
        return

    def __iter__(self):
        return self.packages.__iter__()

    def setVSFlags(self, flags):
        self.vsflags = flags
        return

    def setProbFilter(self, filt):
        self.filt = filt
        return

    def initDB(self):
        return
 
    def closeDB(self):
        return

    def hdrFromFdno(self, rpmOpenDict):
        assert type(rpmOpenDict) is DictType
        return rpmOpenDict

    def addInstall(self, rpmHeader, cbArgs, mode):
        for pkg in self.packages:
            if pkg.rpmHeader == rpmHeader:
                # Already in the transaction set.
                return
        
        self.packages.append(RpmPackage(rpmHeader, cbArgs))
        return

    def check(self, func):
        return

    def setColor(self, color):
        self.color = color

    def getColor(self):
        return self.color

    def order(self):
        return

    def problems(self):
        return

    def run(self, callback, callbackArg):
        for pkg in self.packages:
            callback(RPMCALLBACK_INST_OPEN_FILE,
                     0,
                     0,
                     pkg.cbArgs,
                     (callbackArg,))
            if pkg.name in CORRUPTED_PACKAGES:
                callback(RPMCALLBACK_CPIO_ERROR,
                         0,
                         0,
                         pkg.cbArgs,
                         (callbackArg,))
            callback(RPMCALLBACK_INST_CLOSE_FILE,
                     0,
                     0,
                     pkg.cbArgs,
                     (callbackArg,))
        return
