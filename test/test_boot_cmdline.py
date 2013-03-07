
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
sys.path.append(os.path.join(TEST_DIR, "../../../../apps/scripts/"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'faux'))
import fauxroot

sys.path.append(os.path.join(os.path.dirname(__file__), 'good-config.1'))
import fauxconfig
sys.path.pop()

import userchoices
from boot_cmdline import translateBootCmdLine

from nose.tools import raises

def test_translateBootCmdLine():
    reload(userchoices)

    try:
        fauxroot.resetLogs()
        reload(fauxconfig)
        
        fauxroot.FAUXROOT = [os.path.join(TEST_DIR, "good-config.1")]

        open("/mnt/by-uuid/4aa8e7c6-24ef-4f3e-9986-e628f7d1d51g/"
             "grub/grub.conf.esx3", 'w').close()
        translateBootCmdLine("bootpart=4aa8e7c6-24ef-4f3e-9986-e628f7d1d51b "
                             "rootpart=4aa8e7c6-24ef-4f3e-9986-e628f7d1d61b")

        got = userchoices.getBootUUID()['uuid']
        assert got == "4aa8e7c6-24ef-4f3e-9986-e628f7d1d51b"
        
        got = userchoices.getRootUUID()['uuid']
        assert got == "4aa8e7c6-24ef-4f3e-9986-e628f7d1d61b"

        raises(SystemExit)(translateBootCmdLine)("bootpart=baduuid")

        translateBootCmdLine(
            "ks=UUID:4aa8e7c6-24ef-4f3e-9986-e628f7d1d51b:/ks.cfg")

        mntPath1 = '/mnt/by-uuid/4aa8e7c6-24ef-4f3e-9986-e628f7d1d51b'
        assert fauxroot.SYSTEM_LOG == [
            ['/bin/bash', '/tmp/initscripts.sh'],
            ['cd', '/', '&&', 'INSTALLER=1', '/init', '14.foobar'],
            ['cd', '/', '&&', 'INSTALLER=1', '/init', '71.bogusipmi'],
            ['echo', 'mkblkdevs', '|', 'nash', '--force'],
            ['/usr/bin/mount', '/dev/sda1', mntPath1],
            ['/usr/bin/umount', mntPath1],
            ['/usr/bin/mount', '/dev/sda1', mntPath1]]
        
        assert fauxroot.WRITTEN_FILES[mntPath1].getvalue() == ""
    finally:
        fauxroot.FAUXROOT = None

def test_netOptions():
    def checkExpected():
        expected = {
            'gateway' : '192.168.2.254',
            'nameserver1' : '',
            'nameserver2' : '',
            'hostname' : 'localhost'
            }
        actual = userchoices.getDownloadNetwork()
        assert actual == expected, actual

        actual = userchoices.getDownloadNic()
        assert actual['device'].name == 'vmnic32'
        assert actual['vlanID'] == '5'
        assert actual['bootProto'] == userchoices.NIC_BOOT_STATIC
        assert actual['ip'] == '192.168.2.1'
        assert actual['netmask'] == '255.255.255.0'
        
    try:
        fauxroot.resetLogs()
        reload(fauxconfig)

        fauxroot.FAUXROOT = [os.path.join(TEST_DIR, "good-config.1")]

        translateBootCmdLine(
            "ip=192.168.2.1 gateway=192.168.2.254 "
            "vlanid=5 "
            "netmask=255.255.255.0 netdevice=00:50:56:C0:00:00")
        checkExpected()

        fauxroot.FAUXROOT = None
        fauxroot.resetLogs()
        reload(fauxconfig)

        fauxroot.FAUXROOT = [os.path.join(TEST_DIR, "good-config.1")]

        translateBootCmdLine(
            "ip=192.168.2.1:192.168.2.2:192.168.2.254:255.255.255.0 "
            "vlanid=5 "
            "BOOTIF=01-00-50-56-C0-00-00")
        checkExpected()

        #TODO: we should really add a negative test case
    finally:
        fauxroot.FAUXROOT = None
