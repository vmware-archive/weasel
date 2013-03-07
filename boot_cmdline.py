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
boot_cmdline.py

This module is responsible for parsing arguments that were set on the
"boot:" command line
'''
import os
import re
import sys
import util
import media
import shlex
import cdutil
import devices
import networking
import userchoices
import applychoices
import remote_files
from log import log
from consts import ExitCodes, CDROM_DEVICE_PATH
from grubupdate import GRUB_CONF_PREV

USB_MOUNT_PATH = "/mnt/usbdisk"
UUID_MOUNT_PATH = "/mnt/by-uuid"
CDROM_MOUNT_PATH = "/mnt/cdrom"

genericErr = ('There was a problem with the %s specified on the command'
              ' line.  Error: %s.')

KERNEL_BUFFER_LEN = 256

def failWithLog(msg):
    log.error("installation aborted")
    log.error(msg)
    sys.exit(ExitCodes.WAIT_THEN_REBOOT)

class NetworkChoiceMaker(object):
    '''A NetworkChoiceMaker object will add choices to userchoices that
    are necessary consequences of the user adding some earlier choice.
    For example, if the user chooses an IP address, but doesn't make a
    choice for the netmask, we need to make a guess for the netmask.
    If the user doesn't choose ANY networking options, then the
    assumption is that we're not doing a network install and the
    NetworkChoiceMaker object's "needed" attribute will be False.
    '''
    def __init__(self):
        self.needed = False

    @applychoices.ensureDriversAreLoaded
    def setup(self):
        log.debug('Setting network options for media downloads')
        nicChoices = userchoices.getDownloadNic()
        nic = nicChoices.get('device', None)

        if nic and not nic.isLinkUp:
            failWithLog(('The specified network interface card (Name: %s'
                         ' MAC Address: %s) is not plugged in.'
                         ' Installation cannot continue as requested') %\
                        (nic.name, nic.macAddress))
        elif not nic and not networking.getPluggedInAvailableNIC(None):
            # Check for an available NIC before we go further.
            # It's best to fail early and provide a descriptive error
            failWithLog('This system does not have a network interface'
                        ' card that is plugged in, or all network'
                        ' interface cards are already claimed. '
                        ' Installation cannot continue as requested')

        # Create a netmask if it was left out
        ip = nicChoices.get('ip', None)
        netmask = nicChoices.get('netmask', None)

        if netmask and not ip:
            failWithLog('Netmask specified, but no IP given.')
        if ip and not netmask:
            log.warn('IP specified, but no netmask given.  Guessing netmask.')
            try:
                netmask = networking.utils.calculateNetmask(ip)
            except ValueError, ex:
                msg = ((genericErr + ' A netmask could not be created.')
                       % ('IP Address', str(ex)))
                failWithLog(msg)
            nicChoices.update(netmask=netmask)
            userchoices.setDownloadNic(**nicChoices)

        log.debug("  nic options from boot command line -- %s" % nicChoices)
        log.debug("  net options from boot command line -- %s" %
                  userchoices.getDownloadNetwork())

    def updateNetworkChoices(self, **kwargs):
        self.needed = True
        netChoices = userchoices.getDownloadNetwork()
        if not netChoices:
            newArgs = dict(gateway='', nameserver1='', nameserver2='',
                           hostname='localhost')
        else:
            newArgs = netChoices
        newArgs.update(kwargs)
        userchoices.setDownloadNetwork(**newArgs)

    def updateNicChoices(self, **kwargs):
        self.needed = True
        nicChoices = userchoices.getDownloadNic()
        if not nicChoices:
            # was empty - this is the first time populating it.
            newArgs = dict(device='', vlanID='') #set defaults
        else:
            newArgs = nicChoices
        newArgs.update(kwargs)
        userchoices.setDownloadNic(**newArgs)

# module-level NetworkChoiceMaker object
__networkChoiceMaker = None
def getNetworkChoiceMaker():
    global __networkChoiceMaker
    if not __networkChoiceMaker:
        __networkChoiceMaker = NetworkChoiceMaker()
    return __networkChoiceMaker
        

def _setDownloadIP(match):
    '''Handle the "ip=..." option.'''
    ip = match.group(1)
    try:
        networking.utils.sanityCheckIPString(ip)
    except ValueError, ex:
        failWithLog(genericErr % ('IP Address', str(ex)))

    networkChoiceMaker = getNetworkChoiceMaker()
    networkChoiceMaker.updateNicChoices(ip=ip,
                                        bootProto=userchoices.NIC_BOOT_STATIC)

def _setDownloadNetmask(match):
    '''Handle the "netmask=..." option.'''
    netmask = match.group(1)
    try:
        networking.utils.sanityCheckNetmaskString(netmask)
    except ValueError, ex:
        failWithLog(genericErr % ('Netmask', str(ex)))

    networkChoiceMaker = getNetworkChoiceMaker()
    networkChoiceMaker.updateNicChoices(netmask=netmask)

def _setDownloadGateway(match):
    '''Handle the "gateway=..." option.'''
    gateway = match.group(1)
    try:
        networking.utils.sanityCheckGatewayString(gateway)
    except ValueError, ex:
        failWithLog(genericErr % ('Gateway Address', str(ex)))

    networkChoiceMaker = getNetworkChoiceMaker()
    networkChoiceMaker.updateNetworkChoices(gateway=gateway)


@applychoices.ensureDriversAreLoaded
def _setNetDevice(match):
    '''Handle the "netdevice=..." option.'''
    # The pxelinux BOOTIF option uses dashes instead of colons.
    nicName = match.group(1).replace('-', ':')
    try:
        if ':' in nicName:
            # assume it is a MAC address
            nic = networking.findPhysicalNicByMacAddress(nicName)
            if not nic:
                raise ValueError('No NIC found with MAC address %s' % nicName)
        else:
            # assume it is a vmnicXX style name
            nic = networking.findPhysicalNicByName(nicName)
            if not nic:
                raise ValueError('No NIC found with name %s' % nicName)
    except ValueError, ex:
        failWithLog(genericErr % ('Network Device', str(ex)))

    networkChoiceMaker = getNetworkChoiceMaker()
    networkChoiceMaker.updateNicChoices(device=nic)

@applychoices.ensureDriversAreLoaded
def _setVlanID(match):
    '''Handle the "vlanID=..." option.'''
    vlanID = match.group(1)
    try:
        networking.utils.sanityCheckVlanID(vlanID)
    except ValueError, ex:
        failWithLog(genericErr % ('VLAN ID', str(ex)))

    networkChoiceMaker = getNetworkChoiceMaker()
    networkChoiceMaker.updateNicChoices(vlanID=vlanID)

def _setDownloadNameserver(match):
    '''Handle the "nameserver=..." option.'''
    nameserver = match.group(1)
    try:
        networking.utils.sanityCheckIPString(nameserver)
    except ValueError, ex:
        failWithLog(genericErr % ('Nameserver Address', str(ex)))

    networkChoiceMaker = getNetworkChoiceMaker()
    networkChoiceMaker.updateNetworkChoices(nameserver1=nameserver)

def _upgradeOption(_match):
    # TODO: We're in an upgrade, probably have to run through the init scripts
    # to get storage up and running.
    return []

def _urlOption(match):
    '''Handle the "url=..." option.'''
    return [('--url', match.group(1))]

def _ksFileOption(match):
    '''Handle the "ks=http://<urn>", "ks=file://<path>", etc option.'''
    filePath = match.group(1)
    if remote_files.isURL(filePath) and not filePath.startswith('file'):
        networkChoiceMaker = getNetworkChoiceMaker()
        networkChoiceMaker.needed = True
    return [('-s', filePath)]

def _ksNFSOption(match):
    '''Handle the "ks=nfs:<host>:/path" option.'''
    log.warn("The 'ks=nfs:<host>:/path/to/file' format is deprecated.")
    log.warn("Please use the 'nfs://<host>/path/to/file' format instead.")
    networkChoiceMaker = getNetworkChoiceMaker()
    networkChoiceMaker.needed = True
    return [('-s', "nfs://%s%s" % match.groups())]

@applychoices.ensureDriversAreLoaded
def _ksFileUUIDOption(match):
    uuid = match.group(1)
    path = match.group(2)

    diskSet = devices.DiskSet(forceReprobe=True)
    diskPartTuple = diskSet.findFirstPartitionMatching(uuid=uuid)
    if diskPartTuple:
        disk, _part = diskPartTuple
        userchoices.addDriveUse(disk.name, 'kickstart')
        
    mountPath = os.path.join(UUID_MOUNT_PATH, uuid)
    if not os.path.exists(mountPath):
        os.makedirs(mountPath)
        if util.mount(uuid, mountPath, isUUID=True):
            os.rmdir(mountPath)
            failWithLog("error: cannot mount partition with UUID: %s\n" % uuid)

    ksPath = os.path.join(mountPath, path[1:])
    return [('-s', ksPath)]

def _ksFileCdromOption(match):
    path = match.group(1)

    if not os.path.exists(CDROM_MOUNT_PATH):
        os.makedirs(CDROM_MOUNT_PATH)

    for cdPath in cdutil.cdromDevicePaths():
        if util.mount(cdPath, CDROM_MOUNT_PATH):
            log.warn("cannot mount cd-rom in %s" % cdPath)
            continue

        ksPath = os.path.join(CDROM_MOUNT_PATH, path.lstrip('/'))
        if os.path.exists(ksPath):
            return [('-s', ksPath)]

        util.umount(CDROM_MOUNT_PATH)

    failWithLog("cannot find kickstart file on cd-rom with path -- %s" % path)

def _usbOption(match):
    '''Handle the "ks=usb" and "ks=usb:<path>" option.'''

    try:
        ksFile = match.group(1)
    except IndexError:
        ksFile = "ks.cfg"

    firstTime = True
    while True:
        if not firstTime:
            # XXX Maybe we should just stop retrying after awhile?
            log.info("Insert a USB storage device that contains '%s' "
                     "file to perform a scripted install..." % ksFile)
            util.rawInputCountdown("\rrescanning in %2d second(s), "
                                   "press <enter> to rescan immediately", 10)
        firstTime = False

        diskSet = devices.DiskSet(forceReprobe=True)

        usbDisks = [disk for disk in diskSet.values()
                    if disk.driverName == devices.DiskDev.DRIVER_USB_STORAGE]

        if not usbDisks:
            log.info("") # XXX just for spacing
            log.warn("No USB storage found.")
            continue

        kickstartPath = os.path.join(USB_MOUNT_PATH, ksFile.lstrip('/'))

        if not os.path.exists(USB_MOUNT_PATH):
            os.makedirs(USB_MOUNT_PATH)

        for disk in usbDisks:
            for part in disk.partitions:
                if part.partitionId == -1:
                    continue

                if (part.getFsTypeName() not in ("ext2", "ext3", "vfat")):
                    # Don't try mounting partitions with filesystems that aren't
                    # likely to be on a usb key.
                    continue

                if util.mount(part.consoleDevicePath,
                              USB_MOUNT_PATH,
                              fsTypeName=part.getFsTypeName()):
                    log.warn("Unable to mount '%s'" % part.consoleDevicePath)
                    continue

                if os.path.exists(kickstartPath):
                    userchoices.addDriveUse(disk.name, 'kickstart')
                    return [('-s', kickstartPath)]

                if util.umount(USB_MOUNT_PATH):
                    failWithLog("Unable to umount '%s'" % USB_MOUNT_PATH)

        log.info("")
        log.warn("%s was not found on any attached USB storage." % ksFile)

def _debugOption(_match):
    return [('-d', None)]

def _debugPatchOption(match):
    return [('--debugpatch', match.group(1))]

def _textOption(_match):
    return [('-t', None)]

def _mediaCheckOption(_match):
    return [('--mediacheck', None)]

def _askMediaOption(_match):
    return [('--askmedia', None)]

def _noEjectOption(_match):
    return [('--noeject', None)]

def _setVideoDriver(match):
    '''Handle the video driver selection'''
    return [('--videodriver', match.group(1))]

def _setSerialTty(_match):
    return [('--serial', None)]

@applychoices.ensureDriversAreLoaded
def _bootpartOption(match):
    uuid = match.group(1)
    if not util.uuidToDevicePath(uuid):
        failWithLog("error: cannot find device for UUID: %s\n" % uuid)
        
    userchoices.setBootUUID(uuid)

    mountPath = util.mountByUuid(uuid)
    if not mountPath:
        failWithLog("error: cannot mount boot partition with UUID -- %s" % uuid)

    restoredGrubConf = False
    for prefix in ("boot/grub", "grub"):
        path = os.path.join(mountPath, prefix, "grub.conf")
        if os.path.exists(path):
            tmpPath = os.tempnam(os.path.dirname(path), "grub.conf")
            os.symlink(os.path.basename(GRUB_CONF_PREV), tmpPath)
            # Use rename so the replacement is atomic.
            os.rename(tmpPath, path)
            restoredGrubConf = True
            break
    if not restoredGrubConf:
        log.warn("could not restore %s, upgrade failure will not "
                 "reboot into ESX v3" % GRUB_CONF_PREV)

    util.umount(mountPath)

    return []

@applychoices.ensureDriversAreLoaded
def _rootpartOption(match):
    uuid = match.group(1)
    if not util.uuidToDevicePath(uuid):
        failWithLog("error: cannot find device for UUID: %s\n" % uuid)
    
    userchoices.setRootUUID(uuid)

    return []

def _ignoreOption(_match):
    return

@applychoices.ensureDriversAreLoaded
def _sourceOption(match):
    '''Handle the "source=<path>" option.'''
    path = match.group(1)

    # If the CD is in a drive that is only detected after all the drivers are
    # loaded then we need to rerun the script that finds the install CD.
    if not os.path.exists(path):
        media.runtimeActionMountMedia()
    if not os.path.exists(path):
        failWithLog("error: cannot find source -- %s\n" % path)

    if path == CDROM_DEVICE_PATH:
        pass
    else:
        userchoices.setMediaDescriptor(media.MediaDescriptor(
                partPath=path, partFsName="iso9660"))
    
    return []

  
def translateBootCmdLine(cmdline):
    '''Translate any commands from the given command-line, which is presumably
    from '/proc/cmdline'.

    The 'ks=' option, for example, takes one of the following arguments:

      file:///<path>     The path to the kickstart file, no mounts are done.

    The return value is a list of (option, value) pairs that match what the
    getopt function would return.

    >>> translateBootCmdLine("foo")
    []

    >>> translateBootCmdLine("linux ks=file:///ks.cfg")
    [('-s', '/ks.cfg')]
    >>> translateBootCmdLine("licks=file:///ks.cfg")
    []
    '''

    if len(cmdline) == KERNEL_BUFFER_LEN:
        log.warn("boot command line might have been truncated to %d bytes" %
                 KERNEL_BUFFER_LEN)

    retval = []
    
    # The set of options that are currently handled.  Organized as a list of
    # pairs where the first element is the regex to match and the second is
    # the function that takes the regex and returns a list of (option, value)
    # pairs that match what getopt would return.  The function is also free
    # to perform any necessary setup, like mounting devices.
    # NOTE: order is important
    options = [
        (r'upgrade', _upgradeOption),
        (r'ip=([^:]+).*', _setDownloadIP),
        (r'netmask=(.+)', _setDownloadNetmask),
        (r'gateway=(.+)', _setDownloadGateway),
        (r'nameserver=(.+)', _setDownloadNameserver),
        (r'ks=(/.+)', _ksFileOption),
        (r'ks=UUID:([^:]+):(/.+)', _ksFileUUIDOption),
        (r'ks=cdrom:(/.+)', _ksFileCdromOption),
        (r'ks=((?:file|http|https|ftp|nfs)://.+)', _ksFileOption),
        (r'ks=usb:(/.+)', _usbOption),
        (r'ks=usb', _usbOption),
        (r'ks=nfs:([^:/]+):(/.+)', _ksNFSOption),
        (r'debug', _debugOption),
        (r'debugpatch=(.+)', _debugPatchOption),
        (r'text', _textOption),
        (r'url=(.+)', _urlOption),
        (r'ksdevice=(.+)', _setNetDevice), #for compatibility with anaconda
        (r'netdevice=(.+)', _setNetDevice),
        (r'vlanid=(.+)', _setVlanID),
        (r'bootpart=(.+)', _bootpartOption),
        (r'rootpart=(.+)', _rootpartOption),
        (r'source=(/.+)', _sourceOption),
        (r'askmedia', _askMediaOption),
        (r'askmethod', _askMediaOption),
        (r'noeject', _noEjectOption),
        (r'mediacheck', _mediaCheckOption),
        (r'videodriver=(.+)', _setVideoDriver),
        (r'console=ttyS.*', _setSerialTty),

        # For compatibility with pxelinux
        (r'ip=[^:]+:[^:]+:([^:]+):[^:]+', _setDownloadGateway),
        (r'ip=[^:]+:[^:]+:[^:]+:(.+)', _setDownloadNetmask),
        #  The first two hex digits are the hardware interface type.  Usually
        #  01 for ethernet.
        (r'BOOTIF=\w\w-(.+)', _setNetDevice),
        
        # Suppress complaints about the standard boot options.
        # TODO: Decide whether to add all the possible options or drop the
        # log level of the "if not foundMatch" case below.
        (r'initrd=.+', _ignoreOption),
        (r'mem=.+', _ignoreOption),
        (r'BOOT_IMAGE=.+', _ignoreOption),
        (r'vmkopts=.+', _ignoreOption),
        (r'quiet', _ignoreOption),
        ]

    try:
        for token in shlex.split(cmdline):
            foundMatch = False
            for regex, func in options:
                match = re.match('^%s$' % regex, token)
                if match:
                    foundMatch = True
                    result = func(match)
                    if result:
                        retval.extend(result)
            if not foundMatch:
                log.info('Weasel skipped boot command line token (%s)' % token)
        networkChoiceMaker = getNetworkChoiceMaker()
        if networkChoiceMaker.needed:
            networkChoiceMaker.setup()
    except ValueError, e:
        # shlex.split will throw an error if quotation is bad.
        failWithLog("error: invalid boot command line -- %s" % str(e))

    return retval

def tidyAction():
    # Tidy up if 'ks=usb' was used.
    if os.path.exists(USB_MOUNT_PATH):
        util.umount(USB_MOUNT_PATH)
