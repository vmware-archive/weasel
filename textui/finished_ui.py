
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

'''Finished installation using text installer.
'''

# NOTE:  This is the rudimentary version, to allow a skeletal text
# install process to complete.  Polished version will have proper IP
# address for URL.

import tidy
import userchoices
from log import log
from textrunner import TextRunner

title = "ESX Install Complete"

congratsText = """\
To manage this server after rebooting, use any browser to open
the URL:
    http://%(ipaddr)s
%(warn)s

 1) Reboot and start ESX.
"""

warnText = """\
Warning:  A service console network interface was not detected or
not configured.  You may need to fix this after reboot.
"""

class FinishedWindow(TextRunner):
    def __init__(self):
        super(FinishedWindow, self).__init__()
        self.start = self.congrats
        self.substep = self.start
        self.ipaddr = "<This machine's IP address>"

    def congrats(self):
        "Get IP address, Show congratulatory message."
        cosNICs = userchoices.getCosNICs()
        warn = ''
        if not cosNICs:
            log.error("No COS network adapter found")
            warn = warnText
        elif 'ip' not in cosNICs[0]:
            log.error("COS network adapter missing IP address")
            warn = warnText
        elif not cosNICs[0]['ip']:
            # COS NIC detected, using DHCP
            pass
        else:
            # COS NIC configured using static IP
            self.ipaddr = cosNICs[0]['ip']
        ui = {
            'title': title,
            'body': congratsText % {
                'ipaddr': self.ipaddr,
                'warn': warn },
            'menu': {
                '1': self.stepForward,
            }
        }
        self.setSubstepEnv(ui)
        # tidy.doit() is run in weasel.py

