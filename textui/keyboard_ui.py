
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

'''Get keyboard selection.
'''

import os, os.path

from util import execCommand
from log import log
from systemsettings import SystemKeyboards
import userchoices
from textrunner import TextRunner, SubstepTransitionMenu as TransMenu

consoleKeymapDir = "/lib/kbd/keymaps/i386"
keymapSubdirs = ["azerty", "dvorak", "qwerty", "qwertz"]

askConfirmText = """\
Which keyboard model is attached to this computer?

Current choice:  %(name)s
"""

askConfirmHelpText = """\
To change keyboard model, type '2' (Change), and scroll through list
of choices.  Select the number of the keyboard model you want.
"""

helpText = """\
Select the number of the keyboard model you want.
"""

exceptTextKeyboardNotFound = """\
Warning:  selected keyboard name not found in standard list.
Current choice is not changed.
"""

SCROLL_LIMIT = 20

class KeyboardWindow(TextRunner):
    def __init__(self, fname=None):
        super(KeyboardWindow, self).__init__()
        if not fname:
            fname = os.path.join(
                os.path.dirname(__file__), os.path.pardir, "keyboard.xml")
        self.keyboards = SystemKeyboards()
        self.userinput = None
        self.uiTitle = 'Keyboard'
        self.mapParent = {}             # key: keytable, value: parent
        self.goodNames = []             # use a subset of keyboard.xml
        self.scrollNames = None
        try:
            self.keyboardNames = self.keyboards.getKeyboardNames()
        except Exception, msg:
            log.error(msg)
            log.error("keyboard list unavailable")
            self.keyboardNames = None

        # probe for existing keymaps
        for subdir in keymapSubdirs:
            mapdir = os.path.join(consoleKeymapDir, subdir)
            files = os.listdir(mapdir)
            maps = [name[:-7] for name in files if name.endswith('.map.gz')]
            for m in maps:
                self.mapParent[m] = subdir

        for name in self.keyboardNames:
            table = self.keyboards.keyboards[name].keytable
            if table in self.mapParent:
                self.goodNames.append(name)

        try:
            kbd = userchoices.getKeyboard()
            kbdname = kbd['name']  # if this fails, use default keyboard
        except:
            kbdname = self.keyboards.defaultKeyboard
            d = self.keyboards.getKeyboardSettingsByName(kbdname)
            userchoices.setKeyboard(d.keytable, d.name,
                                    d.model, d.layout, d.variant, d.options)

        self.scrollable = None

        self.start = self.askConfirm    # set start/restart point
        # self.substep = self.start

    def askConfirm(self):
        "ask if user really wants current keyboard choice"
        currentkbd = userchoices.getKeyboard()
        #currmsg = "Current keyboard choice: " + currentkbd['name'] + "\n"
        ui = {
            'title': self.uiTitle,
            'body': askConfirmText % currentkbd + \
                TransMenu.KeepChangeBackHelpExit,
            'menu': {
                '1': self.stepForward,
                '2': self.kbdlist,
                '<': self.stepBack,
                '?': self.askConfirmHelp,
            }
        }
        self.setSubstepEnv(ui)

    def askConfirmHelp(self):
        "show help text for confirmation screen"
        self.helpPushPop(self.uiTitle + ' (Help)',
            askConfirmHelpText + TransMenu.Back)

    def help(self):
        "show help text for scrolling display"
        self.helpPushPop(self.uiTitle + ' (Help)',
            helpText + TransMenu.Back)

    def kbdlist(self):
        "build displayable keyboard list"
        self.scrollNames = self.goodNames
        scrollable = []
        for iName, name in enumerate(self.scrollNames):
            scrollable.append("%3d. %s" % (iName+1, name)) # use 1-indexed
        self.setScrollEnv(scrollable, SCROLL_LIMIT)
        self.setSubstepEnv( {'next': self.scrollDisplay } )

    def scrollDisplay(self):
        "display keyboard choices"
        self.buildScrollDisplay(self.scrollable, self.uiTitle,
            self.update, "<number>: keyboard choice", allowStepRestart=True)

    def update(self):
        "check for numeric input for keyboard selection"
        try:
            selected = self.getScrollChoice()
        except (IndexError, ValueError), msg:
            body = '\n'.join(['Input error', msg[0], TransMenu.Back])
            self.errorPushPop(self.uiTitle +' (Update)', body)
            return

        # register the choice
        try:
            name = self.scrollNames[selected]
            # TODO: handle kbd.runtimeAction
            kbd = self.keyboards.getKeyboardSettingsByName(name)
            userchoices.setKeyboard(kbd.keytable, kbd.name,
                kbd.model, kbd.layout, kbd.variant, kbd.options)
        except AttributeError:   # should only occur if keyboard.xml gets lost
            self.errorPushPop(self.uiTitle +' (Update)',
                exceptTextKeyboardNotFound + TransMenu.Back)
            return

        # if we get this far, set the keyboard
        table = str(kbd.keytable)       # convert from unicode to str.
        path = os.path.join(consoleKeymapDir, self.mapParent[table],
                            "%s.map.gz" % table)
        # want str here, not unicode; otherwise fails in caged_weasel.
        execCommand('loadkeys %s' % path)

        # choice accepted
        self.setSubstepEnv( {'next': self.askConfirm } )

