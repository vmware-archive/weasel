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
debugging

This module is optionally imported in weasel.py.  It monkeypatches some stuff
and provides a hook for further monkeypatching
'''

import applychoices
from log import log

def init():
    import userchoices
    if userchoices.getRunMode() == userchoices.RUNMODE_GUI:
        NextButtonCausesLoadingOfCodeChanges()


def NextButtonCausesLoadingOfCodeChanges():
    import gui
    oldNextButtonPressed = gui.Gui.nextButtonPressed
    def patchedNextButtonPressed(self, *args, **kwargs):
        log.debug('reloading debugging module')
        import debugging
        reload(debugging)
        log.debug('loading install-time code changes')
        debugging.loadInstallTimeCodeChanges()
        oldNextButtonPressed(self, *args, **kwargs)
    gui.Gui.nextButtonPressed = patchedNextButtonPressed


@applychoices.ensureDriversAreLoaded
def livePatch(url):
    '''At this point weasel has started and the scripted install
    is parsing the .ks file.  It is making calls to livePatch
    with URLs destined for weasel.
    It will only replace modules in the local directory.
    '''
    from os import path
    from urlparse import urlparse
    import remote_files
    parsed = urlparse(url)
    remotePath = parsed[2]
    fileName = path.basename(remotePath)
    moduleName = path.splitext(fileName)[0]
    localPath = path.join(path.dirname(__file__), fileName)
    if not path.exists(localPath):
        log.error('Cannot install-patch a module that does not exist')
        return
    remoteFp = remote_files.remoteOpen(url)
    content = remoteFp.read()
    localFp = file(localPath, 'w')
    log.info('Replacing %s with new content' % localPath)
    localFp.write(content)
    localFp.close()
    log.info('Reloading module %s' % moduleName)
    module = __import__(moduleName, globals())
    reload(module)
    if hasattr(module, 'postPatchAction'):
        module.postPatchAction()


def loadInstallTimeCodeChanges(*args, **kwargs):
    '''Use this do do whatever you'd like under the install environment
    Usage:  At the welcome screen, drop into Ctrl-Alt-F2 and cd to
    /usr/lib/vmware/weasel.
    $ killall weasel
    $ killall Xorg
    Edit the getNext function in the screen *previous* to the screen
    you care about. In the getNext function, do the following:
    import debugging
    reload(debugging)
    debugging.loadInstallTimeCodeChanges()
    Then start up the installer again.
    $ weasel
    Step through the installer until you're about to press the Next
    button that will trigger the changed code.  Make a VM snapshot.
    Now you're in a position to dynamically change the code by
    changing this loadInstallTimeCodeChanges functions.  You can
    reload() other modules and monkeypatch their methods.
    '''
    pass

if __name__ == "__main__":
    print 'this is the debugging module'
