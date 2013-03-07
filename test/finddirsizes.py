
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


import sys
import os
import cPickle

DIR_SIZE_FILE = "/tmp/system-dirsizes"
PKG_DATA_FILE = "packageData.pkl"

def main():
    print "Make certain this script is run from the root directory " \
          "of the system you are trying to check."

    if not os.path.exists(PKG_DATA_FILE):
        print "Couldn't find %s, exiting." % PKG_DATA_FILE
        sys.exit(1)

    os.system("find / -mount -type f | xargs ls -s > %s" % DIR_SIZE_FILE)
    if not os.path.exists(DIR_SIZE_FILE):
        print "Couldn't find system dir sizes correctly, exiting."
        sys.exit(1)

    rawDirSizes = open(DIR_SIZE_FILE, 'r').read().split('\n')

    dirDict = {}

    for myDir in rawDirSizes:
        myDir = myDir.strip()

        if not myDir:
            continue

        size, name = myDir.split(maxsplit=1)

        # skip the proc partitions
        if name.startswith('/proc'):
            continue

        dirName = os.path.dirname(name)
        if not dirName in dirDict:
            dirDict[dirName] = 0
        dirDict[dirName] += int(size)

    f = open(PKG_DATA_FILE, 'r')
    rpmDict = cPickle.load(f)
    f.close()

    dataDict = rpmDict['fileSizes']

    for myDir in dirDict.keys():
        if not myDir in dataDict:
            print "Missing dir %s" % myDir
        elif dataDict[myDir] < dirDict[myDir]:
            print "Dir %s too small: %d vs %d" % \
                (myDir, dataDict[myDir], dirDict[myDir])

