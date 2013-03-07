
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

from nose.tools import raises, with_setup

TEST_DIR = os.path.dirname(__file__)

sys.path.insert(0, os.path.join(TEST_DIR, "faux"))
import fauxroot # needed for mock syncKernelBufferToDisk
import parted

PARTED_FSTYPES = {
    'ext2' : { 'name' : 'ext2', 'formattable' : True },
    'ext3' : { 'name' : 'ext3', 'formattable' : True },
    'linux-swap' : { 'name' : 'linux-swap', 'formattable' : True },
    'fat32' : { 'name' : 'fat32', 'formattable' : True },
    'vmfs3' : { 'name' : 'vmfs3', 'formattable' : True },
    'vmkcore' : { 'name' : 'vmkcore', 'formattable' : False },
    }

sys.path.append(os.path.join(TEST_DIR, os.path.pardir))
parted._updateConfig({}, PARTED_FSTYPES)

sys.path.append(os.path.join(os.path.dirname(__file__), 'good-config.1'))
import fauxconfig

import partition
import devices
import fsset
import vmkctl
import userchoices

def teardown_root():
    fauxroot.FAUXROOT = None

def reloadModules():
    '''Reload the modules to reset any global state.'''

    fauxroot.FAUXROOT = None
    reload(partition)
    reload(devices)
    # reload(fsset)
    reload(vmkctl)
    reload(userchoices)
    reload(fauxconfig)

def setupSingleDiskPartitions(parts):
    '''Setup a single 20GB disk in the mock parted/vmkctl with the given
    partitions.'''
    
    reloadModules()
    
    vmkctl.VMKCTL_STORAGE_CONFIG = {
        'disks' : [
        { 'consoleDevice' : '/dev/sda',
          'name' : 'vml.1111',
          'devfsPath' : '/vmfs/devices/disks/vmhba32:0:0:0',
          'model' : 'WDC WD1600ADFS-7',
          'vendor' : 'ATA',
          'lunType' : 0,
          'local' : True,
          'pseudoLun' : False,
          'scsiPaths' : [] },
        ],
        }

    parted._resetConfig()
    parted._updateConfig({
        '/dev/sda' : { 'path' : '/dev/sda',
                       'length' : 40 * 1024 * 1024,
                       'sector_size' : 512,
                       'partitions' : parts,
                       'model' : 'mock'
                       },
        }, PARTED_FSTYPES)

    # Need to setup fauxroot so DiskSet.probeDisks works.
    fauxroot.FAUXROOT = ["good-config.1"]

def setupDoubleDiskPartitions():
    '''Setup two 20GB disks in the mock parted/vmkctl with the given
    partitions.'''
    
    reloadModules()
    
    vmkctl.VMKCTL_STORAGE_CONFIG = {
        'disks' : [
        { 'consoleDevice' : '/dev/sda',
          'name' : 'vml.1111',
          'devfsPath' : '/vmfs/devices/disks/vmhba32:0:0:0',
          'model' : 'WDC WD1600ADFS-7',
          'vendor' : 'ATA',
          'lunType' : 0,
          'local' : True,
          'pseudoLun' : False,
          'scsiPaths' : [] },
        { 'consoleDevice' : '/dev/sdb',
          'name' : 'vml.1112',
          'devfsPath' : '/vmfs/devices/disks/vmhba32:1:0:0',
          'model' : 'WDC WD1600ADFS-7',
          'vendor' : 'ATA',
          'lunType' : 0,
          'local' : True,
          'pseudoLun' : False,
          'scsiPaths' : [] },
        ],
        }

    parted._resetConfig()
    parted._updateConfig({
        '/dev/sda' : { 'path' : '/dev/sda',
                       'length' : 40 * 1024 * 1024,
                       'sector_size' : 512,
                       'partitions' : [],
                       'model' : 'mock'
                       },
        '/dev/sdb' : { 'path' : '/dev/sdb',
                       'length' : 40 * 1024 * 1024,
                       'sector_size' : 512,
                       'partitions' : [],
                       'model' : 'mock'
                       },
        }, PARTED_FSTYPES)

    fauxroot.FAUXROOT = ["good-config.1"]

def expectedParts(*args):
    '''Generate a list of expected partitions for the test_config function.

    The arguments are tuples that contain the partitions type, file system
    type, and size in MB.  The return value is a list of tuples containing:
    (partition number, partition type, fs type, start sector, end sector).

    >>> expectedParts((parted.PRIMARY, 'ext3', 250),
    ...               (parted.PRIMARY, 'ext3', 100))
    [(1, 0, 'ext3', 0, 511999), (2, 0, 'ext3', 512000, 716799)]
    '''
    retval = []
    startSector = 0
    
    for ptype, fstype, size in args:
        endSector = startSector + size * 1024 * 1024 / 512 - 1
        if ptype & parted.FREESPACE:
            partNumber = -1
        elif not retval:
            partNumber = 1
        else:
            partNumber = max([x[0] for x in retval]) + 1
        retval.append((partNumber,
                       ptype,
                       fstype,
                       startSector,
                       endSector))
        if ptype != parted.EXTENDED:
            startSector = endSector + 1
    
    return retval

@with_setup(None, teardown_root)
def check_one_config(conf):
    '''Check the given partition configuration.

    The configuration is checked by: setting up a disk with the initial
    partitions from the "init" field, creating a PartitionRequestSet with the
    requests in the "requests" field, running fitPartitionsOnDevice, and then
    checking the resulting disk layout against the "expected" field.

    See test_configs()
    '''

    setupSingleDiskPartitions(conf['init'])
    
    fsTypes = fsset.getSupportedFileSystems()

    diskSet = devices.DiskSet(forceReprobe=True)
    device = diskSet['vml.1111']
    prs = partition.PartitionRequestSet(device.name)
    # Build up the request set.
    for req in conf['requests']:
        # fsType is just a name, we have to instantiate it.
        req['fsType'] = fsTypes[req['fsType']]()
        prs.append(partition.PartitionRequest(**req))

    prs.sort()

    try:
        prs.fitPartitionsOnDevice()
        prs.savePartitions()
    except Exception, err: # XXX
        assert 'error' in conf, "%s" % err
        assert str(err) == conf['error'], \
               "%s != %s" % (err, conf['error'])
        return
    
    assert 'error' not in conf
    
    pd = device.partitions.partedDisk
    part = None
    for exp in conf['expected']:
        part = pd.next_partition(part)

        assert part.num == exp[0], \
               "%d: %d != %d" % (part.num, part.num, exp[0])
        assert part.type == exp[1], \
               "%d: %d != %d" % (part.num, part.type, exp[1])
        assert not exp[2] or \
               part.fs_type == parted.file_system_type_get(exp[2])
        assert part.geom.start == exp[3], \
               "%d: %d != %d" % (part.num, part.geom.start, exp[3])
        assert part.geom.end == exp[4], \
               "%d: %d != %d" % (part.num, part.geom.end, exp[4])
    
    assert pd.next_partition(part) == None, \
           "%s: more partitions that expected" % conf['desc']


def test_configs():
    '''Generator that returns a bunch of configurations to run through
    check_one_config.'''

    configs = [

        ##
        { 'desc' : 'Empty and should fit easily',

          # The initial partition configuration.
          'init' : [],

          # The partition requests, the dicts are passed directly to the
          # PartitionRequest structure.
          'requests' : [ { 'mountPoint' : '/boot',
                           'fsType' : 'ext3',
                           'minimumSize' : 250 },
                         { 'mountPoint' : '/',
                           'fsType' : 'ext3',
                           'minimumSize' : 100,
                           'grow' : True } ],

          # The expected disk layout after fitPartitionsOnDevice has been run.
          'expected' : expectedParts(
        (parted.PRIMARY, 'ext3', 250),
        (parted.PRIMARY, 'ext3', 20 * 1024 - 250)) },

        ##
        { 'desc' : 'Boot partition comes first',

          # The initial partition configuration.
          'init' : [],

          # The partition requests, the dicts are passed directly to the
          # PartitionRequest structure.
          'requests' : [ { 'mountPoint' : '/var/spool',
                           'fsType' : 'ext3',
                           'minimumSize' : 254 },
                         { 'mountPoint' : '/boot',
                           'fsType' : 'ext3',
                           'minimumSize' : 250 },
                         { 'mountPoint' : '/',
                           'fsType' : 'ext3',
                           'minimumSize' : 250,
                           'grow' : True }, ],

          # The expected disk layout after fitPartitionsOnDevice has been run.
          'expected' : expectedParts(
        (parted.PRIMARY, 'ext3', 250),
        (parted.PRIMARY, 'ext3', 254),
        (parted.EXTENDED, '', 20 * 1024 - 250 - 254),
        (parted.LOGICAL, 'ext3', 20 * 1024 - 250 - 254)) },

        ##
        { 'desc' : 'Empty and should just fit.',
          'init' : [],
          
          'requests' : [ { 'mountPoint' : '/boot',
                           'fsType' : 'ext3',
                           'minimumSize' : 250 },
                         { 'mountPoint' : '/',
                           'fsType' : 'ext3',
                           'minimumSize' : (40 * 1024 / 2) - 250 } ],

          'expected' : expectedParts(
        (parted.PRIMARY, 'ext3', 250),
        (parted.PRIMARY, 'ext3', 20 * 1024 - 250)) },

        ##
        { 'desc' : 'No requests',
          'init' : [],
          
          'requests' : [ ],

          'expected' : expectedParts((parted.FREESPACE, '', 20 * 1024)) },

        ##
        { 'desc' : 'Two grow partitions with no max size.',
          'init' : [],
          
          'requests' : [ { 'mountPoint' : '/boot',
                           'fsType' : 'ext3',
                           'minimumSize' : 250 },
                         { 'mountPoint' : '/',
                           'fsType' : 'ext3',
                           'minimumSize' : 100,
                           'grow' : True },
                         { 'mountPoint' : '/usr',
                           'fsType' : 'ext3',
                           'minimumSize' : 100,
                           'grow' : True } ],

          'expected' : expectedParts(
        (parted.PRIMARY, 'ext3', 250),
        (parted.PRIMARY, 'ext3', (20 * 1024 - 250) / 2),
        (parted.EXTENDED, '', (20 * 1024 - 250) / 2),
        (parted.LOGICAL, 'ext3', (20 * 1024 - 250) / 2)) },

        ##
        { 'desc' : 'Two grow partitions with one max size.',
          'init' : [],
          
          'requests' : [ { 'mountPoint' : '/boot',
                           'fsType' : 'ext3',
                           'minimumSize' : 250 },
                         { 'mountPoint' : '/',
                           'fsType' : 'ext3',
                           'minimumSize' : 100,
                           'maximumSize' : 250,
                           'grow' : True },
                         { 'mountPoint' : '/usr',
                           'fsType' : 'ext3',
                           'minimumSize' : 100,
                           'grow' : True } ],

          'expected' : expectedParts(
        (parted.PRIMARY, 'ext3', 250),
        (parted.PRIMARY, 'ext3', 250),
        (parted.EXTENDED, '', 20 * 1024 - 250 - 250),
        (parted.LOGICAL, 'ext3', 20 * 1024 - 250 - 250)) },

        ##
        { 'desc' : 'Two grow partitions with one max size.',
          'init' : [],
          
          'requests' : [ { 'mountPoint' : '/boot',
                           'fsType' : 'ext3',
                           'minimumSize' : 250 },
                         { 'mountPoint' : '/',
                           'fsType' : 'ext3',
                           'minimumSize' : 100,
                           'maximumSize' : 250,
                           'grow' : True },
                         { 'mountPoint' : '/usr',
                           'fsType' : 'ext3',
                           'minimumSize' : 100,
                           'grow' : True } ],

          'expected' : expectedParts(
        (parted.PRIMARY, 'ext3', 250),
        (parted.PRIMARY, 'ext3', 250),
        (parted.EXTENDED, '', 20 * 1024 - 250 - 250),
        (parted.LOGICAL, 'ext3', 20 * 1024 - 250 - 250)) },

        ##
        { 'desc' : 'Two grow partitions, both with a max size.',
          'init' : [],
          
          'requests' : [ { 'mountPoint' : '/boot',
                           'fsType' : 'ext3',
                           'minimumSize' : 250 },
                         { 'mountPoint' : '/',
                           'fsType' : 'ext3',
                           'minimumSize' : 100,
                           'maximumSize' : 250,
                           'grow' : True },
                         { 'mountPoint' : '/usr',
                           'fsType' : 'ext3',
                           'minimumSize' : 100,
                           'maximumSize' : 250,
                           'grow' : True } ],

          'expected' : expectedParts(
        (parted.PRIMARY, 'ext3', 250),
        (parted.PRIMARY, 'ext3', 250),
        (parted.EXTENDED, '', 20 * 1024 - 250 - 250),
        (parted.LOGICAL, 'ext3', 250),
        (parted.LOGICAL | parted.FREESPACE, '', 20 * 1024 - 250 * 3)) },

        ##
        { 'desc' : 'Partition with oversized max.',
          'init' : [],
          
          'requests' : [ { 'mountPoint' : '/boot',
                           'fsType' : 'ext3',
                           'minimumSize' : 250,
                           'maximumSize' : 100 * 1024,
                           'grow' : True }, ],

          'expected' : expectedParts((parted.PRIMARY, 'ext3', 20 * 1024)) },

        ##
        { 'desc' : 'Large max and no max.',
          'init' : [],
          
          'requests' : [ { 'mountPoint' : '/boot',
                           'fsType' : 'ext3',
                           'minimumSize' : 250,
                           'maximumSize' : 100 * 1024,
                           'grow' : True },
                         { 'mountPoint' : '/',
                           'fsType' : 'ext3',
                           'minimumSize' : 250,
                           'grow' : True }, ],

          'error' : "Couldn't find a spot for the requested partition." },

        ##
        { 'desc' : 'Excess primaries.',
          
          'init' : [
        { 'num' : 0, 'type' : parted.PRIMARY,
          'fs_type' : 'ext3',
          'native_type' : 0x83,
          'geom' : { 'start' : 0, 'end' : 1 }},
        { 'num' : 0, 'type' : parted.PRIMARY,
          'fs_type' : 'ext3',
          'native_type' : 0x83,
          'geom' : { 'start' : 2, 'end' : 3 }},
        { 'num' : 0, 'type' : parted.PRIMARY,
          'fs_type' : 'ext3',
          'native_type' : 0x83,
          'geom' : { 'start' : 4, 'end' : 5 }}, ],
          
          'requests' : [ { 'mountPoint' : '/boot',
                           'fsType' : 'ext3',
                           'minimumSize' : 250,
                           'primaryPartition' : True },
                         { 'mountPoint' : '/',
                           'fsType' : 'ext3',
                           'minimumSize' : 100,
                           'maximumSize' : 250,
                           'primaryPartition' : True,
                           'grow' : True }, ],
          'error' : "Can't have more than 4 primary partitions" },

        ##
        { 'desc' : 'No room for extended',
          
          'init' : [
        { 'num' : 0, 'type' : parted.PRIMARY,
          'fs_type' : 'ext3',
          'native_type' : 0x83,
          'geom' : { 'start' : 0, 'end' : 1 }},
        { 'num' : 0, 'type' : parted.PRIMARY,
          'fs_type' : 'ext3',
          'native_type' : 0x83,
          'geom' : { 'start' : 2, 'end' : 3 }},
        { 'num' : 0, 'type' : parted.PRIMARY,
          'fs_type' : 'ext3',
          'native_type' : 0x83,
          'geom' : { 'start' : 4, 'end' : 5 }},
        { 'num' : 0, 'type' : parted.PRIMARY,
          'fs_type' : 'ext3',
          'native_type' : 0x83,
          'geom' : { 'start' : 6, 'end' : 7 }}, ],
          
          'requests' : [ { 'mountPoint' : '/boot',
                           'fsType' : 'ext3',
                           'minimumSize' : 250 },
                         { 'mountPoint' : '/',
                           'fsType' : 'ext3',
                           'minimumSize' : 100,
                           'maximumSize' : 250,
                           'grow' : True }, ],
          'error' : "Can't add extended partition to handle requests" },

        ##
        { 'desc' : 'Request two more primaries.',
          
          'init' : [
        { 'num' : 0, 'type' : parted.PRIMARY,
          'fs_type' : 'ext3',
          'native_type' : 0x83,
          'geom' : { 'start' : 0, 'end' : 10 * 1024 * 1024 - 1 }},
        { 'num' : 0, 'type' : parted.PRIMARY,
          'fs_type' : 'ext3',
          'native_type' : 0x83,
          'geom' : { 'start' : 10 * 1024 * 1024, 'end' : 20 * 1024 * 1024 - 1 }
          } ],
          
          'requests' : [ { 'mountPoint' : '/boot',
                           'fsType' : 'ext3',
                           'minimumSize' : 5 * 1024,
                           'primaryPartition' : True },
                         { 'mountPoint' : '/',
                           'fsType' : 'ext3',
                           'minimumSize' : 5 * 1024,
                           'primaryPartition' : True }, ],
          
          'expected' : expectedParts(
        (parted.PRIMARY, 'ext3', 5 * 1024),
        (parted.PRIMARY, 'ext3', 5 * 1024),
        (parted.PRIMARY, 'ext3', 5 * 1024),
        (parted.PRIMARY, 'ext3', 5 * 1024)) },

        ##
        { 'desc' : 'Primary after extended.',
          'init' : [
        { 'num' : 0, 'type' : parted.PRIMARY,
          'fs_type' : 'ext3',
          'native_type' : 0x83,
          'geom' : { 'start' : 0, 'end' : 10 * 1024 * 1024 - 1 }},
        { 'num' : 0, 'type' : parted.EXTENDED,
          'fs_type' : 'ext3',
          'native_type' : 0,
          'geom' : { 'start' : 10 * 1024 * 1024, 'end' : 20 * 1024 * 1024 - 1 }
          } ],
          
          'requests' : [ { 'mountPoint' : '/boot',
                           'fsType' : 'ext3',
                           'minimumSize' : 5 * 1024,
                           'primaryPartition' : True },
                         { 'mountPoint' : '/',
                           'fsType' : 'ext3',
                           'minimumSize' : 5 * 1024,
                           'primaryPartition' : True,
                           'grow' : True }, ],
          
          'expected' : expectedParts(
        (parted.PRIMARY, 'ext3', 5 * 1024),
        (parted.EXTENDED, 'ext3', 5 * 1024),
        (parted.PRIMARY, 'ext3', 5 * 1024),
        (parted.PRIMARY, 'ext3', 10 * 1024)) },

        ##
        { 'desc': 'Full and should not fit',
          'init' : [
        { 'num' : 0, 'type' : parted.PRIMARY,
          'fs_type' : 'ext3',
          'native_type' : 0x83,
          'geom' : { 'start' : 0, 'end' : 40 * 1024 * 1024 - 1 }},
        ],
          'requests' : [ { 'mountPoint' : '/boot',
                           'fsType' : 'ext3',
                           'minimumSize' : 250 }, ],
          'error' : "Couldn't find a spot for the requested partition." },
        
        ##
        { 'desc': 'More than one extended partition',
          'init' : [
        { 'num' : 0, 'type' : parted.EXTENDED,
          'fs_type' : 'ext3',
          'native_type' : 0,
          'geom' : { 'start' : 0, 'end' : 20 * 1024 * 1024 - 1 }},
        { 'num' : 0, 'type' : parted.EXTENDED,
          'fs_type' : 'ext3',
          'native_type' : 0,
          'geom' : { 'start' : 20 * 1024 * 1024,
                     'end' : 40 * 1024 * 1024 - 1 }},
        ],
          'requests' : [ { 'mountPoint' : '/boot',
                           'fsType' : 'ext3',
                           'minimumSize' : 250 }, ],
          'error' : 'Found more than one extended partition on a device' },
        
        ##
        { 'desc' : 'Gaps in the freespace.',
          'skip' : 'Not supported',
          
          'init' : [
        { 'num' : 0, 'type' : parted.PRIMARY,
          'fs_type' : 'ext3',
          'native_type' : 0x83,
          'geom' : { 'start' : 0, 'end' : 8 * 1024 * 1024 - 1 }},
        { 'num' : 0, 'type' : parted.PRIMARY,
          'fs_type' : 'ext3',
          'native_type' : 0x83,
          'geom' : { 'start' : 20 * 1024 * 1024, 'end' : 30 * 1024 * 1024 - 1 }
          } ],
          
          'requests' : [ { 'mountPoint' : '/boot',
                           'fsType' : 'ext3',
                           'minimumSize' : 5 * 1024,
                           'primaryPartition' : True },
                         { 'mountPoint' : '/',
                           'fsType' : 'ext3',
                           'minimumSize' : 6 * 1024,
                           'primaryPartition' : False }, ],
          
          'expected' : expectedParts(
        (parted.PRIMARY, 'ext3', 4 * 1024),
        (parted.PRIMARY, 'ext3', 6 * 1024),
        (parted.PRIMARY, 'ext3', 5 * 1024),
        (parted.PRIMARY, 'ext3', 5 * 1024)) },

        ]

    for conf in configs:
        if 'skip' in conf:
            continue
        
        yield check_one_config, conf

@with_setup(None, teardown_root)
def testAddDefaultPartitionRequests():
    setupDoubleDiskPartitions()

    diskSet = devices.DiskSet(forceReprobe=True)
    partition.addDefaultPartitionRequests(diskSet["vml.1111"])
    partition.addDefaultPartitionRequests(diskSet["vml.1112"])

    assert len(userchoices.getPhysicalPartitionRequestsDevices()) == 1
    assert len(userchoices.getVirtualPartitionRequestsDevices()) == 1
    assert len(userchoices.getVirtualDevices()) == 1

    assert userchoices.getPhysicalPartitionRequestsDevices()[0] == \
           'vml.1112'

@with_setup(None, teardown_root)
def testSplit():
    assert partition.splitPath("/dev/hda1") == ("/dev/hda", 1)
    assert partition.splitPath("/dev/rd/c0d0p1") == ("/dev/rd/c0d0", 1)
    assert partition.splitPath("/dev/cciss/c0d0p3") == ("/dev/cciss/c0d0", 3)

@with_setup(None, teardown_root)
def testJoin():
    assert partition.joinPath("/dev/hda", 1) == "/dev/hda1"
    assert partition.joinPath("/dev/rd/c0d0", 1) == "/dev/rd/c0d0p1"
    assert partition.joinPath("/dev/cciss/c0d0", 3) == "/dev/cciss/c0d0p3"

    raises(ValueError)(partition.joinPath)("/dev/foo", 1)

@with_setup(None, teardown_root)
def testEligible():
    reloadModules()
    
    fauxroot.FAUXROOT = ["good-config.1"]
    eligible = partition.getEligibleDisks()
    names = [disk.name for disk in eligible]

    assert names == ['vml.0000', 'vml.0001', 'vml.0006', 'vml.0030']

def testVmfsVolumeLabel():
    cases = [
        ("foobar", (None, '')),
        ("foo bar", (None, '')),
        (" foo", (ValueError,
            "Datastore names must not start or end with spaces.")),
        ("foo ", (ValueError,
            "Datastore names must not start or end with spaces.")),
        (" foo ", (ValueError,
            "Datastore names must not start or end with spaces.")),
        ("   foo   ", (ValueError,
            "Datastore names must not start or end with spaces.")),
        ("foo/bar", (ValueError,
            "Datastore names must not contain the '/' character.")),
        ("", (ValueError,
            "Datastore names must contain at least one character.")),
        ("This is a really, really, really, really, really, really long label",
            (ValueError,
            "Datastore names must be less than 64 characters long.")),
    ]

    def checkVolumeLabel(label, expectedErrors):
        try:
            fsset.vmfs3FileSystem.sanityCheckVolumeLabel(label)
        except expectedErrors[0], msg:
            assert msg[0] == expectedErrors[1], \
                "%s != %s" % (msg[0], expectedErrors[1])
        else:
            assert expectedErrors[0] == None
    
    for label, expectedErrors in cases:
        yield checkVolumeLabel, label, expectedErrors

if __name__ == "__main__":
    import doctest
    doctest.testmod()
