
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

from _util import *
from log import log
try:
    from libutil import getUuid, syncKernelBufferToDisk
except ImportError:
    log.debug("Failed import of 32-bit libutil.  (OK, going to faux...)")

__all__ = [
    'SIZE_GB',
    'SIZE_MB',
    'SIZE_TB',
    'ExecError',
    'execWithCapture',
    'execWithRedirect',
    'execWithRedirectAndCapture',
    'execWithLog',
    'formatValue',
    'formatValueInMegabytes',
    'getValueInMegabytesFromSectors',
    'getValueInSectorsFromMegabyes',
    'getfd',
    'getUuid',
    'syncKernelBufferToDisk',
]

