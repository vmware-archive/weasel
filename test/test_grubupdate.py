
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
import shlex

TEST_DIR = os.path.dirname(__file__)

sys.path.append(os.path.join(TEST_DIR, os.path.pardir))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'faux'))
import fauxroot

sys.path.append(os.path.join(os.path.dirname(__file__), 'good-config.1'))
import fauxconfig
sys.path.pop()

def _testFilePath(filename):
    return os.path.join(TEST_DIR, "upgrade", filename)

import grubupdate

def test_removeTitle():
    def cmpBeforeAfter(confName, title, expectedName):
        conf = open(_testFilePath(confName)).read()
        got = grubupdate.removeTitle(conf, title)
        expected = open(_testFilePath(expectedName)).read()
        assert got == expected

    cases = [
        ("remove-before.0", "title VMware ESX Server", "remove-after.0"),
        ("remove-before.0", "VMware ESX Server", "remove-before.0"),
        ]

    for confName, title, expectedName in cases:
        yield cmpBeforeAfter, confName, title, expectedName

def test_extractBootFiles():
    fauxroot.resetLogs()

    fauxroot.FAUXROOT = [os.path.join(TEST_DIR, "good-config.1")]

    try:
        kernelPath, initrdPath = grubupdate.extractBootFiles("/installer.iso")
        assert kernelPath == "/esx4-upgrade/vmlinuz"
        assert initrdPath == "/esx4-upgrade/initrd.img"

        got = fauxroot.SYSTEM_LOG
        assert got == [
            ['/esx4-upgrade/isoinfo', '-x', '/ISOLINUX/VMLINUZ.;1',
             '-i', '/installer.iso',
             '>', '/esx4-upgrade/vmlinuz'],
            ['/esx4-upgrade/isoinfo', '-x', '/ISOLINUX/INITRD.IMG;1',
             '-i', '/installer.iso',
             '>', '/esx4-upgrade/initrd.img']
            ]
        assert fauxroot.WRITTEN_FILES[kernelPath].getvalue() == \
               "# contents of /ISOLINUX/VMLINUZ.;1 from /installer.iso\n"
        assert fauxroot.WRITTEN_FILES[initrdPath].getvalue() == \
               "# contents of /ISOLINUX/INITRD.IMG;1 from /installer.iso\n"
    finally:
        fauxroot.FAUXROOT = None

def test_uuidForDevice():
    fauxroot.resetLogs()
    reload(fauxconfig)
    try:
        fauxroot.FAUXROOT = [os.path.join(TEST_DIR, "good-config.1")]
        got = grubupdate.uuidForDevice("/dev/sda1")
    finally:
        fauxroot.FAUXROOT = []
        
    print got
    assert got == '4aa8e7c6-24ef-4f3e-9986-e628f7d1d51b'

def test_shquote():
    def cmpQuotedString(stringToQuote):
        shellString = "'%s'" % grubupdate.shquote(stringToQuote)
        actual = shlex.split(shellString)[0]
        
        assert stringToQuote == actual
        
    stringsToQuote = [
        'string with a space',
        'string with a "double quote"',
        "string with a 'single quote'",
        ]

    for elem in stringsToQuote:
        yield cmpQuotedString, elem
