#! /usr/bin/env python

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
The networking package.

Modules and functions for actions related to NICs, IP addresses,
hostnames, virtual switches, and configuring the host's network settings
'''

import utils
from host_config import config
from networking_base import \
                            ConnectException, \
                            WrappedVmkctlException, \
                            init, \
                            connected, \
                            cosConnect, \
                            cosConnectForInstaller, \
                            iScsiConnectForInstaller, \
                            getPluggedInAvailableNIC, \
                            getPhysicalNics, \
                            getVirtualSwitches, \
                            getVirtualNics, \
                            getVmKernelNics, \
                            findPhysicalNicByName, \
                            findPhysicalNicByMacAddress, \
                            PhysicalNicFacade, \
                            VirtualSwitchFacade, \
                            VirtualNicFacade, \
                            VmKernelNicFacade, \
                            StaticIPConfig, \
                            DHCPIPConfig, \
                            hostAction, \
                            hostActionUpdate
