'''A module that provides a "good" fake configuration.

This module is used to initialize the mock modules with a "good" configuration
that should allow the installer to complete successfully.  Most of the
configuration is made up of dictionaries-of-dictionaries that are converted
into objects.

>>> si = vmkctl.StorageInfoImpl()
>>> luns = si.GetDiskLuns()
>>> luns.sort(lambda x, y: cmp(x.GetDevfsPath(), y.GetDevfsPath()))
>>> for lun in luns:
...    print lun.GetDevfsPath()
/vmfs/devices/disks/vmhba32:0:0:0
/vmfs/devices/disks/vmhba32:1:0:0
/vmfs/devices/disks/vmhba33:0:0:0

>>> try:
...    luns[2].GetConsoleDevice()
... except vmkctl.HostCtlException, msg:
...    print "Caught an exception"
Caught an exception

>>> vols = si.GetVmfsFileSystems()
>>> vols[0].GetBlockSize() * vols[0].GetTotalBlocks() == vols[0].GetSize()
True

>>> dev = parted.PedDevice.get("/dev/sda")
>>> dev.sector_size
512
>>> disk = parted.PedDisk.new(dev)
>>> part = disk.next_partition()
>>> part.num
-1
>>> part.type == parted.FREESPACE
True

See test/faux/fauxroot.py
See test/faux/vmkctl.py
See test/faux/parted.py
See test/faux/rpm.py
'''

# XXX This module needs a good refactor/cleanup.

import re
import os
import sys
import stat
import struct
import string
import getopt
import datetime
import itertools
from StringIO import StringIO

CONFIG_DIR = os.path.dirname(__file__)

for fauxPath in [os.path.join(CONFIG_DIR, os.path.pardir, "faux"),
                 # Add pythonroot so we can import vmware.authentication
                 os.path.join(CONFIG_DIR, "../../../../..", "apps/pythonroot"),
                 os.path.join(CONFIG_DIR, "../../../../..", "apps/scripts"),
                 os.path.join(CONFIG_DIR, "../../../../..", "support/scripts")]:
    if fauxPath not in sys.path:
        sys.path.append(fauxPath)

import vmkctl
import parted
import rpm
import fauxroot
import util
import brandiso

_scsiAdapter = {'driver' : 'mptscsi',
                'interfaceType' : vmkctl.ScsiInterface.SCSI_IFACE_TYPE_BLOCK }

_usbAdapter = {'driver' : 'usb-storage',
               'interfaceType' : vmkctl.ScsiInterface.SCSI_IFACE_TYPE_USB }

_ideAdapter = {'driver' : 'ata_piix',
               'interfaceType' : vmkctl.ScsiInterface.SCSI_IFACE_TYPE_IDE }

vmkctl.VMKCTL_STORAGE_CONFIG = {
    'disks' : [
    { 'consoleDevice' : '/dev/sda',
      'name' : 'vml.0000',
      'devfsPath' : '/vmfs/devices/disks/vml.0000',
      'model' : 'WDC FKE1600     ',
      'vendor' : 'ATA             ',
      'lunType' : 0,
      'local' : True,
      'pseudoLun' : False,
      'scsiPaths' : [ { 'adapter' : _scsiAdapter,
                        'adapterName' : 'vmhba32',
                        'channelNumber' : 0,
                        'targetNumber' : 0,
                        'lun' : 0,
                        'targetPathString' : '' } ] },
    { 'consoleDevice' : '/dev/sdb',
      'name' : 'vml.0001',
      'devfsPath' : '/vmfs/devices/disks/vml.0001',
      'model' : 'WDC FKE1700UT   ',
      'vendor' : 'ATA             ',
      'lunType' : 0,
      'local' : True,
      'pseudoLun' : False,
      'scsiPaths' : [ { 'adapter' : _scsiAdapter,
                        'adapterName' : 'vmhba32',
                        'channelNumber' : 0,
                        'targetNumber' : 0,
                        'lun' : 1, 
                        'targetPathString' : 'Fake Path' } ] },
    { 'consoleDevice' : '/dev/sdm',
      'name' : 'vml.0040',
      'devfsPath' : '/vmfs/devices/disks/vml.0040',
      'model' : 'WDC FKE1800UT    ',
      'vendor' : 'ATA              ',
      'lunType' : 0,
      'local' : False,
      'pseudoLun' : False,
      'scsiPaths' : [ { 'adapter' : _scsiAdapter,
                        'adapterName' : 'vmhba32',
                        'channelNumber' : 0,
                        'targetNumber' : 0,
                        'lun' : 2,
                        'targetPathString' :
       'WWPN: 20:06:00:a0:b8:0f:a2:70 WWNN: 20:06:00:a0:b8:0f:a2:6f' } ,
                      { 'adapter' : _scsiAdapter,
                        'adapterName' : 'vmhba32',
                        'channelNumber' : 0,
                        'targetNumber' : 0,
                        'lun' : 5,
                        'targetPathString' :
                            'WWPN: Bo:gu:sP:at:hT:oD:ev:ic:e' },
                      { 'adapter' : _scsiAdapter,
                        'adapterName' : 'vmhba32',
                        'channelNumber' : 0,
                        'targetNumber' : 0,
                        'lun' : 6,
                        'targetPathString' :
                            'WWPN: Bo:gu:sP:at:hT:oD:ev:ic:e' }, ] },
    { 'consoleDevice' : '/dev/sdq',
      'name' : 'vml.0041',
      'devfsPath' : '/vmfs/devices/disks/vml.0041',
      'model' : 'WDC FKE1800UT    ',
      'vendor' : 'ATA              ',
      'lunType' : 0,
      'local' : True,
      'pseudoLun' : False,
      'scsiPaths' : [ { 'adapter' : _scsiAdapter,
                        'adapterName' : 'vmhba30',
                        'channelNumber' : 0,
                        'targetNumber' : 0,
                        'lun' : 0,
                        'targetPathString' : '' } ] },
    { 'consoleDevice' : '/dev/sdc',
      'name' : 'vml.0002',
      'devfsPath' : '/vmfs/devices/disks/vml.0002',
      'model' : 'USB Travelator 2000',
      'vendor' : 'QUEENSTON             ',
      'lunType' : 0,
      'local' : True,
      'pseudoLun' : False,
      'scsiPaths' : [ { 'adapter' : _usbAdapter,
                        'adapterName' : 'vmhba33',
                        'channelNumber' : 0,
                        'targetNumber' : 0,
                        'lun' : 0,
                        'targetPathString' : '' } ] },
    { 'consoleDevice' : '/dev/sdd',
      'name' : 'vml.0003',
      'devfsPath' : '/vmfs/devices/disks/vml.0003',
      'model' : 'DataTraveler 2.0  ',
      'vendor' : 'Kingston          ',
      'lunType' : 0,
      'local' : True,
      'pseudoLun' : False,
      'scsiPaths' : [ { 'adapter' : _usbAdapter,
                        'adapterName' : 'vmhba33',
                        'channelNumber' : 0,
                        'targetNumber' : 0,
                        'lun' : 1,
                        'targetPathString' : '' } ] },
    { 'consoleDevice' : '/dev/sde',
      'name' : 'vmhba35:0:0',
      'devfsPath' : '/vmfs/devices/disks/vmhba35:0:0:0',
      'model' : 'USB CD-ROM Device ',
      'vendor' : 'Half Baked USB    ',
      'lunType' : 0,
      'local' : True,
      'pseudoLun' : False,
      'scsiPaths' : [ { 'adapter' : _usbAdapter,
                        'adapterName' : 'vmhba33',
                        'channelNumber' : 0,
                        'targetNumber' : 1,
                        'lun' : 0,
                        'targetPathString' : '' } ] },
    { 'consoleDevice' : '/dev/sdf',
      'name' : 'vml.0006',
      'devfsPath' : '/vmfs/devices/disks/vml.0006',
      'model' : 'WDC FKE1600    ',
      'vendor' : 'ATA       ',
      'lunType' : 0,
      'local' : False,
      'pseudoLun' : False,
      'scsiPaths' : [ { 'adapter' : _scsiAdapter,
                        'adapterName' : 'vmhba32',
                        'channelNumber' : 0,
                        'targetNumber' : 0,
                        'lun' : 6,
                        'targetPathString' : '' } ] },
    { 'consoleDevice' : '/dev/sdg',
      'name' : 'vml.0025',
      'devfsPath' : '/vmfs/devices/disks/vml.0025',
      'model' : 'Firefly      ',
      'vendor' : 'Lexar       ',
      'lunType' : 0,
      'local' : True,
      'pseudoLun' : False,
      'scsiPaths' : [ { 'adapter' : _usbAdapter,
                        'adapterName' : 'vmhba34',
                        'channelNumber' : 0,
                        'targetNumber' : 2,
                        'lun' : 0,
                        'targetPathString' : '' } ] },
    { 'consoleDevice' : '/dev/sdn',
      'name' : 'vml.0026',
      'devfsPath' : '/vmfs/devices/disks/vml.0026',
      'model' : 'Firefly2     ',
      'vendor' : 'Lexar       ',
      'lunType' : 0,
      'local' : True,
      'pseudoLun' : False,
      'scsiPaths' : [ { 'adapter' : _usbAdapter,
                        'adapterName' : 'vmhba36',
                        'channelNumber' : 0,
                        'targetNumber' : 2,
                        'lun' : 1,
                        'targetPathString' : '' } ] },
    { 'consoleDevice' : '/dev/sdt',
      'name' : 'vml.0030',
      'devfsPath' : '/vmfs/devices/disks/vml.0030',
      'model' : 'IDE HD Model    ',
      'vendor' : 'IDE HD Vendor  ',
      'lunType' : 0,
      'local' : True,
      'pseudoLun' : False,
      'scsiPaths' : [ { 'adapter' : _ideAdapter,
                        'adapterName' : 'vmhba36',
                        'channelNumber' : 0,
                        'targetNumber' : 0,
                        'lun' : 0,
                        'targetPathString' : '' } ] },
    { 'consoleDevice' : '/dev/sdz',
      'name' : 'vml.0666',
      'devfsPath' : '/vmfs/devices/disks/vml.0666',
      'model' : 'Fake LUNZ      ',
      'vendor' : 'FakeOut 5000  ',
      'lunType' : 0,
      'local' : False,
      'pseudoLun' : True,
      'scsiPaths' : [ { 'adapter' : _scsiAdapter,
                        'adapterName' : 'whocares',
                        'channelNumber' : 0,
                        'targetNumber' : 0,
                        'lun' : 0,
                        'targetPathString' : '' } ] },
    { 'consoleDevice' : '/dev/cciss/c0d0',
      'name' : 'vml.0010',
      'devfsPath' : '/vmfs/devices/disks/vml.0010',
      'model' : 'CCISS Disk',
      'vendor' : 'Compaq',
      'lunType' : 0,
      'local' : True,
      'pseudoLun' : False,
      'scsiPaths' : [] },
    { 'consoleDevice' : '/dev/cciss/c0d1',
      'name' : 'vml.0011',
      'devfsPath' : '/vmfs/devices/disks/vml.0011',
      'model' : 'CCISS Disk',
      'vendor' : 'Compaq',
      'lunType' : 0,
      'local' : True,
      'pseudoLun' : False,
      'scsiPaths' : [] },
    ],
    'datastores' : [
    { 'blockSize' : 1048576,
      'blocksUsed' : 2832,
      'consolePath' : '/vmfs/volumes/473027ac-5705f21d-6d09-000c2918f3f6',
      'majorVersion' : 3,
      'minorVersion' : 32,
      'totalBlocks' : 7680,
      'volumeName' : 'Storage 1',
      'uuid' : '473027ac-5705f21d-6d09-000c2918f3f6',
      'diskLuns' : [
          { 'name' : 'vml.0000:5',
            'deviceName' : 'vml.0000', },
      ], },
    { 'blockSize' : 1048576,
      'blocksUsed' : 2832,
      'consolePath' : '/vmfs/volumes/473027ac-5705f21d-6d09-000c2918f3f7',
      'majorVersion' : 3,
      'minorVersion' : 32,
      'totalBlocks' : 14680,
      'volumeName' : 'Storage1',
      'uuid' : '473027ac-5705f21d-6d09-000c2918f3f7',
      'diskLuns' : [
          { 'name' : 'vml.0001:5',
            'deviceName' : 'vml.0001', },
      ], },
    ],
    'interfaces' : [
    { 'driver' : 'mptscsi'}]
    }

vmkctl.VMKCTL_ISCSI_CONFIG = {
      'macAddress' : '00:50:56:C0:00:03',
      'nicIP' : '123.234.111.222',
      'nicSubnetMask' : '255.0.0.0',
      'nicGateway' : '123.255.255.254',
      'nicDhcp' : 0,
      'nicVlan' : 1234,   # Set to None if VLAN not desired

      'targetIP' : '111.222.111.222',
      'targetPort' : 3260,
      'lun' : 1,
      'targetName' : 'iqn.2006-01.edu.berkeley',
      'chapName' : 'Oskie',
      'chapPwd' : 'bears#1_______',

      'initiatorName' : 'iqn.2007-12.com.nonesuch',
      'initiatorAlias' : 'theAlias'}

vmkctl.VMKCTL_NET_CONFIG['pnics'] = (
    vmkctl.Pnic('e1000',
                'vmnic32', True, 1000000,
                vmkctl.MacAddress('00:50:56:C0:00:00'),
                (2, 0, 0)),
    vmkctl.Pnic('afakenic',
                'Acme Ethernet Corp: Fake NIC 2000', True, 2000,
                vmkctl.MacAddress('00:50:56:C0:00:01'),
                (3, 0, 0)),
    vmkctl.Pnic('tfakenic',
                'Tennessee TTT144: Gigabit catfish backbone', False, 1000,
                vmkctl.MacAddress('00:50:56:C0:00:02'),
                (3, 1, 0)),
    vmkctl.Pnic('vfakenic',
                'Vulcan mind-meld wireless terabit', True, 10,
                vmkctl.MacAddress('00:50:56:C0:00:03'),
                (4, 1, 1)),
    vmkctl.Pnic('vfakenic',
                'Vulcan mind-meld wireless terabit', True, 10,
                vmkctl.MacAddress('00:50:56:C0:00:04'),
                (4, 1, 1)),
    vmkctl.Pnic('vfakenic',
                'Vulcan mind-meld wireless terabit', True, 10,
                vmkctl.MacAddress('00:50:56:C0:00:05'),
                (4, 1, 1)),
    vmkctl.Pnic('vfakenic',
                'Vulcan mind-meld wireless terabit', True, 10,
                vmkctl.MacAddress('00:50:56:C0:00:06'),
                (4, 1, 1)),
    vmkctl.Pnic('vfakenic',
                'Vulcan mind-meld wireless terabit', True, 10,
                vmkctl.MacAddress('00:50:56:C0:00:07'),
                (4, 1, 1)),
    vmkctl.Pnic('vfakenic',
                'Vulcan mind-meld wireless terabit', True, 10,
                vmkctl.MacAddress('00:50:56:C0:00:08'),
                (4, 1, 1)),
    vmkctl.Pnic('vfakenic',
                'Vulcan mind-meld wireless terabit', True, 10,
                vmkctl.MacAddress('00:50:56:C0:00:09'),
                (4, 1, 1)),
    )

vmkctl.VMKCTL_MEM_SIZE = 2147418112

parted._resetConfig()
parted._updateConfig({
    '/dev/sda' : { 'path' : '/dev/sda',
                   'length' : 150 * 1024 * 1024,
                   'sector_size' : 512,
                   'partitions' : [{ 'num' : 0, 'type' : parted.PRIMARY,
                                     'fs_type' : 'ext3',
                                     'native_type' : 0x83,
                                     'geom' : { 'start' : 0, 'end' : 204800 }},
                                   { 'num' : 1, 'type' : parted.PRIMARY,
                                     'fs_type' : 'ext3',
                                     'native_type' : 0x83,
                                     'geom' : { 'start' : 204820, 'end' : 400000 }},
                                   { 'num' : 2, 'type' : parted.PRIMARY,
                                     'fs_type' : '',
                                     'native_type' : 0xfb,
                                     'geom' : { 'start' : 400020, 'end' : 700000 }},
                                   ],
                   'model' : 'mock'
                   },
    
    '/dev/sdb' : { 'path' : '/dev/sdb',
                   'length' : 150 * 1024 * 1024,
                   'sector_size' : 512,
                   'partitions' : [{ 'num' : 5, 'type' : parted.LOGICAL,
                                     'fs_type' : '',
                                     'native_type' : 0xfb,
                                     'geom' : { 'start' : 100, 'end' : 200 }}],
                   'model' : 'mock'
                   },
    
    '/dev/sdm' : { 'path' : '/dev/sdm',
                   'length' : 5 * 1024 * 1024,
                   'sector_size' : 512,
                   'partitions' : [],
                   'model' : 'mock'
                   },
    
    '/dev/sdq' : { 'path' : '/dev/sdm',
                   'length' : 4 * 1000 * 1024 * 1024L,
                   'sector_size' : 512,
                   'partitions' : [],
                   'model' : 'mock'
                   },
    
    '/dev/sdd' : { 'path' : '/dev/sdd',
                   'length' : 1 * 1024 * 1024,
                   'sector_size' : 512,
                   'partitions' : [ { 'num' : 0, 'type' : parted.PRIMARY,
                                      'fs_type' : 'ext3',
                                      'native_type' : 0x83,
                                      'geom' : { 'start' : 0, 'end' : 100 } }],
                   'model' : 'mock USB'
                   },
    '/dev/sde' : { 'path' : '/dev/sde',
                   'length' : 0,
                   'sector_size' : 512,
                   'partitions' : [],
                   'model' : 'mock',
                   'error' : True,
                   'errormsg' : 'Error opening /dev/sde: No medium found',
                   },
    '/dev/sdf' : { 'path' : '/dev/sdf',
                   'length' : 1500 * 1024 * 1024,
                   'sector_size' : 512,
                   'partitions' : [{ 'num' : 0, 'type' : parted.PRIMARY,
                                     'fs_type' : 'ext3',
                                     'native_type' : 0x83,
                                     'geom' : { 'start' : 0, 'end' : 200 }},
                                   { 'num' : 1, 'type' : parted.PRIMARY,
                                     'fs_type' : 'ext3',
                                     'native_type' : 0x83,
                                     'geom' : { 'start' : 220, 'end' : 600 }},
                                   ],
                   'model' : 'mock'
                   },
    
    '/dev/sdg' : { 'path' : '/dev/sdg',
                   'length' : 1 * 1024 * 1024,
                   'sector_size' : 512,
                   'partitions' : [ { 'num' : 0, 'type' : parted.PRIMARY,
                                      'fs_type' : 'ext3',
                                      'native_type' : 0x83,
                                      'geom' : { 'start' : 0, 'end' : 100 } }],
                   'model' : 'mock USB'
                   },
    '/dev/sdn' : { 'path' : '/dev/sdn',
                   'length' : 1 * 1024 * 1024,
                   'sector_size' : 512,
                   'partitions' : [ { 'num' : 0, 'type' : parted.PRIMARY,
                                      'fs_type' : 'ext3',
                                      'native_type' : 0x83,
                                      'geom' : { 'start' : 0, 'end' : 100 } }],
                   'model' : 'mock USB'
                   },
    '/dev/sdt' : { 'path' : '/dev/sdt',
                   'length' : 150 * 1024 * 1024,
                   'sector_size' : 512,
                   'partitions' : [],
                   'model' : 'mock'
                   },
    '/dev/cciss/c0d0' : { 'path' : '/dev/cciss/c0d0',
                   'length' : 150 * 1024 * 1024,
                   'sector_size' : 512,
                   'partitions' : [],
                   'model' : 'mock',
                   },
    '/dev/cciss/c0d1' : { 'path' : '/dev/cciss/c0d1',
                   'length' : 1,
                   'sector_size' : 512,
                   'partitions' : [],
                   'model' : 'mock',
                   },
    }, {
    'ext2' : { 'name' : 'ext2', 'formattable' : True },
    'ext3' : { 'name' : 'ext3', 'formattable' : True },
    'linux-swap' : { 'name' : 'linux-swap', 'formattable' : True },
    'fat32' : { 'name' : 'fat32', 'formattable' : True },
    'fat16' : { 'name' : 'fat16', 'formattable' : True },
    'vmfs3' : { 'name' : 'vmfs3', 'formattable' : True },
    'vmkcore' : { 'name' : 'vmkcore', 'formattable' : False },
    })

fauxroot.PART_UUID_CONFIG = {
    '/dev/cciss/c0d0p1' : '4aa8e7c6-24ef-4f3e-9986-e628f7d1d40a',
    '/dev/sda1' : '4aa8e7c6-24ef-4f3e-9986-e628f7d1d51b',
    '/dev/sda2' : '4aa8e7c6-24ef-4f3e-9986-e628f7d1d61b',
    '/dev/sdb1' : '4aa8e7c6-24ef-4f3e-9986-e628f7d1d51d',
    '/dev/sdh1' : '4aa8e7c6-24ef-4f3e-9986-e628f7d1d51e',
    '/dev/sdh2' : '4aa8e7c6-24ef-4f3e-9986-e628f7d1d51f',
    '/dev/sdh4' : '4aa8e7c6-24ef-4f3e-9986-e628f7d1d51c',
    '/dev/sdh5' : '4aa8e7c6-24ef-4f3e-9986-e628f7d1d51d',
    '/dev/hda1' : '4aa8e7c6-24ef-4f3e-9986-e628f7d1d51g',
    '/dev/hda2' : '4aa8e7c6-24ef-4f3e-9986-e628f7d1d52g',
    '/dev/sdf1' : '4aa8e7c6-24ef-4f3e-9986-e628f7d1d51h',
    }

def ext3PartitionContents(uuid):
    superBlockOffset = 0x400
    superBlockFormat = 'IIIIIII7IBBH8IIII16s16s'

    retval = "\0" * superBlockOffset

    superBlock = [0] * 14
    superBlock += [0123, 0357] # magic numbers
    superBlock += [0] + [0] * 11
    superBlock += [util.uuidStringToBits(uuid)]
    superBlock += ['\0' * 16]

    retval += struct.pack(superBlockFormat, *superBlock)
    
    return retval

fauxroot.WRITTEN_FILES["/dev/sda1"] = fauxroot.CopyOnWriteFile(
    ext3PartitionContents(fauxroot.PART_UUID_CONFIG['/dev/sda1']),
    fmode=stat.S_IFBLK,
    rdev=(8 << 8 | 1))
fauxroot.WRITTEN_FILES["/dev/sda2"] = fauxroot.CopyOnWriteFile(
    ext3PartitionContents(fauxroot.PART_UUID_CONFIG['/dev/sda2']),
    fmode=stat.S_IFBLK,
    rdev=(8 << 8 | 1))

# A few fake rpm files for the rpm module to chew on.  (nom nom nom)
rpm.RPM_FILES = {
    'VMware-esx-gunk-e.x.p-0.3.00000.i386.rpm' : dict(
          name='VMware-esx-gunk',
          size=1234,
          requires='',
          conflicts='' ),

    'foopkg-3.2.i386.rpm' : dict(
          name='foopkg',
          size=1234,
          requires='',
          conflicts='' ),

    'VMware-esx-apps-e.x.p-0.3.00000.i386.rpm' : dict(
          name='VMware-esx-apps',
          size=1234,
          requires='',
          conflicts='' ),

    'VMware-esx-drivers-scsi-mptspi-4.0.22vmw-00000.x86_64.rpm' : dict(
          name='VMware-esx-drivers-scsi-mptspi',
          size=1234,
          requires='',
          conflicts='' ),
    
    'VMware-esx-drivers-net-e1000-7.6.15.5-00000.x86_64.rpm' : dict(
          name='VMware-esx-drivers-net-e1000',
          size=1234,
          requires='',
          conflicts='' ),
    }

for rpmFileName, rpmFileDict in rpm.RPM_FILES.items():
    # we need some files to have content for Package.readRPMHeaderInfo
    fp = fauxroot.CopyOnWriteFile('# rpm file')
    path = os.path.join("/mnt/source/VMware/RPMS", rpmFileName)
    fauxroot.WRITTEN_FILES[path] = fp


def _excludeWeaselFile(filename):
    thisDir = os.path.abspath(os.path.dirname(__file__))
    path = os.path.join(thisDir, os.path.pardir, os.path.pardir, filename)
    
    return os.path.normpath(path)

# XXX Hack to exclude weasel data files, when referenced by their absolute path,
# from getting munged by fauxroot magic.
fauxroot.EXCLUDE_FILES = map(_excludeWeaselFile, [
    "timezone.xml",
    "keyboard.xml",
    "weasel.xml",
    # "packages.xml",
    "eula.txt",
    ])

fauxroot.EXCLUDE_PATHS = [
    "/usr/share/zoneinfo",
    ]

fauxroot.EMPTY_FILES = [
    "/vmfs/devices/disks",
    ]

fauxroot.PROMPTS = {
    "Press <enter> to reboot..." : itertools.repeat(""),
    "The machine will reboot automatically " \
        "or\npress <enter> to reboot immediately..." : itertools.repeat(""),
    }

emptyFiles = [
    "/mnt/sysimage/etc/init.d/iptables",
    ]

for filename in emptyFiles:
    fauxroot.WRITTEN_FILES[filename] = fauxroot.CopyOnWriteFile()

UUID_RATCHET = 0

def _fauxUUID():
    '''Return fake UUIDs that have the prefix "4aa8e7c6-24ef-4f3e-9986-" and
    the remaining digits start at zero and are incremented by one each time
    this function is called.'''
    
    global UUID_RATCHET
    
    UUID_RATCHET += 1
    
    f = StringIO("4aa8e7c6-24ef-4f3e-9986-%012x" % UUID_RATCHET)
    f.seek(0)
    return f

fauxroot.PROC_FILES = {
    '/proc/sys/kernel/random/uuid' : _fauxUUID,
    }


# to simulate a bad burn, change BRANDISO_WRITTEN_DIGEST to something else
BRANDISO_WRITTEN_DIGEST = 'g\xa0\xe0\xd93\xff\xd1\xd7\xd8\x94a\x1a\xb1\xec\xd8m'
oldextractISOChecksums = brandiso.extract_iso_checksums
def extractISOChecksums(filename):
    img = StringIO('this is some fake file contents')
    checksumSize = 16
    fauxroot.longRunningFunction(1, 'brandiso.calc_md5', 10)
    digest = brandiso.calc_md5(img, 0, checksumSize)
    return (BRANDISO_WRITTEN_DIGEST, digest, 'SOME_ID')
brandiso.extract_iso_checksums = extractISOChecksums


def binSh(argv):
    if argv[1] == '/tmp/initscripts.sh':
        return ("14.foobar\n"
                "71.bogusipmi\n",
                0)
    return ("", 0)

# Tracks the current device index (e.g. /dev/sdc)
VMFS_DEVICE = string.ascii_lowercase.index('h')
# Tracks vmfs volumes that have been created by vmkfstools.
VMFS_IMAGES = {}

def usrSbinVmkfstools(argv):
    '''Mock vmkfstools that creates fake vmfs volumes for the mock vsd.'''
    global VMFS_DEVICE

    opts, args = getopt.getopt(argv[1:], 'c:C:b:S:VP')
    size = 0
    volumeName = None
    blockSize = 1048576
    for opt, val in opts:
        if opt in ('-c',):
            size = int(val[:-1])
            if val.lower().endswith('m'):
                size *= 1024 * 1024
        elif opt in ('-S',):
            volumeName = val
        elif opt in ('-b',):
            if val.lower().endswith('m'):
                blockSize = int(val[:-1]) * 1024 * 1024
        elif opt in ('-P',):
            return (
                "Mode: public\n"
                "Capacity 72477573120 (69120 file blocks * 1048576), "
                "63816335360 (60860 blocks) avail\n", 0)

    if size:
        devname = '/dev/sd%s' % string.ascii_lowercase[VMFS_DEVICE]
        VMFS_DEVICE += 1
        parted._updateConfig(devices = {
            devname : { 'path' : devname,
                        'length' : size,
                        'sector_size' : 512,
                        'partitions' : [],
                        'model' : 'vm-mock' }
            })
        VMFS_IMAGES[args[0]] = devname
    elif volumeName:
        # Add the new volume to the list of datastores.
        uuid = _fauxUUID().read()
        vmkctl.VMKCTL_STORAGE_CONFIG['datastores'].append({
            'blockSize' : blockSize,
            'blocksUsed' : 2832,
            'consolePath' : '/vmfs/volumes/%s' % uuid,
            'majorVersion' : 3,
            'minorVersion' : 32,
            'totalBlocks' : 7680,
            'volumeName' : volumeName,
            'uuid' : uuid,
            'diskLuns' : [
            { 'name' : 'vml.0000:5',
              'deviceName' : 'vml.0000', },
            ],
            })
        
    return ("", 0)
    

def usrSbinVsd(argv):
    '''Mock vsd that returns the device name for a mock vmfs volume.'''
    
    opts, args = getopt.getopt(argv[1:], 'cuf:')
    size = 0
    devname = ""
    for opt, val in opts:
        if opt in ('-f',):
            devname = VMFS_IMAGES[val]

    return (devname, 0)

def initScript(argv):
    'Mock init scripts.'''

    opts, args = getopt.getopt(argv[1:], '')
    result = INIT_SCRIPTS.get(args[1])

    if result:
        return result
    else:
        return ('', 0)

INIT_SCRIPTS = {'14.foobar' : ("Foobar", 0), '71.bogusipmi' : ("Foobar", 1)}

PACKAGES_XML_CONTENTS = open(os.path.join(
        CONFIG_DIR, "mnt/source/packages.xml")).read()

PACKAGE_DATA_PKL_CONTENTS = open(os.path.join(
        CONFIG_DIR,
        "mnt/source/VMware/RPMS/packageData.pkl")).read()

DRIVERS_XML_CONTENTS = open(os.path.join(
        CONFIG_DIR, "../drivers/drivers.good.xml")).read()

MPTSPI_RPM_CONTENTS = '# RPM file'

E1000_RPM_CONTENTS = '\xed\xab\xee\xdb\x03\x00\x00\x00\x00\xffVMware-esx-drivers-net-e1000-7.6.15.5-00000\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\x00\x05\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x8e\xad\xe8\x01\x00\x00\x00\x00\x00\x00\x00\x04\x00\x00\x00P\x00\x00\x00>\x00\x00\x00\x07\x00\x00\x00@\x00\x00\x00\x10\x00\x00\x01\r\x00\x00\x00\x06\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x03\xe8\x00\x00\x00\x04\x00\x00\x00,\x00\x00\x00\x01\x00\x00\x03\xec\x00\x00\x00\x07\x00\x00\x000\x00\x00\x00\x10b3169d561af51210b776048283c0822903c5499f\x00\x00\x00\x00\x00\x01m\xde\x0e\xf3A\xd6\x00\xde\x99\x9d\xa2\xb9\xbf\x15\x19\x9f\xfe\xf1\x00\x00\x00>\x00\x00\x00\x07\xff\xff\xff\xc0\x00\x00\x00\x10\x8e\xad\xe8\x01\x00\x00\x00\x00\x00\x00\x007\x00\x00\x03\x90\x00\x00\x00?\x00\x00\x00\x07\x00\x00\x03\x80\x00\x00\x00\x10\x00\x00\x00d\x00\x00\x00\x08\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x03\xe8\x00\x00\x00\x06\x00\x00\x00\x02\x00\x00\x00\x01\x00\x00\x03\xe9\x00\x00\x00\x06\x00\x00\x00\x1f\x00\x00\x00\x01\x00\x00\x03\xea\x00\x00\x00\x06\x00\x00\x00(\x00\x00\x00\x01\x00\x00\x03\xec\x00\x00\x00\t\x00\x00\x00.\x00\x00\x00\x01\x00\x00\x03\xed\x00\x00\x00\t\x00\x00\x00@\x00\x00\x00\x01'

PARTITION_CONTENTS = {
    "/dev/sda1" : {
        "grub/grub.conf" : open(os.path.join(
                CONFIG_DIR, "mnt/sysimage/boot/grub/grub.conf")).read(),
        "System.map-2.6.18-53.ESX" : "",
        "initrd.img" : "",
        "initrd-2.6.18-53.ESX.img" : "",
        "config-2.6.18-53.ESX" : "",
        "vmlinuz" : "",
        "vmlinuz-2.6.18-53.ESX" : "",
        },
    "/dev/sdd1" : {
        "packages.xml" : PACKAGES_XML_CONTENTS,
        },
    "/dev/sdf1" : {
        "grub/grub.conf" : open(os.path.join(
                CONFIG_DIR, "mnt/sysimage/boot/grub/grub.conf")).read(),
        "System.map-2.6.18-53.ESX" : "",
        "initrd.img" : "",
        "initrd-2.6.18-53.ESX.img" : "",
        "config-2.6.18-53.ESX" : "",
        "vmlinuz" : "",
        "vmlinuz-2.6.18-53.ESX" : "",
        },
    "/dev/sdg1" : {
        "packages.xml" : "", # bad file
        "esx.iso" : "",
        "esx_40.iso" : "",
        },
    "/dev/sdn1" : {
        "packages.xml" : "", # bad file
        },
    "/dev/sr1" : {
        "packages.xml" : "", # bad file
        },
    "/mnt/media/esx.iso" : {
        "packages.xml" : PACKAGES_XML_CONTENTS,
        },
    "/mnt/media/esx_40.iso" : {
        "packages.xml" : PACKAGES_XML_CONTENTS.replace("e.x.p", "4.0"),
        },
    "/dev/cdrom" : {
        "metadata.zip" : "# empty",
        "packages.xml" : PACKAGES_XML_CONTENTS,
        "drivers.xml" : DRIVERS_XML_CONTENTS,
        "VMware/RPMS/foopkg-3.2.i386.rpm" : "# rpm file",
        "VMware/RPMS/VMware-esx-apps-e.x.p-0.3.00000.i386.rpm" : "# rpm file",
        "VMware-esx-drivers-scsi-mptspi-4.0.22vmw-00000.x86_64.rpm" : \
          MPTSPI_RPM_CONTENTS,
        "VMware-esx-drivers-net-e1000-7.6.15.5-00000.x86_64.rpm" : \
          E1000_RPM_CONTENTS,
        },
    # use these "partitions" to fake NFS
    "jpowell-esx.eng.vmware.com:/test/dir" : {
        "metadata.zip" : "# empty",
        "packages.xml" : PACKAGES_XML_CONTENTS,
        "VMware/RPMS/packageData.pkl" : PACKAGE_DATA_PKL_CONTENTS,
        "VMware/RPMS/foopkg-3.2.i386.rpm" : "# rpm file",
        "VMware/RPMS/VMware-esx-apps-e.x.p-0.3.00000.i386.rpm" : "# rpm file",
        "VMware/RPMS/VMware-esx-gunk-e.x.p-0.3.00000.i386.rpm" : "# rpm file",
        },
    "good.server:/var/www/two" : {
        "packages.xml" : PACKAGES_XML_CONTENTS,
        "VMware/RPMS/packageData.pkl" : PACKAGE_DATA_PKL_CONTENTS,
        },
    "good.server:/var/www/" : {
        "esx.iso" : "",
        },
    "/mnt/nfs-isosrc/esx.iso" : {
        "packages.xml" : PACKAGES_XML_CONTENTS,
        "VMware/RPMS/packageData.pkl" : PACKAGE_DATA_PKL_CONTENTS,
        "VMware/RPMS/foopkg-3.2.i386.rpm" : "# rpm file",
        "VMware/RPMS/VMware-esx-apps-e.x.p-0.3.00000.i386.rpm" : "# rpm file",
        "VMware/RPMS/VMware-esx-gunk-e.x.p-0.3.00000.i386.rpm" : "# rpm file",
        },
    }

PARTITION_CONTENTS["/dev/sr0"] = PARTITION_CONTENTS["/dev/cdrom"]


def binMount(argv):
    (opts, args) = getopt.getopt(argv[1:], "t:o:")

    devPath = os.path.normpath(args[0])
    if len(args) == 2 and devPath in PARTITION_CONTENTS:
        for filename, data in PARTITION_CONTENTS[devPath].items():
            f = open(os.path.join(args[1], filename), 'w')
            try:
                f.write(data)
            finally:
                f.close()

    return ("", 0)

def usrBinUmount(argv):
    if len(argv) == 2:
        if argv[1] == "/mnt/source":
            # XXX Hack ... the files in the real file system shouldn't be there
            # after this unmount, so mask the one we care about out.
            fauxroot.MASKED_FILES['/mnt/source/packages.xml'] = True

        deadFilenames = [name for name in fauxroot.WRITTEN_FILES
                         if name.startswith(argv[1])]
        for filename in deadFilenames:
            fauxroot.UMOUNTED_FILES[filename] = fauxroot.WRITTEN_FILES[filename]
            del fauxroot.WRITTEN_FILES[filename]

    return ("", 0)

def sbinMountNfs(argv):
    return binMount(["/bin/mount", argv[1], argv[2]])

def usrBinEject(argv):
    return ("", 0)

def initd41vmkiscsi(argv):
    consoleDevice = '/dev/sdia'
    newone = {'consoleDevice' : consoleDevice,
              'name' : 'vml.020',
              'devfsPath' : '/vmfs/devices/disks/vml.020',
              'model' : 'EQLOGIC_ISCSI',
              'vendor' : 'EQLOGIC',
              'lunType' : 0,
              'scsiPaths' : [] }
    # Append if not there yet.
    for d in vmkctl.VMKCTL_STORAGE_CONFIG['disks']:
        if d['consoleDevice'] == consoleDevice:
            return ("", 0)
    vmkctl.VMKCTL_STORAGE_CONFIG['disks'].append(newone)
    parted._updateConfig({consoleDevice: {
       'path' : consoleDevice,
       'length' : 1000000,
       'sector_size' : 512,
       'partitions' : [],
       'model' : newone['model']}})

    ## I'll welcome suggestions for how to do this right:
    fauxroot.PART_UUID_CONFIG[consoleDevice+'1'] = \
        '4aa8e7c6-24ef-4f3e-9986-e628f7d1d51iscsi'
    return ("", 0)

def usrSbinEsxcfgAuth(argv):
    return ("", 0)

def usrSbinMkswap(argv):
    assert fauxroot.FAUXROOT
    
    swapFile = open(argv[2], 'w')
    swapFile.write("x" * 2048)
    swapFile.close()
    
    return ("", 0)

def esx4UpgradeIsoinfo(argv):
    if ">" in argv:
        redirect = argv.index(">")
        outputPath = argv[redirect + 1]
        output = open(outputPath, 'w')

        (opts, args) = getopt.getopt(argv[1:redirect], "i:x:")
        for opt, arg in opts:
            if opt in ("-i",):
                isoPath = arg
            elif opt in ("-x",):
                extractPath = arg
        
        output.write("# contents of %s from %s\n" % (extractPath, isoPath))
        output.close()

        return ("", 0)
    
    return ("", 0)

TUNE2FS_OUTPUT = """tune2fs 1.32 (09-Nov-2002)
Filesystem volume name:   <not available>
Last mounted on:          <not available>
Filesystem UUID:          %s
Filesystem magic number:  0xEF53
Filesystem revision #:    1 (dynamic)
Filesystem features:      has_journal filetype needs_recovery sparse_super
Default mount options:    (none)
Filesystem state:         clean
Errors behavior:          Continue
Filesystem OS type:       Linux
Inode count:              26104
Block count:              104391
Reserved block count:     5219
Free blocks:              69993
Free inodes:              26068
First block:              1
Block size:               1024
Fragment size:            1024
Blocks per group:         8192
Fragments per group:      8192
Inodes per group:         2008
Inode blocks per group:   251
Filesystem created:       Thu Aug  9 08:34:52 2007
Last mount time:          Wed Dec 12 00:34:23 2007
Last write time:          Wed Dec 12 00:34:23 2007
Mount count:              28
Maximum mount count:      -1
Last checked:             Thu Aug  9 08:34:52 2007
Check interval:           0 (<none>)
Reserved blocks uid:      0 (user root)
Reserved blocks gid:      0 (group root)
First inode:              11
Inode size:             128
Journal UUID:             <none>
Journal inode:            8
Journal device:           0x0000
First orphan inode:       0
"""

def sbinTune2fs(argv):
    (opts, args) = getopt.getopt(argv[1:], "lc:i:j:")

    if ("-l", '') in opts and args[0] in fauxroot.PART_UUID_CONFIG:
        return (TUNE2FS_OUTPUT % fauxroot.PART_UUID_CONFIG[args[0]], 0)
    
    return ("", 0)

SH_CWD = ""
def shcd(argv):
    global SH_CWD
    
    SH_CWD = argv[1]

    return ("", 0)

def cpio(argv):
    # XXX This command only emulates what's needed for esx4upgrade.py and is
    # expecting the arguments as given there.
    argsUpToRedirect = argv[1:argv.index(">")]
    (_opts, args) = getopt.getopt(argsUpToRedirect, "di")
    
    for pattern in args:
        if not os.path.isabs(pattern):
            pattern = os.path.join(SH_CWD, pattern)

        f = open(pattern, 'w')
        f.write("# empty\n")
        f.close()

def gunzip(argv):
    # XXX This command only emulates what's needed for esx4upgrade.py and is
    # expecting the arguments as given there.
    if "|" in argv:
        argsUpToPipe = argv[1:argv.index("|")]
        (opts, args) = getopt.getopt(argsUpToPipe, "c")

        if args[0] == "/mnt/cdrom/isolinux/initrd.img":
            # XXX fill more out?

            otherCommand = argv[argv.index("|") + 1:]
            if otherCommand[0] == "cpio":
                cpio(otherCommand)
            
            return ("", 0)
    
    return ("", 1)

def binLoadkeys(argv):
    return ("", 0)

def usrBinSetxkbmap(argv):
    return ("", 0)

def usrSbinUseradd(argv):
    (opts, args) = getopt.getopt(argv[1:], "c:d:g:s:u:p:o")

    entry = [args[0], "x", "0", "0", "Joe Blow", "/home/blow", "/bin/sh"]

    for opt, arg in opts:
        if opt in ("-c",):
            entry[4] = arg
        elif opt in ("-d",):
            entry[5] = arg
        elif opt in ("-g",):
            entry[3] = arg
        elif opt in ("-s",):
            entry[6] = arg
        elif opt in ("-u",):
            entry[2] = arg
        elif opt in ("-p",):
            entry[1] = arg
    
    f = open("/etc/passwd", 'a')
    f.write("%s\n" % ":".join(entry))
    f.close()

    return ("", 0)

def usrSbinUsermod(argv):
    (opts, args) = getopt.getopt(argv[1:], "d:s:")

    contents = open("/etc/passwd", 'r').read()

    entryLine = [line for line in contents.split() if line.startswith(args[0])]
    if not entryLine:
        return ("unknown user: %s" % args[0], 1)
    
    entry = entryLine[0].split(':')

    for opt, arg in opts:
        if opt in ("-d",):
            entry[5] = arg
        elif opt in ("-s",):
            entry[6] = arg

    newContents = re.sub(re.escape(entryLine[0]), ":".join(entry), contents)
    
    f = open("/etc/passwd", 'w')
    f.write(newContents)
    f.close()

    return ("", 0)

def usrSbinGrub(argv):
    return ("", 0)

def esxcfgBoot(argv):
    (opts, args) = getopt.getopt(argv[1:], "b", ["update-trouble", "rebuild"])

    image, version = ["initrd.img", "2.6.18-34.ESX"] # XXX hardcoded

    # touch the initrd.img this should make.
    base, ext = os.path.splitext(image)
    path = "%s-%s%s" % (base, version, ext)
    open(os.path.join("/boot", path), "w").close()
    open(os.path.join("/boot", image), "w").close()
    
    return ("", 0)

def shecho(argv):
    if argv == ["echo", "mkblkdevs", "|", "nash", "--force"]:
        for disk in vmkctl.VMKCTL_STORAGE_CONFIG['disks']:
            # touch the devices so DiskSet.probeDisks() works.
            open(disk['consoleDevice'], 'w').close()

def binRpm(argv):
    return ("", 0)

def esxcfgConfigCheck(argv):
    return ("", 0)

def sbinChkconfig(argv):
    return ("", 0)

def tzDataUpdate(argv):
    return ("", 0)

def chvt(argv):
    return ("", 0)

def date(argv):
    #TODO: just ignore the time zone env variable for now
    tzenv, date, dashS, newValue = argv
    # newValue is of the form MMddhhmmYYYY.ss
    month  = int(newValue[0:2])
    day    = int(newValue[2:4])
    hour   = int(newValue[4:6])
    minute = int(newValue[6:8])
    year   = int(newValue[8:12])
    second = int(newValue[-2:])
    old = datetime.datetime(*fauxroot.oldLocaltime()[:6])
    new = datetime.datetime(year, month, day, hour, minute, second)
    fauxroot.setTimeDelta(new - old)

def usrSbinCheckSerial(argv):
    (opts, args) = getopt.getopt(argv[1:], "c:")

    for opt, arg in opts:
        if opt in ('-c',):
            if arg in ("0this-0is0a-valid-seria-lnumb",
                       "thisi-saval-idser-ialnu-mber1"):
                return ("", 0)
            elif arg in ("thisi-sanex-pired-seria-lnumb",):
                return ("", 4 << 8)
            elif re.match(r'\w{5}-\w{5}-\w{5}-\w{5}-\w{5}', arg) is not None:
                return ("", 5 << 8)
    
    return ("invalid serial number", 3 << 8)

def insmod(argv):
    return ("", 0)

def touch(argv):
    for filename in argv[1:]:
        fp = open(filename, 'a')
        fp.close()

    return ("", 0)

def usrBinChage(argv):
    return ("", 0)

def usrSbinEsxcfgInfo(_argv):
    return ("    |---Physical Mem.............2147483648\n"
            "    |---Service Console Mem (Cfg).....272\n", 0)

def usrSbinEsxcfgFirewall(argv):
    (opts, args) = getopt.getopt(argv[1:], "h", [
            "allowIncoming",
            "blockIncoming",
            "allowOutgoing",
            "blockOutgoing",
            "openPort=",
            "closePort=",
            "enableService",
            "disableService",
            ])

    for opt, arg in opts:
        if opt == "--openPort":
            if arg.startswith("1,"):
                return ("", 1)
        elif opt == "--closePort":
            if arg.startswith("700,"):
                return ("already closed", 1)

    return ("", 0)

def sbinLspci(_argv):
    return ("", 0)

def usrSbinEsxupdate(_argv):
    return ("", 0)

def etcInitdIptables(argv):
    return ("", 0)

fauxroot.EXEC_FUNCTIONS = {
    "." : binSh,
    "/bin/sh" : binSh,
    "/bin/bash" : binSh,
    "/usr/sbin/vmkfstools" : usrSbinVmkfstools,
    "/usr/sbin/vsd" : usrSbinVsd,
    "/bin/mount" : binMount,
    "/usr/bin/mount" : binMount,
    "/usr/bin/umount" : usrBinUmount,
    "/sbin/umount.nfs" : usrBinUmount,
    "/usr/bin/eject" : usrBinEject,
    "/init.d/41.vmkiscsi" : initd41vmkiscsi,
    "/usr/sbin/esxcfg-auth" : usrSbinEsxcfgAuth,
    "/usr/sbin/mkswap" : usrSbinMkswap,
    "/esx4-upgrade/isoinfo" : esx4UpgradeIsoinfo,
    "/sbin/tune2fs" : sbinTune2fs,
    "/usr/sbin/tune2fs" : sbinTune2fs,
    "cd" : shcd,
    "gunzip" : gunzip,
    "/bin/loadkeys" : binLoadkeys,
    "/usr/bin/setxkbmap" : usrBinSetxkbmap,
    "/usr/sbin/useradd" : usrSbinUseradd,
    "/usr/sbin/usermod" : usrSbinUsermod,
    "/usr/sbin/grub" : usrSbinGrub,
    "echo" : shecho,
    "/bin/rpm" : binRpm,
    "/sbin/chkconfig" : sbinChkconfig,
    "/mnt/sysimage/usr/sbin/esxcfg-configcheck" : esxcfgConfigCheck,
    "/usr/sbin/esxcfg-boot" : esxcfgBoot,
    "/usr/sbin/tzdata-update" : tzDataUpdate,
    "chvt" : chvt,
    "date" : date,
    "/usr/sbin/check_serial" : usrSbinCheckSerial,
    "/sbin/mount.nfs" : sbinMountNfs,
    "insmod" : insmod,
    "touch" : touch,
    "/usr/bin/chage" : usrBinChage,
    "/usr/sbin/esxcfg-info" : usrSbinEsxcfgInfo,
    "/usr/sbin/esxcfg-firewall" : usrSbinEsxcfgFirewall,
    "/init" : initScript,
    "/sbin/lspci" : sbinLspci,
    "/usr/sbin/esxupdate" : usrSbinEsxupdate,
    "/etc/init.d/iptables" : etcInitdIptables,
    }

if __name__ == "__main__": #pragma: no cover
   import doctest
   os.chdir(os.path.join(os.path.curdir, os.path.dirname(__file__)))
   doctest.testmod()
