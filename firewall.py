
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
import util
import userchoices

from consts import HOST_ROOT
from exception import InstallationError

def hostAction(_context):
    choices = userchoices.getESXFirewall()

    if choices:
        if choices['incoming'] == userchoices.ESXFIREWALL_ALLOW:
            incomingFlag = "--allowIncoming"
        else:
            incomingFlag = "--blockIncoming"
        if choices['outgoing'] == userchoices.ESXFIREWALL_ALLOW:
            outgoingFlag = "--allowOutgoing"
        else:
            outgoingFlag = "--blockOutgoing"

        try:
            util.execCommand("/usr/sbin/esxcfg-firewall %s %s" % (
                    incomingFlag, outgoingFlag),
                             root=HOST_ROOT,
                             raiseException=True)
        except Exception, e:
            raise InstallationError(
                "Could not change global firewall rules.", e)

    for rule in userchoices.getPortRules():
        args = ["/usr/sbin/esxcfg-firewall"]

        if rule['state'] == userchoices.PORT_STATE_OPEN:
            args += ["--openPort",
                     "%(number)s,%(protocol)s,%(direction)s,%(name)s" % rule]
        else:
            args += ["--closePort",
                     "%(number)s,%(protocol)s,%(direction)s" % rule]
        
        # esxcfg-firewall fails if --closePort is used on an already closed port
        try:
            util.execWithLog(args[0], args, root=HOST_ROOT, raiseException=True)
        except util.ExecError, e:
            if rule['state'] == userchoices.PORT_STATE_OPEN:
                raise InstallationError(
                    "Could not %(state)s port %(number)s in the firewall." %
                    rule, e)
        except Exception, e:
            raise InstallationError(
                "Could not %(state)s port %(number)s in the firewall." %
                rule, e)
            
    serviceRules = userchoices.getServiceRules()

    # If we've set the time from an NTP server, we also need to open port 123
    isNTP = bool(userchoices.getTimedate().get('ntpServer'))
    if isNTP:
        # TODO: a user-specified NTP service rule should trump this implicit 
        # setting however this shouldn't come up in Kandinsky because 
        # scripted install doesn't let you set the ntp server, and the 
        # GUI / Text installs don't let you set up firewall rules
        serviceRules.append({'state': userchoices.PORT_STATE_ON,
                             'serviceName': 'ntpClient'})

    for service in serviceRules:
        args = ["/usr/sbin/esxcfg-firewall"]

        if service['state'] == userchoices.PORT_STATE_ON:
            args += ["--enableService", service['serviceName']]
        else:
            args += ["--disableService", service['serviceName']]

        try:
            util.execWithLog(args[0], args, root=HOST_ROOT, raiseException=True)
        except Exception, e:
            raise InstallationError(
                "Could not turn %(state)s %(serviceName)s in the firewall." % 
                service, e)

def tidyAction():
    # XXX Using iptables isn't the recommended way to do this, but it works.
    # We need to make sure the firewall is down to let any necessary network
    # traffic through, like nfs umount stuff.
    args = ["/etc/init.d/iptables", "stop"]
    if os.path.exists(os.path.join(HOST_ROOT, args[0].lstrip('/'))):
        util.execWithLog(args[0], args, root=HOST_ROOT)
