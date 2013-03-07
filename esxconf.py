
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
import md5
import glob
import shutil
import shlex
import userchoices

import tempfile
import devices
import util

from log import log
from consts import HOST_ROOT
from migrate import clonePath

INITRD_ESX_CONF_CHECKSUM = None
ESXCONF_FILE = "/etc/vmware/esx.conf"

def _computeEsxConfChecksum():
    m = md5.new()
    m.update(open(ESXCONF_FILE).read())
    retval = m.hexdigest()
    log.info("digest of initrd esx.conf -- %s" % retval)

    return retval

def hostActionCopyConfig(_config):
    global INITRD_ESX_CONF_CHECKSUM
    
    globsToCopy = [
        '/etc/hosts',
        '/etc/resolv.conf',
        '/etc/vmware/esx.conf',
        '/etc/xinetd.d/vmware-authd', # Referenced when turning off ipv6
        '/etc/modprobe.d/blacklist', # Referenced when turning off ipv6
        '/etc/sysconfig/network',
        '/etc/sysconfig/network-scripts/ifcfg-vswif*',
        ]

    # TODO: remove this configcheck, it should be done on bootup.  It's safe
    # to run multiple times though.
    rc = os.system(os.path.join(HOST_ROOT, "usr/sbin/esxcfg-configcheck"))
    assert rc == 0

    for globPath in globsToCopy:
        for srcPath in glob.glob(globPath):
            dstPath = os.path.join(HOST_ROOT, srcPath.lstrip('/'))
            try:
                clonePath(srcPath, dstPath)
                if os.path.islink(srcPath):
                   os.lchown(dstPath, 0, 0)
                else:
                   os.chown(dstPath, 0, 0)

                # XXX Maybe we should turn the files in the initrd into soft
                # links that point at the installed versions of the files...
            except IOError, e:
                log.error("cannot copy %s to %s -- %s" % (
                    srcPath, dstPath, str(e)))

    INITRD_ESX_CONF_CHECKSUM = _computeEsxConfChecksum()

def validateAction(_context):
    '''Check to make sure we have not updated the initrd esx.conf after we
    copied it to the installed system, where it might have also been modified.
    '''
    
    if _computeEsxConfChecksum() != INITRD_ESX_CONF_CHECKSUM:
        log.error("initrd esx.conf has changed after copying to the chroot!")

def hostActionRemoveVmdk(_context):
    vmdkLocation = userchoices.getExistingVmdkLocation().get('vmdkLocation')

    if vmdkLocation:
        log.info("Removing existing vmdk")
        #shutil.rmtree(os.path.split(vmdkLocation)[0])
        devices.removeVmdkFile(vmdkLocation)

def runtimeActionExtractVmdkPathFromInitrd(driveName):
    '''Open the initrd.img file on a disk and find the location of the
       Console VMDK file from esx.conf.
    '''
    diskSet = devices.DiskSet()
    drive = diskSet[driveName]
    partition = drive.findFirstPartitionMatching(fsTypes=('ext3'))
    
    if not partition or partition.partitionId != 1:
        return ''

    tmpMntDir = tempfile.mkdtemp(prefix='weasel', dir='/mnt')
    partition.fsType.mount(partition.consoleDevicePath, tmpMntDir)

    tmpDir = tempfile.mkdtemp(prefix='weasel')

    initrdFilePath = os.path.join(tmpMntDir, 'initrd.img')

    cmd = "cd %s && zcat %s | cpio -id %s" % \
        (tmpDir, initrdFilePath, ESXCONF_FILE[1:])
    util.execCommand(cmd)

    vmdkPath = getValueFromConfig(os.path.join(tmpDir, ESXCONF_FILE[1:]),
                                  '/boot/cosvmdk')   

    partition.fsType.umount(tmpMntDir)

    shutil.rmtree(tmpMntDir)
    shutil.rmtree(tmpDir)

    return vmdkPath

def getValueFromConfig(fileName, esxKey):
    '''Search through esx.conf and find the value for a given key'''
    if not os.path.exists(fileName):
        return None

    lines = open(fileName).readlines()
    for line in lines:
        tokens = shlex.split(line)

        if len(tokens) == 3:
            key = tokens[0]
            value = tokens[2]

            if key != esxKey:
                continue
            else:
                return value
    return None
