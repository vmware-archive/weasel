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

"""
networking_base.py module.

Public API:
init()
cosConnectForInstaller(...)
iScsiConnectForInstaller(...)
cosConnect(...)
getPhysicalNics()
getVirtualNics()
getVmKernelNics()
getVirtualSwitches()
getPluggedInAvailableNIC()
"""

import vmkctl
import workarounds
import userchoices
import task_progress
from util import splitInts
from log import log

# ==========================================================================
# module constants
# ==========================================================================
_PORTGROUP_SIZE = 128
_PORTGROUP_DOWNLOAD = 'Download portgroup'
_PORTGROUP_COS = 'Service Console'
_PORTGROUP_VM = 'VM Network'
_PORTGROUP_VMK = 'iSCSI portgroup'

_HOST_INTERFACE_PREFIX = 'vswif'

_connectedVNic = None
_iscsiConnectedVmkNic = None
_networkDriverIsLoaded = False

class ConnectException(Exception):
    '''An Exception that occurs during a connect* function'''

class WrappedVmkctlException(Exception):
    def __init__(self, hostCtlException):
        Exception.__init__(self)
        self.msg = hostCtlException.GetMessage()
    def __repr__(self):
        return '<WrappedVmkctlException (%s)>' % self.msg
    def __str__(self):
        return '<WrappedVmkctlException (%s)>' % self.msg

def wrapHostCtlExceptions(fn):
    '''A decorator that you can use to modify functions that call vmkctl
    methods.  It will catch any vmkctl.HostCtlException and wrap it in a
    more python friendly WrappedVmkctlException
    '''
    def newFn(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except vmkctl.HostCtlException, ex:
            raise WrappedVmkctlException(ex)
    newFn.__name__ = fn.__name__ #to make the stacktrace look better
    return newFn
    

# ==========================================================================
# aliases to vmkctl singletons
# ==========================================================================
_netInfo = vmkctl.NetworkInfoImpl()
_routingInfo = vmkctl.RoutingInfoImpl()
_vswitchInfo = vmkctl.VirtualSwitchInfoImpl()
_consoleNicInfo = vmkctl.ConsoleNicInfoImpl()
_vmkernelNicInfo = vmkctl.VmKernelNicInfoImpl()

# ==========================================================================
# module-internal helper functions
# ==========================================================================

def _checkInit():
    '''To be called from any function that assumes init() has been called
    and can not be expected to work otherwise.  Throws an exception if
    init() has not been called
    '''
    if not _networkDriverIsLoaded:
        init()

def findPhysicalNicByName(name):
    for nic in getPhysicalNics():
        if nic.name == name:
            return nic
    return None

def findPhysicalNicByMacAddress(macAddress):
    for nic in getPhysicalNics():
        if nic.macAddress.lower() == macAddress.lower():
            return nic
    return None

def makePermanentCosPortgroupName():
    return getAvailablePortGroupName(_PORTGROUP_COS)
def makeVMPortgroupName():
    return getAvailablePortGroupName(_PORTGROUP_VM)
def makeDownloadPortgroupName():
    return getAvailablePortGroupName(_PORTGROUP_DOWNLOAD)
def makeVmkPortgroupName():
    return getAvailablePortGroupName(_PORTGROUP_VMK)

def disconnectDownloadNetwork():
    # XXX Need to drop NFS here since the download IP config might be different
    # from the IP config for the machine itself.  We should probably find a
    # better way to do this type of stuff, but this does the job fine for now.
    import remote_files
    remote_files.tidyAction()

    # this shouldn't affect any of the vmkernel nics
    for vNic in getVirtualNics():
        if vNic.portGroupName.startswith(_PORTGROUP_DOWNLOAD):
            vNic.remove()
    for vSwitch in getVirtualSwitches():
        for portGroup in vSwitch.portGroups:
            if portGroup.name.startswith(_PORTGROUP_DOWNLOAD):
                vSwitch.removePortGroup(portGroup.name)
        if not vSwitch.portGroups: #deleted them all
            vSwitch.remove()
        else:
            log.debug('Virtual Switch %s not empty.  Not removing.' % vSwitch)
            log.debug('portgroups : %s' % str(vSwitch.portGroups))

# =========================================================================
# Main API - Functions intended for universal use that actually do stuff
# =========================================================================

# ----------------------------------------------------------------------------
def init():
    '''Do the necessary initial actions that all the other networking_base
    functions depend on.  eg, load networking drivers
    '''
    global _networkDriverIsLoaded
    if not _networkDriverIsLoaded:
        workarounds.PrepareSystemForNetworking()
        _networkDriverIsLoaded = True

# ----------------------------------------------------------------------------
def setHostWideUserchoices(choices):
    '''Enact the userchoices for the host-wide options
    eg, gateway, hostname, nameservers
    The choices argument is either userchoices.getCosNetwork() or
    userchoices.getDownloadNetwork()
    '''
    log.info('Setting the host-wide networking options')
    log.debug('using choices: %s' % str(choices))
    import host_config # avoid circular imports
    if not choices:
        raise ConnectException('No network conf choices have been made.')

    if choices['gateway']:
        host_config.config.gateway = choices['gateway']
    # XXX vmkctl does not support clearing the gateway right now.
    # else:
    #     host_config.config.gateway = host_config.config.DEFAULT_GATEWAY
    if choices['hostname']:
        host_config.config.hostname = choices['hostname']
    else:
        # vmkctl does not like empty host names.
        host_config.config.hostname = 'localhost'
    #clear out any existing nameservers
    for nameserver in list(host_config.config.nameservers):
        host_config.config.nameservers.remove(nameserver)
    for nameserver in [choices['nameserver1'], choices['nameserver2']]:
        if nameserver:
            host_config.config.nameservers.append(nameserver)
        
# ----------------------------------------------------------------------------
@wrapHostCtlExceptions
def hostAction(context):
    '''Enact the choices in userchoices, and save them permanently to
    the host system.
    First remove any network setup that may have been necessary to download
    the installation media.
    Leave iSCSI networking intact, though, as we don't want to lose access to
    the drive.
    '''
    # userchoices contains all the authoritative info for this host,
    # so clobber any previous settings.
    disconnectDownloadNetwork()


    cosNicChoices = userchoices.getCosNICs()
    if not cosNicChoices:
        return
    if len(cosNicChoices) > 1:
        log.warn('There were more than one group of choices for the COS NIC')
        log.warn('cosNicChoices: %s' % str(cosNicChoices))

    firstSuccessfullyEnabledVNic = None
    for nicChoices in cosNicChoices:
        pNic = nicChoices['device'] # a reference to a PhysicalNicFacade
        vlanID = nicChoices['vlanID']
        if not vlanID:
            vlanID = None
        # this will bump any previous ones that were occupying 'Service Console'
        portGroupName = makePermanentCosPortgroupName()
        vSwitch = VirtualSwitchFacade(portGroupName=portGroupName,
                                      vlanID=vlanID)
        if userchoices.getAddVmPortGroup():
            vmPortGroupName = makeVMPortgroupName()
            vSwitch.addPortGroup(vmPortGroupName)
        vSwitch.uplink = pNic
        if nicChoices['bootProto'] == userchoices.NIC_BOOT_STATIC:
            if not nicChoices['ip'] or not nicChoices['netmask']:
                msg = ('COS NIC %s is not fully defined. Missing '
                       'IP address or netmask' % str(pNic))
                raise Exception(msg)
            ipConf = StaticIPConfig(nicChoices['ip'], nicChoices['netmask'])
        elif nicChoices['bootProto'] == userchoices.NIC_BOOT_DHCP:
            ipConf = DHCPIPConfig()
        else:
            msg = 'Unknown bootProto specified for %s' % pNic
            raise Exception(msg)
        vNic = VirtualNicFacade(ipConfig=ipConf, portGroupName=portGroupName)
        try:
            vNic.enable()
        except vmkctl.HostCtlException, ex:
            # this is not an error since the install might be done in a 
            # "factory" where the network is not actually the production 
            # network, but may cause difficulties running the 
            # %postinstall script
            log.warn('Could not bring up network for NIC %s with IP Config %s'
                     % (pNic, ipConf))
            log.warn('Exception message: %s' % ex.GetMessage())
        else:
            if not firstSuccessfullyEnabledVNic:
                firstSuccessfullyEnabledVNic = vNic

    # Fix the device naming
    _netInfo.RestorePnics()

    # setHostWideUserchoices must go *after* disconnectDownloadNetwork, as
    # ifdown can clobber /etc/resolv.conf.  It must also go after any static
    # IP addresses have been set, because setting the hostname relies on
    # them existing.
    choices = userchoices.getCosNetwork()
    if choices:
        setHostWideUserchoices(choices)
        if choices['gateway']:
            import host_config # avoid circular imports
            try:
                # If we were able to successfully bring up a vNic, then that's 
                # the one we should use for routing.  If we didn't bring one up
                # then just call activateGatewayRouting with no args and trust
                # that it will do the right thing.
                if firstSuccessfullyEnabledVNic:
                    args = [firstSuccessfullyEnabledVNic.name]
                else:
                    args = []
                host_config.config.activateGatewayRouting(*args)
            except WrappedVmkctlException, ex:
                # May not have worked if the NIC did not have a link.  This is
                # harmless except perhaps for a %post install script, so we
                # can continue the install
                msg = ('Routing activation: Not able to set the default'
                       ' gateway.\n Perhaps the chosen NIC was not linked.\n'
                       ' Routing exception message: %s' % str(ex))
                log.warn(msg)
    else:
        log.info('No choice made for gateway, hostname, dns. Relying on DHCP')

    # now that we've set up all the vmkctl objects, we need to save the
    # config so that they come up after reboot
    workarounds.hostActionCopyConfig(None)

    _netInfo.SetCosIpv6Enabled(True)
    

# ----------------------------------------------------------------------------
@wrapHostCtlExceptions
def hostActionUpdate(_context):
    '''Update the configuration files during an upgrade.'''
    for vNic in getVirtualNics():
        vNic.updateConfig()
    workarounds.BlacklistIPv6Driver()

    # Since this is called only when upgrading from 3.x to KL.next, we
    # turn it on by default. Nothing to do from upgrading from 4.0.
    _netInfo.SetCosIpv6Enabled(True)
    
# ----------------------------------------------------------------------------
def connected():
    return _connectedVNic != None

# ----------------------------------------------------------------------------
@wrapHostCtlExceptions
def getPhysicalNics():
    '''Returns a (possibly empty) list of PhysicalNicFacade objects
    constructed from all the VmkCtl::Network::Pnic objects known to the system.
    '''
    _checkInit()
    return [PhysicalNicFacade(pnic) for pnic in _netInfo.GetPnics()]

# ----------------------------------------------------------------------------
@wrapHostCtlExceptions
def getVirtualNics():
    '''returns a (possibly empty) list of virtual nics'''
    _checkInit()
    return [VirtualNicFacade(realVnic) for realVnic in
            _consoleNicInfo.GetServiceConsoleNics()]

# ----------------------------------------------------------------------------
@wrapHostCtlExceptions
def getVmKernelNics():
    '''returns a (possibly empty) list of vmkernel nics'''
    _checkInit()
    return [VmKernelNicFacade(realVmkNic) for realVmkNic in
            _vmkernelNicInfo.GetVmKernelNics()]

# ----------------------------------------------------------------------------
@wrapHostCtlExceptions
def getVirtualSwitches():
    '''returns a (possibly empty) list of virtual switches'''
    _checkInit()
    return [VirtualSwitchFacade(realVswitch) for realVswitch in
            _vswitchInfo.GetVirtualSwitches()]

# ----------------------------------------------------------------------------
def cosConnectForInstaller(failOnWarnings=True, onlyConfiguredNics=True):
    '''Like cosConnect, but it uses userchoices and if you use this
    function exclusively, it will keep only one connected Vnic at a time.
    Tries to make a connection in the following order, stopping after the
    first successful connection is made:
     1. try to use the config in userchoices.*DownloadNic and *DownloadNetwork
     2. try to use the config in userchoices.*CosNic and *CosNetwork
     3. try to use DHCP connections on any remaining NICs

    Arguments:
    failOnWarnings: if True, raise an exception on otherwise survivable
               warnings
    onlyConfiguredNics: if True, don't attempt any nics that haven't been
               configured by the user.  ie, don't try #3 above
    '''
    log.info('Attempting to bring up the network.')
    def doRaise(msg):
        raise Exception(msg)
    if failOnWarnings:
        logOrRaise = doRaise
    else:
        logOrRaise = log.warn

    # ensure we're only manipulating one COS nic
    disconnectDownloadNetwork()
    global _connectedVNic
    if _connectedVNic:
        log.info('Brought down the already-enabled Virtual NIC.')
        _connectedVNic = None

    argsForCosConnect = []
    allNicChoices = []

    downloadNicChoices = userchoices.getDownloadNic()
    if downloadNicChoices:
        log.info('The user chose specific network settings for downloading'
                 'remote media.  Those choices will be attempted first.')
        if not downloadNicChoices['device']:
            availableNIC = getPluggedInAvailableNIC(None)
            if availableNIC:
                downloadNicChoices.update(device=availableNIC)
                allNicChoices.append(downloadNicChoices)
            else:
                logOrRaise('Could not find a free Physical NIC to attach to'
                           ' download network specifications %s' 
                           % str(downloadNicChoices))
        else:
            allNicChoices.append(downloadNicChoices)

    cosNicChoices = userchoices.getCosNICs()
    if cosNicChoices:
        allNicChoices += cosNicChoices
    else:
        msg = 'No COS NICs have been added by the user.'
        logOrRaise(msg)

    for nicChoices in allNicChoices:
        log.debug('nicChoices %s' %str(nicChoices))
        log.debug('Setting vlan (%(vlanID)s), ipConf (%(bootProto)s, %(ip)s, %(netmask)s) '
                  'for NIC %(device)s' % nicChoices)
        assert nicChoices['device']
        nic = nicChoices['device'] # a reference to a PhysicalNicFacade
        vlanID = nicChoices['vlanID']
        if not vlanID:
            vlanID = None #make sure it's None, not just ''
        if nicChoices['bootProto'] == userchoices.NIC_BOOT_STATIC:
            if not nicChoices['ip'] or not nicChoices['netmask']:
                msg = ('COS NIC %s is not fully defined. Missing '
                       'IP address or netmask' % str(nic))
                logOrRaise(msg)
            ipConf = StaticIPConfig(nicChoices['ip'], nicChoices['netmask'])
        elif nicChoices['bootProto'] == userchoices.NIC_BOOT_DHCP:
            ipConf = DHCPIPConfig()
        else:
            msg = 'Unknown bootProto specified for %s' % nic
            logOrRaise(msg)
            ipConf = DHCPIPConfig()

        argsForCosConnect.append((nic, vlanID, ipConf))

    if not onlyConfiguredNics:
        # we've tried all the user-configured nics, now try the rest with DHCP
        configuredNics = [choices['device'] for choices in allNicChoices]
        unConfiguredNics =  set(getPhysicalNics()) - set(configuredNics)
        # sort these for repeatability's sake.
        unConfiguredNics = list(unConfiguredNics)
        unConfiguredNics.sort()
        for nic in unConfiguredNics:
            if not nic.isLinkUp:
                continue # it would be pointless to try unplugged NICs
            log.info('Setting unconfigured NIC %s to use DHCP' % nic)
            ipConf = DHCPIPConfig()
            argsForCosConnect.append((nic, None, ipConf))

    for nic, vlanID, ipConf in argsForCosConnect:
        try:
            log.info('Bringing up network interface for NIC %s. Using ipConf %s'
                     % (nic,ipConf))
            vnic = cosConnect(pNic=nic, vlanID=vlanID, ipConf=ipConf)
        except vmkctl.HostCtlException, ex:
            msg = 'vmkctl HostCtlException:'+ ex.GetMessage()
            logOrRaise(msg)
        else:
            log.info('COS has an enabled Virtual NIC %s.' % vnic)
            _connectedVNic = vnic
            break #we only need one to work

    import host_config # avoid circular imports

    # setHostWideUserchoices must go *after* disconnectDownloadNetwork, as
    # ifdown can clobber /etc/resolv.conf.  It must also go after any static
    # IP addresses have been set, because setting the hostname relies on
    # them existing.
    choices = userchoices.getDownloadNetwork()
    if not choices:
        choices = userchoices.getCosNetwork()
    if choices:
        setHostWideUserchoices(choices)
        if _connectedVNic:
            # Seting up gateway routing requires the vNic to be wired up 
            # to the switch port.
            host_config.config.activateGatewayRouting(_connectedVNic.name)
        else:
            logOrRaise('Could not activate routing through the gateway. '
                       'A connected Virtual NIC is required.')
    else:
        log.debug('No host network choices made.  Only DHCP will succeed.')


    # Calling cosConnect while set to DHCP could have picked up a new
    # nameserver, so we'll need to refresh the active process' DNS resolver
    host_config.config.nameservers.refresh()



# ----------------------------------------------------------------------------
@wrapHostCtlExceptions
def iScsiConnectForInstaller(pNic, vSwitch=None, portGroupName=None,
                             vlanID=None, ipConf=None):
    global _iscsiConnectedVmkNic
    import host_config # avoid circular imports

    # ensure we're only manipulating one iSCSI nic
    if _iscsiConnectedVmkNic:
        log.info('Bringing down the connected Virtual NIC.')
        _iscsiConnectedVmkNic.remove()
        _iscsiConnectedVmkNic = None
        raise NotImplementedError('clean the vswitch and the portgroup')

    if not portGroupName:
        portGroupName = makeVmkPortgroupName()

    if not ipConf:
        ipConf = DHCPIPConfig()

    if isinstance(ipConf, StaticIPConfig):
        vmkctlIP = vmkctl.Ipv4Address(host_config.config.vmkernelGateway)
        _routingInfo.SetVmKernelDefaultGateway(vmkctlIP)

    _iscsiConnectedVmkNic = VmKernelNicFacade(ipConf, portGroupName,
                                              pNic.macAddress)

    return cosConnect(pNic, vSwitch, portGroupName, vlanID,
                      _iscsiConnectedVmkNic, ipConf)


            
# ----------------------------------------------------------------------------
def getPluggedInAvailableNIC(*args):
    '''Finds the first Physical NIC that is both plugged in and not
    being used by some Virtual Switch.
    If called with an argument, and no suitable NIC is found, the
    argument will be returned instead.  (inspired by dict.get()
    If no argument is given and no suitable NIC is found, this function
    will raise a ConnectException
    '''
    liveNics = [nic for nic in getPhysicalNics()
                if nic.isLinkUp]
    if not liveNics:
        if args:
            return args[0]
        raise ConnectException('No physical NICs plugged in')

    takenNics = [vswitch.uplink for vswitch in getVirtualSwitches()
                 if vswitch.uplink != None]
    availableNics = set(liveNics) - set(takenNics)
    if not availableNics:
        if args:
            return args[0]
        raise ConnectException('All plugged in NICs are taken')

    # sort these for repeatability's sake
    availableNics = list(availableNics)
    availableNics.sort()
    return availableNics[0]

# ----------------------------------------------------------------------------
@wrapHostCtlExceptions
def getAvailablePortGroupName(pgName):
    '''This is slightly magic.  It should always return the requested pgName
    It will go to great pains to make this portgroup name available.
    First, by trying to rename (by suffixing it with 0-99) any portGroup
    that already has that name.  If all 100 potential replacements are
    taken, it resorts to deleting that old portgroup.
    '''
    allNames = _netInfo.GetAllPortGroupNames()
    if pgName in allNames:
        # Rename the old Portgroup
        log.warn('Portgroup name %s conflicts with one already used', pgName)
        for vswitch in getVirtualSwitches():
            for portGroup in vswitch.portGroups:
                if portGroup.name == pgName:
                    for i in range(100):
                        replacementName = pgName + str(i)
                        if replacementName not in allNames:
                            break
                    else:
                        log.warn('No replacement found.')
                        log.warn('Removing old portgroup.')
                        vswitch.removePortGroup(pgName)
                        break
                    log.warn('Renaming old portgroup to %s', replacementName)
                    portGroup.name = replacementName
    return pgName
    
# ----------------------------------------------------------------------------
def cosConnect(pNic=None, vSwitch=None, portGroupName=None, vlanID=None,
               vNic=None, ipConf=None):
    '''Attempt to bring up (connect) a COS network interface.
    Should be able to robustly deal with any or all of the arguments left
    as None.
    '''
    task_progress.taskStarted('network')
    import host_config # in the function namespace to avoid circular imports
    if not host_config.config.hostname:
        host_config.config.hostname = 'localhost'

    if not pNic:
        pNic = getPluggedInAvailableNIC()
            
    task_progress.taskProgress('network')
    if not portGroupName:
        portGroupName = makeDownloadPortgroupName()

    if not vSwitch:
        vSwitch = VirtualSwitchFacade(portGroupName=portGroupName,
                                      vlanID=vlanID)

    vSwitch.uplink = pNic

    if not ipConf:
        ipConf = DHCPIPConfig()

    task_progress.taskProgress('network')
    if not vNic:
        vNic = VirtualNicFacade(ipConfig=ipConf, portGroupName=portGroupName)

    try:
        try:
            # We can't reliably check vNic.enabled, so just disable the
            # re-enable.
            vNic.disable()
            vNic.enable()
        except vmkctl.HostCtlException, ex:
            log.error('HostCtlException during cosConnect(): '+ ex.GetMessage())
            log.debug('If you are testing the installer inside a VM, make'
                      'sure promiscuous mode is available')
            raise WrappedVmkctlException(ex)
    finally:
        task_progress.taskFinish('network')
    
    return vNic

# =========================================================================
# Backend classes
# =========================================================================

#------------------------------------------------------------------------------
class PhysicalNicFacade(object):
    '''A class to encapsulate information about Network Interface Controllers
    (AKA Network Interface Cards)
    '''
    def __init__(self, vmkctlPnic):
        self.__vmkctlPnic = vmkctlPnic

    def __cmp__(self, other):
        '''Compare by the .name attribute.
        Physical NIC names are of the form vmnicN where N is a
        number, non-zero-padded, and possibly longer than one digit.

        This method trusts that vmkctl has put the vmnic names in the
        right order.
        '''
        return cmp(splitInts(self.name), splitInts(other.name))

    def __eq__(self, other):
        # kkress has assured me that unique nics will always have unique names
        return isinstance(other, self.__class__) and self.name == other.name

    def __ne__(self, other):
        return not self == other

    def __hash__(self):
        # necessary for set comparisons / differences
        return hash(self.name)

    def __str__(self):
        return '<Physical NIC %s>' % self.name

    def _getVmkctlPnic(self):
        '''This should only be used by 'friend' callers.'''
        return self.__vmkctlPnic

    @wrapHostCtlExceptions
    def _getName(self):
        # hopefully vmkctl gives us something that's unique
        return self.__vmkctlPnic.GetName()
    name = property(_getName)

    @wrapHostCtlExceptions
    def _getDriverName(self):
        return self.__vmkctlPnic.GetDriverName()
    driverName = property(_getDriverName)

    @wrapHostCtlExceptions
    def _getHumanReadableName(self):
        pdev = self.__vmkctlPnic.GetPciDevice()
        if pdev:
            devName = pdev.GetDevice()
            if devName:
                return devName
        driverName = self.__vmkctlPnic.GetDriverName()
        if driverName:
            return '%s Network Adapter' % driverName
        return 'Unknown Network Adapter'
    humanReadableName = property(_getHumanReadableName)

    @wrapHostCtlExceptions
    def _getIsLinkUp(self):
        return self.__vmkctlPnic.IsLinkUp()
    isLinkUp = property(_getIsLinkUp)

    @wrapHostCtlExceptions
    def getMacAddress(self):
        return self.__vmkctlPnic.GetMacAddress().GetStringAddress()
    macAddress = property(getMacAddress)


#------------------------------------------------------------------------------
class PortGroupFacade(object):
    def __init__(self, realPortGroup):
        self.__portGroup = realPortGroup

    def __repr__(self):
        return '<PortGroup %s>' % self.name

    def __eq__(self, otherNameOrPortGroup):
        if isinstance(otherNameOrPortGroup, PortGroupFacade):
            return self.name == otherNameOrPortGroup.name
        else:
            return self.name == otherNameOrPortGroup

    def __ne__(self, other):
        return not self == other

    @wrapHostCtlExceptions
    def _getName(self):
        return self.__portGroup.GetName()
    @wrapHostCtlExceptions
    def _setName(self, val):
        return self.__portGroup.SetName(val)
    name = property(_getName, _setName)

#------------------------------------------------------------------------------
class VirtualSwitchFacade(object):
    '''A convenient way to create and manipulate Virtual Switches.
    VirtualSwitchFacade has 2 interesting attributes:
    portGroup (read-only) and uplink. Besides the constructor, it also has
    a remove method.  If the remove method is not called, the Virtual Switch
    will persist on the host after the VirtualSwitchFacade has been garbage-
    collected.
    '''
    @wrapHostCtlExceptions
    def __init__(self, realVswitch=None, portGroupName=None, name=None,
                 vlanID=None):

        if realVswitch and portGroupName:
            log.error('VirtualSwitchFacade constructed with a real Virtual'
                      ' Switch.  Ignoring the specified portgroup name')
        elif not (realVswitch or portGroupName):
            raise Exception('VirtualSwitchFacade constructor must be passed'
                            ' either a real Virtual Switch or a portgroup name')
        if realVswitch:
            self.__vswitch = realVswitch
        else:
            if vlanID == None:
                self._vlanID = None
            else:
                self._vlanID = int(vlanID)
            self._createVirtualSwitch(name) # creates self.__vswitch
            self.addPortGroup(portGroupName)

        self.name = self.__vswitch.GetName()

    def __repr__(self):
        if hasattr(self, 'name'):
            name = self.name
        else:
            name = ''
        return '<VirtualSwitchFacade %s (ID: %d)>' % (name, id(self))

    def _createVirtualSwitch(self, name=None):
        '''A helper to __init__.'''
        _checkInit()
        if not name:
            name = self._nextVSwitchName()
        log.debug('Creating a Virtual Switch (%s)' % name)
        try:
            self.__vswitch = _vswitchInfo.AddVirtualSwitch(name,
                                                           _PORTGROUP_SIZE)
        except vmkctl.HostCtlException, ex:
            msg = ex.GetMessage()
            raise Exception('Virtual Switch could not be added with name %s '
                            'and Portgroup size %d.\n' 
                            'Details: HostCtlException was %s'
                            % (name, _PORTGROUP_SIZE, msg))

    def _nextVSwitchName(self):
        '''A helper to __init__. Finds and returns the next Virtual Switch
        name.  Names are of the pattern vSwitchX (X is a positive integer)'''

        def makeVSwitchName(i):
            return 'vSwitch%d' % i

        newName = makeVSwitchName(0)
        existingSwitches = _vswitchInfo.GetVirtualSwitches()
        if existingSwitches:
            # Generate a new name, formed from "vSwitch" appended to the lowest
            # untaken number.
            takenNames = [switch.GetName() for switch in existingSwitches]
            maxSwitches = _netInfo.GetMaxVirtualSwitches()
            if len(existingSwitches) >= maxSwitches:
                msg = ('Could not add Virtual Switch. The maximum number of'
                       ' Virtual Switches are already present')
                raise Exception(msg)
            i = 0
            while newName in takenNames:
                log.info('The Virtual Switch name %s is already taken. Trying'
                         ' %s' % (newName, makeVSwitchName(i+1)))
                i += 1
                newName = makeVSwitchName(i)
        return newName

    def _clearUplinks(self):
        uplinks = self.__vswitch.GetUplinks()
        for uplink in uplinks:
            log.info('Removing uplink %s' % uplink)
            self.__vswitch.RemoveUplink(uplink)

    @wrapHostCtlExceptions
    def remove(self):
        log.debug('Removing Virtual Switch %s' % str(self))
        self._clearUplinks()
        for portGroup in self.portGroups:
            self.removePortGroup(portGroup.name)
        _vswitchInfo.RemoveVirtualSwitch(self.name)

    @wrapHostCtlExceptions
    def setUplink(self, physicalNic):
        '''Select a physical NIC to be the uplink to the outside network.
        A _VirtualNetwork object only allows one uplink at a time
        '''
        if not isinstance(physicalNic, PhysicalNicFacade):
            # assume it is a string
            foundNic = findPhysicalNicByName(physicalNic)
            if not foundNic:
                raise ValueError('%s did not match any physical nics' 
                                 % physicalNic)
            physicalNic = foundNic

        self._clearUplinks()

        newUplink = physicalNic.name
        log.info('Adding uplink %s' % newUplink)
        # NOTE: an exception that looks like Status(bad000N)= Busy here 
        #       means the pnic is claimed by some other vswitch
        self.__vswitch.AddUplink(newUplink)
        teamingPolicy = self.__vswitch.GetTeamingPolicy()
        teamingPolicy.SetUplinkOrder([newUplink])
        teamingPolicy.SetMaxActiveUplinks(1)
        self.__vswitch.SetTeamingPolicy(teamingPolicy)

    @wrapHostCtlExceptions
    def getUplink(self):
        '''Note: callers must be able to deal with a return value of None'''
        uplinks = self.__vswitch.GetUplinks()
        if not uplinks:
            return None

        uplink = uplinks[0] # Should be exactly one
        for physicalNic in getPhysicalNics():
            if uplink == physicalNic.name:
                return physicalNic

        raise Exception('Uplink %s was not found' % uplink)

    uplink = property(getUplink, setUplink)

    @wrapHostCtlExceptions
    def _getPortGroups(self):
        portGroups = []
        for realPortGroup in self.__vswitch.GetPortGroups():
            portGroups.append(PortGroupFacade(realPortGroup))
        return portGroups
    portGroups = property(_getPortGroups)

    @wrapHostCtlExceptions
    def addPortGroup(self, portGroupName):
        log.debug('Adding Portgroup "%s" to Virtual Switch %s' % (portGroupName, self))
        try:
            realPortGroup = self.__vswitch.AddPortGroup(portGroupName)
        except vmkctl.HostCtlException, ex:
            msg = ex.GetMessage()
            raise Exception('Port Group could not be added with name %s.\n'
                            'Details: HostCtlException was %s'
                            % (portGroupName, msg))
        if self._vlanID != None:
            realPortGroup.SetVlanId(self._vlanID)

    @wrapHostCtlExceptions
    def removePortGroup(self, portGroupName):
        log.debug('Removing Portgroup %s from Virtual Switch %s'
                  % (portGroupName, self))
        self.__vswitch.RemovePortGroup(portGroupName)


#------------------------------------------------------------------------------
class VmKernelNicFacade(object):
    '''An abstraction of a VmKernel NIC.'''
    def __init__(self, realVmkNic=None,
                 ipConfig=None, portGroupName=None, macAddress=None,
                 tsoMss=0, mtu=0):
        '''Constructor should be called with EITHER a real vmkNic OR
        with ifConfig, portGroupName, macAddress [,tsoMss, mtu]
        '''
        log.debug('Creating a VmKernel NIC')

        if realVmkNic:
            #sanity check
            if ipConfig or portGroupName or macAddress:
                log.error('VmKernelNicFacade constructed with a real vmkNic,'
                          ' ignoring the other specified args')
            self._initWithRealVmkNic(realVmkNic)
        else:
            self._initWithArgs(ipConfig, portGroupName, macAddress, tsoMss, mtu)

    @wrapHostCtlExceptions
    def _initWithRealVmkNic(self, realVmkNic):
        self.portGroupName = realVmkNic.GetPortGroupName()
        self.__vmkNic = realVmkNic

    @wrapHostCtlExceptions
    def _initWithArgs(self, ipConfig, portGroupName, macAddress, tsoMss, mtu):
        self.portGroupName = portGroupName

        # create the VmKernel NIC Facade
        vmkctlMacAddress = vmkctl.MacAddress(macAddress)
        vmkctlIpConfig = ipConfig._getVmkctlIpConfig()
        try:
            self.__vmkNic = _vmkernelNicInfo.AddVmKernelNic(portGroupName,
                                                            vmkctlIpConfig,
                                                            vmkctlMacAddress,
                                                            tsoMss, mtu)
        except vmkctl.HostCtlException, ex:
            log.error('VmKernelNicFacade constructor failed.')
            log.error('AddVmKernelNic message: %s' % ex.GetMessage())

    def __str__(self):
        return '<VmKernel NIC %s>' % self.name

    @wrapHostCtlExceptions
    def disable(self):
        return self.__vmkNic.Disable()
    
    @wrapHostCtlExceptions
    def enable(self):
        return self.__vmkNic.Enable()
    
    @wrapHostCtlExceptions
    def _getName(self):
        return self.__vmkNic.GetName()
    name = property(_getName)

    @wrapHostCtlExceptions
    def _getEnabled(self):
        log.warn('IsEnabled only tells whether the ONBOOT flag is true')
        return self.__vmkNic.IsEnabled()
    enabled = property(_getEnabled)

    @wrapHostCtlExceptions
    def remove(self):
        log.debug('Removing VmKernel NIC %s' % self)
        _vmkernelNicInfo.RemoveVmKernelNic(self.name)



#------------------------------------------------------------------------------
class VirtualNicFacade(object):
    '''An abstraction of a Virtual NIC.'''

    def __init__(self, realVnic=None, ipConfig=None, portGroupName=None):
        '''VirtualNic shouldn't need to be constructed outside the
        networking_base module. If you're calling this from outside,
        you're probably doing something wrong
        '''
        log.debug('Creating a Virtual NIC')

        self.driverName = 'VMware Virtual NIC'
        self.humanReadableName = self.driverName
    
        # sanity-check the arguments
        if realVnic and ipConfig:
            log.error('VirtualNicFacade constructed with a real Vnic,'
                      ' ignoring the specified ipConfig')
        elif not (realVnic or ipConfig):
            raise Exception('VirtualNicFacade constructed without a real Vnic'
                            ' but the needed ipConfig argument was missing')
        elif ipConfig and not portGroupName:
            msg = ('VirtualNicFacade constructed with an ipConfig, but'
                   ' the needed port group name was ommitted.')
            log.error(msg)
            raise ValueError(msg)

        # create the Virtual NIC Facade
        if realVnic:
            self.__vNic = realVnic
        else:
            self.createVnic(ipConfig, portGroupName) # creates self.__vNic

    def __str__(self):
        return '<Virtual NIC %s>' % self.name

    @wrapHostCtlExceptions
    def disable(self):
        return self.__vNic.Disable()
    
    def enable(self):
        if self.enabled:
            log.debug('Calling enable() on an already-enabled Virtual NIC')

        try:
            return self.__vNic.Enable()
        except vmkctl.HostCtlException, ex:
            exMsg = ex.GetMessage()
            # TODO XXX: this is very unsavoury
            if self.enabled and 'returned with non-zero status' in exMsg:
                log.warn('vmkctl cried wolf. Ignoring exception.')
                log.warn('Ignored exception was: %s' % exMsg)
            else:
                raise
    
    @wrapHostCtlExceptions
    def _getName(self):
        return self.__vNic.GetName()
    name = property(_getName)

    @wrapHostCtlExceptions
    def _getEnabled(self):
        return self.__vNic.IsEnabled()
    enabled = property(_getEnabled)

    @wrapHostCtlExceptions
    def _getPortGroupName(self):
        return self.__vNic.GetPortGroupName()
    portGroupName = property(_getPortGroupName)


    @wrapHostCtlExceptions
    def _nextVnicName(self):
        takenNumbers = set()
        vnics = _consoleNicInfo.GetServiceConsoleNics()
        candidate = 0
        for vnic in vnics:
            vnicName = vnic.GetName()
            numberPart = vnicName[len(_HOST_INTERFACE_PREFIX):]
            num = int(numberPart)
            takenNumbers.add(num)
            while candidate in takenNumbers: #O(1) lookup
                candidate += 1
        return _HOST_INTERFACE_PREFIX + str(candidate)

    @wrapHostCtlExceptions
    def createVnic(self, wrappedIPConf, portGroupName):
        '''Creates a Virtual NIC and associates it with an ipConfig.  This
        should result in a vswifX interface being created on the COS
        '''
        ipConf = wrappedIPConf._getVmkctlIpConfig()
        name = self._nextVnicName()
        macGen = vmkctl.MacAddressGenerator.GetSingleton()
        macAddr = macGen.GenerateVswifMacAddr(name)
        task_progress.taskProgress('network')
        self.__vNic = _consoleNicInfo.AddServiceConsoleNic(
                           name,
                           portGroupName,
                           ipConf,
                           macAddr,
                           False) # False => don't enable the interface now

    @wrapHostCtlExceptions
    def remove(self):
        log.debug('Removing Virtual NIC %s' % str(self))
        _consoleNicInfo.RemoveServiceConsoleNic(self.name)

    @wrapHostCtlExceptions
    def updateConfig(self):
        '''Get and then set the config so any changes to the file format are
        updated.  For example, adding IPv6 variables to the ifcfg-vswif file.'''
        self.__vNic.SetIpConfig(self.__vNic.GetConfiguredIpConfig())


#------------------------------------------------------------------------------
class DHCPIPConfig(object):
    @wrapHostCtlExceptions
    def __init__(self):
        self.__ipconf = vmkctl.IpConfig()
        self.__ipconf.SetUseDhcp(True)
        # SetDhcpDns will allow the DHCP response to alter /etc/resolv.conf
        self.__ipconf.SetDhcpDns(True)

    def __str__(self):
        return '<DHCPIPConfig>'

    def _getVmkctlIpConfig(self):
        '''This should only be used by 'friend' callers.  ie, VirtualNetwork'''
        return self.__ipconf


#------------------------------------------------------------------------------
class StaticIPConfig(object):
    @wrapHostCtlExceptions
    def __init__(self, ip, netmask):
        self.ip = ip
        vmkctlIP = vmkctl.Ipv4Address(ip)
        vmkctlNetmask = vmkctl.Ipv4Address(netmask)
        self.__ipconf = vmkctl.IpConfig()
        self.__ipconf.SetUseDhcp(False)
        self.__ipconf.SetIpv4Address(vmkctlIP)
        self.__ipconf.SetIpv4Netmask(vmkctlNetmask)

    def __str__(self):
        return '<StaticIPConfig %s>' % self.ip

    def _getVmkctlIpConfig(self):
        '''This should only be used by 'friend' callers.  ie, VirtualNetwork'''
        return self.__ipconf

