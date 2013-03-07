#! /usr/bin/env python

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


"""
Usage: python test_review.py .bs-file

The .bs files are in bora/server/weasel/test/scriptedinstall/files.
Those whose names start with "simple." are your best bet for being mostly
complete.
"""

import sys
import os
import getopt

TEST_DIR = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(TEST_DIR, "faux"))
sys.path.append(os.path.join(TEST_DIR, '..'))
sys.path.append(os.path.join(TEST_DIR, '../gui'))
sys.path.append(os.path.join(TEST_DIR, '../textui'))
sys.path.append(os.path.join(TEST_DIR, "../../../../apps/scripts/"))

import fauxroot
import test_scriptedinstall
import gui
import review_ui

def usage():
    print "Usage: test_review.py [-hgt] <kickstart-file1>"
    print
    print "Display the review for the configuration given in the kickstart"
    print "file."
    print
    print "Options:"
    print "  -h    Display this help message."
    print "  -g    Display the review in gui mode. (default)"
    print "  -t    Display the review in text mode."
    return

if __name__ == '__main__':
    try:
        (opts, args) = getopt.getopt(sys.argv[1:], "htg")

        mode = "gui"
        for opt, arg in opts:
            if opt == '-t':
                mode = "text"
            elif opt == '-g':
                mode = "gui"
            elif opt == '-h':
                usage()
                sys.exit(0)

        if not args:
            raise getopt.error("no kickstart files given")
        
        for fileName in args:
            #
            # Populate the userchoices singleton.
            #
            fauxroot.FAUXROOT = [os.path.join(TEST_DIR, "good-config.1")]
            si = test_scriptedinstall.ScriptedInstallPreparser(fileName)
            (result, errors, warnings) = si.preParse()
            if result == test_scriptedinstall.Result.FAIL:
                print "result=", result
                print '\n'.join(errors)
                print '\n'.join(warnings)
                fauxroot.FAUXROOT = None
                continue

            if mode == "gui":
                sys.argv[1] = 'review'
                gui.DebugCheatingOn()
                gui.Gui()
            elif mode == "text":
                rw = review_ui.ReviewWindow()
                rw.run()

            fauxroot.FAUXROOT = None
    except getopt.error, e:
        sys.stderr.write("error: %s\n" % str(e))
        usage()
        sys.exit(1)
