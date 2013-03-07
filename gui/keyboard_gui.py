
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

# display the keyboard window
import gobject
import gtk
import userchoices
from common_windows import MessageWindow

from log import *

import systemsettings
import exception

class KeyboardWindow:
    SCREEN_NAME = 'keyboard'

    def __init__(self, controlState, xml):
        controlState.displayHeaderBar = True
        controlState.windowIcon = 'keyboard.png'
        controlState.windowTitle = "Select Keyboard"
        controlState.windowText = "Select the type of keyboard for this system"

        self.ics = controlState.gui
        self.keyboards = systemsettings.SystemKeyboards()
        self.setupKeyboardSelection(xml)

    def setupKeyboardSelection(self, xml):
        self.view = xml.get_widget("KeyboardTreeView")
        scrolled = xml.get_widget("KeyboardScrolledWindow")

        if not self.view.get_model():
            model = gtk.TreeStore(gobject.TYPE_STRING, gobject.TYPE_PYOBJECT)

            keyboards = self.keyboards.getKeyboardNames()

            for keyboard in keyboards:
                log.debug("keyboard = %s" % (keyboard))
                kbd = self.keyboards.getKeyboardSettingsByName(keyboard)

                iter = model.insert_before(None, None)
                model.set_value(iter, 0, keyboard)
                model.set_value(iter, 1, kbd)

            renderer = gtk.CellRendererText()

            column = gtk.TreeViewColumn("Keyboard", renderer, text=0)
            self.view.append_column(column)

            self.view.set_model(model)
            selectedPath = keyboards.index(self.keyboards.getDefaultKeyboard())
            self.view.set_cursor(selectedPath)
            self.view.scroll_to_cell(selectedPath)

        scrolled.show_all()

    def getNext(self):
        (model, iter) = self.view.get_selection().get_selected() 
        if not iter:
            MessageWindow(None, "Invalid Keyboard",
                "You must select a keyboard to install ESX.")
            raise exception.StayOnScreen

        kbd = model.get(iter, 1)[0]
        try:
            kbd.runtimeAction()
            log.debug("Keyboard selected = %s" % (kbd.getName()))

            userchoices.setKeyboard(kbd.getKeytable(),
                                kbd.getName(),
                                kbd.getModel(),
                                kbd.getLayout(),
                                kbd.getVariant(),
                                kbd.getOptions())

        except RuntimeError, ex:
            MessageWindow(self.ics.getWindow(),
                "Keymap Error", "Couldn't load keymap \"%s\"."
                "\n\nUsing the keymap already loaded." %
                (kbd.getName(),), type="warning")


