
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
from log import log
from consts import HOST_ROOT

SERIAL_NUM_COMPONENT_COUNT = 5
SERIAL_NUM_COMPONENT_SIZE = 5

LICENSE_CHECK_RESULT = {
    # Taken from bora/support/check_serial/checkserial.c
    3 : "The serial number is invalid.",
    4 : "The serial number has expired.",
    5 : "No matching licenses for serial number."
    }

LICENSE_FILES = {
    'vmware.lic' : '00000-00000-00000-00000-00000',
    'license.cfg' : '''\
<ConfigRoot>
  <epoc>AQD+yggAAADiCmBn38isEzQAAABkejVCpdVgHC65kP/1jU+xDb0LTK9yl6er44nh6C71HanhkXnUou5QLMZ4vsD6vtNIJZoD</epoc>
  <mode>eval</mode>
  <owner/>
</ConfigRoot>
''',
    }

class LicenseException(Exception):
    pass

def checkSerialNumber(value):
    args = ["/usr/sbin/check_serial", "-c", value]
    rc = util.execWithLog(args[0], args)
    if rc != 0:
        if os.WIFEXITED(rc):
            code = os.WEXITSTATUS(rc)
        else:
            code = None
        msg = LICENSE_CHECK_RESULT.get(
            code, "Internal error while validating serial number.")
        raise LicenseException(msg)

def hostAction(_context):
    for licenseFileName, licenseContents in LICENSE_FILES.items():
        filePath = os.path.join(HOST_ROOT, 'etc/vmware', licenseFileName)
        licenseFile = open(filePath, 'w')
        licenseFile.write(licenseContents)
        licenseFile.close()
        os.chmod(filePath, 0600)

    choice = userchoices.getSerialNumber()
    if not choice:
        log.info("no license key entered, defaulting to evaluation mode")
        return
    
    for licenseFile in ['license.cfg', 'vmware.lic']:
        filePath = os.path.join(HOST_ROOT, 'etc/vmware', licenseFile)
        os.system('touch %s' % filePath)
        os.chmod(filePath, 0600)

    licFilePath = os.path.join(HOST_ROOT, 'etc/vmware/vmware.lic')
    licFile = open(licFilePath, 'w')
    try:
        licFile.write(choice['esx'])
    finally:
        licFile.close()
