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
timezone module
'''
import os
import shutil
import xml.dom.minidom

import userchoices
from util import XMLGetText, XMLGetTextInFirstElement, GetWeaselXMLFilePath
from consts import HOST_ROOT

from log import log

#-----------------------------------------------------------------------------
def cmpOffsetString(a, b):
    '''Compare two timezone offset strings.  ie "UTC+10:30"
    >>> cmpOffsetString('UTC+00:00', 'UTC+00:00')
    0
    >>> cmpOffsetString('UTC+01:00', 'UTC+00:00')
    1
    >>> cmpOffsetString('UTC-01:00', 'UTC+00:00')
    -1
    >>> cmpOffsetString('FOO+01:00', 'UTC+00:00')
    Timezone Offset malformed: invalid literal for float(): FOO-01.00
    0
    '''
    a = a.replace('UTC','')
    a = a.replace(':','.')
    b = b.replace('UTC','')
    b = b.replace(':','.')
    try:
        a = float(a)
        b = float(b)
    except ValueError, ex:
        log.warn('Timezone Offset malformed: '+ str(ex))
        return 0
    return cmp(a,b)
        

#-----------------------------------------------------------------------------
def hostActionTimezone(_context):
    choice = userchoices.getTimezone()
    timezones = TimezoneList()
    if choice:
        tz = timezones.findByZoneName(choice['tzName'])
        isUTC = choice['isUTC']
    else:
        tz = timezones.defaultTimezone
        isUTC = True
    assert tz
    tz.hostAction(isUTC)

#-----------------------------------------------------------------------------
def GetTextOrEmpty(node, tagName):
    if not node.getElementsByTagName(tagName):
        return ''
    return XMLGetTextInFirstElement(node, tagName)
    

#-----------------------------------------------------------------------------
class Timezone(object):
    def __init__(self, zoneName, offset, city, cityOffsetName,
                 offsetPos=None, cityPos=None, showAsMapOffset=None):
        def stringToPosition(posStr):
            if posStr == '':
                return None
            return [int(x) for x in posStr.split(',')]

        self.zoneName = zoneName
        self.offset = offset
        self.city = city
        self.cityOffsetName = cityOffsetName
        # Some important cities lie in weird half-hour offsets that aren't
        # shown on the map, so we show these cities in nearby offsets instead
        self.showAsMapOffset = showAsMapOffset

        if hasattr(offsetPos, 'split'): #finds str and unicode objects
            offsetPos = stringToPosition(offsetPos)
        self.offsetPos = offsetPos

        if hasattr(cityPos, 'split'):
            cityPos = stringToPosition(cityPos)
        self.cityPos = cityPos

    def __repr__(self):
        return self.zoneName + '('+ self.city +')'

    def runtimeAction(self):
        os.environ['TZ'] = self.zoneName

    def hostAction(self, isUTC):
        srcTZFile = os.path.join(HOST_ROOT, 'usr/share/zoneinfo', self.zoneName)
        dstTZFile = os.path.join(HOST_ROOT, 'etc/localtime')
        clockFile = os.path.join(HOST_ROOT, 'etc/sysconfig/clock')

        try:
            shutil.copy( srcTZFile, dstTZFile )
        except EnvironmentError, ex:
            log.error('Error copying timezone (from: %s): %s' %
                      (srcTZFile, str(ex)))

        fp = open( clockFile, 'w' )
        fp.write('ZONE=%s\n' % self.zoneName)
        # set hardware clock to UTC?
        fp.write('UTC=%s\n' % str(isUTC).lower())
        # true for ARC- or AlphaBIOS-based Alpha systems
        fp.write('ARC=%s\n' % 'false')
        fp.close()


#-----------------------------------------------------------------------------
class TimezoneList(object):
    def __init__(self, fname='timezone.xml'):
        self._timezones = []
        self.defaultTimezone = None
        self.parseTimezoneList(fname)

    def index(self, tz):
        return self._timezones.index(tz)

    def __iter__(self):
        return iter(self._timezones)

    def __getitem__(self, index):
        return self._timezones[index]

    def parseTimezoneList(self, fname='timezone.xml'):
        fpath = GetWeaselXMLFilePath(fname)
        doc = xml.dom.minidom.parse(fpath)

        for offsetNode in doc.getElementsByTagName("offset"):
            offset = offsetNode.getAttribute('name')
            # careful not to get a child city's mappos
            offsetPos = None
            for child in offsetNode.childNodes:
                if hasattr(child, 'tagName') and child.tagName == 'mappos':
                    offsetPos = XMLGetText(child)
                    break
            for cityNode in offsetNode.getElementsByTagName('city'):
                zoneName = GetTextOrEmpty(cityNode, 'zone')
                cityName = GetTextOrEmpty(cityNode, 'name')
                cityOffsetName = GetTextOrEmpty(cityNode, 'offsetname')
                cityPos  = GetTextOrEmpty(cityNode, 'mappos')
                showAsMapOffset = GetTextOrEmpty(cityNode, 'showasmapoffset')

                # sanity check the data we got from the XML...
                if showAsMapOffset and offsetPos:
                    msg = ('Parsing timezone XML file: timzeone %s has both '
                           'showmapasoffset and an offset with a mappos') %\
                          zoneName
                    raise ValueError(msg)

                fileName = os.path.join('/usr/share/zoneinfo/', zoneName)
                if not os.path.exists(fileName):
                    log.warn('Timezone missing: Could not find %s' % fileName)
                    continue
                
                # for these args, None is prefered over an empty string
                kwargs = {'offsetPos': (offsetPos or None),
                          'cityPos': (cityPos or None),
                          'showAsMapOffset': (showAsMapOffset or None),
                         }
                zone = Timezone(zoneName, offset, cityName, cityOffsetName,
                                **kwargs)
                
                self._timezones.append(zone)
                
                if cityNode.getAttribute('default') == '1':
                    self.defaultTimezone = zone
                
    def findByCityName(self, name):
        '''Returns the timezone matching the name, or None'''
        for tz in self:
            if tz.city == name:
                return tz
        raise IndexError("Timezone at (%s) not found." % name)

    def findByOffsetName(self, name):
        '''Returns the *first* timezone matching the offset name, or None'''
        for tz in self:
            if tz.offset == name:
                return tz
        raise IndexError("Timezone at offset (%s) not found." % name)

    def findByZoneName(self, name):
        '''Returns the *first* timezone matching the zone name, or None'''
        for tz in self:
            if tz.zoneName == name:
                return tz
        raise IndexError("Timezone with zone name (%s) not found." % name)

    def allTimezonesWithOffsetName(self, name):
        '''Returns the timezones matching the offset name, or []'''
        return [tz for tz in self if tz.offset == name]

    def groupByOffsets(self):
        offsetDict = {}
        for tz in self:
            group = offsetDict.get(tz.offset, None)
            if not group:
                group = []
                offsetDict[tz.offset] = group
            group.append(tz)
        return offsetDict

    def sortedIter(self):
        '''Return an iterable of timezones that is sorted by offset'''
        groupedTimezones = self.groupByOffsets()
        offsetNames = sorted(groupedTimezones.keys(), cmp=cmpOffsetString)
        for offsetName in offsetNames:
            timezones = groupedTimezones[offsetName]
            for tz in timezones:
                yield tz

    def getTimezoneStrings(self):
        '''Returns a list of strings in the format "OffsetName - TZName"
        '''
        zones = []
        for zone in self._timezones:
            zoneStr = "%s - %s" % (zone.offset, zone.city)
            zones.append(zoneStr)
        return zones
