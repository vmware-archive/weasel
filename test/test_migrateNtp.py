
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
import glob

TEST_DIR = os.path.dirname(__file__)
sys.path.append(os.path.join(TEST_DIR, os.path.pardir))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'faux'))
import fauxroot

sys.path.append(os.path.join(os.path.dirname(__file__), 'good-config.1'))
import fauxconfig
sys.path.pop()

import consts

import migration
from migration.simple import migrateActionNtp, migrateActionNtpd

def test_migrateNtp():
    def cmpNtpConf(path, expectedAccum, expectedHandlers):
        accum = []
        fullPath = os.path.join(TEST_DIR, "upgrade", path)
        rc = migrateActionNtp(fullPath, "", accum)
        assert rc
        assert accum == expectedAccum

        for path, handler in expectedHandlers:
            assert path in migration.MIGRATION_HANDLERS
            assert migration.MIGRATION_HANDLERS[path] == handler
        
    cases = [
        ("ntp.conf.0",
         ["/var/lib/ntp/drift", "/etc/ntp/keys",],
         [],
         ),
        
        ("ntp.conf.1",
         ["/var/lib/ntp/ntp.drift",
          "/var/log/ntpstats/",
          "/foo",
          "/etc/custom.ntp.conf",],
         [("/etc/custom.ntp.conf", migrateActionNtp)],
         ),
        ]
    
    for path, expectedAccum, expectedHandlers in cases:
        yield (cmpNtpConf, path, expectedAccum, expectedHandlers)

def test_migrateNtpd():
    try:
        fauxroot.FAUXROOT = ["good-config.1"]
        
        open('/ntpd.old', 'w').write(
            'OPTIONS="-U \'ntp-edited\' -T /foo-U -e $(TIME)"\n')
        
        accum = []
        migrateActionNtpd('/ntpd.old', '/ntpd.new', accum)

        actual = open('/ntpd.new').read()
        expected = 'OPTIONS="-u \'ntp-edited\' -i /foo-U "\n'
        
        assert actual == expected
    finally:
        fauxroot.FAUXROOT = []
