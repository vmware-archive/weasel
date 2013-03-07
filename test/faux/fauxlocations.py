#! /usr/bin/python

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
Faux Locations
Provides an interface to map locations (usually URLs) to file-like
objects or to callables that simulate some kind of error

Note, NFS remote locations can be faked by making a "partition" in
fauxconfig.py

Main API:
---------
get(loc, default)
add(loc, callable_)
remove(loc)
'''

import os
import re
import urllib2
import urlparse
import socket
import exceptions
from StringIO import StringIO

#------------------------------------------------------------------------------
def get(loc, default=None):
    '''For the given location, return a filelike object, if there is
    no matching location in _fauxLocations, return the default.

    This function can throw any number of exceptions or have various
    side effects, because it will call the callable associated with
    this loc.
    '''
    for regexp, value in _fauxLocations:
        match = re.match(regexp, loc)
        if match:
            return value(loc)
    return default

#------------------------------------------------------------------------------
def add(loc, callable_):
    _fauxLocations.append((loc, callable_))

#------------------------------------------------------------------------------
def remove(loc):
    matches = [x for x in _fauxLocations if x[0] == loc]
    if not matches:
        return
    assert len(matches) == 1
    _fauxLocations.remove(matches[0])


# ============================================================================
# Various functions to simulate server problems / other behaviour
# ============================================================================

def sleep():
    pass #TODO: when simulation slowness is added, turn this on.

def fauxrootOpen(loc):
    '''Hands off to open(), which is actually fauxroot.open()'''
    _protocol, _host, fullpath, _unused, _unused, _unused = \
       urlparse.urlparse(loc)
    return open(os.path.join('/mnt/source', fullpath.lstrip('/')))

def noNetworkConnection(loc):
    sleep()
    sockErr = socket.gaierror(-2, 'Name or service not known')
    raise urllib2.URLError(sockErr)

def returnEmptyFile(loc):
    return StringIO('')

def returnJunkFile(loc):
    return StringIO('this is not valid xml')

def returnValidXML(loc):
    return StringIO('<xml></xml>')

def httpLocThatRequiresAProxy(loc):
    import networking
    if networking.config._useProxy:
        return fauxrootOpen(loc)
    sleep()
    sockErr = socket.gaierror(110, 'Connection timed out')
    raise urllib2.URLError(sockErr)

def httpServerDoesNotExist(loc):
    raise urllib2.HTTPError(loc, 503, 'Service Unavailable', None, StringIO())

def ftpServerDoesNotExist(loc):
    sockErr = socket.gaierror(-5, 'No address associated with hostname')
    raise urllib2.URLError(sockErr)

def ftpLocThatRequiresAProxy(loc):
    import networking
    if networking.config._useProxy:
        return fauxrootOpen(loc)
    sleep()
    sockErr = socket.error(110, 'Connection timed out')
    raise exceptions.IOError('ftp error', sockErr)


# ============================================================================
# fauxLocations is a list of pairs.  The pairs are of the format:
# ( regular_expression, callable object )
#
# if you want the request to be successful, the second argument should
# be a callable that returns a file-like object.
# if you want the request to fail, the second argument should raise some
# exception when it is called.
#
# Note this explicitly IS NOT a dict, it is a list so order is preserved
_fauxLocations = [
    (r"http://server\.does\.not\.exist/+.*",
     httpServerDoesNotExist
    ),
    (r"ftp://server\.does\.not\.exist/+.*",
     ftpServerDoesNotExist
    ),
    (r"http://requires\.a\.proxy/+.*",
     httpLocThatRequiresAProxy
    ),
    (r"ftp://requires\.a\.proxy/+.*",
     ftpLocThatRequiresAProxy
    ),
    (r"ftp://bad\.mediaroot\.returns\.emptyfile/+packages.xml",
     returnEmptyFile
    ),
    (r".*://bad\.mediaroot\.returns\.junk/+packages.xml",
     returnJunkFile
    ),
]
