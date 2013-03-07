
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

'''Migrates services in /etc/init.d and for xinetd.'''

import os
import re
import util

import handlers

from consts import HOST_ROOT
from log import log

class XinetdConf:
    '''Class used to process xinet.conf files.'''
    
    def __init__(self):
        self.directives = [
            (r'\s*service (.+)', self._handleService),
            (r'\s*include (.+)', self._handleInclude),
            (r'\s*includedir (.+)', self._handleIncludedir),
            (r'\s*\{', self._pushSection),
            ]

        self.keyFilter = [] # List of keys in a service config to save.
        self.sectionStack = []
        self.includedFiles = []
        self.includedDirs = []
        self.lastServiceName = None
        self.services = {}
        
    def _handleService(self, match):
        self.lastServiceName = match.group(1).strip()

    def _handleInclude(self, match):
        self.includedFiles.append(match.group(1).strip())

    def _handleIncludedir(self, match):
        self.includedDirs.append(match.group(1).strip())

    def _pushSection(self, _match):
        self.sectionStack.append(dict())

    def _popSection(self):
        assert self.sectionStack

        serviceId = self.sectionStack[-1].get('id', self.lastServiceName)
        if serviceId:
            self.services[serviceId] = self.sectionStack[-1]
        self.sectionStack.pop()
        self.lastServiceName = None
        
    def _handlePair(self, key, value):
        if not self.keyFilter or key in self.keyFilter:
            self.sectionStack[-1][key] = value
        
    def feedLine(self, line):
        line = line.lstrip()

        if not line or line.startswith("#"):
            return

        if self.sectionStack:
            if line.startswith("}"):
                self._popSection()
            else:
                pair = re.split(r'=|\+=|-=', line, 1)
                if len(pair) == 2:
                    self._handlePair(pair[0].strip(), pair[1].strip())
                else:
                    log.debug("skipped section body line -- %s" % line)
        else:
            match = None
            for regex, handler in self.directives:
                match = re.match(regex, line)
                if match:
                    handler(match)
                    break

            if not match:
                log.debug("unmatched xinetd.conf line -- %s" % line)

def migrateActionXinetdConf(oldPath, _newPath, accum):
    if not os.path.isfile(oldPath):
        log.info("skipping non-file -- %s" % oldPath)
        return

    if os.path.splitext(oldPath)[1] in \
            [".rpmnew", ".rpmsave", ".rpmorig", ".swp"]:
        log.info("skipping file with bad extension -- %s" % oldPath)
        return 

    log.info("updating services in %s" % oldPath)
    
    xc = XinetdConf()
    conf = open(oldPath)
    try:
        for line in conf:
            xc.feedLine(line)

        for directory in xc.includedDirs:
            globbed = os.path.join(directory, "*")
            handlers.MIGRATION_HANDLERS[globbed] = migrateActionXinetdConf
            accum.append(globbed)

        for filename in xc.includedFiles:
            handlers.MIGRATION_HANDLERS[filename] = migrateActionXinetdConf
            accum.append(filename)

        for serviceName, serviceSettings in xc.services.items():
            xinetPath = os.path.join(HOST_ROOT, "etc/xinetd.d", serviceName)
            if not os.path.exists(xinetPath):
                log.info("  skipping discontinued xinetd service -- %s\n" %
                         serviceName)
                continue
            
            disable = serviceSettings.get('disable', 'yes').lower()
            if disable in ('yes', '1', 'true'):
                onoff = 'off'
            else:
                onoff = 'on'
            args = [
                "/sbin/chkconfig",
                serviceName,
                onoff,
                ]
            rc = util.execWithLog(args[0], args, root=HOST_ROOT)
            # assert rc == 0 # TODO: handle errors
    finally:
        conf.close()
    
    return False

def migrateActionServices(oldPath, _newPath, accum):
    log.info("updating service level for %s" % oldPath)
    
    rcdir = os.path.basename(os.path.dirname(oldPath))
    rcMatch = re.match(r'rc(\d)\.d', rcdir)
    if not rcMatch:
        log.warn("unknown level -- %s" % oldPath)
        return False

    level = rcMatch.group(1)
    
    serviceMatch = re.match(r'([SK])\d\d(.+)', os.path.basename(oldPath))
    if not serviceMatch:
        log.warn("unknown service -- %s" % oldPath)
        return False

    if serviceMatch.group(1) == "S":
        onoff = "on"
    else:
        onoff = "off"

    name = serviceMatch.group(2)

    initPath = os.path.join(HOST_ROOT, "etc/init.d", name)

    isChkconfigService = False
    try:
        initFile = open(initPath)
        for line in initFile:
            if 'chkconfig' in line:
                isChkconfigService = True
                break
    except IOError, _e:
        log.info("  service discontinued -- %s" % name)
        return False

    if not isChkconfigService:
        log.info("  service is not supported by chkconfig -- %s" % name)
        return False
    
    args = [
        "/sbin/chkconfig",
        "--level", level,
        name,
        onoff
        ]
    rc = util.execWithLog(args[0], args, root=HOST_ROOT)
    # assert rc == 0 # TODO: handle errors

    return False
