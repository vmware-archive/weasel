
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

'''A module that fakes the parted module.

This module provides enough mock classes of the parted module to do a run
through of a weasel installation.  Configuration is done through the
_updateConfig function, which takes a device and filesystem configuration.

See test/good-config.1/fauxconfig.py
'''

from itertools import izip

PARTED_DEV_CONFIG = {}
PARTED_FS_CONFIG = {}

class error(Exception):
    pass

class PedFSType:

    def __init__(self, values):
        self.__dict__.update(values)

    def __repr__(self):
        return repr(self.__dict__)

def file_system_type_get(name):
    return PARTED_FS_CONFIG[name]

class PedDiskLabelType:
    def __init__(self, values):
        self.__dict__.update(values)

PARTED_DISKLABEL_CONFIG = {
    "msdos" : PedDiskLabelType({ "name" : "msdos" }),
    "loop" : PedDiskLabelType({ "name" : "loop" }),
    }

def disk_type_get(name):
    return PARTED_DISKLABEL_CONFIG[name]

class PedGeom:

    def __init__(self, values):
        self.__dict__.update(values)

    def __repr__(self):
        return repr(self.__dict__)

PRIMARY = 0
LOGICAL = 1
EXTENDED = 2
FREESPACE = 4
METADATA = 8
PROTECTED = 16

_PARTED_NATIVE_TYPE = {
  'ext3' : 0x83,
  'ext2' : 0x83,
  'linux-swap' : 0x82,
  'fat32' : 0,
  'vmfs3' : 0xfb,
  'vmkcore' : 0xfc
}

PARTITION_BOOT = 1

class PedPartition:

    def __init__(self, values):
        self.__dict__.update(values)
        if self.fs_type:
            self.fs_type = file_system_type_get(self.fs_type)
        self.geom = PedGeom(self.geom)
        self.flags = {}
        
    def get_name(self):
        return self.name

    def set_flag(self, flag, value):
        self.flags[flag] = value

    def _flatten(self):
        '''Flatten this object back into a dictionary so we can store it in
        PARTED_DEV_CONFIG when a new partition layout is committed.'''
        retval = dict(self.__dict__)
        if self.fs_type:
            retval['fs_type'] = self.fs_type.name
        retval['geom'] = dict(self.geom.__dict__)
        
        return retval

    def __repr__(self):
        return repr(self.__dict__)

class PedDevice:

    @staticmethod
    def get(path):
        retval = PARTED_DEV_CONFIG[path]
        if retval.__dict__.has_key('error') and retval.__dict__['error']:
            raise error, "Error: " + retval.errormsg
        return retval

    def __init__(self, values):
        self.__dict__.update(values)
        self.committedPartitions = map(PedPartition, self.partitions)

    def disk_new_fresh(self, label):
        return PedDisk.new(self)

    def constraint_any(self):
        return 'XXX-constraint'

class PedDisk:

    @staticmethod
    def new(dev):
        return PedDisk(dev)

    def __init__(self, dev):
        self.dev = dev
        self.partitions = map(PedPartition, dev.partitions)
        if hasattr(dev, "labeltype"):
            self.type = PARTED_DISKLABEL_CONFIG[dev.labeltype]
        else:
            self.type = PARTED_DISKLABEL_CONFIG["msdos"]
        self._fill_freespace()

    def commit(self):
        self.dev.committedPartitions = list(self.partitions)

        # Update the "root" object with the new configuration so any subsequent
        # calls to PedDisk.new() get the new config.
        PARTED_DEV_CONFIG[self.dev.path].partitions = [
            part._flatten() for part in self.partitions if part.num != -1]
        return

    def delete_all(self):
        self.partitions = []
        self._fill_freespace()
        self.commit() # XXX

    def partition_new(self, type, fsType, start, end):
        '''
        start - Starting sector for the partition.
        end - Ending sector for the partition, inclusive.
        '''

        if fsType:
            fsType = fsType.name
        return PedPartition({
            'num' : -1,
            'fs_type' : fsType,
            'type' : type,
            'native_type' : _PARTED_NATIVE_TYPE.get(fsType),
            'geom' : { 'start' : start, 'end' : end }
            })

    def add_partition(self, newpart, constraint):
        assert constraint == 'XXX-constraint'

        self.partitions.append(newpart)
        self._fill_freespace()

    def _partition_new_free(self, start, end):
        def isInExtendedPart(xpart):
            return (xpart.type == EXTENDED and
                    xpart.geom.start <= start < xpart.geom.end and
                    xpart.geom.start < end <= xpart.geom.end)
        
        assert start <= end

        xparts = filter(isInExtendedPart, self.partitions)
        if xparts:
            ptype = LOGICAL + FREESPACE
        else:
            ptype = FREESPACE

        return self.partition_new(ptype, None, start, end)

    def _fill_freespace(self):
        self.partitions = filter(
            lambda x: x.type & FREESPACE == 0, self.partitions)
        self._sort()

        start = 0
        end = self.dev.length - 1
        newParts = []
        for part in self.partitions:
            if part.geom.start != start:
                newParts.append(
                    self._partition_new_free(start, part.geom.start))

            if part.type != EXTENDED:
                start = part.geom.end + 1

        if start < end:
            newParts.append(self._partition_new_free(start, end))
        
        self.partitions.extend(newParts)
        self._sort()
        self._renumber()

    def _sort(self):
        self.partitions.sort(lambda x, y: cmp(x.geom.start, y.geom.start))

    def _renumber(self):
        nonfree = [p for p in self.partitions if p.type & FREESPACE == 0]
        for (num, part) in enumerate(nonfree):
            part.num = num + 1 # partitions are not zero-based

    def next_partition(self, prev=None):
        if not prev:
            index = 0
        else:
            index = self.partitions.index(prev) + 1
        if index < len(self.partitions):
            return self.partitions[index]
        else:
            return None

def _updateConfig(devices = None, fsdict = None):
    if fsdict:
        for fs in fsdict:
            PARTED_FS_CONFIG[fs] = PedFSType(fsdict[fs])
    if devices:
        for dev in devices:
            PARTED_DEV_CONFIG[dev] = PedDevice(devices[dev])

def _resetConfig():
    PARTED_DEV_CONFIG = {}
    PARTED_FS_CONFIG = {}
