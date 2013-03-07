
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
import fsset
import migrate
import userchoices
import partition
import util
from log import log
from consts import HOST_ROOT, ESX3_INSTALLATION
from remote_files import NFSMounter

class FstabFile(migrate.TextConfigFile):
    class FsData(migrate.NamedList):
        STRUCT = ['device', 'mntpoint', 'fstype', 'flags', 'freq', 'passno']

        def isMigratable(self):
            return ((self.device.startswith("UUID=") or
                     self.fstype == "nfs") and
                    (self.fstype != "swap"))

        def isDoubleMounted(self, combinedBootAndRoot):
            return (self.mntpoint in ["/boot"] or
                    (combinedBootAndRoot and self.mntpoint in ["/"]))

    REQ_FIELD_COUNT = 3
    ELEMENT_TYPE = FsData

    def _addDefaultFields(self, fields):
        '''The last two fields in fstab (freq and passno) are not required to
        be in the file, so we initialize them to their default value of zero.'''
        retval = list(fields)
        # The flags field can be blank, so we fill it in with "defaults".
        if len(retval) == self.REQ_FIELD_COUNT:
            retval.append("defaults")
        # The remaining fields can also be blank, they should be filled with
        # zeroes.
        while (self.REQ_FIELD_COUNT <=
               len(retval) <
               len(self.ELEMENT_TYPE.STRUCT)):
            retval.append("0")
        return retval

def hostActionWriteFstab(_context):
    allRequests = partition.allUserPartitionRequests()
    allRequests.sort(sortByMountPoint=True)

    myFsset = fsset.FileSystemSet()
    for request in allRequests:
        # skip vmfs partitions since they can't be mounted
        if (not isinstance(request.fsType, fsset.swapFileSystem) and
            not request.mountPoint):
            continue

        uuid = request.fsType.getUuid(request.consoleDevicePath)
        if uuid:
            spec = "UUID=%s" % uuid
        else:
            spec = request.consoleDevicePath

        if isinstance(request.fsType, fsset.swapFileSystem):
            mountPoint = "swap"
        else:
            mountPoint = request.mountPoint
        entry = fsset.FileSystemSetEntry(
            spec, mountPoint, request.fsType, format=False)
        myFsset.addEntry(entry)


    # Make sure all the mount points exist.
    for entry in myFsset:
        path = os.path.join(consts.HOST_ROOT, entry.mountPoint.lstrip('/'))
        if not os.path.exists(path):
            os.makedirs(path)

    # panic when the filesystem with the logs goes read-only
    myFsset.sort(sortByMountPoint=True)
    myFsset.reverse()

    for entry in myFsset:
        if entry.mountPoint in ['/var/log', '/var', '/']:
            assert 'errors=' not in entry.options

            if not entry.options:
                entry.options = 'errors=panic'
                break
            else:
                entry.options += ',errors=panic'
                break

    # re-sort by mount point
    myFsset.sort(sortByMountPoint=True)

    util.writeConfFile(consts.HOST_ROOT + 'etc/fstab', str(myFsset))

def hostActionMigrateFstab(_context):
    oldFile = FstabFile.fromFile(HOST_ROOT + ESX3_INSTALLATION + "/etc/fstab")
    newFile = open(os.path.join(HOST_ROOT, "etc/fstab"), 'a')

    try:
        # Write out any entries that should need be cleaned out by the upgrade
        # cleanup script.
        for entry in oldFile:
            if entry.isDoubleMounted(
                userchoices.isCombinedBootAndRootForUpgrade()):
                # Write out the entry for "/boot" or "/" if there is no "/boot"
                # in the old install.
                if userchoices.isCombinedBootAndRootForUpgrade():
                    entry.mntpoint = ESX3_INSTALLATION + entry.mntpoint
                newFile.write("%s\n" % " ".join(entry))

        # Write out a header to demarcate the start of the entries that should
        # be removed by the upgrade cleanup script.
        newFile.write(
            "\n"
            "# BEGIN migrated entries\n"
            "#   Note: Any entries in this section will be removed\n"
            "#   when cleaning out the ESX v3 installation.\n")
        for entry in oldFile:
            if not entry.isMigratable():
                log.warning("not migrating fstab entry: %s" % " ".join(entry))
                continue

            if entry.mntpoint.startswith(ESX3_INSTALLATION):
                # Skip entries that have already been migrated by the first
                # loop above.
                continue
            
            # We have to mount /boot in the old and new cos, so it'll be rw
            # and show up twice in the file.
            if not entry.isDoubleMounted(
                userchoices.isCombinedBootAndRootForUpgrade()):
                entry.flags += ",ro"
            
            oldMntpoint = entry.mntpoint
            entry.mntpoint = ESX3_INSTALLATION + entry.mntpoint
            newFile.write("%s\n" % " ".join(entry))
            
            if oldMntpoint in ["/",]:
                # We've already mounted the old root by this point since we
                # need to be able to read the old fstab.
                continue

            # Mount the rest of entries in case they're needed by the %post.
            mntpoint = os.path.normpath(HOST_ROOT + entry.mntpoint)
            if os.path.islink(mntpoint):
                # XXX The user's configuration needs to be corrected...
                log.warn("mount point refers to a link, ignoring...")
                rc = 1
            elif entry.fstype in ["swap"]:
                # ignore
                rc = 0
            elif entry.fstype in ["nfs"]:
                # Don't use the cos infrastructure to do the mount since
                # resolv.conf/hosts is not transferred over yet.
                mounter = NFSMounter(mntpoint)
                host, root = entry.device.split(':', 1)
                if mounter.mount(host, root, entry.flags + ",bg,soft,nolock"):
                    rc = 0
                else:
                    rc = 1
            else:
                rc = util.mount(entry.device, mntpoint)
                
            if rc:
                log.warn("unable to mount -- %s" % " ".join(entry))
        newFile.write("# END migrated entries\n")
    finally:
        newFile.close()
