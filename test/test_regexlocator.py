
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


import re
import os
import sys

TEST_DIR = os.path.dirname(__file__)

sys.path.append(os.path.join(TEST_DIR, os.path.pardir))
from regexlocator import RegexLocator

def validateRegex(name, inputToTest, expectedResult):
    regexToTest = getattr(RegexLocator, name)
    matched = re.match('^(' + regexToTest + ')$', inputToTest) is not None
    assert matched == expectedResult

def testRegexes():

    # Hash of regex names to a list of test cases to run.  Each test case is
    # a pair containing the string to test and the expected yes/no match result
    inputs = {
        "bootloader" : [
        ("mbr", True),
        ("none", True),
        ("partition", True),

        ("mbrfoo", False),
        ],

        # To generate, run grub and use the md5crypt command.
        "md5" : [
        ("$1$7U8tB$KvxsVx7VskMJuUtaDG.Z01", True),
        ("$1$7U8tB$KvxsVx7VskMJuUtaDG.Z01/", True),

        ("dfkjld", False),
        ("$1$7U8tB$KvxsVx7VskMJuUtdsfagaaDG.Z01/a", False),
        ],
        
        "directory" : [
        ("/", True),
        ("/foo/bar", True),
        ("/foo/bar/", True),
        
        ("foo/bar", False),
        ("foo", False),
        ],

        "mountpoint" : [
        ("None", True),
        ("/", True),
        ("/var/log", True),
        ("/var/log/", True),
        ("swap", True),
        ],

        "vmdkname" : [
        ("cos", True),
        ("foobar1234", True),

        ("/cos", False),
        ("foo/bar", False),
        ]
        }

    for name in inputs:
        for inputToTest, expectedResult in inputs[name]:
            yield validateRegex, name, inputToTest, expectedResult
