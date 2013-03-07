
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
import sys

TEST_DIR = os.path.dirname(__file__)
sys.path.append(os.path.join(TEST_DIR, os.path.pardir))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'faux'))
import fauxroot

sys.path.append(os.path.join(os.path.dirname(__file__), 'good-config.1'))
import fauxconfig
sys.path.pop()

import consts

import partition
import fstab
import fsset
import userchoices
import workarounds
from migrate_support import cmpMigratedFiles
from StringIO import StringIO

def test_emptyFstab():
    reload(userchoices)

    try:
        fauxroot.FAUXROOT = [os.path.join(TEST_DIR, "good-config.1")]
        fstab.hostActionWriteFstab(None)

        actual = open(os.path.join(consts.HOST_ROOT, "etc", "fstab")).read()
        expected = """\
None                    /dev/pts                devpts  defaults        0 0
/dev/cdrom              /mnt/cdrom              udf,iso9660 noauto,owner,kudzu,ro 0 0
/dev/fd0                /mnt/floppy             auto    noauto,owner,kudzu 0 0
None                    /proc                   proc    defaults        0 0
None                    /sys                    sysfs   defaults        0 0
"""
        assert actual == expected
        assert os.path.exists(os.path.join(consts.HOST_ROOT, "mnt/cdrom"))
        assert os.path.exists(os.path.join(consts.HOST_ROOT, "mnt/floppy"))
    finally:
        fauxroot.FAUXROOT = None

def test_migrateFstab():
    def sideEffects0():
        actualLog = fauxroot.SYSTEM_LOG
        expectedLog = [
            ['insmod', '/lib/sunrpc.ko'],
            ['insmod', '/lib/nfs_acl.ko'],
            ['insmod', '/lib/lockd.ko'],
            ['insmod', '/lib/nfs.ko'],
            ['/sbin/mount.nfs', 'exit14:/', '/mnt/sysimage/esx3-installation/mnt/exit14', '-v', '-o', 'rsize=32768,wsize=32768,timeo=14,intr,ro,bg,soft,nolock'],
            ['/sbin/mount.nfs', 'exit15:/', '/mnt/sysimage/esx3-installation/mnt/exit15', '-v', '-o', 'defaults,ro,bg,soft,nolock']
            ]
        assert actualLog == expectedLog
    
    cases = [
        ("fstab.old.0", "fstab.new.0", "fstab.mig.0"),
        ]

    for oldPath, newPath, expectedPath in cases:
        yield (cmpMigratedFiles,
               fstab.hostActionMigrateFstab, "etc/fstab",
               oldPath, newPath, expectedPath,
               sideEffects0)

def test_setSwapUUID():
    class ZeroFauxUUID:
        """A custom '/proc/sys/kernel/random/uuid' generator that returns a
        UUID that starts with zero the first time it is called.

        This is used to test the fix for bug 269129.
        """
        
        def __init__(self):
            self.counter = 0

        def __call__(self):
            f = StringIO(
                "%02da8e7c6-24ef-4f3e-9986-123456789abc" % self.counter)
            f.seek(0)
            self.counter += 1
            return f
        
    oldFauxUUID = fauxroot.PROC_FILES['/proc/sys/kernel/random/uuid']
    try:
        fauxroot.FAUXROOT = [os.path.join(TEST_DIR, "good-config.1")]

        # We want to test that setSwapUUID does not return a UUID that starts
        # with a zero, so use the custom UUID generator.
        uuidgen = ZeroFauxUUID()
        fauxroot.PROC_FILES['/proc/sys/kernel/random/uuid'] = uuidgen

        workarounds.setSwapUUID('/dev/sdc1')

        swapFs = fsset.swapFileSystem()
        actual = swapFs.getUuid('/dev/sdc1')

        # Make sure the ZeroFauxUUID object was called more than once.  The
        # first time should've returned a UUID starting with zero.
        assert uuidgen.counter == 2

        expected = '01a8e7c6-24ef-4f3e-9986-123456789abc'
        assert actual == expected
    finally:
        fauxroot.PROC_FILES['/proc/sys/kernel/random/uuid'] = oldFauxUUID
        fauxroot.FAUXROOT = None
