
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

sys.path.append(os.path.join(os.path.dirname(__file__), os.path.pardir))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'faux'))
import fauxroot

sys.path.append(os.path.join(os.path.dirname(__file__), 'good-config.1'))
import fauxconfig
sys.path.pop()

from nose.tools import raises

def teddst_exit():
    import weasel
    import scui
    
    oldScui = scui.Scui

    def explode(_arg):
        assert False
    def noop(_arg):
        return

    scui.Scui = explode
    raises(AssertionError)(weasel.main)(['weasel', '-s', 'ks.cfg'])
    
    scui.Scui = noop
    assert weasel.main(['weasel', '-s', 'ks.cfg']) == 0
    
    scui.Scui = oldScui
