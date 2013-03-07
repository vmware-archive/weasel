
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

sys.path.append(os.path.join(os.path.dirname(__file__), 'good-config.1'))
import fauxconfig

import precheck

def test_default_cos():
    '''Generator that returns several different cos sizes'''

    cases = [ {'memSize' : 2147418112,
               'expectedCosSize' : 300 },
              {'memSize' : 21474181120,
               'expectedCosSize' : 432 },
              {'memSize' : 41474181120,
               'expectedCosSize' : 528 },
              {'memSize' : 341474181120,
               'expectedCosSize' : 800 },
            ]

    def compareCosMemSize(memSize, expectedCosSize):
        physicalMem = memSize / 1024 / 1024
        assert precheck.getConsoleMemorySize(272, physicalMem) == expectedCosSize
        
    for case in cases:
        yield compareCosMemSize, case['memSize'], case['expectedCosSize']

