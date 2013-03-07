
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

import re
import os
import sys
from datetime import datetime

TEST_DIR = os.path.dirname(__file__)

sys.path.append(os.path.join(TEST_DIR, os.path.pardir))
from timezone import *

def test_cmp():
    assert cmpOffsetString('UTC-00:00', 'UTC+00:00') == 0


def test_hostActionTimezone():
    pass

def test_GetTextOrEmpty():
    from xml.dom import minidom
    a = '<foo><bar /></foo>'
    b = '<foo> bar </foo>'
    aDom = minidom.parseString(a)
    bDom = minidom.parseString(b)

    assert GetTextOrEmpty(aDom, 'foo') == ''
    assert GetTextOrEmpty(bDom, 'foo') == ' bar '
    

def test_Timezone_constructor():
    tz = Timezone('z', 'UTC+00:00', 'Pantstopia', 'pants')
    assert tz.zoneName == 'z'
    assert tz.offset == 'UTC+00:00'
    assert tz.city == 'Pantstopia'
    assert tz.cityOffsetName == 'pants'
    assert tz.offsetPos == None
    assert tz.cityPos == None

    tz = Timezone('z', 'UTC+00:00', 'Pantstopia', 'pants', '', '')
    assert tz.zoneName == 'z'
    assert tz.offset == 'UTC+00:00'
    assert tz.city == 'Pantstopia'
    assert tz.cityOffsetName == 'pants'
    assert tz.offsetPos == None
    assert tz.cityPos == None

    tz = Timezone('z', 'UTC+00:00', 'Pantstopia', 'pants', '5,6', '9,9')
    assert tz.zoneName == 'z'
    assert tz.offset == 'UTC+00:00'
    assert tz.city == 'Pantstopia'
    assert tz.cityOffsetName == 'pants'
    print tz.offsetPos
    assert tz.offsetPos == [5,6]
    assert tz.cityPos == [9,9]

    tz = Timezone(u'z', u'UTC+00:00', u'Pantstopia', u'pants', u'5,6', u'9,9')
    assert tz.zoneName == 'z'
    assert tz.offset == 'UTC+00:00'
    assert tz.city == 'Pantstopia'
    assert tz.cityOffsetName == 'pants'
    print tz.offsetPos
    assert tz.offsetPos == [5,6]
    assert tz.cityPos == [9,9]

def test_Timezone_runtimeAction():
    tz = Timezone('US/Pacific', 'UTC-08:00', 'Pantstopia', 'pants')
    tz.runtimeAction()
    clock = datetime.now()

    tz = Timezone('US/Eastern', 'UTC-05:00', 'Pantstopia', 'pants')
    tz.runtimeAction()
    delta = datetime.now() - clock

    print 'delta', delta
    # TODO

    
def test_TimezoneList_constructor():
    tzList = TimezoneList()
    assert tzList
    assert len(tzList._timezones) > 1

def test_TimezoneList():
    tzList = TimezoneList()
    print tzList.getTimezoneStrings()
    assert tzList.findByCityName('San Francisco, USA')
    assert tzList.findByOffsetName('UTC+10:00')
    assert tzList.findByZoneName('US/Pacific')
    assert tzList.allTimezonesWithOffsetName('UTC+10:00')
    assert len(tzList.allTimezonesWithOffsetName('UTC+10:00')) > 1
    grouped = tzList.groupByOffsets()
    assert grouped
    assert 'UTC+10:00' in grouped
    assert grouped['UTC+10:00']
    assert len(grouped['UTC+10:00']) > 1

    count = 0
    for tz in tzList.sortedIter():
        assert tz.offset
        count += 1

    assert count == len(tzList._timezones)

    assert tzList.getTimezoneStrings()


