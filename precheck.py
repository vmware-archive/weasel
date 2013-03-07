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

import os
import re
import sys
import glob
import math
import getopt
import libxml2
import operator
import commands
from grubupdate import findDeviceForPath, splitPath

# TODO: Fill in with real sizes
BOOT_MIN_SIZE = 50 # MB
ROOT_MIN_SIZE = 110 # MB
SIZE_MB = 1024L * 1024L

MEM_MIN_SIZE = 2 * 1024 - 32 # MB (Subtract 32MB for reserved mem)

# size in MB
DEFAULT_ROOT_SIZE = 5000
DEFAULT_LOG_SIZE = 2000
VMDK_OVERHEAD_SIZE = 1000

# XXX Have to be careful to keep this version in-sync...
VERSION = "2.6.18-92.ESX"
EXISTING_INSTALL_PATHS = [
    "/boot/initrd-%s.img" % VERSION,
    "/boot/vmlinuz-%s.img" % VERSION,
    "/boot/trouble/initrd.img",
    "/boot/trouble/vmlinuz.img",
    ]

EXISTING_UPGRADE_PATHS = [
    "/esx4-upgrade/initrd.img",
    "/esx4-upgrade/vmlinuz",
    "/esx4-upgrade/isoinfo",
    ]

def usage(argv):
    print "usage: %s [-h] [iso-location]" % argv[0]
    print

def getConsoleMemorySize(oldCosMem, physicalMem):
    '''Returns the size in MB for the size of the console OS.'''
    # NOTE: math.log in python 2.2 on esx v3 does not take a base argument
    consoleMem = int((math.log(max(1000, physicalMem) / 1000) /
                      math.log(2)) * 100)
    if consoleMem < oldCosMem:
        consoleMem = oldCosMem
    if consoleMem < 300:
        return 300
    elif consoleMem > 800:
        return 800
    else:
        return consoleMem

def getDefaultSwapSize(oldCosMem, physMemSize):
    '''Return the default swap size, which is 2x the size of the
       Console memory.
    '''
    return getConsoleMemorySize(oldCosMem, physMemSize) * 2

def getVmdkSize(infoText):
    return (DEFAULT_ROOT_SIZE +
            DEFAULT_LOG_SIZE +
            getDefaultSwapSize(_parseCosMemory(infoText),
                               _parseMemory(infoText)) +
            VMDK_OVERHEAD_SIZE)

class Result:
    ERROR = "ERROR"
    WARNING = "WARNING"
    SUCCESS = "SUCCESS"
    
    def __init__(self, name, found, expected,
                 comparator=operator.eq, mismatchCode=None):
        if not mismatchCode:
            mismatchCode = Result.ERROR
        
        self.name = name
        self.found = found
        self.expected = expected
        if comparator(self.found, self.expected):
            self.code = Result.SUCCESS
        else:
            self.code = mismatchCode

class PciInfo:
    '''Class to encapsulate PCI data'''
    
    def __init__(self, vendorId, deviceId, description=""):
        '''Construct a PciInfo object with the given values: vendorId and
        deviceId should be strings with the appropriate hex values.  Description
        is an english description of the PCI device.'''
        
        self.vendorId = vendorId
        self.deviceId = deviceId
        self.description = description

    def __eq__(self, rhs):
        return (self.vendorId == rhs.vendorId and
                self.deviceId == rhs.deviceId)

    def __ne__(self, rhs):
        return (self.vendorId != rhs.vendorId or
                self.deviceId != rhs.deviceId)

    def __str__(self):
        return "%s [%s] [%s]" % (self.description, self.vendorId, self.deviceId)

    def __repr__(self):
        return "<PciInfo '%s'>" % str(self)

UNSUPPORTED_PCI_IDE_DEVICE_LIST = [
    # Fill out based on -- https://wiki.eng.vmware.com/PATADrivers ?
    PciInfo("10b9", "5228", "ALi15x3"),
    PciInfo("10b9", "5229", "ALi15x3"),
    PciInfo("1080", "c693", "Cypress CY82c693"),
    PciInfo("1078", "0000", "Cyrix MediaGX 5510/5520"),
    PciInfo("1078", "0002", "Cyrix MediaGX 5510/5520"),
    PciInfo("1078", "0102", "Cyrix MediaGX 5530"),
    PciInfo("1103", "0003", "HPT 343/363"),
    PciInfo("1103", "0004", "HPT 366"),
    PciInfo("1042", "1000", "Micron PCTech RZ1000"),
    PciInfo("1042", "1001", "Micron PCTech RZ1000"),
    PciInfo("0e11", "ae33", "Compaq Triflex"),
    PciInfo("1039", "5513", "SiS"),
    PciInfo("1039", "5518", "SiS"),
    PciInfo("1039", "1180", "SiS"),
    PciInfo("1055", "9130", "EFAR SLC90E66"),
    ]

UNSUPPORTED_PCI_DEVICE_LIST = UNSUPPORTED_PCI_IDE_DEVICE_LIST + [
    # Any other devices we want to warn about?
    PciInfo("8086", "1229", "Ethernet Pro 100"),
    ]

def _parseCpuInfo(cpuinfoText):
    retval = {
        'flags' : []
        }

    for line in cpuinfoText.split('\n'):
        match = re.match(r'([^:]+)\s*:\s*(.+)', line)

        if not match:
            continue

        key, value = match.groups()
        key = key.strip()
        value = value.strip()
        if key == "flags":
            retval[key] = value.split(' ')

    return retval

def _parsePciInfo(pciinfoText):
    '''Parse the output of "lspci -mn" and return a list of PciInfo objects.

    >>> _parsePciInfo('00:00.0 "0600" "8086" "277c" "1028" "01de"\n'
    ...               '00:01.0 "0604" "8086" "277d" "" ""')
    [<PciInfo ' [8086] [277c]'>, <PciInfo ' [8086] [277d]'>]
    '''
    
    retval = []
    for line in pciinfoText.split('\n'):
        m = re.match(r'^\w+:\w+\.\w+ "[^"]+" "(\w+)" "(\w+)"', line)
        if not m:
            continue

        retval.append(PciInfo(m.group(1), m.group(2)))

    return retval

def _parseCosMemory(infoText):
    m = re.search(r'Service Console Mem \(Cfg\)\.+(\d+)', infoText)
    if not m:
        sys.stderr.write('error: could not get cos memory size\n')
        retval = 0
    else:
        retval = long(m.group(1))

    return retval

def _parseMemory(infoText):
    m = re.search(r'Physical Mem\.+(\d+)', infoText)
    if not m:
        sys.stderr.write('error: could not get memory size\n')
        retval = 0
    else:
        retval = long(m.group(1)) / SIZE_MB

    return retval

def checkMemorySize(infoText):
    '''Check the size of memory as listed in infoText, which is the output of
    esxcfg-info.'''

    found = _parseMemory(infoText)
    
    return Result("MEMORY_SIZE", [found], [MEM_MIN_SIZE],
                  comparator=operator.ge)

def _samePartitionForBootAndRoot():
    rootStat = os.stat("/")
    bootStat = os.stat("/boot")

    return rootStat.st_dev == bootStat.st_dev

def _parseBlockDevices(devicesText):
    '''Parse the output of /proc/devices and return a list of pairs where the
    first element is a device node number and the second is the name of the
    driver/device.'''
    
    _chText, blkText = devicesText.split("Block devices:")

    blkDevices = re.findall("\s*(\d+) (\w+)", blkText)
    return [(int(devNode), name) for devNode, name in blkDevices]

def _getSystemUuid():
    try:
        esxconf = open("/etc/vmware/esx.conf")
        try:
            for line in esxconf:
                m = re.match('/system/uuid = "([\w-]+)"', line)
                if m:
                    return m.group(1)
        finally:
            esxconf.close()
    except (OSError, IOError), e:
         sys.stderr.write("error: cannot open esx.conf -- %s\n" % str(e))
         
    return None

def _diskUsageVisitor(accum, dirname, names):
    for name in names:
        try:
            path = os.path.join(dirname, name)

            if os.path.islink(path):
                continue
            
            accum[0] += os.path.getsize(path)
        except (IOError, OSError), _e:
            sys.stderr.write("warn: unable to get the size of -- %s\n" % path)

def _diskUsage(path):
    '''Return the amount of disk space used by the given path and any
    subdirectories.
    '''
    
    accum = [0]
    os.path.walk(path, _diskUsageVisitor, accum)
    return accum[0]
            
def checkCpu(cpuinfo):
    found = "lm" in cpuinfo['flags']
    
    return Result("SUPPORTED_CPU", [found], [True])

def _discountExistingPaths(paths):
    '''Count up the size of the files in the given list of paths.

    For reupgrades, we want to ignore files from any previous upgrade attempts
    when doing our size checks.
    '''
    
    retval = 0
    for path in paths:
        if not os.path.exists(path):
            continue
        
        try:
            retval += os.path.getsize(path)
        except (OSError, IOError), e:
            sys.stderr.write("error: could not stat %s -- %s\n" % (
                    path, str(e)))
    
    return retval / SIZE_MB

def checkStagingStorage():
    st = os.statvfs("/")

    # f_bavail is a 64-bit number, so this should not overflow.
    found = (st.f_frsize * st.f_bavail) / SIZE_MB
    found += _discountExistingPaths(EXISTING_UPGRADE_PATHS)
    expected = ROOT_MIN_SIZE

    return Result("STAGING_STORAGE", [found], [expected],
                  comparator=operator.ge)

def checkBootStorage():
    st = os.statvfs("/boot")

    found = (st.f_frsize * st.f_bavail) / SIZE_MB
    found += _discountExistingPaths(EXISTING_INSTALL_PATHS)
    expected = BOOT_MIN_SIZE
    if _samePartitionForBootAndRoot():
        expected += ROOT_MIN_SIZE
    
    return Result("BOOT_STORAGE", [found], [expected],
                  comparator=operator.ge)

def checkSaneGrubConf():
    expected = True

    try:
        grubConf = open("/boot/grub/grub.conf", "r")
        # TODO: Add more checking.
        found = True
    except (OSError, IOError):
        found = False
    
    return Result("SANE_GRUB_CONF", [found], [expected])

def checkSaneEsxConf():
    expected = True

    found = (_getSystemUuid() is not None)
    
    return Result("SANE_ESX_CONF", [found], [expected])

def checkBootDevice(blkdevs, pciinfo):
    partMajors = (os.stat("/").st_dev >> 8, os.stat("/boot").st_dev >> 8)

    # XXX This check is just an approximation now, it checks if the root or
    # /boot partitions are on an IDE drive and there is an unsupported IDE
    # chipset in the machine.
    
    partOnIde = False
    for devNode, name in blkdevs:
        # Check if the root or /boot partitions are on a device with an "ide"
        # name (e.g. "ide0").
        if devNode in partMajors and name.startswith("ide"):
            partOnIde = True

    hasUnsupportedIde = False
    for device in UNSUPPORTED_PCI_IDE_DEVICE_LIST:
        if device in pciinfo:
            hasUnsupportedIde = True

    found = not (partOnIde and hasUnsupportedIde)
    
    return Result("BOOT_DEVICE", [found], [True],
                  mismatchCode=Result.WARNING)

def checkRootBootable():
    rootDev = findDeviceForPath("/")
    bootDev = findDeviceForPath("/boot")

    found = (splitPath(rootDev)[0] == splitPath(bootDev)[0])

    return Result("ROOT_BOOTABLE", [found], [True])

def checkUnsupportedDevices(pciinfo):
    found = []
    for device in UNSUPPORTED_PCI_DEVICE_LIST:
        if device in pciinfo:
            found.append(device)
    
    return Result("UNSUPPORTED_DEVICES", found, [],
                  mismatchCode=Result.WARNING)

def checkSaneInventory(inventoryDoc):
    return Result("SANE_INVENTORY", [inventoryDoc is not None], [True])

def checkOldVMXs(inventoryDoc):
    found = []

    if inventoryDoc:
        for node in inventoryDoc.xpathEval('//vmxCfgPath'):
            if not node.content.startswith('/vmfs/'):
                found.append(node.content)
        
    return Result("OLD_VMX", found, [])

def _ensureVmwarePath():
    '''We make use of the vmware.authentication package, so this function
    ensures that it is in the PYTHONPATH.'''
    vmwarePythonRoot = os.path.join("/usr/lib/vmware/python2.2/site-packages")
    if vmwarePythonRoot not in sys.path:
        sys.path.append(vmwarePythonRoot)

def checkActiveDirectory(fwinfo):
    _ensureVmwarePath()
    
    from vmware.authentication.PAMManager import PAMManager

    krbFound = False
    fwServiceFound = False
    pm = PAMManager()
    authStack = pm.GetStack("auth")
    if authStack:
        for elem in authStack:
            if elem[0].find("pam_krb5.so") != -1:
                krbFound = True
    fwServiceFound = (fwinfo.find('activeDirectorKerberos') != -1)
    return Result("ACTIVE_DIRECTORY", [krbFound and fwServiceFound], [False])

def findExistingVmdks():
    '''The name for a cos vmdk created by the upgrade process has the following
    format: /vmfs/volumes/<volume-name>/esxconsole-<system-uuid>/ .'''
    uuid = _getSystemUuid()
    if not uuid:
        sys.stderr.write('warning: could not read system UUID\n')
        return {}
    
    foundVmdks = glob.glob(os.path.join("/vmfs/volumes",
                                        "*",
                                        "esxconsole-%s" % uuid))

    retval = {}
    for vmdk in foundVmdks:
        try:
            realVmdkPath = os.path.realpath(vmdk)
            if realVmdkPath in retval:
                continue
            
            retval[realVmdkPath] = _diskUsage(vmdk) / SIZE_MB
        except (IOError, OSError), _e:
            sys.stderr.write('warning: could not get size for -- %s\n' % vmdk)
    
    return retval

VMDK_XML = '''\
    <vmdk>
      <path>%s</path>
      <size>%s</size>
    </vmdk>
'''

def vmdkDictToXML(vmdkDict):
    retval = '  <vmdklist>\n'
    for vmdk in vmdkDict.items():
        retval += VMDK_XML % vmdk
    retval += '  </vmdklist>\n'
    
    return retval

RESULT_XML = '''    <test>
      <name>%(name)s</name>
      <expected>
        %(expected)s
      </expected>
      <found>
        %(found)s
      </found>
      <result>%(code)s</result>
    </test>
'''

def _marshalResult(result):
    # XXX This is just a hack to get things going...  Marshalling might have
    # to be done a little differently depending on the types (i.e. plain strings
    # vs. references to vmfsvolumes).
    
    intermediate = {
        'name' : result.name,
        'expected' : '\n        '.join([('<value>%s</value>' % exp)
                                        for exp in result.expected]),
        'found' : '\n        '.join([('<value>%s</value>' % fnd)
                                     for fnd in result.found]),
        'code' : result.code,
        }
    
    return RESULT_XML % intermediate

def resultsToXML(results):
    retval = '  <tests>\n'
    for result in results:
        retval += _marshalResult(result)
    retval += '  </tests>\n'
    
    return retval

def main(argv):
    try:
        (opts, args) = getopt.getopt(argv[1:], "h", ["help"])

        for opt, arg in opts:
            if opt in ("-h", "--help"):
                usage()
    except getopt.error, e:
        sys.stderr.write(str(e))
        return 1

    esxinfo = commands.getoutput("/usr/sbin/esxcfg-info")
    cpuinfo = _parseCpuInfo(open("/proc/cpuinfo").read())
    fwinfo  = commands.getoutput("/usr/sbin/esxcfg-firewall -q")

    status, lspciOutput = commands.getstatusoutput("/sbin/lspci -mn")
    if status != 0:
        sys.stderr.write("error: lspci failed with status %s -- %s\n" % (
                status, lspciOutput))
    pciinfo = _parsePciInfo(lspciOutput)
    blkdevs = _parseBlockDevices(open("/proc/devices").read())

    try:
        def _callback(ctx, str):
            sys.stderr.write("%s %s", ctx, str)
            return

        libxml2.registerErrorHandler(_callback, "")
        inventoryDoc = libxml2.parseFile("/etc/vmware/hostd/vmInventory.xml")
    except libxml2.parserError, e:
        inventoryDoc = None
        sys.stderr.write('error: could not parse vmInventory.xml -- %s\n' %
                         str(e))

    results = [
        checkCpu(cpuinfo),
        checkStagingStorage(),
        checkBootStorage(),
        checkBootDevice(blkdevs, pciinfo),
        checkRootBootable(),
        checkUnsupportedDevices(pciinfo),
        checkMemorySize(esxinfo),
        checkSaneGrubConf(),
        checkSaneEsxConf(),
        checkSaneInventory(inventoryDoc),
        checkOldVMXs(inventoryDoc),
        checkActiveDirectory(fwinfo),
        ]

    xml = '<?xml version="1.0"?>\n'
    xml += '<precheck>\n'
    xml += "  <vmfsSpaceRequired>%s</vmfsSpaceRequired>\n" % \
        getVmdkSize(esxinfo)
    xml += vmdkDictToXML(findExistingVmdks())
    xml += resultsToXML(results)
    xml += '</precheck>\n'

    print xml
    
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
