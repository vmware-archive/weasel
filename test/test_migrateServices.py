
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
import migrate
import migration.services as ms

from migrate_support import copyIntoRoot

def test_xinetdconf():
    def cmpConf(filename, expectedFiles, expectedDirs, expectedServices):
        conf = open(os.path.join(TEST_DIR, "upgrade", filename))
        try:
            xc = ms.XinetdConf()
            xc.keyFilter = ["id", "disable"]
            for line in conf:
                xc.feedLine(line)

            assert xc.includedFiles == expectedFiles
            assert xc.includedDirs == expectedDirs
            assert xc.services == expectedServices
        finally:
            conf.close()
    
    cases = [
        ("xinetd.conf.0", [], ['/etc/xinetd.d'], {}),

        ("vmware-authd", [], [], {
                "vmware-authd" : { "disable" : "no" }
                }),
        
        ("time", [], [], {
                "time-stream" : { "disable" : "yes", "id" : "time-stream" }
                }),
        
        ]

    for case in cases:
        yield (cmpConf,) + case

def test_migrate():
    try:
        fauxroot.resetLogs()

        srcDir = os.path.join(TEST_DIR, "upgrade")
        root = os.path.join(TEST_DIR, "good-config.1")
        esx3 = consts.HOST_ROOT + consts.ESX3_INSTALLATION
    
        copyIntoRoot(os.path.join(srcDir, "xinetd.conf.1"),
                     root,
                     os.path.join(esx3, "etc/xinetd.conf"))
        copyIntoRoot(os.path.join(srcDir, "time"),
                     root,
                     os.path.join(esx3, "etc/xinetd.d/time"))
        copyIntoRoot(os.path.join(srcDir, "time"),
                     root,
                     os.path.join(consts.HOST_ROOT, "etc/xinetd.d/time-stream"))
        copyIntoRoot(os.path.join(srcDir, "vmware-authd"),
                     root,
                     os.path.join(esx3, "etc/xinetd.d/vmware-authd"))
        copyIntoRoot(os.path.join(srcDir, "vmware-authd"),
                     root,
                     os.path.join(consts.HOST_ROOT,
                                  "etc/xinetd.d/vmware-authd"))
        
        fauxroot.FAUXROOT = [root]

        migrate.migratePath("/etc/xinetd.conf")

        assert fauxroot.SYSTEM_LOG == [
            ['/sbin/chkconfig', 'time-stream', 'off'],
            ['/sbin/chkconfig', 'vmware-authd', 'on'],
            ]
    finally:
        fauxroot.FAUXROOT = None
