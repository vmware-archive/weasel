
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
import util
import time
import vmkctl
import userchoices
import partition
from log import log

def validateCHAPPassword(pwd):
    if not 12 <= len(pwd) <= 16:
        raise ValueError, "CHAP password must be 12-16 characters long."


def validateIQN(iqnStr):
    """
    Must start with "iqn" (all lower-case)
    Year-month after first '.'.
    Reversed domain name after that.
    Optional colon followed by anything the owner of the domain name likes,
        e.g. :storage.diskarrays-sn-a8675309

    For example: iqn.2004-12.com.vmware:storage.diskarrays-sn-a8675309

    IQN stands for "iSCSI Qualified Name".
    See http://tools.ietf.org/html/rfc3720

    Raises a ValueError if anything goes wrong.
    """
    if not iqnStr:
        iqnStr = ''
    iqnStr = iqnStr.strip()

    pieces = iqnStr.split('.')
    rDomain = '.'.join(pieces[2:]).split(':')[0]
    badRDomain = (('' in rDomain.split('.')) or
                  (' ' in rDomain))

    # TODO: Try doing this whole thing with a regex.
    implausibleDate = (  (len(pieces)<2)
                      or (not re.match(r'^[0-9]+\-[0-9]+$', pieces[1]))
                      or (int(pieces[1].split('-')[0]) < 1945)
                      or (not 0 < int(pieces[1].split('-')[1]) < 13) )
        # That ruled out years before 1945 and months outside 1-12.

    if( (len(pieces) < 4)  # Not enough room for a plausible domain name
        or implausibleDate
        or badRDomain
        or (pieces[0] != 'iqn')
      ):
        raise ValueError,  'The iqn "' + iqnStr + '" is invalid.'


class IscsiBootTable:
    """
    Reads VSI nodes.
    Populated by a vmkctlpy call.
    """
    def __init__(self,
      macAddress,     #vmkModules/vmkibft/iSCSIBootTable/Primary/Nic/mac_address
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
      initiatorAlias #vmkModules/vmkibft/iSCSIBootTable/Primary/iSCSI/Initiator/alias
    ):
        params = locals()
        del params['self']
        self.__dict__.update(params)
        if self.nicVlan == -1: # Convention for corresponding C++ interface
            self.nicVlan = None


def getNicMacAddresses():
    """
    Return a list of the MAC addresses of the NICs known to the iSCSI boot
    tables.  There'll be at most two elements in the list -- the MAC addresses
    from the primary and the secondary boot tables.
    """
    bt = getIscsiBootTable()
    return [bt.macAddress,]


def getIscsiBootTable():
    try:
        table = vmkctl.StorageInfoImpl().GetiScsiBootTables().GetPrimary()
        # There's no secondary boot table in the VSI nodes, for now.

        return IscsiBootTable(
                      macAddress = table.GetMacAddress(),
                      nicIP = table.GetNicIP(),
                      nicSubnetMask = table.GetNicSubnetMask(),
                      nicGateway = table.GetNicGateway(),
                      nicDhcp = table.GetNicDhcp(),
                      nicVlan = table.GetNicVlan(),
                      targetIP = table.GetTargetIP(),
                      targetPort = table.GetTargetPort(),
                      lun = table.GetLun(),
                      targetName = table.GetTargetName(),
                      chapName = table.GetChapName(),
                      chapPwd = table.GetChapPwd(),
                      initiatorName = table.GetInitiatorName(),
                      initiatorAlias = table.GetInitiatorAlias())
    except vmkctl.HostCtlException, ex:
        raise RuntimeError, "Caught vmkctl.HostCtlException reading IscsiBootTable: "\
            + str(ex.GetMessage())


class vmkNicAndNetworkRollerbacker:
    """
    Supports "Cancel" buttons on the iSCSI dialogs by storing "previous"
    versions of userchoices.__vmkNetwork and __vmkNics.
    """
    _prevVmkNetwork = {}
    _prevVmkNics = []

    @staticmethod
    def backup():
        vmkNicAndNetworkRollerbacker._prevVmkNetwork = \
            userchoices.getVmkNetwork().copy()
        vmkNicAndNetworkRollerbacker._prevVmkNics = \
            userchoices.getVmkNICs()[:]

    @staticmethod
    def rollback():
        try:
            userchoices.setVmkNetwork(gateway=
                vmkNicAndNetworkRollerbacker._prevVmkNetwork['gateway'])
        except KeyError:
            userchoices.setVmkNetwork(gateway='')
        userchoices.setVmkNICs(
            vmkNicAndNetworkRollerbacker._prevVmkNics)


def showLuns():
    for lun in vmkctl.StorageInfoImpl().GetDiskLuns():
        log.debug("  lun.GetName()=" + str(lun.GetName()))

VSWITCH_NAME = "iSCSI switch"
PORTGROUP_NAME = "iSCSI portgroup"

def tearDownVmkNic():
    vmknicInfo = vmkctl.VmKernelNicInfoImpl()
    for nic in vmknicInfo.GetVmKernelNics():
        vmknicInfo.RemoveVmKernelNic(nic.GetName())

    vswinfo = vmkctl.VirtualSwitchInfoImpl()
    for s in vswinfo.GetVirtualSwitches():
        if s.GetName() == VSWITCH_NAME:
            s.RemovePortGroup(PORTGROUP_NAME)
            vswinfo.RemoveVirtualSwitch(VSWITCH_NAME)


def activate(dhcp, ip, netmask, gateway, macAddressAsString):
    ''' Bring up the designated iSCSI (vmk) NIC and its virtual network.
    Run the iSCSI init script.

    Arg dhcp is a bool.
    '''
    log.debug("LUNs before activating iSCSI:")
    showLuns()

    try:
        tearDownVmkNic() # In case we've been here once already.
        log.debug("Ran tearDownVmkNic()")
    except vmkctl.HostCtlException, ex:
        log.debug("AddVmKernelNic(): " + str(ex.GetMessage()))
        raise

    macAddress = vmkctl.MacAddress(macAddressAsString)
    vmknicInfo = vmkctl.VmKernelNicInfoImpl()
    vswitch = vmkctl.VirtualSwitchInfoImpl().AddVirtualSwitch(VSWITCH_NAME)

    pg = vswitch.AddPortGroup(PORTGROUP_NAME)

    ipConfig = vmkctl.IpConfig()
    if dhcp:
        ipConfig.SetUseDhcp(True)
    else:
        ipConfig.SetUseDhcp(False)
        ipConfig.SetIpv4Address(vmkctl.Ipv4Address(ip))
        ipConfig.SetIpv4Netmask(vmkctl.Ipv4Address(netmask))

    newNic = None
    try:
        newNic = vmknicInfo.AddVmKernelNic(PORTGROUP_NAME, ipConfig,
                                           macAddress, 0, 0)
    except vmkctl.HostCtlException, ex:
        log.debug("AddVmKernelNic(): " + str(ex.GetMessage()))
        raise

    if not dhcp:
        try:
            vmkctl.RoutingInfoImpl().SetVmKernelDefaultGateway(
                vmkctl.Ipv4Address(gateway))
        except vmkctl.HostCtlException, ex:
            log.debug("SetVmKernelDefaultGateway(): " + str(ex.GetMessage()))
            raise

    for pnic in vmkctl.NetworkInfoImpl().GetPnics():
        if pnic.GetMacAddress().GetStringAddress() == \
        macAddress.GetStringAddress():
            try:
                vswitch.AddUplink(pnic.GetName())
            except vmkctl.HostCtlException, ex:
                log.debug("vswitch.addUplink("+pnic.GetName()+"): " + \
                          str(ex.GetMessage()))
                raise

    try:
        newNic.Enable()
    except vmkctl.HostCtlException, ex:
        log.debug("newNic.Enable(): " + str(ex.GetMessage()))
        raise

    ## Used to be in /etc/rc.d/init.d
    util.execCommand('/init.d/41.vmkiscsi')
    log.debug("Just ran /init.d/41.vmkiscsi")

    log.debug("Rescanning LUNs...")
    iScsiIFs = vmkctl.StorageInfoImpl().GetiScsiInterfaces()
    if len(iScsiIFs) < 1:
        raise SystemError, "No iSCSI interfaces found, or found but their option "\
                           "ROMs are misconfigured.  Cannot configure iSCSI."
        # This could happen if 1) the NIC doesn't support iSCSI or (2) the data
        # in the NIC's option ROM doesn't make sense (in a way that the sanity
        # checks in validateIQN() didn't catch).

    ## TODO: we should scan only on sofware iScsi interfaces, but for the time being
    ## ScsiInterfaceImpl::IsSoftwareiScsi() doesn't work and Prasanna doesn't
    ## know when he'll be able to take care of that.
    for intf in iScsiIFs:
        try:
            log.debug("HACK: sleeping before Rescan()")
            intf.Rescan()
            ## HACK!  Rescan() is async.  Need a better solution than a race
            ## condition.
            time.sleep(3)
        except vmkctl.HostCtlException, ex:
            log.debug("iScsiIFs[0].Rescan(): " + str(ex.GetMessage()))
            raise

    # Create /dev/nodes.  (This gets called again in partition.py.)
    log.debug("Creating device nodes...")
    partition.createDeviceNodes()

    log.debug("LUNs after activating iSCSI:")
    showLuns()
