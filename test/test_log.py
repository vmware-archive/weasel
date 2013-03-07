
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
import logging
from StringIO import StringIO

TEST_DIR = os.path.dirname(__file__)
sys.path.append(os.path.join(TEST_DIR, '..'))

from log import log

def testURLPasswordFilter():
    def cmpLogRecords(msg, expected):
        strStream = StringIO()
        sHandler = logging.StreamHandler(strStream)
        log.addHandler(sHandler)
        log.info(msg)
        log.removeHandler(sHandler)

        got = strStream.getvalue()
        
        assert got == ("%s\n" % expected), (got, expected)

    cases = [
        ("Creating Package object for ftp://user1:secret@10.20.123.73/foo.rpm",
         "Creating Package object for ftp://user1:XXXXXX@10.20.123.73/foo.rpm"),

        ("http://foo:blah@bar:8080/boo", "http://foo:XXXXXX@bar:8080/boo"),
        ("http://blah:8080/boo", "http://blah:8080/boo"),

        ("http://blah/boo", "http://blah/boo"),
        ]

    for msg, expected in cases:
        yield cmpLogRecords, msg, expected
