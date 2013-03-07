
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

TEST_DIR = os.path.dirname(__file__)

sys.path.append(os.path.join(TEST_DIR, os.path.pardir))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'faux'))

import fauxroot

# Use good-config.1 as the fake configuration.
sys.path.append(os.path.join(os.path.dirname(__file__), 'good-config.1'))
import fauxconfig
sys.path.pop()

sys.path.append(os.path.join(os.path.dirname(__file__),
                             '../../../../apps/scripts'))

import customdrivers
from customdrivers import InvalidDriversXml, InvalidVersion

def test_good_driversxml():
    def loadXml(fileName, expectedEntries):
        customDrivers = \
            customdrivers.CustomDriversXML(os.path.join('drivers', fileName))

        for entry in expectedEntries:
            fileName = entry[0]
            entry = entry[1:]

            print customDrivers.driverDict[fileName]
            print entry

            assert customDrivers.driverDict[fileName] == entry

    cases = [
        ('drivers.good.xml',
         [ (u'VMware-esx-drivers-scsi-mptspi-4.0.22vmw-00000.x86_64.rpm',
            u'VMware-esx-drivers-scsi-mptspi',
            u'4.0.22vmw-00000',
            u'VMware ESX LSI Logic SCSI Driver',
            [ u'usr/lib/vmware/vmkmod/mptspi.o' ],
            [ u'etc/vmware/pciid/mptspi.xml' ],
            [],
           ),
           (u'VMware-esx-drivers-net-e1000-7.6.15.5-00000.x86_64.rpm',
            u'VMware-esx-drivers-net-e1000',
            u'7.6.15.5-00000',
            u'VMware ESX Intel E1000 Network Driver',
            [ u'usr/lib/vmware/vmkmod/e1000.o' ],
            [ u'etc/vmware/pciid/e1000.xml' ],
            [ u'/foo/bar/baz',
              u'/foo/bar/boo' ],
           ),
         ]
        ),
        ('drivers.good.xml-2',
         [ (u'rpms/Test-driver-0.0.0.test.rpm',
            u'Test-driver',
            u'0.0.0',
            u'Test driver',
            [''], [''], [''],
           )
         ],

        ),
    ]

    for fileName, expectedEntries in cases:
        yield loadXml, fileName, expectedEntries

def test_bad_driversxml():
    def loadXml(fileName, expectedErrors):
        try:
            customdrivers.CustomDriversXML(os.path.join('drivers', fileName))
        except expectedErrors[0], msg:
            print ">" + msg[0]
            print ":" + expectedErrors[1]
            assert msg[0] == expectedErrors[1]
        else:    
            raise ValueError, "Didn't find an error."

    cases = [
        ('drivers.bad.xml',
         (InvalidDriversXml, 'The driverlist tag wasn\'t found.')),
        ('drivers.bad.xml-2',
         (InvalidVersion,
          'Got an unexpected version type for the driver disk.')),
        ('drivers.bad.xml-3',
         (InvalidDriversXml, 'More than one driverlist found.')),
        ('drivers.bad.xml-4',
         (InvalidDriversXml,
          'Driver entries must contain a name, version, filename and the pci table and driver binary entries.')),
        ('drivers.bad.xml-5',
         (InvalidDriversXml,
          'Driver entries must contain a name, version, filename and the pci table and driver binary entries.')),
        ('drivers.bad.xml-6',
         (InvalidDriversXml,
          'Driver entries must contain a name, version, filename and the pci table and driver binary entries.')),
        ('drivers.bad.xml-7',
         (InvalidDriversXml,
          'Driver entries must contain a name, version, filename and the pci table and driver binary entries.')),
        ('drivers.bad.xml-8',
         (InvalidDriversXml,
          'The driver disk provided had a malformed drivers.xml file and can not be used.')),
        ('drivers.bad.xml-9',
         (InvalidDriversXml,
          'More than one driver entry with the same file name was found.')),
    ]

    for fileName, expectedErrors in cases:
        yield loadXml, fileName, expectedErrors


