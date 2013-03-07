
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

'''A mock vmkctl module.

This module provides some storage-related classes of vmkctl that we use in the
installer.  To configure the module, set the VMKCTL_STORAGE_CONFIG variable to a
dictionary that contains a "disks" key with a value of a list dictionaries to
use when initializing the VMDiskLuns objects.

See test/good-config.1/fauxconfig.py
'''

import parted
import fauxroot

from log import log

VMKCTL_STORAGE_CONFIG = {}
VMKCTL_ISCSI_CONFIG = {}
VMKCTL_NET_CONFIG = {}
VMKCTL_CPU_CONFIG = {}

VMKCTL_MEM_SIZE = 20000
VMKCTL_COS_MEM_SIZE = 272

class ScsiInterface:
    SCSI_IFACE_TYPE_BLOCK = 1
    SCSI_IFACE_TYPE_IDE = 2
    SCSI_IFACE_TYPE_USB = 3
    SCSI_IFACE_TYPE_SATA = 4
    
    def __init__(self, values):
        self.__dict__.update(values)

    def GetDriver(self):
        return self.driver

    def Rescan(self):
        pass

    def IsSoftwareiScsi(self):
        return True

    def GetInterfaceType(self):
        return self.interfaceType

class ScsiPath:
    def __init__(self, values):
        self.__dict__.update(values)
        self.adapter = ScsiInterface(self.adapter)
        if self.targetPathString:
            targetMap = { 'targetString' : self.targetPathString }
            self.transportMapping = TransportMapping(targetMap)
        else:
            self.transportMapping = None

    def GetAdapter(self):
        return self.adapter

    def GetAdapterName(self):
        return self.adapterName

    def GetChannelNumber(self):
        return self.channelNumber

    def GetTargetNumber(self):
        return self.targetNumber

    def GetLun(self):
        return self.lun

    def GetTransportMapping(self):
        return self.transportMapping

class TransportMapping:
    def __init__(self, values):
        self.__dict__.update(values)

    def GetTargetString(self):
        return self.targetString

class VMDiskLunParts:
    def __init__(self, values):
        self.__dict__.update(values)
        return

    def GetDeviceName(self):
        return self.deviceName

class VMPartition:
    def __init__(self, devfsPath, partitionNumber):
        self.devfsPath = devfsPath
        self.partitionNumber = partitionNumber

    def GetDevfsPath(self):
        return self.devfsPath

    def GetPartition(self):
        return self.partitionNumber

class VMDiskLuns:
    def __init__(self, values):
        self.__dict__.update(values)
        self.scsiPaths = map(ScsiPath, self.scsiPaths)
        return

    def GetLunType(self):
        return self.lunType

    def GetConsoleDevice(self):
        if self.model == "USB Travelator 2000":
            raise HostCtlException, "Blah blah blah - some fake text"
        return self.consoleDevice

    def GetDevfsPath(self):
        return self.devfsPath

    def GetName(self):
        return self.name

    def GetModel(self):
        return self.model

    def GetVendor(self):
        return self.vendor

    def GetPaths(self):
        return self.scsiPaths

    def GetPartitions(self):
        retval = [VMPartition(self.devfsPath, 0)]
        # We partition through parted, so ask it for the current config.
        pdevice = parted.PedDevice.get(self.consoleDevice)
        pdisk = parted.PedDisk.new(pdevice)
        for part in pdisk.partitions:
            retval.append(VMPartition("%s:%d" % (self.devfsPath, part.num),
                                      part.num))

        return retval

    def IsLocal(self):
        return self.local

    def IsPseudoLun(self):
        return self.pseudoLun

    def __repr__(self):
        return repr(self.__dict__)



class VMStorage:
    def __init__(self, values):
        self.__dict__.update(values)

    def GetBlockSize(self):
        return self.blockSize

    def GetBlocksUsed(self):
        return self.blocksUsed

    def GetSize(self):
        return self.blockSize * self.totalBlocks

    def GetMajorVersion(self):
        return self.majorVersion

    def GetMinorVersion(self):
        return self.minorVersion

    def GetTotalBlocks(self):
        return self.totalBlocks

    def GetVolumeName(self):
        return self.volumeName

    def GetConsolePath(self):
        return self.consolePath

    def GetUuid(self):
        return self.uuid

    def GetExtents(self):
        return map(VMDiskLunParts, self.diskLuns)

    def __repr__(self):
        return repr(self.__dict__)


class StorageInfo:
    def __init__(self, values):
        self.__dict__.update(values)

    def GetDiskLuns(self):
        return map(VMDiskLuns, self.disks)

    def GetVmfsFileSystems(self):
        return map(VMStorage, self.datastores)

    def GetiScsiBootTables(self):
        return IscsiBootTables()

    def GetiScsiInterfaces(self):
        return map(ScsiInterface, self.interfaces)

    def RescanVmfs(self):
        return
    
    def __repr__(self):
        return repr(self.__dict__)



def StorageInfoImpl():
    return StorageInfo(VMKCTL_STORAGE_CONFIG)


class IscsiBootTables:
    def GetPrimary(self):
        return IscsiBootTable(**VMKCTL_ISCSI_CONFIG)
    # No secondary for now
        

class IscsiBootTable:
    """
    Fields are exactly as in iscsi.IscsiBootTable; only difference is that this
    one has getter functions.
    """
    def __init__(self,
      macAddress,     #vmkModules/vmkibft/iSCSIBootTable/mac_address
      nicIP,          #vmkModules/vmkibft/iSCSIBootTable/Primary/Nic/ip_address
      nicSubnetMask,  #vmkModules/vmkibft/iSCSIBootTable/Primary/Nic/subnet_mask
      nicGateway,     #vmkModules/vmkibft/iSCSIBootTable/Primary/Nic/gateway_ip_address
      nicDhcp,        #vmkModules/vmkibft/iSCSIBootTable/Primary/Nic/dhcp_flag
      nicVlan,        #vmkModules/vmkibft/iSCSIBootTable/Primary/Nic/vlan
      targetIP,       #vmkModules/vmkibft/iSCSIBootTable/Primary/iSCSI/Target/ip_address
      targetPort,     #vmkModules/vmkibft/iSCSIBootTable/Primary/iSCSI/Target/tcp_port
      lun,            #vmkModules/vmkibft/iSCSIBootTable/Primary/iSCSI/Target/lun
      targetName,     #vmkModules/vmkibft/iSCSIBootTable/Primary/iSCSI/Target/name
      chapName,       #vmkModules/vmkibft/iSCSIBootTable/Primary/iSCSI/Target/chap_name
      chapPwd,        #vmkModules/vmkibft/iSCSIBootTable/Primary/iSCSI/Target/chap_secret
      initiatorName,  #vmkModules/vmkibft/iSCSIBootTable/Primary/iSCSI/Initiator/name
      initiatorAlias  #vmkModules/vmkibft/iSCSIBootTable/Primary/iSCSI/Initiator/alias
    ):
        params = locals()
        del params['self']
        self.__dict__.update(params)
        if self.nicVlan == -1: # Convention for corresponding C++ interface
            self.nicVlan = None

        #
        # Generate getter functions for all the instance fields.  For example,
        # we generate a self.GetChapPwd() that returns self.chapPwd.
        #
        def _getByName(var):
            return self.__dict__[var]
        for var in locals():
            self.__dict__['Get' + var[0].upper() + var[1:]] = \
                lambda var=var: _getByName(var)


class HostCtlException(Exception):
    def __init__(self, msg):
        self.buriedMessage = msg
        self.args = ()

    def GetMessage(self):
        return self.buriedMessage

#
# Stuff called from network.py
#
class MacAddress:
    def __init__(self, stringAddress):
        self._stringAddress = stringAddress
    def GetStringAddress(self):  # Just the string representation
        return self._stringAddress

class PciDevice:
    def __init__(self, name, pciPosition):
        self.name = name

        assert len(pciPosition) == 3
        self.pciPosition = pciPosition

    def GetDevice(self):
        return self.name

    def GetPciString(self):
        return '%03d:%02d.%d' % self.pciPosition

    def GetBus(self):
        return self.pciPosition[0]

    def GetSlot(self):
        return self.pciPosition[1]

    def GetFunction(self):
        return self.pciPosition[2]


class Pnic:
    def __init__(self, driverName, humanReadableName, isLinkUp, speed,
                 macAddress, pciPosition=(0, 0, 0)):
        args = locals()
        del args['self']
        self.__dict__.update(args)
        self.pciDevice = PciDevice(humanReadableName, pciPosition)

    def GetDriverName(self): return self.driverName

    def GetName(self): return self.humanReadableName

    def IsLinkUp(self): return self.isLinkUp

    def LinkSpeed(self): return self.speed

    def GetMacAddress(self): return self.macAddress

    def GetPciDevice(self): return self.pciDevice


class NetworkInfoImpl:
    def GetPnics(self):
        fauxroot.longRunningFunction(1,'getpnics')
        return VMKCTL_NET_CONFIG['pnics']

    def GetMaxVirtualSwitches(self):
        return 128

    def GetAllPortGroupNames(self):
        fauxroot.longRunningFunction(1,'getallportgroupnames')
        return PortGroupImpl.allNames

    def RestorePnics(self):
        return

    def SetCosIpv6Enabled(self, enabled):
        return

class PortGroupImpl:
    allNames = []
    def __init__(self, name):
        self.name = name
        PortGroupImpl.allNames.append(name)
        self.vlanid = 0

    def __del__(self):
        if self.name in PortGroupImpl.allNames:
            PortGroupImpl.allNames.remove(self.name)

    def GetName(self):
        return self.name

    def SetName(self, name):
        PortGroupImpl.allNames.remove(self.name)
        self.name = name
        PortGroupImpl.allNames.append(self.name)

    def GetVlanId(self):
        return self.vlanid

    def SetVlanId(self, value):
        self.vlanid = value

class VirtualSwitch:
    def __init__(self, name, portgroupSize):
        params = locals()
        del params['self']
        self.__dict__.update(params)
        self.name = name
        self.portGroup = {}
        self.uplinks = []
        self.teamingPolicy = TeamingPolicy()

    def GetName(self):
        return self.name

    def AddPortGroup(self, pgrpName):
        fauxroot.longRunningFunction(1,'addportgroup')
        retval = PortGroupImpl(pgrpName)
        self.portGroup[pgrpName] = retval
        return retval

    def RemovePortGroup(self, pgrpName):
        del self.portGroup[pgrpName]

    def GetPortGroups(self):
        return self.portGroup.values()

    def GetUplinks(self):
        fauxroot.longRunningFunction(1,'getuplinks')
        log.debug("VirtualSwitch.GetUplinks() called")
        return self.uplinks

    def RemoveUplink(self, link):
        log.debug("VirtualSwitch.RemoveUplink() called")
        self.uplinks.remove(link)

    def AddUplink(self, link):
        fauxroot.longRunningFunction(1,'adduplink')
        log.debug("VirtualSwitch.AddUplink() called")
        self.uplinks.append(link)

    def GetTeamingPolicy(self):
        return self.teamingPolicy.copy()

    def SetTeamingPolicy(self, teamingPolicy):
        self.teamingPolicy = teamingPolicy


class VirtualSwitchInfoImpl:
    rep = {}
    
    def GetVirtualSwitches(self):
        fauxroot.longRunningFunction(1,'getvirtualswitches')
        return self.rep.values()

    def AddVirtualSwitch(self, name, portgroupSize=32):
        fauxroot.longRunningFunction(1,'addvirtualswitch')
        self.rep[name] = VirtualSwitch(name, portgroupSize)
        return self.rep[name]

    def RemoveVirtualSwitch(self, name):
        del self.rep[name]


class TeamingPolicy:
    def SetUplinkOrder(self, nicList):
        assert type(nicList) == list

    def SetMaxActiveUplinks(self, num):
        assert type(num) == int

    def copy(self):
        return TeamingPolicy()


class Vnic:
    def __init__(self, name, portgroupName, ipConf):
        params = locals()
        del params['self']
        self.__dict__.update(params)
        self.enabled = False

    def GetName(self):
        return self.name

    def SetIpConfig(self, ipConf):
        fauxroot.longRunningFunction(1, 'setipconfig')
        self.ipConf = ipConf

    def GetConfiguredIpConfig(self):
        return self.ipConf
        
    def GetIpConfig(self):
        return self.ipConf

    def Enable(self):
        if self.enabled:
            raise Exception('This will cause a DHCP bug in vmkctl!')
        fauxroot.longRunningFunction(3, 'enable')
        self.enabled = True

    def Disable(self):
        self.enabled = False

    def IsEnabled(self):
        return self.enabled

    def GetPortGroupName(self):
        return self.portgroupName

class VnicImpl:
    @classmethod
    def CreateVnic(vnicName, portgroupName, macAddress):
        fauxroot.longRunningFunction(1,'createvnic')
        vnic = Vnic(vnicName, portgroupName, None)
        vnic.macAddress = macAddress #not yet used
        return vnic

    

class NicInfoImpl:
    ''' Base class for ConsoleNicInfoImpl and VmKernelNicInfoImpl.
        Note there is no class NicInfoImpl in libvmkctl (though perhaps there
        should be).
    '''
    def __init__(self):
        self.nics = []

    def getNics(self):
        return self.nics

    def removeNic(self, nicName):
        for cnt, nic in enumerate(self.nics):
            if nic.GetName() == nicName:
                del self.nics[cnt]
                return
        raise ValueError, "[v]nicName " + nicName + " not found"

class ConsoleNicInfoImpl(NicInfoImpl):
    def __init__(self):
        NicInfoImpl.__init__(self)
        self.GetServiceConsoleNics = self.getNics
        self.RemoveServiceConsoleNic = self.removeNic

    def AddServiceConsoleNic(self, nextName, portgroupName, ipConf,
                             macAddr, enableInterface):
        fauxroot.longRunningFunction(1,'addserviceconsolenic')
        vnic = Vnic(nextName, portgroupName, ipConf)
        vnic.macAddress = macAddr #not yet used
        if enableInterface:
            vnic.Enable()
        self.nics.append(vnic)
        return self.nics[-1]


class IpConfig:
    def __init__(self):
        self.useDhcp = False
        self.dhcpDns = False
        self.vmkctlIP = None
        self.vmkctlNetmask = None

    def SetUseDhcp(self, val):
        self.useDhcp = val

    def SetDhcpDns(self, val):
        self.dhcpDns = val

    def SetIpv4Address(self, vmkctlIP):
        self.vmkctlIP = vmkctlIP

    def SetIpv4Netmask(self, vmkctlNetmask):
        self.vmkctlNetmask = vmkctlNetmask

def CastIp(ipv4Address):
    # Observe as I magically cast this to an IpAddress object:
    return ipv4Address # presto!
    
class Ipv4Address:
    def __init__(self, addr):
        self.addr = addr

    def __str__(self):
        return self.addr

    def GetStringAddress(self):
        return self.addr

    def __eq__(self, other):
        return str(self) == str(other)

    def __ne__(self, other):
        return not self == other

class MacAddressGenerator:
    mySingleton = None
    callCounter = 0

    @classmethod
    def GetSingleton(cls):
        if not cls.mySingleton:
            cls.mySingleton = MacAddressGenerator()
        return cls.mySingleton

    def GenerateVswifMacAddr(self, vNicName):
        counter = MacAddressGenerator.callCounter
        MacAddressGenerator.callCounter += 1
        MacAddressGenerator.callCounter %= 256
        suffix = hex(counter)[2:].zfill(2)
        macAddrString = '00:DE:AD:BE:EF:' + suffix
        return MacAddress(macAddrString)
        

class DnsConfigImpl:
    hostname = ''
    domain = ''
    nameservers = []
    domainsString = ''
    saveCounter = 0

    def GetHostname(self):
        return DnsConfigImpl.hostname

    def SetHostname(self, hostname):
        DnsConfigImpl.hostname = hostname

    def GetDomain(self):
        return DnsConfigImpl.domain

    def SetDomain(self, domain):
        DnsConfigImpl.domain = domain

    def GetNameServers(self):
        return DnsConfigImpl.nameservers

    def RemoveNameServers(self):
        DnsConfigImpl.nameservers = []

    def AddNameServer(self, nameserver):
        DnsConfigImpl.nameservers.append(nameserver)

    def RemoveNameServer(self, nameserver):
        DnsConfigImpl.nameservers.remove(nameserver)

    def SetSearchDomainsString(self, domainsString):
        DnsConfigImpl.domainsString = domainsString

    def GetSearchDomainsString(self):
        return DnsConfigImpl.domainsString

    def SaveConfig(self):
        DnsConfigImpl.saveCounter += 1
        log.debug("DnsConfigImpl.SaveConfig called.  Count:%d" 
                  % DnsConfigImpl.saveCounter)

    def Refresh(self):
        pass

class RoutingInfoImpl:
    consDefaultGateway = Ipv4Address('0.0.0.0')
    vmkDefaultGateway = Ipv4Address('0.0.0.0')
    def GetConsoleDefaultGateway(self):
        return RoutingInfoImpl.consDefaultGateway
    def SetConsoleDefaultGateway(self, gw, vnicName, confOnly=False):
        RoutingInfoImpl.consDefaultGateway = gw
    def GetVmKernelDefaultGateway(self):
        return RoutingInfoImpl.vmkDefaultGateway
    def SetVmKernelDefaultGateway(self, gw):
        RoutingInfoImpl.vmkDefaultGateway = gw

class VmKernelNic:
    def __init__(self, pg, ipConf, mac, tsoMss, mtu):
        self.args = (pg, ipConf, mac, tsoMss, mtu)
        self.name = mac
        self.enabled = False

    def GetName(self):
        return self.name

    def Enable(self):
        log.debug('VmKernelNic Enable!')
        self.enabled = True

    def GetEnabled(self):
        return self.enabled

class VmKernelNicInfoImpl(NicInfoImpl):
    def __init__(self):
        NicInfoImpl.__init__(self)
        self.GetVmKernelNics = self.getNics
        self.RemoveVmKernelNic = self.removeNic

    def AddVmKernelNic(self, pg, ipConf, mac, tsoMss, mtu):
        args = (pg, ipConf, mac, tsoMss, mtu)
        self.nics.append(VmKernelNic(*args))
        return self.nics[-1]
        
#
# End of network.py support
#

class Uuid:
    def __init__(self, uuidStr):
        self.uuidStr = uuidStr

class MemoryInfoImpl:
    def __init__(self):
        self.physicalMemory = VMKCTL_MEM_SIZE

    def GetPhysicalMemory(self):
        return self.physicalMemory

    def SetServiceConsoleReservedMem(self, cosMemSize, esxConfOnly):
        global VMKCTL_COS_MEM_SIZE
        VMKCTL_COS_MEM_SIZE = cosMemSize

    def GetServiceConsoleReservedMem(self):
        return VMKCTL_COS_MEM_SIZE

class SystemInfoImpl:
    COS_VMDK = ""
    
    def SetServiceConsoleVmdk(self, path):
        self.COS_VMDK = path

    def GetSystemUuid(self):
        return Uuid("47b51b25-7c15-28d3-7cd0-000c2935404a")

    def GetDateTime(self):
        class DateTime:
            def __init__(self):
                self.year = 2008
                self.month = 11
                self.day   = 11
                self.hour  = 11
                self.min   = 11
                self.sec   = 11
        return DateTime()

    def SetDateTime(self, dt):
        pass

class CpuInfo:
    HV_NOTPRESENT = 0
    HV_NOTSUPPORTED = 1
    HV_DISABLED = 2
    HV_ENABLED = 3

    def __init__(self, values):
        self.__dict__.update(values)

    def GetHVSupport(self):
        if not hasattr(self, 'HVSupport'):
            return self.HV_NOTPRESENT
        else:
            return self.HVSupport

def CpuInfoImpl():
    return CpuInfo(VMKCTL_CPU_CONFIG)

def reset():
    global VMKCTL_STORAGE_CONFIG, VMKCTL_ISCSI_CONFIG, VMKCTL_NET_CONFIG
    global VMKCTL_CPU_CONFIG, VMKCTL_MEM_SIZE
    
    VMKCTL_STORAGE_CONFIG = {}
    VMKCTL_ISCSI_CONFIG = {}
    VMKCTL_NET_CONFIG = {}
    VMKCTL_CPU_CONFIG = {}

    VMKCTL_MEM_SIZE = 20000
    VMKCTL_COS_MEM_SIZE = 272

    PortGroupImpl.allNames = []
    VirtualSwitchInfoImpl.rep = {}
    MacAddressGenerator.callCounter = 0
    DnsConfigImpl.hostname = ''
    DnsConfigImpl.domain = ''
    DnsConfigImpl.nameservers = []
    DnsConfigImpl.callCounter = 0
    RoutingInfoImpl.consDefaultGateway = Ipv4Address('0.0.0.0')
    RoutingInfoImpl.vmkDefaultGateway = Ipv4Address('0.0.0.0')
    SystemInfoImpl.COS_VMDK = ""
