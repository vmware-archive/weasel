
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

# display the welcome window
import gtk
import gobject
import exception
import userchoices
import users
from common_windows import MessageWindow
from common_windows import CommonWindow

from signalconnect import connectSignalHandlerByDict

class PasswordWindow:
    SCREEN_NAME = 'rootpassword'
    
    def __init__(self, controlState, xml):
        controlState.displayHeaderBar = True
        controlState.windowIcon = 'adminpassword.png'
        controlState.windowTitle = "Set Administrator Password"
        controlState.windowText = \
            "Enter the administrator (root) password for ESX"

        self.controlState = controlState
        self.xml = xml
        self.accounts = []

        self.passwdEntry1 = self.xml.get_widget("RootpasswordPassword1Entry")
        self.passwdEntry2 = self.xml.get_widget("RootpasswordPassword2Entry")

        self.view = self.xml.get_widget("AdduserTreeView")
        self.scrolled = self.xml.get_widget("AdduserScrolledWindow")
        self.removeButton = self.xml.get_widget("RemoveuserButton")

        self.addUserWindow = AddUserWindow(self.xml, self)

        setupUserAccountsView(self.view, self.scrolled)

        connectSignalHandlerByDict(self, PasswordWindow, self.xml,
          { ('AdduserButton', 'clicked'): 'addUser',
            ('RemoveuserButton', 'clicked'): 'removeUser',
          })

        self.restoreUsers()

        controlState.initialFocus = self.passwdEntry1


    def restoreUsers(self):
        '''Retrieve any previous users from userchoices and populate.'''

        for account in userchoices.getUsers():
            self.accounts.append((account['username'], account['password']))

        self.updateAccounts()


    def commitUsers(self):
        '''Save the user accounts in userchoices.'''

        userchoices.clearUsers()

        for username, password in self.accounts:
            userchoices.addUser(username, password,
                                userchoices.ROOTPASSWORD_TYPE_MD5)

    def setRemoveButton(self):
        if self.accounts and len(self.accounts) > 0:
            self.removeButton.set_sensitive(True)
        else:
            self.removeButton.set_sensitive(False)

    def addUser(self, *args):
        self.addUserWindow.show()

    def removeUser(self, widget, *args):
        store, selected = self.view.get_selection().get_selected_rows()

        if not selected:
            MessageWindow(None, 'User Account Error',
                'You must select an account to remove.')
            return

        window = MessageWindow(None, "Delete User Account",
            "Are you sure you want to remove this user account?",
            type='yesno')

        if window.affirmativeResponse:
            for entry in selected:
                # remove the entry at the storeIndex
                storeIndex = entry[0]
                self.accounts.pop(storeIndex)
                self.updateAccounts()

    def updateAccounts(self):
        _populateUserAccountsModel(self.view, self.scrolled, self.accounts)
        self.setRemoveButton()

    def getBack(self):
        self.commitUsers()

    def getNext(self):
        passwd1 = self.passwdEntry1.get_text()
        passwd2 = self.passwdEntry2.get_text()

        if passwd1 != passwd2:
            MessageWindow(self.controlState.gui.getWindow(),
                "Administrator Password Error",
                "The two passwords entered did not match.")
            raise exception.StayOnScreen

        try:
            users.sanityCheckPassword(passwd1)
        except ValueError, msg:
            MessageWindow(self.controlState.gui.getWindow(),
                "Administrator Password Error", msg[0])
            raise exception.StayOnScreen

        userchoices.setRootPassword(users.cryptPassword(passwd1),
                                    userchoices.ROOTPASSWORD_TYPE_MD5)

        self.commitUsers()

class AddUserWindow(CommonWindow):
    def __init__(self, xml, parent):
        CommonWindow.__init__(self)

        self.xml = xml
        self.parent = parent

        self.userName = self.xml.get_widget("AdduserNameEntry")
        self.passwdEntry1 = self.xml.get_widget("AdduserPassword1Entry")
        self.passwdEntry2 = self.xml.get_widget("AdduserPassword2Entry")

        self.dialog = self.xml.get_widget("adduser")

        connectSignalHandlerByDict(self, AddUserWindow, self.xml,
          { ('AdduserOkButton', 'clicked'): 'okClicked',
            ('AdduserCancelButton', 'clicked'): 'cancelClicked',
          })


        self.addFrameToWindow()

    def okClicked(self, *args):
        userName = self.userName.get_text()

        for account, passwd in self.parent.accounts:
            if account == userName:
                MessageWindow(None, "User Account Error",
                    "That account has already been added.")
                return

        try:
            users.sanityCheckUserAccount(userName)
        except ValueError, msg:
            MessageWindow(None, "User Account Error", msg[0])
            return

        passwd1 = self.passwdEntry1.get_text()
        passwd2 = self.passwdEntry2.get_text()

        if passwd1 != passwd2:
            MessageWindow(None, "Password Input Error",
                "The two passwords entered did not match.")
            return

        try:
            users.sanityCheckPassword(passwd1)
        except ValueError, msg:
            MessageWindow(None, "Password Input Error", msg[0])
            return

        self.parent.accounts.append((userName, passwd1))
        self.parent.updateAccounts()

        self.hide()

    def cancelClicked(self, *args):
        self.hide()

    def show(self):
        self.userName.set_text('')
        self.passwdEntry1.set_text('')
        self.passwdEntry2.set_text('')
        self.dialog.show_all()

    def hide(self):
        self.dialog.hide_all()

def setupUserAccountsView(view, scrolled):
    if not view.get_columns():
        model = gtk.TreeStore(gobject.TYPE_STRING)

        renderer = gtk.CellRendererText()
        column = gtk.TreeViewColumn("User Name", renderer, text=0)
        view.append_column(column)
        view.set_model(model)

    scrolled.show_all()

def _populateUserAccountsModel(view, scrolled, accounts):
    model = view.get_model()
    model.clear()

    for user, passwd in accounts:
        driverIter = model.append(None, [user])

    view.expand_all()
    scrolled.show_all()

