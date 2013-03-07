
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
from StringIO import StringIO

TEST_DIR = os.path.dirname(__file__)

sys.path.append(os.path.join(TEST_DIR, os.path.pardir))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'faux'))
import fauxroot

# Use good-config.1 as the fake configuration.
sys.path.append(os.path.join(os.path.dirname(__file__), 'good-config.1'))
import fauxconfig
sys.path.pop()

import esxupgrade

def _testFilePath(filename):
    return os.path.join(TEST_DIR, "upgrade", filename)

def test_deserializePrecheck():
    def cmpPrecheckDict(precheckName, expectedDict):
        precheckOutput = open(_testFilePath(precheckName)).read()
        actualDict = esxupgrade.deserializePrecheck(precheckOutput)

        print expectedDict
        print " ----"
        print actualDict
        assert expectedDict == actualDict

    cases = [
        ("precheck.0.xml", {'errors' : [], 'warnings' : [], 'info' : {},
                            'vmdk': [], 'vmfsSpaceRequired': 8000}),
        ("precheck.fail.xml",
         { 'errors' : [{'result' : 'ERROR',
                        'name' : 'SUPPORTED_CPU',
                        'expected' : 'True',
                        'found' : 'False'}],
           'warnings' : [],
           'info' : {},
           'vmdk': [],
           'vmfsSpaceRequired': 8000}),
        ]

    for precheckName, expectedDict in cases:
        yield cmpPrecheckDict, precheckName, expectedDict

def test_convertPrecheckToKickstart():
    def cmpKickstart(precheckName, kickstartName, config):
        precheckOutput = open(_testFilePath(precheckName)).read()
        expectedKickstart = open(_testFilePath(kickstartName)).read()
        precheckDict = esxupgrade.deserializePrecheck(precheckOutput)

        assert precheckDict['errors'] == []

        actualKickstart = esxupgrade.convertPrecheckToKickstart(
            precheckDict, config)

        print actualKickstart
        assert expectedKickstart == actualKickstart

    cases = [
        ("precheck.0.xml", "upgrade.0.ks", {
                'datastoreName' : 'Storage 2',
                'extraSpace' : 4000,
                'extraSpaceFlag' : ' --extraspace=4000',
                'reboot': 'reboot',
                'removeISO' : '',
                'post' : '%post\necho Hello, World\n'}),
        ]

    for precheckName, kickstartName, config in cases:
        yield cmpKickstart, precheckName, kickstartName, config

EXPECTED_FAIL_OUTPUT = """\
WARNING: The /boot partition is on an unsupported disk type.
WARNING: The following PCI devices may not be supported: 8086:27e2, 8086:244e
ERROR: A 64-bit CPU is required.
ERROR: At least 110 MB of free disk space on the root partition is required, found 50 MB.
ERROR: At least 140 MB of free disk space on the /boot partition is required, found 50 MB.
ERROR: At least 1023 MB of memory is required, found 512 MB.
ERROR: /boot/grub/grub.conf is missing/invalid.
ERROR: /etc/vmware/esx.conf is missing/invalid.
ERROR: unknown precheck test
ERROR: Not enough free space for VMDK on datastore Storage 1 (need 80000000MB, 60860MB available)
"""
        
def test_precheckFail():
    '''Make sure esxupgrade parses all of the precheck failures correctly.'''
    
    fauxroot.resetLogs()
    
    failFile = open(os.path.join(TEST_DIR, "upgrade", "precheck.allfail.xml"))
    try:
        failOutput = failFile.read()
    finally:
        failFile.close()

    oldStderr = sys.stderr
        
    fauxroot.FAUXROOT = [os.path.join(TEST_DIR, "good-config.1")]
    try:
        open("/esx4-upgrade/isoinfo", "w").write("# empty\n")
        open("/mnt/cdrom/initrd.img", "w").write("# empty\n")
        os.makedirs("/vmfs/volumes/Storage 1")

        def precheck(_argv):
            return (failOutput, 0)
            
        fauxroot.EXEC_FUNCTIONS["python"] = precheck

        sys.stderr = StringIO()
        
        esxupgrade.main(["esxupgrade.py", "Storage 1"])

        actualOutput = sys.stderr.getvalue()

        print actualOutput
        assert actualOutput == EXPECTED_FAIL_OUTPUT
    finally:
        fauxroot.FAUXROOT = None
        sys.stderr = oldStderr
