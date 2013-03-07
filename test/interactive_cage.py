#! /usr/bin/python

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

'''
Run this from the root weasel directory to interactively play with modules
in a caged environment
'''

import os

if not os.path.exists('test/good-config.1/'):
    print 'Must be run from the root Weasel directory'
    exit(1)

# ipython needs the *real* user's home dir
HOME = os.environ['HOME']
fake_home = 'test/good-config.1/' + HOME
if not os.path.exists(fake_home):
    print 'Making a symlink from %s to %s' % (fake_home, HOME)
    os.symlink(HOME, fake_home)

# the caging of the weasel...
import sys
sys.path.insert(0, 'test/faux')
sys.path.append('test/good-config.1/')
import fauxroot
import fauxconfig
fauxroot.FAUXROOT = ['test/good-config.1/']

# start ipython
from IPython.Shell import IPShellEmbed
shell = IPShellEmbed()
shell()

