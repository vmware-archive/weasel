
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
import tempfile

TEST_DIR = os.path.dirname(__file__)

sys.path.insert(0, os.path.join(TEST_DIR, "faux"))
import fauxroot

sys.path.append(os.path.join(TEST_DIR, os.path.pardir))

import script
import userchoices
import applychoices

def testEmptyPostScript():
    reload(userchoices)
    
    def emptyPostBinSh(argv):
        assert 0, "there is no post-script, so we should not get here"
    fauxroot.EXEC_FUNCTIONS['/bin/sh'] = emptyPostBinSh

    context = applychoices.Context(applychoices.ProgressCallback())
    script.hostActionPostScript(context)

    del fauxroot.EXEC_FUNCTIONS['/bin/sh']

def testPostScript():
    reload(userchoices)

    # Setup our fake '/bin/sh' executable that just checks its args.
    def postBinSh(argv):
        assert argv[0] == '/bin/sh'
        assert argv[1] == '/tmp/ks-script'
        postBinSh.ran = True
        
        return 0
    postBinSh.ran = False
    fauxroot.EXEC_FUNCTIONS['/bin/sh'] = postBinSh

    # setup a temporary directory for testing
    tmproot = tempfile.mkdtemp(suffix='test_script')
    try:
        os.makedirs(os.path.join(tmproot, 'mnt/sysimage', 'tmp'))
        os.chroot(tmproot)

        # set a script to run.
        userchoices.addPostScript(script.Script(
            '''#! /bin/sh

            echo Hello, World!
            ''',
            '/bin/sh',
            True,
            0,
            False))
        context = applychoices.Context(applychoices.ProgressCallback())
        script.hostActionPostScript(context)
        assert postBinSh.ran, "the post script was not run?!"

        assert not os.path.exists(os.path.join(
            'mnt/sysimage', 'tmp', 'ks-script')), \
            "post script was not generated?"
    finally:
        fauxroot.FAUXROOT = None # clear out our fake chroot

        os.removedirs(os.path.join(tmproot, 'mnt/sysimage', 'tmp'))
        
        del fauxroot.EXEC_FUNCTIONS['/bin/sh']
