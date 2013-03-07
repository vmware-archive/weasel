
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

sys.path.insert(0, os.path.join(TEST_DIR, "faux"))
sys.path.insert(1, TEST_DIR+'/..')

DEFAULT_CONFIG_NAME = "good-config.1"
sys.path.append(os.path.join(os.path.dirname(__file__), DEFAULT_CONFIG_NAME))
import fauxconfig
sys.path.pop()

import iscsi

def test_iqn():
    '''Generator that tries out a bunch of valid and invalid IQNs'''

    # Second element of each tuple indicates whether the first element is a
    # valid IQN.
    iqns = [('iqn.2002-02.com.vmware', True),
            ('iqn.2002-02.com.vmware:anythingY0u :L1ke', True),
            ('IQN.1996-04.org.trhj', False),                    # capital IQN
            ('IQN.1914-07.at.ferd.franz', False),               # Too old
            ('qnn.2002-02.com.vmware', False),                  # qnn
            ('iqn.2002-13.com.vmware', False),                  # month
            ('iqn.2002-02-31.edu.walden', False),               # date format
            ('', False),
            ('iqn.2002-10.com.fo o', False),                    # space
            ('iqn.2002-10.:org.bar', False),                    # no domain
            ('iqn.2002-02.edu.walden.', False)                  # trailing '.'
           ]
        
    for iqn in iqns:
        yield check_one_iqn, iqn


def check_one_iqn(iqn):
    try:
        iscsi.validateIQN(iqn[0])
    except ValueError:
        assert not iqn[1]
    else:
        assert iqn[1]
