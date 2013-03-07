
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
import sys
import glob

TEST_DIR = os.path.dirname(__file__)

sys.path.append(os.path.join(TEST_DIR, os.path.pardir))
sys.path.append(os.path.join(TEST_DIR, os.path.pardir, "gui"))
sys.path.append(os.path.join(TEST_DIR, "../../../../apps/scripts/"))
import util

sys.path.insert(0, os.path.join(TEST_DIR, 'faux'))
import fauxroot

DEFAULT_CONFIG_NAME = "good-config.1"
sys.path.append(os.path.join(TEST_DIR, DEFAULT_CONFIG_NAME))
import fauxconfig
sys.path.pop()

import rpm
import vmkctl
import docage
import userchoices
import kiwi.ui.test.runner

singletons = []

class ResettableSingleton(object):
    def __new__(cls, *p, **kw):
        if not '_the_only_instance' in cls.__dict__ or \
                not cls._the_only_instance:
            cls._the_only_instance = object.__new__(cls)
            if not '_singleton_init' in cls.__dict__:
                msg = 'Class '+ str(cls) +\
                      ' does not have the special _singleton_init function'
                raise NotImplementedError(msg)
            cls._singleton_init(cls._the_only_instance, *p, **kw)
            global singletons
            singletons.append(cls)
        return cls._the_only_instance


def test_gui():
    # Executes the kiwi-based tests in the test/gui directory.

    import singleton
    singleton.Singleton = ResettableSingleton
    
    def playWrapper(filename):
        global singletons
        fauxroot.resetLogs()
        rpm.reset()
        vmkctl.reset()
        
        sys.path.append(os.path.join(TEST_DIR, DEFAULT_CONFIG_NAME))
        reload(fauxconfig)
        sys.path.pop()
        
        reload(userchoices)

        import customdrivers
        reload(customdrivers)
        
        import networking
        reload(networking.networking_base)

        import media
        reload(media)
        
        import gui
        reload(gui)

        import installlocation_gui
        reload(installlocation_gui)
        
        import timezone_gui
        reload(timezone_gui)
        
        import timedate_gui
        reload(timedate_gui)
        
        import datastore_gui
        reload(datastore_gui)
        
        import setupvmdk_gui
        reload(setupvmdk_gui)

        import network_address_widgets
        reload(network_address_widgets)
        
        # XXX sucks to have to reload to reset global state like this...
        for singletonClass in singletons:
            singletonClass._the_only_instance = None
        singletons = []

        oldDir = os.getcwd()
        try:
            os.chdir(os.path.join(TEST_DIR, os.pardir))
            kiwi.ui.test.runner.play_file(filename, None)
        except SystemExit, e:
            pass
        finally:
            os.chdir(oldDir)

        runner = kiwi.ui.test.runner.runner
        for exception, traceback in runner._caughtExceptions:
            raise exception, None, traceback
        
    testFiles = glob.glob(os.path.join(TEST_DIR, "gui", "*"))
    testFiles.sort()
    for testFile in testFiles:
        if testFile.endswith(".old"):
            # "test/replay-gui -p" saves previous version with a .old suffix,
            # don't bother running those.
            continue
        yield playWrapper, testFile
