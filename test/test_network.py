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

'''
Test suite for the network module
'''
import os
import sys
import doctest

TEST_DIR = os.path.dirname(__file__)

sys.path.append(os.path.join(TEST_DIR, os.path.pardir))
sys.path.insert(0, os.path.join(TEST_DIR, 'faux')) #for vmkctl

from networking.utils import *
import networking.utils
import userchoices
import log

from nose.tools import raises

def messageGotLogged(exerciseFn, expectedMsgFragment):
    import logging
    from StringIO import StringIO
    strStream = StringIO()
    sHandler = logging.StreamHandler(strStream)
    log.log.addHandler(sHandler)

    exerciseFn()
    
    sHandler.flush()
    log.log.removeHandler(sHandler)
    strStream.seek(0)

    return expectedMsgFragment in strStream.read()

def test_utilsDoctests():
    failures, numRun = doctest.testmod(networking.utils)
    assert failures == 0, 'Some doctests failed'

def test_sanityCheckers():
    sanityCheckHostname("foobar")
    sanityCheckIPString("123.123.123.123")
    sanityCheckNetmaskString("255.0.0.0")

def test_calculations():
    assert calculateNetmask("192.168.1.4") == '255.255.255.0'
    assert ipStringToNumber("192.168.1.5") == 3232235781
    assert ipNumberToString(3232235781) == '192.168.1.5'
    assert calculateGateway("192.168.1.5", "255.255.255.0") == '192.168.1.254'
    assert calculateNameserver("192.168.1.5", "255.255.255.0") == '192.168.1.1'

def test_formatting():
    assert formatIPString("123.034.099.100") == '123.34.99.100'
    assert formatIPString("0.0") == ''

def test_sanityCheckersFail():
    raises(ValueError)(sanityCheckHostname)("foobar.*.com")
    raises(ValueError)(sanityCheckHostname)("foobar.^.com")
    raises(ValueError)(sanityCheckHostname)("a.&.b")

    raises(ValueError)(sanityCheckIPString)("1.1.1.256")
    raises(ValueError)(sanityCheckIPString)("-1.1.1.1")
    raises(ValueError)(sanityCheckIPString)("1.1.1")

    raises(ValueError)(sanityCheckGatewayString)("1.1.1")
    raises(ValueError)(sanityCheckGatewayString)("0.1.1.1")

    raises(ValueError)(sanityCheckNetmaskString)("1.1.1")
    raises(ValueError)(sanityCheckNetmaskString)("0.1.1.1")

    def exerciseFn():
        sanityCheckHostname("3foobar")

    assert messageGotLogged(exerciseFn, 'starts with a digit')

def test_formattingFail():
    raises(ValueError)(formatIPString)("foobar")
    raises(ValueError)(formatIPString)(".")


if __name__ == "__main__":

    #if the user specifies a specific test to run, just run that then exit
    testName = None
    try:
        testName = sys.argv[1]
    except IndexError:
        print 'Usage:'
        print 'You can run this test suite using nosetests:'
        print '$ nosetests -d '+ __file__
        print 'You can run an individual test by running:'
        print '$ '+ __file__ +' <test name>'

    if testName:
        print "________Just running ", testName
        locals()[testName]()
        print "________PASSED"
        sys.exit()
