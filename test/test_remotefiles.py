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
Unit tests for the remote_files module
'''
import os
import sys
from nose.tools import raises, with_setup


TEST_DIR = os.path.dirname(__file__)
DEFAULT_CONFIG_NAME = "good-config.1"

sys.path.append(os.path.join(TEST_DIR, os.path.pardir))
sys.path.insert(0, os.path.join(TEST_DIR, 'faux'))
# For pciidlib
sys.path.append(os.path.join(TEST_DIR, "../../../../apps/scripts/"))

import fauxroot

sys.path.append(os.path.join(TEST_DIR, DEFAULT_CONFIG_NAME))
import fauxconfig
sys.path.pop()

import remote_files
import urllib2
import socket
RemoteFileError = remote_files.RemoteFileError
HTTPError = urllib2.HTTPError
URLError = urllib2.URLError
gaierror = socket.gaierror

def setup_root():
    fauxroot.FAUXROOT = [os.path.join(TEST_DIR, DEFAULT_CONFIG_NAME)]

def teardown_root():
    fauxroot.FAUXROOT = []
    
def checkXML(localPath):
    import xml.dom.minidom
    from xml.parsers.expat import ExpatError
    try:
        xml.dom.minidom.parse(localPath)
    except ExpatError, ex:
        return False
    return True

@with_setup(setup_root, teardown_root)
def test_remoteOpen_negative():
    remoteOpen = remote_files.remoteOpen
    raises(RemoteFileError)(remoteOpen)('')
    raises(RemoteFileError)(remoteOpen)('unknown://foo.com/')
    raises(IOError)(remoteOpen)('http://')
    raises(IOError)(remoteOpen)('file:///does/not/exist')

@with_setup(setup_root, teardown_root)
def test_remoteOpen_negative_network():
    remoteOpen = remote_files.remoteOpen
    try:
        remoteOpen('http://server.does.not.exist/foo.xml')
    except Exception, ex:
        pass
    assert isinstance(ex, HTTPError)
    assert ex.code == 503

    try:
        remoteOpen('ftp://server.does.not.exist/foo.xml')
    except Exception, ex:
        pass
    assert isinstance(ex, URLError)
    assert isinstance(ex.args[0], gaierror)
    assert ex.args[0].args[0] == -5

@with_setup(setup_root, teardown_root)
def test_remoteOpen_positive():
    remoteOpen = remote_files.remoteOpen
    fp = remoteOpen('http://some.server/packages.xml')
    assert fp
    fp = remoteOpen('ftp://bad.mediaroot.returns.emptyfile/packages.xml')
    assert fp
    fp = remoteOpen('http://bad.mediaroot.returns.junk/packages.xml')
    assert fp

@with_setup(setup_root, teardown_root)
def test_downloadLocally_positive():
    fauxroot.resetLogs()

    downloadLocally = remote_files.downloadLocally
    loc = downloadLocally('http://bad.mediaroot.returns.junk/packages.xml')
    assert loc.endswith('/tmp/packages.xml')
    assert loc in fauxroot.WRITTEN_FILES
    os.remove(loc) #clean up

    raises(RemoteFileError)(downloadLocally)('http://bad.mediaroot.returns.junk/packages.xml', integrityChecker=checkXML)

@with_setup(setup_root, teardown_root)
def test_remoteOpen_proxy():
    fauxroot.resetLogs()
    remoteOpen = remote_files.remoteOpen

    raises(URLError)(remoteOpen)('http://requires.a.proxy/packages.xml')
    raises(IOError)(remoteOpen)('ftp://requires.a.proxy/packages.xml')

    import userchoices
    userchoices.setMediaProxy('proxy.vmware.com', '3128')

    fp = remoteOpen('http://requires.a.proxy/packages.xml')
    assert fp
    fp = remoteOpen('ftp://requires.a.proxy/packages.xml')
    assert fp

    userchoices.unsetMediaProxy()

    raises(URLError)(remoteOpen)('http://requires.a.proxy/packages.xml')
    raises(IOError)(remoteOpen)('ftp://requires.a.proxy/packages.xml')
