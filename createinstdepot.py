#!/usr/bin/python

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
###############################################################################
#
# createinstdepot.py [WORKING_DIR]
#
# This script is used to recreate the packageData.pkl database necessary
# for customizing ESX.  The packageData.pkl database contains copies of
# each of the RPM headers used by the ESX installer, as well as a 
# listing of each of the directories created by the RPM packages with
# the sum of the sizes of each of the files which would be located in that
# directory.  This size is used by the ESX installer to dynamically
# determine the minimum partition sizes.
#
# The script will also check to make sure all the dependencies for the RPMs
# in the depot are satisfied, and that no conflicts are present.

import rpm
import os
import stat
import glob
import sys
import cPickle
import struct
import shutil
import tempfile

SEEK_CUR = 1

FILEOBJ_FILENAME = 0
FILEOBJ_SIZE = 1
FILEOBJ_MODE = 2
SIZE_MB = 1024 * 1024
BLOCK_SIZE = 4 * 1024

transactionSet = None
rpmDict = { 'headerSizes': {}, 'fileSizes': {} }

# kludge the space checker by making it require more space to
# accomodate packages that dynamically eat up extra space
extraDirectorySpace = \
    [('/var', 40 * SIZE_MB),
     ('/tmp', 800 * SIZE_MB),
     ('/var/lib/rpm', 20 * SIZE_MB),
     ('/var/log', 512 * SIZE_MB),
     ('/', 10 * SIZE_MB),
     ('/usr/lib/locale', 55 * SIZE_MB),
     ('/var/cache/man/cat1', 1 * SIZE_MB),
     ('/lib/modules/2.6.18-92.ESX', 1 * SIZE_MB),
     ('/usr/lib64/perl5/5.8.8/x86_64-linux-thread-multi/auto/sdbm', 
      1 * SIZE_MB),
    ]

def roundUpTo(num, boundary):
    return (num + (boundary - 1)) & ~(boundary - 1)

def processRPMHeaderInfo(fileName):
    global rpmDict
    headerSizes = rpmDict['headerSizes']

    fd = open(fileName, 'r')

    # read past lead and first 8 bytes
    fd.seek(104)
    (sigindex, ) = struct.unpack('>I', fd.read(4))
    (sigdata, ) = struct.unpack('>I', fd.read(4))

    # index is 4x32bit segments or 16 bytes
    sigsize = sigdata + (sigindex * 16)

    # round off to the next 8 byte boundary
    tail = 0
    if sigsize % 8:
        tail = 8 - (sigsize % 8)

    hdrstart = 112 + sigsize + tail

    # go to the start of the header
    fd.seek(hdrstart)
    fd.seek(8, SEEK_CUR)

    (hdrindex, ) = struct.unpack('>I', fd.read(4))
    (hdrdata, ) = struct.unpack('>I', fd.read(4))

    # add 16 bytes to account for misc data at the end of the sig
    hdrsize = hdrdata + (hdrindex * 16) + 16

    hdrend = hdrstart + hdrsize
    fd.close()

    pkgSize = os.path.getsize(fileName)

    fd = os.open(fileName, os.O_RDONLY)
    header = transactionSet.hdrFromFdno(fd)
    os.close(fd)

    transactionSet.addInstall(header, [], 'i')

    headerSizes[os.path.basename(fileName)] = (
        header['name'], pkgSize, hdrstart, hdrend)


def processFileSize(fileName):
    global rpmDict
    sizeDict = rpmDict['fileSizes']

    fd = os.open(fileName, os.O_RDONLY)
    header = transactionSet.hdrFromFdno(fd)
    os.close(fd)

    files = header.fiFromHeader()

    for fileObj in files:
        fileName = fileObj[FILEOBJ_FILENAME]
        size = roundUpTo(fileObj[FILEOBJ_SIZE], BLOCK_SIZE)
        mode = fileObj[FILEOBJ_MODE]

        if stat.S_ISDIR(mode):
            if fileName not in sizeDict:
                sizeDict[fileName] = BLOCK_SIZE
        elif stat.S_ISREG(mode) or stat.S_ISLNK(mode):
            dirName = os.path.dirname(fileName)
            if dirName not in sizeDict:
                sizeDict[dirName] = BLOCK_SIZE
            if stat.S_ISLNK(mode):
                sizeDict[dirName] += BLOCK_SIZE
            else:
                sizeDict[dirName] += size
        else:
            print "Didn't know how to handle %s" % fileName


def addExtraSpace():
    '''Adds a fudge factor for certain files not included in the
       rpm package headers
    '''
    global rpmDict

    sizeDict = rpmDict['fileSizes']

    for entry in extraDirectorySpace:
        if entry[0] not in sizeDict:
            sizeDict[entry[0]] = BLOCK_SIZE
        sizeDict[entry[0]] += entry[1]
        print "%s requires %d" % (entry[0], sizeDict[entry[0]])

def printDependencies(deplist):
    '''Handle any unresolved dependencies returned by the
    TransactionSet.check() method.
    '''
    for (N, V, R), (reqN, reqV), needsFlags, suggestedPackage, sense in deplist:
        msg = '%s-%s-%s' % (N, V, R)
        # Conflict or requires?
        if sense == rpm.RPMDEP_SENSE_CONFLICTS:
            msg += ' conflcts with'
        elif sense == rpm.RPMDEP_SENSE_REQUIRES:
            msg += ' requires'
        else:
            msg += ' has unknown relationship to'
        msg += ' %s' % reqN
        # <, <=, =, >=, >, or none of the above?
        op = ''
        if needsFlags & rpm.RPMSENSE_GREATER:
            op += '>'
        elif needsFlags & rpm.RPMSENSE_LESS:
            op += '<'
        if needsFlags & rpm.RPMSENSE_EQUAL:
            op += '='
        if op and reqV:
            msg += ' %s %s' % (op, reqV)
        sys.stderr.write('%s\n' % msg)

def main():
    global transactionSet, rpmDict

    argv = sys.argv

    if not os.path.isdir(argv[1]):
        print "You need to specify a directory"
        sys.exit(1)

    rpmDir = sys.argv[1]

    # We don't want to use the default RPM database on the developer or build
    # machine.  Doing so throws off dependency and conflict checking, as there
    # are likely a lot of installed packages on the build host that will
    # conflict with packages in our test transaction and/or provide things
    # that would not normally be in our test transaction.
    tmpdir = tempfile.mkdtemp()

    try:
        rpm.addMacro('_dbpath', tmpdir)

        transactionSet = rpm.TransactionSet()
        transactionSet.setVSFlags(~(rpm.RPMVSF_NORSA|rpm.RPMVSF_NODSA))

        # read each of the rpms
        for f in glob.glob(os.path.join(rpmDir, "*.rpm")):
            print "Processing package: %s" % (os.path.basename(f)) 
            try:
                processRPMHeaderInfo(f)
                processFileSize(f)
            except (IOError, OSError, struct.error), msg:
                print "Failed:  %s." % (msg[0])
                sys.exit(1)

        addExtraSpace()

        pf = open(os.path.join(rpmDir, 'packageData.pkl'), 'w')
        cPickle.dump(rpmDict, pf)
        pf.close()

        unsatisfiedDeps = transactionSet.check()
    finally:
        shutil.rmtree(tmpdir)

    if unsatisfiedDeps:
        printDependencies(unsatisfiedDeps)
        sys.stderr.write("error: some packages have unresolved dependencies "
                         "or conflicts\n")
        sys.exit(1)

if __name__ == '__main__':
    main()


