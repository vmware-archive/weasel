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
networking.host_config module

The sole interface to this module is the `config` identifier.

Note, the proxy settings will be for every protocol that urllib2
serves.  That means HTTP and FTP.

>>> from networking import host_config
>>> host_config.config.hostname
''
>>> host_config.config.hostname = 'localhost'
>>> host_config.config.hostname
'localhost'
>>> host_config.config.gateway
'0.0.0.0'
>>> host_config.config.vmkernelGateway
'0.0.0.0'
>>> host_config.config.nameservers
<NameServerCollection []>
>>> host_config.config.nameservers.append('123.123.123.1')
>>> host_config.config.nameservers. += ['123.123.123.2', '123.123.123.3']
>>> host_config.config.nameservers
<NameServerCollection ['123.123.123.1', '123.123.123.2', '123.123.123.3']>
>>> host_config.setupProxy('proxy.example.com', 3128)
>>> host_config.useProxy = True
'''

import vmkctl
import urllib2
from log import log
from networking_base import wrapHostCtlExceptions


#------------------------------------------------------------------------------
_dnsConfigImpl = None
def _getDnsConfigImpl():
    '''The constructor vmkctl.DnsConfigImpl() has side effects, even
    though it is a singleton.  Thus we have to be extra careful.
    '''
    global _dnsConfigImpl
    if _dnsConfigImpl == None:
        _dnsConfigImpl = vmkctl.DnsConfigImpl()
    return _dnsConfigImpl


#------------------------------------------------------------------------------
class NameServerCollection(object):
    ''' An iterable and somewhat list-like collection of name servers
    Using instances of NameServerCollection will affect vmkctl.DnsConfig
    Note: One can not address a name server by index.  Indexes
    are not presumed to be the same between calls to dnsConfig.GetNameServers()
    '''
    @wrapHostCtlExceptions
    def _getNameServers(self):
        dnsConfig = _getDnsConfigImpl()
        return [ns.GetStringAddress() for ns in dnsConfig.GetNameServers()]

    def __contains__(self, item):
        return item in self._getNameServers()

    def __eq__(self, foreignList):
        return set(self._getNameServers()) == set(foreignList)

    def __ne__(self, foreignList):
        return not self.__eq__(foreignList)

    def __iadd__(self, foreignList):
        self.extend(foreignList)
        return self

    def __iter__(self):
        return iter(self._getNameServers())

    def __len__(self):
        return len(self._getNameServers())

    def __str__(self):
        return str(self._getNameServers())

    def __repr__(self):
        return '<NameServerCollection %s>' % repr(self._getNameServers())

    @wrapHostCtlExceptions
    def _save(self):
        dnsConfig = _getDnsConfigImpl()
        dnsConfig.SaveConfig()
        self.refresh()

    @wrapHostCtlExceptions
    def append(self, ipAddress, deferSaving=False):
        '''Works like list.append.
        Optionally use deferSaving when doing "batches"
        '''
        # TODO: I am trusting here that ipAddress has been previously 
        #       sanity-checked perhaps I should be less trusting
        if ipAddress in self:
            return #don't add duplicate name servers
        log.info('Adding nameserver %s' % ipAddress)
        dnsConfig = _getDnsConfigImpl()
        dnsConfig.AddNameServer(vmkctl.Ipv4Address(ipAddress))
        if not deferSaving:
            self._save()

    @wrapHostCtlExceptions
    def extend(self, iterable):
        '''Works like list.extend'''
        # TODO: I am trusting here that it has been previously sanity-checked
        #       perhaps I should be less trusting
        for ipAddress in iterable:
            self.append(ipAddress, deferSaving=True)
        self._save()

    @wrapHostCtlExceptions
    def remove(self, ipAddress):
        dnsConfig = _getDnsConfigImpl()
        if ipAddress not in self:
            return ValueError('NameServerCollection.remove(x): x not present')
        log.info('Removing nameserver %s' % ipAddress)
        dnsConfig.RemoveNameServer(vmkctl.Ipv4Address(ipAddress))
        self._save()

    @wrapHostCtlExceptions
    def refresh(self):
        '''Allows the current process to pick up any changes that have been
        made to the DNS configuration files.
        '''
        dnsConfig = _getDnsConfigImpl()
        # Refresh() calls res_init() to reset the DNS resolver for this process
        dnsConfig.Refresh()

            

class HostConfig(object):
    '''Simple container for conveniently and log-iffically getting/setting
    these attributes:
    * hostname
    * nameservers
    * gateway
    * vmkernelGateway
    '''
    DEFAULT_GATEWAY = '0.0.0.0'

    def __init__(self):
        self.nameservers = NameServerCollection()
        self._useProxy = False
        # null handler turns proxy off
        self._noProxyHandler = urllib2.ProxyHandler({})
        self._proxyHandler = None
        self._desiredGateway = None
        self._vmkctlKnowsDesiredGateway = True

    def _verifyHostnameSaved(self, hostname):
        '''Weasel is reliant on vmkctl to do the right thing.  Sometimes
        vmkctl is finicky and doesn't do what we expect, like not writing
        the hostname to the conf files.  We want to know about those errors
        earlier rather than later.  So check that files get written properly.
        '''
        # This function is not critical, so if it borks, don't take
        # Weasel down with it.
        try:
            fp = open('/etc/hosts', 'r')
            etcHostsContent = fp.read()
            fp.close()
            fp = open('/etc/sysconfig/network', 'r')
            etcSysconfigNetworkContent = fp.read()
            fp.close()
            if hostname not in etcHostsContent:
                log.error('Hostname (%s) did not get saved in /etc/hosts'
                          % hostname)
            if hostname not in etcSysconfigNetworkContent:
                log.error('Hostname (%s) did not get saved in'
                          ' /etc/sysconfig/network' % hostname)
            dnsConfig = _getDnsConfigImpl()
            vHostname = dnsConfig.GetHostname()
            if hostname != vHostname:
                log.error('Hostname (%s) did not get saved in'
                          ' DnsConfigImpl (%s)' % (hostname, vHostname))
        except Exception, ex:
            log.error('Exception while verifying the saving of the hostname'
                      ' (%s). Exception: %s' % (hostname, str(ex)))

    @wrapHostCtlExceptions
    def _getHostname(self):
        dnsConfig = _getDnsConfigImpl()
        return dnsConfig.GetHostname()

    @wrapHostCtlExceptions
    def _setHostname(self, newFQDN):
        # TODO: I am trusting here that it has been previously sanity-checked
        #       perhaps I should be less trusting
        dnsConfig = _getDnsConfigImpl()
        oldHostname = dnsConfig.GetHostname()
        if oldHostname and oldHostname != newFQDN:
            log.info('Changing hostname from %s to %s'
                     % (oldHostname, newFQDN))
        else:
            log.info('Setting hostname to %s' % newFQDN)
        headAndTail = newFQDN.split('.', 1)
        dnsConfig.SetHostname(headAndTail[0])
        if len(headAndTail) > 1:
            domain = headAndTail[1]
            dnsConfig.SetDomain(domain)
            if domain != 'localdomain':
                dnsConfig.SetSearchDomainsString(domain)
        else:
            dnsConfig.SetDomain('')
            dnsConfig.SetSearchDomainsString('')
        dnsConfig.SaveConfig()
        self._verifyHostnameSaved(headAndTail[0])
    hostname = property(_getHostname, _setHostname)

    def _verifyConsoleGatewaySaved(self, gateway):
        '''Weasel is reliant on vmkctl to do the right thing.  Sometimes
        vmkctl is finicky and doesn't do what we expect, like not writing
        the gateway to the conf files.  Furthermore, it may not complain.
        We want to know about those errors earlier rather than later,
        so check that files get written properly.
        '''
        # This function is not critical, so if it borks, don't take
        # Weasel down with it.
        try:
            fp = open('/etc/sysconfig/network', 'r')
            etcSysconfigNetworkContent = fp.read()
            fp.close()
            if ('GATEWAY=%s' % gateway) not in etcSysconfigNetworkContent:
                log.error('Gateway (%s) did not get saved in'
                          ' /etc/sysconfig/network' % gateway)
            if self._vmkctlKnowsDesiredGateway:
                rInfo = vmkctl.RoutingInfoImpl()
                vGateway = rInfo.GetConsoleDefaultGateway().GetStringAddress()
                if gateway != vGateway:
                    log.error('Gateway (%s) did not get saved in'
                              ' RoutingInfoImpl (%s)' % (gateway, vGateway))

        except Exception, ex:
            log.error('Exception while verifying the saving of the gateway'
                      ' (%s). Exception: %s' % (gateway, str(ex)))

    @wrapHostCtlExceptions
    def _getConsoleGateway(self):
        if self._vmkctlKnowsDesiredGateway:
            routeInfo = vmkctl.RoutingInfoImpl()
            return routeInfo.GetConsoleDefaultGateway().GetStringAddress()
        else:
            return self._desiredGateway

    @wrapHostCtlExceptions
    def _setConsoleGateway(self, newGateway,
                           vswifName='vswif0', setConfFileOnly=True):
        '''Set the default network gateway for the Console OS.
        Arguments:
         vswifName: name of the vswif. ie, 'vswif0'.  If the named vswif
         hasn't actually been created, ie, there's no vNic with that name,
         then setConfFileOnly should be set to True.  Using an empty string
         results in no GATEWAYDEV being set in /etc/sysconfig/network

         setConfFileOnly: setting to False will result in vmkctl
         trying to bring up the new gateway, which results in a call
         to `/sbin/ip route replace ...`
        '''
        # TODO: I am trusting here that it has been previously sanity-checked
        #       perhaps I should be less trusting
        routeInfo = vmkctl.RoutingInfoImpl()

        oldGateway = self._getConsoleGateway()
        if oldGateway and oldGateway not in [self.DEFAULT_GATEWAY, newGateway]:
            log.info('Changing gateway from %s to %s'
                     % (oldGateway, newGateway))
        else:
            log.info('Setting gateway to %s' % newGateway)

        self._desiredGateway = newGateway
        if setConfFileOnly:
            self._vmkctlKnowsDesiredGateway = False
        vmkctlGateway = vmkctl.Ipv4Address(newGateway)
        routeInfo.SetConsoleDefaultGateway(vmkctlGateway,
                                           vswifName,
                                           setConfFileOnly)
        self._verifyConsoleGatewaySaved(newGateway)
    gateway = property(_getConsoleGateway, _setConsoleGateway)

    @wrapHostCtlExceptions
    def _getVmkernelGateway(self):
        routeInfo = vmkctl.RoutingInfoImpl()
        return routeInfo.GetVmKernelDefaultGateway().GetStringAddress()

    @wrapHostCtlExceptions
    def _setVmkernelGateway(self, newGateway):
        # TODO: I am trusting here that it has been previously sanity-checked
        #       perhaps I should be less trusting
        routeInfo = vmkctl.RoutingInfoImpl()

        oldGateway = self._getVmkernelGateway()
        if oldGateway and oldGateway not in [self.DEFAULT_GATEWAY, newGateway]:
            log.info('Changing vmkernel gateway from %s to %s'
                     % (oldGateway, newGateway))
        else:
            log.info('Setting vmkernel gateway to %s' % newGateway)

        vmkctlGateway = vmkctl.Ipv4Address(newGateway)
        routeInfo.SetVmKernelDefaultGateway(vmkctlGateway)
    vmkernelGateway = property(_getConsoleGateway, _setConsoleGateway)

    def setupProxy(self, host, port, username=None, password=None):
        if password:
            passwordString = ':'+ password
        else:
            passwordString = ''
        if username:
            userpassString = username + passwordString + '@'
        else:
            userpassString = ''
        url = 'http://%s%s:%s' % (userpassString, host, str(port))
        # NOTE: this will not work with HTTPS
        self._proxyHandler = urllib2.ProxyHandler({'http': url, 'ftp': url})

    def _getUseProxy(self):
        return self._useProxy
    def _setUseProxy(self, val):
        if not val:
            if self._useProxy:
                log.debug('Turning off installer proxy server support')
                opener = urllib2.build_opener(self._noProxyHandler)
                urllib2.install_opener(opener)
                self._useProxy = False
            # elif self._useProxy was already False, just return
            return

        if not self._proxyHandler:
            raise ValueError('Can not turn on proxy before it has been set up')
        log.debug('Turning on installer proxy server support')
        opener = urllib2.build_opener(self._proxyHandler)
        urllib2.install_opener(opener)
        self._useProxy = True
        
    useProxy = property(_getUseProxy, _setUseProxy)

    def activateGatewayRouting(self, vswifName='vswif0'):
        self._setConsoleGateway(self.gateway, vswifName, setConfFileOnly=False)


# create an instance for use as part of the API for the networking package
config = HostConfig()
