
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

'''Wrapper that runs weasel in the faux chroot environment.

This module is useful for testing weasel on your desktop and should also make
it easier to test odd/broken hardware configurations.  For example, to run
through most of a GUI install with the default "good-config.1" configuration:

  $ python test/caged_weasel.py weasel.py --nox

See test/faux/fauxroot.py, test/good-config.1/fauxconfig.py
'''

import os
import sys
import logging
import string

try:
    TEST_DIR = os.path.dirname(__file__)
except NameError:
    # pdb doesn't initialize __file__; get TEST_DIR from alternate source.
    # assumes invocation as: pdb test/caged_weasel.py ...
    TEST_DIR = os.path.abspath(os.path.dirname(sys.argv[0]))

sys.path.insert(0, os.path.join(TEST_DIR, "faux"))

chrootConfig = os.environ.get("CHROOT_CONFIG",
                              os.path.join(TEST_DIR, "good-config.1"))
sys.path.append(chrootConfig)
sys.path.append(os.path.join(TEST_DIR, "../../../../apps/scripts/"))
sys.path.append(os.path.join(TEST_DIR, "../../../../support/scripts/"))

import fauxroot
import fauxconfig
import parted
import log

fauxroot.FAUXROOT = [chrootConfig]

if len(sys.argv) < 2:
    print "usage: %s <module-file> [arg1 arg2 ...]" % sys.argv[0]
    print
    print "Environment:"
    print "  CHROOT_CONFIG       The name of the configuration to use."
    print "                      Default (and only one at the moment): good-config.1"
    print "  VERBOSE             Set this to print out the full contents of"
    print "                      captured files."
    print "  SLOWNESS            Set the amount of artificial slowness."
    print "                      (default: 1)."
    print
    print "Examples:"
    print "  To open the 'installlocation' screen:"
    print "    $ python test/caged_weasel.py test/skip_to_step.py installlocation"
    print
    print "  To run through a GUI installation:"
    print "    $ python test/caged_weasel.py weasel.py --nox"
else:
    os.environ['G_DEBUG'] = 'fatal-warnings'

    try:
        # XXX Need to repair the file log since the log module gets imported
        # before the FAUXROOT is all setup.
        log.handler2 = logging.FileHandler('/var/log/weasel.log')
        log.handler2.setFormatter(log.formatterForLog)
        log.log.addHandler(log.handler2)
    except IOError:
        #Could not open for writing.  Probably not the root user
        pass
    
    try:
        fauxroot.SIMULATION_SLOWNESS = int(os.environ.get("SLOWNESS", "1"))
    except ValueError:
        fauxroot.SIMULATION_SLOWNESS = 1
        
    sys.argv = sys.argv[1:]
    __file__ = sys.argv[0]
    __name__ = "__main__"
    try:
        execfile(__file__)
    finally:
        fauxroot.FAUXROOT = []

        print "SYSTEM_LOG:"
        print " ", "\n  ".join(map(str, fauxroot.SYSTEM_LOG))

        print
        for path, dev in parted.PARTED_DEV_CONFIG.items():
            print "%s PARTITIONS:" % path
            print "\n".join(map(repr, dev.committedPartitions))

        print
        print "SLEEP_LOG: %s" % str(fauxroot.SLEEP_LOG)

        verbose = False
        if os.environ.get("VERBOSE", False):
            verbose = True
        
        print
        print "WRITTEN_FILES:"
        for path in fauxroot.WRITTEN_FILES:
            print path
            content = fauxroot.WRITTEN_FILES[path].getvalue()
            nonPrintableChars = (char for char in content
                                 if char not in string.printable)
            for char in nonPrintableChars:
                # hit one.  that means the content had non-printables
                content = "<Non-Printable File>" #perhaps repr..?
                break

            if verbose:
                print "  " + (content.replace('\n', '\n  '))
            else:
                lines = content.split('\n')
                print "  " + '\n  '.join(lines[0:5])
