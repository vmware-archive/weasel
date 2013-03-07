
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
import glob
import doctest

TEST_DIR = os.path.dirname(__file__)

sys.path.append(os.path.join(TEST_DIR, os.path.pardir))

sys.path.append(os.path.join(TEST_DIR, "scriptedinstall", "files"))
sys.path.insert(0, os.path.join(TEST_DIR, 'faux'))
import fauxroot

# For pciidlib
sys.path.append(os.path.join(TEST_DIR, "../../../../apps/scripts/"))

DEFAULT_CONFIG_NAME = "good-config.1"
sys.path.append(os.path.join(TEST_DIR, DEFAULT_CONFIG_NAME))
import fauxconfig
sys.path.pop()

def test_text():
    def runDoctest(fileName):
        failures, _total = doctest.testfile(fileName,
                                            report=True,
                                            optionflags=(doctest.REPORT_UDIFF|
                                                         doctest.ELLIPSIS))
        assert failures == 0

    allTests = (glob.glob(os.path.join("textui_test", "positive.*")) +
                glob.glob(os.path.join("textui_test", "negative.*")))
    for fileName in allTests:
        yield runDoctest, fileName
