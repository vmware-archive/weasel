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
networking/utils.py module

Utility functions for universal use.  Mainly for checking / manipulating
IP Addresses and hostnames.
"""

import re
import string
import urllib
import urlparse
from socket import INADDR_BROADCAST
from log import log

LOOPBACK_NET = 127
MULTICAST_NET = 224

def stringToOctets(ipString):
    '''Turn an IP Address-like string into a list of ints.
    "123.123.123.123" -> [123,123,123,123]
    '''
    octets = ipString.split(".")
    try:
        octets = [int(x) for x in octets]
    except ValueError:
        raise ValueError, "IP string has non-numeric characters"
    return octets

def sanityCheckHostname(hostname):
    '''Check to see if the input string is a valid hostname.
    Refer to RFC 1034, section 3.5 for the rules.
    Raise a ValueError if it is not.

    >>> sanityCheckHostname("foobar")
    >>> sanityCheckHostname("foobar.com")
    >>> sanityCheckHostname("123foobar.com") #will log a warning
    >>> sanityCheckHostname("-foobar.com")
    Traceback (most recent call last):
      . . .
    ValueError: Hostname labels must not start or end with a hyphen.
    >>> sanityCheckHostname("foo.-bar.com")
    Traceback (most recent call last):
      . . .
    ValueError: Hostname labels must not start or end with a hyphen.
    >>> sanityCheckHostname("foobar.com-")
    Traceback (most recent call last):
      . . .
    ValueError: Hostname labels must not start or end with a hyphen.
    >>> sanityCheckHostname("foobar..com")
    Traceback (most recent call last):
      . . .
    ValueError: Hostname labels must not be empty.
    >>> sanityCheckHostname("f*bar.com")
    Traceback (most recent call last):
      . . .
    ValueError: Hostname labels can only contain letters, digits and hyphens
    '''
    if len(hostname) < 1:
        raise ValueError("Hostname must be at least one character.")

    if len(hostname) > 255:
        raise ValueError("Hostname must be less than 256 characters.")
    
    for label in hostname.split('.'):
        if label == '':
            raise ValueError("Hostname labels must not be empty.")

        if len(label) > 63:
            raise ValueError("Hostname labels must be less than 64 characters.")

        if '-' in [label[0], label[-1]]:
            raise ValueError("Hostname labels must not "
                             "start or end with a hyphen.")

        if label[0] in string.digits:
            # hostnames starting with digits exist in the wild, so just warn
            log.warn('Hostname label (%s) starts with a digit.' % label)
    
        allowedLabelChars = string.ascii_letters + string.digits + "-"
        if label.strip(allowedLabelChars) != '':
            raise ValueError("Hostname labels can only contain letters, "
                             "digits and hyphens")

def sanityCheckIPString(ipString):
    '''Check to see if the input string is a valid IP address.
    Raise a ValueError if it is not.

    >>> sanityCheckIPString("10.20.30.40")
    >>> sanityCheckIPString("256.0.0.1")
    Traceback (most recent call last):
      . . .
    ValueError: IP string contains an invalid octet.
    >>> sanityCheckIPString("10.20.30.40.50")
    Traceback (most recent call last):
      . . .
    ValueError: IP string did not contain four octets.
    '''
    octets = stringToOctets(ipString)
    
    if len(octets) != 4:
        raise ValueError, "IP string did not contain four octets."
    
    if octets[0] < 1:
        raise ValueError, "IP string contains an invalid first octet."

    if octets[0] == LOOPBACK_NET:
        raise ValueError, "IP address cannot be in the loopback network."

    if octets[0] == MULTICAST_NET:
        raise ValueError, "IP address cannot be in the multicast network."
    
    for octet in octets:
        if not 0 <= octet <= 255:
            raise ValueError, "IP string contains an invalid octet."


def sanityCheckIPorHostname(ipOrHost):
    '''Check to see if the input string is a valid IP address or hostname.
    Raise a ValueError if it is not.

    >>> sanityCheckIPorHostname("10.20.30.40")
    >>> sanityCheckIPorHostname("test.com")
    '''
    if re.match(r'^\d+\.\d+\.\d+\.\d+$', ipOrHost):
        sanityCheckIPString(ipOrHost)
    else:
        sanityCheckHostname(ipOrHost)


def sanityCheckGatewayString(gwString):
    '''Check to see if the input string is a valid IP address that can
    be used as a gateway.
    Raise a ValueError if it is not.
    '''
    sanityCheckIPString(gwString)


def sanityCheckNetmaskString(nmString):
    '''Check to see if the input string is a valid netmask.
    Raise a ValueError if it is not.
    >>> sanityCheckNetmaskString('255.255.252.0')
    >>> sanityCheckNetmaskString('255.0.252.0')
    Traceback (most recent call last):
      . . .
    ValueError: Netmask is invalid.
    >>> sanityCheckNetmaskString('256.0.0.0')
    Traceback (most recent call last):
      . . .
    ValueError: Netmask string contains an invalid octet.
    '''
    octets = stringToOctets(nmString)
    
    if len(octets) != 4:
        raise ValueError, "Netmask does not contain four octets."
    
    if not octets[0]:
        raise ValueError, "First octet is zero."
    
    foundZero = False
    
    for octet in octets:
        if not 0 <= octet <= 255:
            raise ValueError, "Netmask string contains an invalid octet."
        for x in reversed(range(8)):
            if not octet >> x & 1:
                foundZero = True
            if octet >> x & 1 and foundZero:
                raise ValueError, "Netmask is invalid."


def sanityCheckIPandNetmask(ipString, nmString, addrDesc="IP"):
    '''Check to make sure the IP address is not the network address and is not
    the network broadcast address.

    >>> sanityCheckIPandNetmask('192.168.2.1', '255.255.255.255')
    >>> sanityCheckIPandNetmask('192.168.2.1', '255.255.255.0')
    >>> sanityCheckIPandNetmask('192.168.2.255', '255.255.255.0')
    Traceback (most recent call last):
      . . .
    ValueError: IP address corresponds to the broadcast address.
    >>> sanityCheckIPandNetmask('192.168.2.0', '255.255.255.0')
    Traceback (most recent call last):
      . . .
    ValueError: IP address corresponds to the network address.
    >>> sanityCheckIPandNetmask('192.168.2.255', '255.255.252.0')
    
    '''
    ip = ipStringToNumber(ipString)
    nm = ipStringToNumber(nmString)
    if nm == INADDR_BROADCAST:
        # There is only a single host in the "network", the remaining tests
        # don't apply.
        return
    # Is 'ip' the network address?
    if (ip & nm) == ip:
        raise ValueError("%s address corresponds to the network address." %
                         addrDesc)
    # Is 'ip' the (ones) broadcast address?
    if (ip & (~nm)) == (INADDR_BROADCAST & (~nm)):
        raise ValueError("%s address corresponds to the broadcast address." %
                         addrDesc)


def sanityCheckIPSettings(ipString, nmString, gwString):
    '''Check to make sure all of the given settings are sane.  The IP and
    gateway need to be valid wrt the netmask and they need to be in the same
    network.

    >>> sanityCheckIPSettings('192.168.2.2', '255.255.255.0', '192.168.2.1')
    >>> sanityCheckIPSettings('192.168.3.2', '255.255.255.0', '192.168.2.1')
    Traceback (most recent call last):
      . . .
    ValueError: IP and Gateway are not on the same network.

    '''
    ip = ipStringToNumber(ipString)
    nm = ipStringToNumber(nmString)
    gw = ipStringToNumber(gwString)
    sanityCheckIPandNetmask(ipString, nmString)
    sanityCheckIPandNetmask(gwString, nmString, "Gateway")
    # Do they lie on the same network?
    if (ip & nm) != (gw & nm):
        raise ValueError, "IP and Gateway are not on the same network."


def sanityCheckVlanID(vlanID):
    '''Check to see if the input string is a valid VLAN ID.
       Raise a ValueError if it is not.
    '''
    try:
        int(vlanID)
    except ValueError:
        raise ValueError, "Vlan ID must be a number from 0 to 4095."

    if not 0 <= int(vlanID) <= 4095:
        raise ValueError, "Vlan ID must be a number from 0 to 4095."


def sanityCheckMultipleIPsString(multipleIPString):
    '''Check to see if the input string contains two or more valid IP addreses.
       Raise a ValueError if it is not.
    '''
    ips = re.split(',', multipleIPString)
    for ip in ips:
        sanityCheckIPString(ip)


def sanityCheckPortNumber(portNum):
    '''Check to see if the input string is a valid port number.
       Raise a ValueError if it is not.
    '''
    # NB - this can be 49151 or 65535.  49152-65535 are unassigned but it is
    #      possible to use them

    highestPort = 65535 
    try:
        int(portNum)
    except ValueError:
        raise ValueError, "Port number must be a number from 1 to %d." % \
            highestPort

    if not 1 <= int(portNum) <= highestPort:
        raise ValueError, "Port number must be a number from 1 to %d." % \
            highestPort
    

def sanityCheckUrl(url, expectedProtocols=None):
    '''Try to determine whether a given url string is valid or not.
       expectedProtocols is a list.  Generally ['http','https'] or ['ftp'].
    '''
    protocol, username, password, host, port, path = parseFileResourceURL(url)

    if not protocol or not host:
        raise ValueError, "The specified URL is malformed."

    if port:
        sanityCheckPortNumber(port)

    if expectedProtocols and protocol not in expectedProtocols:
        raise ValueError, "Expected a url of type %s but got '%s'." % \
            (expectedProtocols, protocol)

    sanityCheckIPorHostname(host)


def parseFileResourceURL(url):
    '''Parse out all of the relevant fields that identify a file resource,
    it returns all information about params, queries, and anchors as part of
    the "path".
    
    url -> protocol, username, password, host, port, path
    >>> parseFileResourceURL('http://1.2.3.4')
    ('http', '', '', '1.2.3.4', '', '')
    >>> parseFileResourceURL('http://user:pass@1.2.3.4:80/foo')
    ('http', 'user', 'pass', '1.2.3.4', '80', '/foo')
    >>> parseFileResourceURL('http://example.com/foo/bar?a=1&b=2#anchor')
    ('http', '', '', 'example.com', '', '/foo/bar?a=1&b=2#anchor')
    >>> input = 'http://u:p@example.com:80/fo%20o.txt'
    >>> output = parseFileResourceURL(input)
    >>> input == unparseFileResourceURL(*output)
    True
    '''
    parseResult = urlparse.urlparse(url)
    protocol, netloc, path, params, query, fragment = parseResult
    path = urlparse.urlunparse(('','',path, params, query, fragment))
    username = ''
    password = ''
    if '@' in netloc:
        userpass, hostport = netloc.split('@', 1)
        if ':' in userpass:
            username, password = userpass.split(':', 1)
        else:
            username = userpass
    else:
        hostport = netloc
    if ':' in hostport:
        host, port = hostport.rsplit(':', 1)
    else:
        host = hostport
        port = ''

    username = urllib.unquote(username)
    password = urllib.unquote(password)
    path = urllib.unquote(path)
    return protocol, username, password, host, port, path

    
def unparseFileResourceURL(protocol, username, password, host, port, path):
    '''
    >>> unparseFileResourceURL('http', '', '', '1.2.3.4', '', '')
    'http://1.2.3.4/'
    >>> unparseFileResourceURL('http', 'user', 'pass', '1.2.3.4', '80', '/foo')
    'http://user:pass@1.2.3.4:80/foo'
    '''
    username = urllib.quote(username, '')
    password = urllib.quote(password, '')
    path = urllib.quote(path)
    if not path.startswith('/'):
        path = '/' + path
    if port:
        hostport = host +':'+ port
    else:
        hostport = host
    if password:
        userpass = username +':'+ password
    else:
        userpass = username
    if userpass:
        netloc = userpass +'@'+ hostport
    else:
        netloc = hostport
    return protocol +'://'+ netloc + path


def cookPasswordInFileResourceURL(url):
    '''Parse url to find password, and if it exists, make it opaque.

    >>> cookPasswordInFileResourceURL('http://user:pass@1.2.3.4:80/foo')
    'http://user:XXXXXXXX@1.2.3.4:80/foo'
    >>> cookPasswordInFileResourceURL('http://1.2.3.4/foo/bar')
    'http://1.2.3.4/foo/bar'
    '''
    protocol, username, password, host, port, path = parseFileResourceURL(url)
    if password:
        password = 'XXXXXXXX'
    newurl = unparseFileResourceURL(protocol, username, password, host, port, path)
    return newurl


def formatIPString(ipString):
    '''Get rid of any preceding zeroes'''
    octets = map(lambda x: "%s" % (int(x)), ipString.split('.'))
    
    if len(octets) == 4:
        return string.join(octets, '.')
    else:
        return ""


def calculateNetmask(ipString):
    '''return a netmask string (a guess of what the netmask would be)
    for the given IP address string.
    '''
    sanityCheckIPString(ipString)
    octets = stringToOctets(ipString)
    
    if octets[0] < 128:
        netmask = "255.0.0.0"
    elif octets[0] < 192:
        netmask = "255.255.0.0"
    else:
        netmask = "255.255.255.0"
    return netmask


def ipStringToNumber(ipString):
    '''Get a numerical value from an IP address-like string
    Arguments:
    ipString - is a string in dotted-quad format.  It does not have to be
               a valid IP Address.  eg, it can also be a netmask string
    '''
    octets = stringToOctets(ipString)

    if len(octets) != 4:
        raise ValueError, 'IP string is invalid.'
    
    multipliers = (24, 16, 8, 0)
    ipNumber = 0
    for i, octet in enumerate(octets):
        ipNumber += octet << multipliers[i]
    return ipNumber


def ipNumberToString(ipNumber):
    '''Get an IP address-like string from a numerical value.
    '''
    ipString = "%d.%d.%d.%d" % (
        (ipNumber >> 24) & 0x000000ff,
        (ipNumber >> 16) & 0x000000ff,
        (ipNumber >> 8) & 0x000000ff,
        ipNumber & 0x000000ff)
    return ipString


def calculateGateway(ipString, netmaskString):
    '''return a gateway string (a guess of what the gateway would be)
    for the given IP address and netmask strings.
    '''
    ipNumber = ipStringToNumber(ipString)
    netmaskNumber = ipStringToNumber(netmaskString)
    
    netaddress = ipNumber & netmaskNumber
    broadcast = netaddress | ~netmaskNumber
    
    return ipNumberToString(broadcast - 1)


def calculateNameserver(ipString, netmaskString):
    '''return a nameserver IP address string (a guess of what the 
    nameserver IP might be) for the given IP address and netmask strings.
    '''
    ipNumber = ipStringToNumber(ipString)
    netmaskNumber = ipStringToNumber(netmaskString)
    
    netaddress = ipNumber & netmaskNumber
    return ipNumberToString(netaddress + 1)
