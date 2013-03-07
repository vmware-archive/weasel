
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
skip_to_step.py
------
To test a screen in the GUI, just run `python skip_to_step.py stepName`.
Where stepName is the install step as defined in gui.py
'''


import sys
import os
import getopt
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
import gtk
import gui
import textui.main


# Some screens need to have userchoices prepared or else they will throw
# all sorts of crazy razzmatazz.
#
# put any preparation in a function named prepare_STEPNAME and magic will
# take care of you.

def prepare_media():
    import userchoices
    userchoices.setShowInstallMethod(True)

def prepare_bootloader():
    gui.installSteps.insert(gui.installSteps.index('timezone'), 'bootloader')

def prepare_cosnetwork():
    import userchoices
    import networking
    device = networking.getPhysicalNics()[0]
    userchoices.addCosNIC(device, 0, None, None)
    
def prepare_timedate():
    prepare_cosnetwork() #for NTP

def DebugCheatingOn(step):
        stepIndex = gui.installSteps.index(step)
        gui.installSteps = gui.installSteps[stepIndex:]
        # Gui.__init__ will try to remove the 'media' screen, so insert it
        if 'media' not in gui.installSteps:
            gui.installSteps.insert(0, 'media')

        def monkeyCancel(self, *args):
            if hasattr(self.currentWindow, "getCancel"):
                self.currentWindow.getCancel()
            gtk.main_quit()
        #monkey-patch alert!
        gui.Gui.cancelButtonPressed = monkeyCancel


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print 'You need to provide a step to jump to'
        print 'Usage: python2.4 skip_to_step.py [-t] <stepname>'
        sys.exit(1)

    mode = "gui"
    (opts, args) = getopt.getopt(sys.argv[1:], "t", [])
    for opt, arg in opts:
        if opt == "-t":
            mode = "text"

    step = args[0]
    fnName = 'prepare_'+ step
    if fnName in globals():
        globals()[fnName]()

    if mode == "gui":
        DebugCheatingOn(step)
        gui.Gui()
    elif mode == "text":
        textui.main.main(["main.py", step])
