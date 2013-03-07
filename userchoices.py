
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

from copy import deepcopy
from pprint import pformat

'''
userchoices abstracts all the choices a user can make during the installation
process.  It is accessed as a singleton from gui.py and from each of the
screens.  It provides getter and setter methods for the various choices
available to a user.

This module's API is basically a collection of get* and set* functions.

The get* functions return _copies_ of the data, to maintain encapsulation.

Usage:
import userchoices
userchoices.setMyProperty(foo='bar')
...
myProp = userchoices.getMyProperty()
if not myProp:
   # handle unset property condition
else:
   # do something with myProp['foo']
'''

# ----------------------------------------------------------------------------
# Section 1: Simple boolean toggles
# ----------------------------------------------------------------------------

__toggles = { 'paranoid':   False,
              'debug':      False,
              'startX':     True,
              'upgrade':    False,
              'reboot':     False,
              'noEject':    False,
              'acceptEULA': True,
              'zeroMBR':    False,
              'dryrun':     False,
              'mediacheck': False,
              'activateNetwork':        False,
              'showInstallMethod':      False,
              'resetEsxLocation':       True,
              'ignoreDeps':             False,
              'resolveDeps':            False,
              'driversLoaded':          False,
              'addVmPortGroup':         True,
            }

def setParanoid(paranoid):
    global __toggles
    __toggles['paranoid'] = paranoid

def getParanoid():
    return __toggles['paranoid']

def setStartX(startX):
    global __toggles
    __toggles['startX'] = startX

def getStartX():
    return __toggles['startX']

def setShowInstallMethod(showInstall):
    global __toggles
    __toggles['showInstallMethod'] = showInstall

def getShowInstallMethod():
    return __toggles['showInstallMethod']

def setDebug(debug):
    global __toggles
    __toggles['debug'] = debug

def getDebug():
    return __toggles['debug']

def setUpgrade(upgrade):
    global __toggles
    __toggles['upgrade'] = upgrade

def getUpgrade():
    return __toggles['upgrade']

def setReboot(reboot):
    global __toggles
    __toggles['reboot'] = reboot

def getReboot():
    return __toggles['reboot']

def setNoEject(noEject):
    global __toggles
    __toggles['noEject'] = noEject

def getNoEject():
    return __toggles['noEject']

def setAcceptEULA(acceptEULA):
    global __toggles
    __toggles['acceptEULA'] = acceptEULA

def getAcceptEULA():
    return __toggles['acceptEULA']

def setZeroMBR(zeroMBR):
    global __toggles
    __toggles['zeroMBR'] = zeroMBR

def getZeroMBR():
    return __toggles['zeroMBR']

def setDryrun(dryrun):
    global __toggles
    __toggles['dryrun'] = dryrun

def getDryrun():
    return __toggles['dryrun']

def setMediaCheck(mediacheck):
    global __toggles
    __toggles['mediacheck'] = mediacheck

def getMediaCheck():
    return __toggles['mediacheck']

def setActivateNetwork(activateNetwork):
    global __toggles
    __toggles['activateNetwork'] = activateNetwork

def getActivateNetwork():
    return __toggles['activateNetwork']

def setResetEsxLocation(resetEsxLocation):
    global __toggles
    __toggles['resetEsxLocation'] = resetEsxLocation

def getResetEsxLocation():
    return __toggles['resetEsxLocation']

def setDriversLoaded(driversLoaded):
    global __toggles
    __toggles['driversLoaded'] = driversLoaded

def getDriversLoaded():
    return __toggles['driversLoaded']

def setAddVmPortGroup(addVmPortGroup):
    global __toggles
    __toggles['addVmPortGroup'] = addVmPortGroup

def getAddVmPortGroup():
    return __toggles['addVmPortGroup']


# ----------------------------------------------------------------------------
# Section 2: Data stored as dicts
# ----------------------------------------------------------------------------

__runMode = {}

RUNMODE_GUI = 'gui'
RUNMODE_TEXT = 'text'
RUNMODE_SCRIPTED = 'scripted'

def setRunMode(runMode):
    global __runMode
    __runMode = locals()

def getRunMode():
    return __runMode.copy()

def setIgnoreDeps(ignoreDeps):
    global __toggles
    __toggles['ignoreDeps'] = ignoreDeps

def getIgnoreDeps():
    return __toggles['ignoreDeps']

def setResolveDeps(resolveDeps):
    global __toggles
    __toggles['resolveDeps'] = resolveDeps

def getResolveDeps():
    return __toggles['resolveDeps']

__keyboard = {}

def setKeyboard(keytable, name, model, layout, variant, options):
    global __keyboard
    # NOTE using locals() is hackish, but saves coding.
    # Don't add anything to local scope in this function, either
    # before or after the assignment, otherwise it will screw up
    # the data in the __foo module-level variable
    __keyboard = locals()

def getKeyboard():
    return __keyboard.copy()



__auth = {}

def setAuth(nis, kerberos, ldap,
            nisServer=None, nisDomain=None,
            kerberosRealm=None, kerberosKDC=None, kerberosServer=None,
            ldapAuth=False, ldapServer=None, ldapBaseDN=None, ldapTLS=False,):
    '''nis, kerberos, ldap arguments are booleans'''
    global __auth
    __auth = locals()

def getAuth():
    return __auth.copy()

__boot = {}

BOOT_LOC_MBR = 'mbr'
BOOT_LOC_PARTITION = 'partition'
BOOT_PASSWORD_TYPE_PLAIN = 'plain'
BOOT_PASSWORD_TYPE_MD5 = 'md5'

#TODO: do I need to differentiate at all between text and md5 passwords?
def setBoot(upgrade, doNotInstall=False, location=BOOT_LOC_MBR,
             kernelParams='',
             password='', passwordType=BOOT_PASSWORD_TYPE_PLAIN,
             driveOrder=None):
    global __boot
    __boot = locals()

def getBoot():
    return __boot.copy()

def clearBoot():
    global __boot
    __boot = {}



__bootUUID = {}

def setBootUUID(uuid):
    global __bootUUID
    __bootUUID = locals()

def getBootUUID():
    return __bootUUID.copy()


__rootUUID = {}

def setRootUUID(uuid):
    global __rootUUID
    __rootUUID = locals()

def getRootUUID():
    return __rootUUID.copy()

def isCombinedBootAndRootForUpgrade():
    return getUpgrade() and __bootUUID and (__bootUUID == __rootUUID)


__weaselTty = ''

def setWeaselTTY(devname):
    global __weaselTty
    __weaselTty = devname

def getWeaselTTY():
    return __weaselTty


__videoDriver = ''

def setVideoDriver(driverName):
    global __videoDriver
    __videoDriver = driverName

def getVideoDriver():
    return __videoDriver


__clearPartitions = {}

CLEAR_PARTS_ALL = 'all'
CLEAR_PARTS_NOVMFS = 'novmfs'

def setClearPartitions(drives=[], whichParts=CLEAR_PARTS_ALL):
    global __clearPartitions
    __clearPartitions = locals()

def getClearPartitions():
    return __clearPartitions.copy()


# Map of drive names to a set of strings that described how the drive is being
# used by the installer.  For example, addDriveUse('foo', 'kickstart') means
# that the drive contains the kickstart file.
__driveUses = {}

def addDriveUse(driveName, useName):
    useSet = __driveUses.get(driveName, set())
    useSet.add(useName)
    __driveUses[driveName] = useSet

def delDriveUse(driveName, useName):
    if driveName in __driveUses and useName in __driveUses[driveName]:
        __driveUses[driveName].remove(useName)
        if not __driveUses[driveName]:
            del __driveUses[driveName]

def getDrivesInUse():
    return __driveUses.keys()


__mediaDescriptor = None

def setMediaDescriptor(media):
	global __mediaDescriptor
	__mediaDescriptor = media

def getMediaDescriptor():
	return __mediaDescriptor


# Location of the vmdk file to remove while doing the install.  This is
# useful if you're preserving the VMFS partitions.
__existingVmdkLocation = {}

def setExistingVmdkLocation(vmdkLocation):
    global __existingVmdkLocation
    __existingVmdkLocation = locals()

def getExistingVmdkLocation():
    return __existingVmdkLocation.copy()

def clearExistingVmdkLocation():
    global __existingVmdkLocation
    __existingVmdkLocation = {}


__mediaLocation = {}

def setMediaLocation(mediaLocation):
    global __mediaLocation
    # mediaLocation can not refer to a file, it must refer to a directory.
    # to make this unambiguous in URLs, we append '/' if it's not already
    # there.
    if not mediaLocation.endswith('/'):
        mediaLocation += '/'
    __mediaLocation = locals()

def getMediaLocation():
    return __mediaLocation.copy()

def clearMediaLocation():
    global __mediaLocation
    __mediaLocation = {}


__mediaProxy = {}

def setMediaProxy(server, port, username='', password=''):
    global __mediaProxy
    __mediaProxy = locals()

def getMediaProxy():
    return __mediaProxy.copy()

def unsetMediaProxy():
    global __mediaProxy
    __mediaProxy = {}


__debugPatchLocation = {}

def setDebugPatchLocation(debugPatchLocation):
    global __debugPatchLocation
    __debugPatchLocation = locals()

def getDebugPatchLocation():
    return __debugPatchLocation.copy()


__rootPassword = {}

ROOTPASSWORD_TYPE_CRYPT = 'crypt'
ROOTPASSWORD_TYPE_MD5 = 'md5'

def setRootPassword(password, passwordType):
    global __rootPassword
    __rootPassword = locals()

def getRootPassword():
    return __rootPassword.copy()



__timezone = {}

def setTimezone(tzName, offset=None, city=None, isUTC=True):
    global __timezone
    __timezone = locals()

def getTimezone():
    return __timezone.copy()


__timedate = {}

def setTimedate(ntpServer=None):
    # to set the time & date, just change the os date so that it keeps
    # ticking forward.  If the time the user entered was kept in the
    # userchoices object, it would be frozen, and there would be a
    # significant delta between when they entered it and when applychoices
    # got called
    global __timedate
    __timedate = locals()

def getTimedate():
    return __timedate.copy()


__vmLicense = {}

VM_LICENSE_MODE_SERVER = 'server'
VM_LICENSE_MODE_FILE = 'file'

def setVMLicense(mode, features, edition, server=None):
    global __vmLicense
    __vmLicense = locals()

def getVMLicense():
    return __vmLicense.copy()


__mouse = {}

def setMouse(mouseType, device, emuThree):
    global __mouse
    __mouse = locals()

def getMouse():
    return __mouse.copy()



__lang = None

def setLang(lang):
    global __lang
    __lang = locals()

def getLang():
    return __lang.copy()



__langSupport = None

def setLangSupport(lang, default):
    global __langSupport
    __langSupport = locals()

def getLangSupport():
    return __langSupport.copy()



__esxFirewall = {}

ESXFIREWALL_ALLOW = 'allow'
ESXFIREWALL_BLOCK = 'block'

def setESXFirewall(incoming, outgoing):
    '''Both the arguments must be specified.  The provided ESXFIREWALL_
    constants can be used for either the incoming or outgoing arguments.
    Examples:
    >>> import userchoices
    >>> userchoices.setESXFirewall(userchoices.ESXFIREWALL_BLOCK,
    ...                            userchoices.ESXFIREWALL_ALLOW)
    >>> userchoices.setESXFirewall(incoming=userchoices.ESXFIREWALL_BLOCK,
    ...                             outgoing=userchoices.ESXFIREWALL_ALLOW)
    '''
    global __esxFirewall
    __esxFirewall = locals()

def getESXFirewall():
    return __esxFirewall.copy()



__downloadNetwork = {}
__cosNetwork = {}
__vmkNetwork = {}

NETWORK_DEFAULT_GATEWAY = ''
NETWORK_DEFAULT_NAMESERVER = ''
NETWORK_DEFAULT_HOSTNAME = ''

def setDownloadNetwork(gateway, nameserver1, nameserver2, hostname):
    global __downloadNetwork
    __downloadNetwork = locals()

def getDownloadNetwork():
    return __downloadNetwork.copy()

def setCosNetwork(gateway, nameserver1, nameserver2, hostname):
    global __cosNetwork
    __cosNetwork = locals()

def getCosNetwork():
    return __cosNetwork.copy()

def clearCosNetwork():
    global __cosNetwork
    __cosNetwork = {}

def setVmkNetwork(gateway):
    """ For iSCSI only, for now """
    global __vmkNetwork
    __vmkNetwork['gateway'] = gateway

def getVmkNetwork():
    return __vmkNetwork.copy()


__iscsiInitiatorAndTarget = {}

def setIscsiInitiatorAndTarget(initiatorIQN, initiatorAlias,
                               targetIQN, targetIP, targetPort,
                               targetUserName, targetPwd):
    global __iscsiInitiatorAndTarget
    __iscsiInitiatorAndTarget = locals()

def getIscsiInitiatorAndTarget():
    return __iscsiInitiatorAndTarget.copy()


__rootScriptLocation = {}

def setRootScriptLocation(rootScriptLocation):
    global __rootScriptLocation
    __rootScriptLocation = locals()

def getRootScriptLocation():
    return __rootScriptLocation.copy()


__preScripts = []

def addPreScript(script):
    global __preScripts
    __preScripts.append(locals())

def clearPreScripts():
    global __preScripts
    __preScripts = []

def getPreScripts():
    return __preScripts

__postScripts = []

def addPostScript(script):
    global __postScripts
    __postScripts.append(locals())

def clearPostScripts():
    global __postScripts
    __postScripts = []

def getPostScripts():
    return __postScripts


# ----------------------------------------------------------------------------
# Section 3: User choices that are multiple
# ----------------------------------------------------------------------------

__users = []

USERPASSWORD_TYPE_CRYPT = 'crypt'
USERPASSWORD_TYPE_MD5 = 'md5'

def addUser(username, password, passwordType, fullName=""):
    global __users
    __users.append(locals())

def delUser( user ):
    """To delete a item, you will have to first get a reference
    to it from getUser() so that you can uniquely identify it
    Throws: ValueError when the item is not in the list.
    """
    global __users
    __users.remove(user)

def getUsers():
    return deepcopy(__users)

def clearUsers():
    global __users
    __users = []



__downloadNic = {}
__cosNics = []
__vmkNics = []

NIC_BOOT_DHCP = 'dhcp'
NIC_BOOT_STATIC = 'static'

def setDownloadNic(device, vlanID, bootProto=NIC_BOOT_DHCP, ip='', netmask=''):
    global __downloadNic
    __downloadNic = locals()

def getDownloadNic():
    return __downloadNic.copy()


# ip and netmask default to '' for the sake of brevity on the caller's side
def addCosNIC(device, vlanID, bootProto=NIC_BOOT_DHCP, ip='', netmask=''):
    __cosNics.append( locals() )

def delCosNIC(nic):
    """To delete a item, you will have to first get a reference
    to it from getNIC() so that you can uniquely identify it
    Throws: ValueError when the item is not in the list.
    """
    __cosNics.remove(nic)

def getCosNICs():
    return __cosNics[:]

def getCosNICDevices():
    result = []
    for nic in getCosNICs():
        result.append(nic['device'])
    return result

def getClaimedNICDevices():
    result = []
    for nic in getCosNICs() + getVmkNICs():
        if nic['device'] not in result:
            result.append(nic['device'])
    return result

#
# VMK versions of the above:
#
def addVmkNIC(device, vlanID, bootProto=NIC_BOOT_DHCP, ip='', netmask=''):
    __vmkNics.append(locals())

def delVmkNIC(nic):
    __vmkNics.remove(nic)

def getVmkNICs():
    return __vmkNics[:]

def setVmkNICs(newVmkNics):
    global __vmkNics
    __vmkNics = newVmkNics[:]


__virtual_devices = []

def addVirtualDevice(device):
    global __virtual_devices
    __virtual_devices.append(locals())

def delVirtualDevice(device):
    global __virtual_devices
    __virtual_devices.remove(device)

def getVirtualDevices():
    return list(__virtual_devices)

def getVirtualDevicesByPhysicalDeviceName(deviceName):
    virtualDevices = []
    for virtualDev in __virtual_devices:
        if virtualDev['device'].physicalDeviceName == deviceName:
            virtualDevices.append(virtualDev)
    return virtualDevices

def clearVirtualDevices():
    global __virtual_devices
    __virtual_devices = []

# place where we're going to store the /boot partition
__esxPhysicalDevice = ''

def setEsxPhysicalDevice(device):
    global __esxPhysicalDevice
    __esxPhysicalDevice = device

def getEsxPhysicalDevice():
    return __esxPhysicalDevice


__esxDatastoreDeviceName = None

def setEsxDatastoreDevice(deviceName):
    assert deviceName is None or isinstance(deviceName, str)
    
    global __esxDatastoreDeviceName
    __esxDatastoreDeviceName = deviceName

def getEsxDatastoreDevice():
    return __esxDatastoreDeviceName


__vmdkDatastore = ''

def setVmdkDatastore(datastoreName):
    global __vmdkDatastore
    __vmdkDatastore = datastoreName

def getVmdkDatastore():
    return __vmdkDatastore


__partitionPhysicalRequests = {}

def checkPhysicalPartitionRequestsHasDevice(device):
    return __partitionPhysicalRequests.has_key(device)

def setPhysicalPartitionRequests(device, requests):
    global __partitionPhysicalRequests
    __partitionPhysicalRequests[device] = requests

def addPhysicalPartitionRequests(device, requests):
    if not checkPhysicalPartitionRequestsHasDevice(device):
        setPhysicalPartitionRequests(device, requests)
    else:
        __partitionPhysicalRequests[device] += requests

def getPhysicalPartitionRequests(device):
    return __partitionPhysicalRequests[device]

def getPhysicalPartitionRequestsDevices():
    return __partitionPhysicalRequests.keys()

def delPhysicalPartitionRequests(device):
    del __partitionPhysicalRequests[device]

def clearPhysicalPartitionRequests():
    global __partitionPhysicalRequests
    __partitionPhysicalRequests = {}


__partitionMountRequests = []

def addPartitionMountRequest(request):
    __partitionMountRequests.append(request)

def getPartitionMountRequests():
    return list(__partitionMountRequests)

def clearPartitionMountRequests():
    global __partitionMountRequests
    __partitionMountRequests = []

    
# virtual partition requests (ones inside of a vmdk) need to happen after
# the other partitions have been set up, so we have to seperate them out
# from normal requests

__partitionVirtualRequests = {}

def checkVirtualPartitionRequestsHasDevice(device):
    return __partitionVirtualRequests.has_key(device)

def setVirtualPartitionRequests(device, requests):
    global __partitionVirtualRequests
    __partitionVirtualRequests[device] = requests

def getVirtualPartitionRequests(device):
    return __partitionVirtualRequests[device]

def getVirtualPartitionRequestsDevices():
    return __partitionVirtualRequests.keys()

def delVirtualPartitionRequests(device):
    del __partitionVirtualRequests[device]


__esxSupplementaryDriverList = []

def addSupplementaryDriver(filename, driver, version, description,
                           driverList, snippetList, removeList):
    global __esxSupplementaryDriverList
    __esxSupplementaryDriverList.append(locals())

def removeSupplementaryDriver(driver):
    global __esxSupplementaryDriverList
    __esxSupplementaryDriverList.remove(driver)

def getSupplementaryDrivers():
    return deepcopy(__esxSupplementaryDriverList)

def clearSupplementaryDrivers():
    global __esxSupplementaryDriverList
    __esxSupplementaryDriverList = []


__esxPortRules = []

PORT_STATE_OPEN = 'open'
PORT_STATE_CLOSED = 'closed'
PORT_PROTO_TCP = 'tcp'
PORT_PROTO_UDP = 'udp'
PORT_DIRECTION_IN = 'in'
PORT_DIRECTION_OUT = 'out'

def addPortRule(state, number, protocol, direction, name=None):
    global __esxPortRules
    __esxPortRules.append(locals())

def delPortRule(portRule):
    """To delete a item, you will have to first get a reference
    to it from getPortRule() so that you can uniquely identify it
    Throws: ValueError when the item is not in the list.
    """
    global __esxPortRules
    __esxPortRules.remove(portRule)

def getPortRules():
    return deepcopy(__esxPortRules)


__esxServiceRules = []

PORT_STATE_ON = 'on'
PORT_STATE_OFF = 'off'

def addServiceRule(serviceName, state):
    global __esxServiceRules
    __esxServiceRules.append( locals() )

def delServiceRule(serviceRule):
    """To delete a item, you will have to first get a reference
    to it from getServiceRule() so that you can uniquely identify it
    Throws: ValueError when the item is not in the list.
    """
    global __esxServiceRules
    __esxServiceRules.remove(serviceRule)

def getServiceRules():
    return deepcopy(__esxServiceRules)


# async driver packages not part of primary.xml
__packageObjectsToInstall = []

def addPackageObjectToInstall(package):
    if package not in __packageObjectsToInstall:
        __packageObjectsToInstall.append(package)

def delPackageObjectToInstall(package):
    if package in __packageObjectsToInstall:
        __packageObjectsToInstall.remove(package)

def getPackageObjectsToInstall():
    return __packageObjectsToInstall


__packagesToInstall = []

def addPackageToInstall(package):
    if package not in __packagesToInstall:
        __packagesToInstall.append(package)

def delPackageToInstall(package):
    if package in __packagesToInstall:
        __packagesToInstall.remove(package)

def getPackagesToInstall():
    return __packagesToInstall

__packagesNotToInstall = []

def addPackageNotToInstall(package):
    if package not in __packagesNotToInstall:
        __packagesNotToInstall.append(package)

def delPackageNotToInstall(package):
    if package in __packagesNotToInstall:
        __packagesNotToInstall.remove(package)

def getPackagesNotToInstall():
    return __packagesNotToInstall


__serialNumber = {}

def setSerialNumber(esx):
    global __serialNumber
    __serialNumber = locals()

def getSerialNumber():
    return __serialNumber.copy()

def clearLicense():
    global __serialNumber
    __serialNumber = {}

# ----------------------------------------------------------------------------
# dumpToString
# ----------------------------------------------------------------------------
def dumpToString():
    '''Dump all of the interesting attributes in the userchoices module
    to a string
    '''
    def isNonMagicNonUppercaseData(name, obj):
        return not (
               (name.startswith('__') and name.endswith('__'))
               or name.upper() == name
               or callable(obj)
               )
    items = globals().items()
    strings = [pformat(item) for item in items
               if isNonMagicNonUppercaseData(*item)]
    strings.sort()
    dump = '\n'.join(strings)
    return dump
