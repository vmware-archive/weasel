
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

import cdutil
import fsset
import devices
import timedate
import partition
import userchoices
import networking.utils as net_utils

from log import log
from consts import HOST_ROOT
from grubupdate import shquote
from scriptedinstallutil import interpreters

invertedInterpreters = dict(
    [(value, key) for key, value in interpreters.items()])

def ignoreOnDefault(*choiceFuncs):
    '''Decorator that checks any userchoice functions passed as arguments and
    returns an empty string if they all returned an empty dictionary.
    '''
    
    def _decorator(wrappee):
        def _wrapper(*args, **kwargs):
            nonDefaults = 0
            for func in choiceFuncs:
                if func():
                    nonDefaults += 1

            if nonDefaults == 0:
                return ""

            return wrappee(*args, **kwargs)

        _wrapper.__name__ = wrappee.__name__
        return _wrapper

    return _decorator

def isFirstDisk(diskList):
    return (len(diskList) == 1 and
            diskList[0] == partition.getEligibleDisks()[0].name)

def _genFlags():
    retval = ""
    
    if userchoices.getParanoid():
        retval += "paranoid\n"

    if userchoices.getReboot():
        noEject = ""
        if userchoices.getNoEject():
            noEject = " --noeject"
        retval += "reboot%s\n" % noEject

    if userchoices.getZeroMBR():
        retval += "zerombr\n"

    if userchoices.getDryrun():
        retval += "dryrun\n"

    if userchoices.getAcceptEULA():
        retval += "accepteula\n"

    return retval

@ignoreOnDefault(userchoices.getPackagesToInstall,
                 userchoices.getPackagesNotToInstall)
def _genPackages():
    retval = ""
    flags = ""
    if userchoices.getResolveDeps():
        flags += " --resolvedeps"
    if userchoices.getIgnoreDeps():
        flags += " --ignoredeps"
    
    retval += "%%packages%s\n" % flags

    for pkg in userchoices.getPackagesToInstall():
        retval += "%s\n" % pkg
    for pkg in userchoices.getPackagesNotToInstall():
        retval += "-%s\n" % pkg

    return retval

@ignoreOnDefault(userchoices.getKeyboard)
def _genKeyboard():
    return "keyboard %s\n" % userchoices.getKeyboard()['keytable']

@ignoreOnDefault(userchoices.getAuth)
def _genAuth():
    flags = ""
    choice = userchoices.getAuth()

    if choice['nis']:
        flags += " --enablenis"
        if choice['nisServer']:
            flags += " --nisserver=%s" % choice['nisServer']
        if choice['nisDomain']:
            flags += " --nisdomain=%s" % choice['nisDomain']

    if choice['kerberos']:
        flags += " --enablekrb5"
        if choice['kerberosRealm']:
            flags += " --krb5realm=%s" % choice['kerberosRealm']
        if choice['kerberosKDC']:
            flags += " --krb5kdc=%s" % choice['kerberosKDC']
        if choice['kerberosServer']:
            flags += " --krb5adminserver=%s" % choice['kerberosServer']

    if choice['ldap']:
        flags += " --enableldap"
        if choice['ldapAuth']:
            flags += " --enableldapauth"
        if choice['ldapServer']:
            flags += " --ldapserver=%s" % choice['ldapServer']
        if choice['ldapBaseDN']:
            flags += " --ldapbasedn=%s" % choice['ldapBaseDN']
        if choice['ldapTLS']:
            flags += " --enableldaptls"

    return "auth %s\n" % flags

@ignoreOnDefault(userchoices.getBoot)
def _genBoot():
    flags = ""
    choice = userchoices.getBoot()

    if choice['doNotInstall']:
        flags += " --location=none"
    else:
        flags += " --location=%s" % choice['location']

    if choice['kernelParams']:
        flags += " --append='%s'" % shquote(choice['kernelParams'])

    if choice['password']:
        flagName = "--password"
        if choice['passwordType'] == userchoices.BOOT_PASSWORD_TYPE_MD5:
            flagName = "--md5pass"
        flags += " %s='%s'" % (flagName, shquote(choice['password']))

    if choice['driveOrder']:
        flags += " --driveorder=%s" % ",".join(
            [disk.name for disk in choice['driveOrder']])

    if choice['upgrade']:
        flags += " --upgrade"

    return "bootloader %s\n" % flags

def _genEsxLocation():
    choices = userchoices.getPartitionMountRequests()

    if choices:
        assert len(choices) == 1
        bootReq = choices[0]
        comment = ""
    else:
        comment = \
            "# Uncomment the esxlocation line and comment out the clearpart\n" \
            "# and physical partitions to do a non-destructive reinstall.\n" \
            "#"
        for dev in userchoices.getPhysicalPartitionRequestsDevices():
            reqset = userchoices.getPhysicalPartitionRequests(dev)
            for req in reqset:
                if req.mountPoint == '/boot':
                    bootReq = req
                    break
    
    flags = ""
    if bootReq.clearContents:
        flags += " --clearcontents"
        
    flags += " --uuid=%s" % bootReq.fsType.getUuid(bootReq.consoleDevicePath)

    return "%sesxlocation%s\n" % (comment, flags)

@ignoreOnDefault(userchoices.getClearPartitions)
def _genClearPart():
    choice = userchoices.getClearPartitions()
    
    retval = \
        "# Canonical drive names:\n" \
        "clearpart --drives=%s\n" % ",".join(choice['drives'])

    if isFirstDisk(choice['drives']):
        retval += \
            "# Uncomment to use first detected disk:\n" \
            "#clearpart --firstdisk\n"

    return retval

def _genInstall():
    devChoice = userchoices.getMediaDescriptor()
    urlChoice = userchoices.getMediaLocation()

    if not urlChoice and not devChoice:
        return "install cdrom\n"

    if devChoice:
        if devChoice.partPath in cdutil.cdromDevicePaths():
            return "install cdrom\n"
        else:
            return "install usb\n"
        
    # XXX proxy not handled...
    return "install url %s\n" % urlChoice['mediaLocation']

@ignoreOnDefault(userchoices.getRootPassword)
def _genRootpw():
    choice = userchoices.getRootPassword()
    
    return "rootpw --iscrypted %s\n" % choice['password']
    
@ignoreOnDefault(userchoices.getTimezone)
def _genTimezone():
    choice = userchoices.getTimezone()

    flags = ""
    
    return "timezone%s '%s'\n" % (flags, shquote(choice['tzName']))

def _genTimedate():
    choice = userchoices.getTimedate()
    if not choice or not choice['ntpServer']:
        return ""
    
    ntpConf = timedate.ntp_conf_content % choice
    return ("\n"
            "# ntp settings\n"
            "esxcfg-firewall --enableService ntpClient\n"
            "chkconfig ntpd on\n"
            "cat > /etc/ntp.conf <<EOF\n"
            "%s\n"
            "EOF\n" % ntpConf)

@ignoreOnDefault(userchoices.getSerialNumber)
def _genSerialNumber():
    return "vmserialnum --esx=%s\n" % userchoices.getSerialNumber()['esx']

@ignoreOnDefault(userchoices.getESXFirewall)
def _genFirewall():
    flags = ""
    choice = userchoices.getESXFirewall()

    if choice['incoming'] == userchoices.ESXFIREWALL_ALLOW:
        flags += " --allowIncoming"
    if choice['outgoing'] == userchoices.ESXFIREWALL_ALLOW:
        flags += " --allowOutgoing"

    return "firewall%s\n" % flags

def _genFirewallPortRules():
    retval = ""
    
    for rule in userchoices.getPortRules():
        flags = ""

        if rule['state'] == userchoices.PORT_STATE_OPEN:
            flags += " --open"
        else:
            flags += " --close"

        flags += " --port=%d" % rule['number']
        flags += " --proto=%s" % rule['protocol']
        flags += " --dir=%s" % rule['direction']
        if rule['name']:
            flags += " --name=%s" % rule['name']

        retval += "firewallport%s\n" % flags

    return retval

def _genFirewallPortServices():
    retval = ""
    
    for rule in userchoices.getServiceRules():
        flags = ""

        if rule['state'] == userchoices.PORT_STATE_ON:
            flags += " --enableService=%s" % rule['serviceName']
        else:
            flags += " --disableService=%s" % rule['serviceName']

        retval += "firewallport%s\n" % flags

    return retval

def _genNetwork():
    networkChoice = userchoices.getCosNetwork()
    nicChoice = userchoices.getCosNICs()[0]

    flags = ""

    flags += " --addvmportgroup=%s" % \
        str(userchoices.getAddVmPortGroup()).lower()
    
    flags += " --device=%s" % nicChoice['device'].name
    if nicChoice['vlanID']:
        flags += " --vlanid=%s" % nicChoice['vlanID']

    if nicChoice['bootProto'] == userchoices.NIC_BOOT_DHCP:
        flags += " --bootproto=dhcp"
    else:
        flags += " --bootproto=static"
        flags += " --ip=%s" % nicChoice['ip']
        flags += " --netmask=%s" % nicChoice['netmask']
        flags += " --gateway=%s" % networkChoice['gateway']
        if networkChoice['nameserver1']:
            # can be unset in a static setup.
            flags += " --nameserver=%s" % networkChoice['nameserver1']
            if networkChoice['nameserver2']:
                flags += ",%s" % networkChoice['nameserver2']
        if networkChoice['hostname']:
            flags += " --hostname=%s" % networkChoice['hostname']

    return "network%s\n" % flags

def _genScripts(command, getter, defaultScript=False):
    choice = getter()
    if not choice:
        if defaultScript:
            return "%s --interpreter=bash\n" % command
        else:
            return ""
    
    retval = ""
    for scriptDict in choice:
        scriptObj = scriptDict['script']
        flags = ""

        flags += " --interpreter=%s" % invertedInterpreters[scriptObj.interp]
        if command == "%post":
            if not scriptObj.inChroot:
                flags += " --nochroot"
            if scriptObj.ignoreFailure:
                flags += " --ignorefailure=%s" % str(
                    scriptObj.ignoreFailure).lower()
        if scriptObj.timeoutInSecs:
            flags += " --timeout=%d" % scriptObj.timeoutInSecs
    
        retval +=  "%s%s\n%s\n" % (command, flags, scriptObj.script)
        
    return retval

def _genPreScripts():
    return _genScripts("%pre", userchoices.getPreScripts)
    
def _genPostScripts():
    return _genScripts("%post", userchoices.getPostScripts, True)
    
def _genPartitionRequest(dev, req):
    flags = ""
    
    flags += " --fstype=%s" % req.fsType.name
    
    if isinstance(req.fsType, fsset.vmfs3FileSystem):
        virtDev = userchoices.getVirtualDevicesByPhysicalDeviceName(dev)
        if len(virtDev):
            assert len(virtDev) == 1

            virtDevName = virtDev[0]['device'].name
            if userchoices.checkVirtualPartitionRequestsHasDevice(virtDevName):
                virtualRequests = userchoices.getVirtualPartitionRequests(
                    virtDevName)
                virtSize = virtualRequests.getMinimumSize() + \
                    devices.VMDK_OVERHEAD_SIZE
                if req.minimumSize < virtSize:
                    req.minimumSize = virtSize
    
    flags += " --size=%d" % req.minimumSize
    
    if req.maximumSize:
        flags += " --maxsize=%d" % req.maximumSize
    if req.grow:
        flags += " --grow"
    if req.primaryPartition:
        flags += " --asprimary"
    if req.badBlocks:
        flags += " --badblocks"

    partName = req.mountPoint
    if not partName:
        if isinstance(req.fsType, fsset.vmfs3FileSystem):
            partName = req.fsType.volumeName
        elif isinstance(req.fsType, fsset.swapFileSystem):
            partName = "swap"
    
    return "part '%s' %s" % (shquote(partName or "none"), flags)

def _genPhysicalPartitions():
    retval = ""

    for dev in userchoices.getPhysicalPartitionRequestsDevices():
        reqs = userchoices.getPhysicalPartitionRequests(dev)
        for req in reqs:
            partStr = _genPartitionRequest(dev, req)
            flags1 = " --ondisk=%s" % dev
            retval += "%s %s\n" % (partStr, flags1)

            if isFirstDisk([dev]):
                flags2 = " --onfirstdisk"
                retval += \
                    "# Uncomment to use first detected disk:\n" \
                    "#%s %s\n" % (partStr, flags2)

    return retval

def _genVirtualDisk():
    retval = ""

    for vdevDict in userchoices.getVirtualDevices():
        vdev = vdevDict['device']
        flags = ""

        flags += " --size=%d" % vdev.size

        m = re.match(r'^[^\-]+-\w{8}-\w{4}-\w{4}-\w{4}-\w{12}$', vdev.imagePath)
        if not m:
            flags += " --path='%s'" % shquote(
                "%s/%s" % (vdev.imagePath, vdev.imageName))
        flags += " --onvmfs='%s'" % shquote(vdev.vmfsVolume)

        retval += "virtualdisk '%s'%s\n" % (shquote(vdev.name), flags)

    return retval

def _genVirtualPartitions():
    retval = ""

    for vdev in userchoices.getVirtualPartitionRequestsDevices():
        reqs = userchoices.getVirtualPartitionRequests(vdev)
        for req in reqs:
            partStr = _genPartitionRequest(vdev, req)

            retval += "%s --onvirtualdisk='%s'\n" % (partStr, shquote(vdev))

    return retval

def hostAction(_context):
    ks = ""
    post = ""

    genFuncs = [
        _genFlags,
        _genKeyboard,
        _genAuth,
        _genBoot,
        _genClearPart,
        _genEsxLocation,
        _genInstall,
        _genRootpw,
        _genTimezone,
        _genSerialNumber,
        _genFirewall,
        _genFirewallPortRules,
        _genFirewallPortServices,
        _genNetwork,
        _genPhysicalPartitions,
        _genVirtualDisk,
        _genVirtualPartitions,
        _genPackages,
        _genPreScripts,
        _genPostScripts,
        _genTimedate
        ]

    try:
        for gf in genFuncs:
            fragment = gf()
            if fragment:
                ks += "\n" + fragment

        ksPath = os.path.join(HOST_ROOT, "root/ks.cfg")
        ksFile = open(ksPath, "w")
        os.chmod(ksPath, 0600)
        ksFile.write(ks)
        ksFile.write(post)
        ksFile.close()
    except Exception, e:
        log.exception("Failed to generate ks.cfg, this is not fatal...")
