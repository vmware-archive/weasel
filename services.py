
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

''' services.py

This module deals with system services in the cos.
'''

import util
import userchoices
from consts import HOST_ROOT

def hostAction(_context):
    cmd = "/sbin/chkconfig"
    # Turn these guys off for the sake of security.
    util.execWithLog(cmd, [cmd, "netfs", "off"], root=HOST_ROOT)
    util.execWithLog(cmd, [cmd, "nfslock", "off"], root=HOST_ROOT)
    util.execWithLog(cmd, [cmd, "portmap", "off"], root=HOST_ROOT)
    # our firewall script does what is necessary
    util.execWithLog(cmd, [cmd, "iptables", "off"], root=HOST_ROOT)
    
    # on cos 26 chkconfig --add doesn't turn the service on.
    util.execWithLog(cmd, [cmd, "sshd", "on"], root=HOST_ROOT)

    # If we've set the time from an NTP server, we need to start ntpd
    isNTP = bool(userchoices.getTimedate().get('ntpServer'))
    if isNTP:
        util.execWithLog(cmd, [cmd, "ntpd", "on"], root=HOST_ROOT)
