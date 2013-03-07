'''Infrastructure for testing configuration migration code.'''

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
import consts

TEST_DIR = os.path.dirname(__file__)
import fauxroot
import difflib

def copyIntoRoot(src, root, dst):
    try:
        contents = open(src).read()
        fauxroot.FAUXROOT = [root]
        open(dst, 'w').write(contents)
    finally:
        fauxroot.FAUXROOT = None

def cmpMigratedFiles(func, hostPath, oldPath, newPath, expectedPath,
                     sideEffects=None, setupFunc=None):
    '''Comparator for migration functions.

    This comparator will setup the fake environment with the given files,
    execute the migration function, and then check the resulting file to ensure
    it is correct.

    func - The host-action migration function to execute.
    hostPath - The path of the file on the host (e.g. "/etc/passwd").
    oldPath - The path of the file in test/upgrade that contains the ESX v3
      configuration.
    newPath - The path of the file in test/upgrade that contains the ESX v4
      configuration or None for an empty file.
    expectedPath - The path of the file in test/upgrade that contains the
      expected result of the migration.
    sideEffects - An optional function that should be called to test for other
      side effects, like commands that needed to be executed.
    '''

    # Read in the contents of the files
    oldContents = open(os.path.join(TEST_DIR, "upgrade", oldPath)).read()
    if newPath is not None:
        newContents = open(os.path.join(TEST_DIR, "upgrade", newPath)).read()
    else:
        newContents = ""
    expected = open(os.path.join(TEST_DIR, "upgrade", expectedPath)).read()
    
    try:
        fauxroot.resetLogs()

        # Set the fake chroot and
        fauxroot.FAUXROOT = [os.path.join(TEST_DIR, "good-config.1")]

        # ... write the files to the fake environment.
        open(os.path.join(consts.HOST_ROOT + consts.ESX3_INSTALLATION,
                          hostPath),
             'w').write(oldContents)
        open(os.path.join(consts.HOST_ROOT, hostPath),
             'w').write(newContents)

        if setupFunc:
            setupFunc()

        # Execute the migration in the fake environment.
        func(None)

        # Read back the file and
        actual = open(os.path.join(consts.HOST_ROOT, hostPath)).read()

        # ... produce a diff for easy reading.
        diffLines = [line for line in difflib.unified_diff(
            actual.split('\n'), expected.split('\n'))]
        if diffLines:
            print " ** DIFF **"
            print "\n".join(diffLines)

        assert actual == expected

        if sideEffects:
            sideEffects()
    finally:
        fauxroot.FAUXROOT = None
