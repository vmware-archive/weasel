
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
gui.py
------
This is the root module for all the GUI code.  It creates the gui window
and loads the Glade XML for all the steps in the installer.
'''


import exception
import sys
import os
import dispatch
import gtk
import gtk.glade
import gobject

import media
import userchoices
from log import *
from consts import ExitCodes

#TODO: someday fix the name collision and make gui/ a proper package
sys.path.append(os.path.join(os.path.dirname(__file__), 'gui'))
from common_windows import MessageWindow
from common_windows import ExceptionWindow
from common_windows import MountMediaDelegate

import welcome_gui
import eula_gui
import keyboard_gui
import customdrivers_gui
import driverload_gui
import cosnetworkadapter_gui
import cosnetwork_gui
import installmedia_gui
import httpmedia_gui
import ftpmedia_gui
import nfsmedia_gui
import usbmedia_gui
import timezone_gui
import timedate_gui
import setupchoice_gui
import installlocation_gui
import esxlocation_gui
import datastore_gui
import setupvmdk_gui
import password_gui
import review_gui
import iscsisetup_gui
import iscsinetwork_gui
import installation_gui
import bootloader_gui
import license_gui
import finished_gui

installSteps = [
    'welcome',
    'eula',
    'keyboard',
    'customdrivers',
    'driverload',
    'license',
    'cosnetworkadapter',
    'cosnetwork',
    'media',
    'setupchoice',
    'installlocation',
    'timezone',
    'timedate',
    'password',
    'review',
    'installation',
    'finished',
]

media.MOUNT_MEDIA_DELEGATE = MountMediaDelegate()

class StepState:
    def __init__(self, screenClass):
        self.screenClass = screenClass
        self.screenName = screenClass.SCREEN_NAME
        self.screenPath = os.path.join(
            os.path.dirname(__file__), "gui/glade/%s.glade" % self.screenName)
        self.screenXml = gtk.glade.XML(self.screenPath)

        frameWindow = self.screenXml.get_widget(self.screenName)
        # de-parent the widget from its parent window
        child = frameWindow.get_children()[0]
        frameWindow.remove(child)
        
        # save the child to be used elsewhere
        self.screenWindow = child

    def createWindow(self, ics):
        return self.screenClass(ics, self.screenXml)

class InstallControlState:
    def __init__(self, gui):
        # save so we can refresh if necessary
        self.gui = gui

        self.initialFocus = None
        self.displayBanner = True
        self.displayHeaderBar = False
        self.windowIcon = None
        self.windowTitle = None
        self.windowText = None
        self.nextButtonEnabled = True
        self.backButtonEnabled = True
        self.cancelButtonEnabled = True
        self.cancelButtonShow = True
        self.finishButtonShow = False

    def getDisplayBanner(self):
        return self.displayBanner

    def setDisplayBanner(self, arg):
        self.displayBanner = arg

    def getDisplayHeaderBar(self):
        return self.displayHeaderBar

    def setDisplayHeaderBar(self, arg):
        self.displayHeaderBar = arg

    def getWindowIcon(self):
        return self.windowIcon

    def setWindowIcon(self, arg):
        self.windowIcon = arg

    def getWindowTitle(self):
        return self.windowTitle

    def setWindowTitle(self, arg):
        self.windowTitle = arg

    def getWindowText(self):
        return self.windowText

    def setWindowText(self, arg):
        self.windowText = arg

    def getNextButtonEnabled(self):
        return self.nextButtonEnabled

    def setNextButtonEnabled(self, arg, refresh=False):
        self.nextButtonEnabled = arg
        if refresh:
            self.gui.handleControlState(self)

    def getBackButtonEnabled(self):
        return self.backButtonEnabled

    def setBackButtonEnabled(self, arg):
        self.backButtonEnabled = arg

    def getCancelButtonShow(self):
        return self.cancelButtonShow

    def setCancelButtonShow(self, arg, refresh=False):
        self.cancelButtonShow = arg
        if refresh:
            self.gui.handleControlState(self)

    def getCancelButtonEnabled(self):
        return self.cancelButtonEnabled

    def setCancelButtonEnabled(self, arg, refresh=False):
        self.cancelButtonEnabled = arg
        if refresh:
            self.gui.handleControlState(self)

    def getFinishButtonShow(self):
        return self.finishButtonShow

    def setFinishButtonShow(self, arg, refresh=False):
        self.finishButtonShow = arg
        if refresh:
            self.gui.handleControlState(self)

    def insertStep(self, step, target):
        idx = self.gui.dispatch.index(target)
        self.gui.dispatch.insert(idx, step)

    def removeStep(self, step):
        self.gui.dispatch.remove(step)

    def setCurrentStep(self, step):
        self.gui.dispatch.step = self.gui.dispatch.index(step)

    def getStepList(self):
        return self.gui.dispatch

class Gui:
    def __init__(self):
        sys.excepthook = lambda type, value, tb: \
            exception.handleException(self, (type, value, tb))

        self.xml = gtk.glade.XML(os.path.join(os.path.dirname(__file__),
                                               "gui/glade/weasel.glade"))

        # get the main window
        self.window = self.xml.get_widget("mainwindow")
        self.currentWindow = None

        self.banner = self.xml.get_widget("banner")
        self.headerbar = self.xml.get_widget("headerbar")
        self.headerbarIcon = self.xml.get_widget("headerbarIcon")
        self.headerbarTitle = self.xml.get_widget("headerbarTitle")
        self.headerbarText = self.xml.get_widget("headerbarText")
        self.frame = self.xml.get_widget("frame")

        self.nextButton = self.xml.get_widget("MainNextButton")
        self.backButton = self.xml.get_widget("MainBackButton")
        self.finishButton = self.xml.get_widget("MainFinishButton")
        self.cancelButton = self.xml.get_widget("MainCancelButton")

        if userchoices.getDebug():
            self.debugButton = self.xml.get_widget("MainDebugButton")
            self.debugButton.show_now()
        else:
            self.debugButton = None

        self.nextCallbackId = None
        self.backCallbackId = None

        self.wasCancelled = False

        # get our hook for where we're going to draw the various gui bits

        self.stepToClass = {
            'welcome' : StepState(welcome_gui.WelcomeWindow),
            'keyboard' : StepState(keyboard_gui.KeyboardWindow),
            'customdrivers' : StepState(customdrivers_gui.CustomDriversWindow),
            'driverload' : StepState(driverload_gui.DriverLoadWindow),
            'eula' : StepState(eula_gui.EulaWindow),
            'setupchoice' : StepState(setupchoice_gui.SetupChoiceWindow),
            'installlocation' :
                StepState(installlocation_gui.InstallLocationWindow),
            'esxlocation' : StepState(esxlocation_gui.EsxLocationWindow),
            'datastore' : StepState(datastore_gui.DataStoreWindow),
            'timezone' : StepState(timezone_gui.TimezoneWindow),
            'timedate' : StepState(timedate_gui.TimedateWindow),
            'setupvmdk' : StepState(setupvmdk_gui.SetupVmdkWindow),
            'password' : StepState(password_gui.PasswordWindow),
            'media' : StepState(installmedia_gui.InstallMediaWindow),
            'nfsmedia' : StepState(nfsmedia_gui.NFSInstallMediaWindow),
            'httpmedia' : StepState(httpmedia_gui.HTTPInstallMediaWindow),
            'ftpmedia' : StepState(ftpmedia_gui.FTPInstallMediaWindow),
            'usbmedia' : StepState(usbmedia_gui.USBInstallMediaWindow),
            'cosnetwork' : StepState(cosnetwork_gui.CosNetworkWindow),
            'cosnetworkadapter' :
                StepState(cosnetworkadapter_gui.CosNetworkAdapterWindow),
            'review' : StepState(review_gui.ReviewWindow),
            'installation' : StepState(installation_gui.InstallationWindow),
            'bootloader' : StepState(bootloader_gui.BootloaderWindow),
            'license' : StepState(license_gui.LicenseWindow),
            'finished' : StepState(finished_gui.FinishedWindow),
            }
        
        self.dispatch = dispatch.Dispatcher(stepList=installSteps)

        # XXX - need to check if /mnt/source is mounted or not so we can
        #       still keep the media screen if we need to
        # remove the install media set unless askmethod was called
        if not userchoices.getShowInstallMethod():
            self.dispatch.remove('media')

        self.setScreen()

        self.xml.signal_autoconnect({
		'debug' : self.debugButtonPressed,
		'back' : self.backButtonPressed,
		'next' : self.nextButtonPressed,
		'finish' : self.finishButtonPressed,
		'cancel' : self.cancelButtonPressed,
	})

        self.setCursor(gtk.gdk.LEFT_PTR)

        gtk.main()

    def exceptionWindow(self, desc, details):
        log.error("Uncaught exception in gui:")
        log.error(details)
        
        ew = ExceptionWindow(desc, details)
        return ew.run()

    def debugButtonPressed(self, *args):
        log.debug("Debug button pressed")
        os.system("chvt 1")

        import pdb
        try:
            pdb.set_trace()
        except:
            log.error("Couldn't start the debugger")
            sys.exit(-1)

        os.system("chvt 6")

    def backButtonPressed(self, *args):
        '''This just puts _actualBackButtonPressed on the idle queue.
        We have to do it this way to allow the cursor change to take
        place'''
        
        if self.backCallbackId is not None:
            # _actualBackButtonPressed is not done yet.
            return

        log.debug("Back button pressed")

        self.setCursor(gtk.gdk.WATCH)
        self.backButton.set_sensitive(False) #handleControlState reverts it
        self.backCallbackId = gobject.idle_add(self._actualBackButtonPressed)
        
    def _actualBackButtonPressed(self):
        try:
            if hasattr(self.currentWindow, "getBack"):
                self.currentWindow.getBack()
        except exception.StayOnScreen:
            self.backButton.set_sensitive(True)
        else:
            self.dispatch.goBack()
            self.setScreen(direction='back')

        self.backCallbackId = None
        self.setCursor(gtk.gdk.LEFT_PTR)

    def nextButtonPressed(self, *args):
        '''This just puts _actualNextButtonPressed on the idle queue.
        We have to do it this way to allow the cursor change to take
        place'''

        if self.nextCallbackId is not None:
            # _actualNextButtonPressed is not done yet.
            return

        log.debug("Next button pressed")
        self.setCursor(gtk.gdk.WATCH)
        self.nextButton.set_sensitive(False) #handleControlState reverts it
        self.nextCallbackId = gobject.idle_add(self._actualNextButtonPressed)

    def _actualNextButtonPressed(self):
        try:
            if hasattr(self.currentWindow, "getNext"):
                self.currentWindow.getNext()
        except exception.StayOnScreen:
            self.nextButton.set_sensitive(True)
        else:
            self.dispatch.goNext()
            self.setScreen(direction='next')

        self.nextCallbackId = None
        self.setCursor(gtk.gdk.LEFT_PTR)

    def finishButtonPressed(self, *args):
        if hasattr(self.currentWindow, "getFinished"):
            self.currentWindow.getFinished()
        gtk.main_quit()

    def cancelButtonPressed(self, *args):
        title = "Cancel Installation"
        text = "Are you certain you would like to cancel your installation?"

        window = MessageWindow(self.getWindow(), title, text, 'yesno')
        if window.affirmativeResponse:
            if hasattr(self.currentWindow, "getCancel"):
                self.currentWindow.getCancel()
            self.wasCancelled = True
            gtk.main_quit()

    def getWindow(self):
        return self.window

    def setScreen(self, direction='next'):
        step = self.dispatch[self.dispatch.currentStep()]
        stepState = self.stepToClass[step]

        ics = InstallControlState(self)
        self.currentWindow = stepState.createWindow(ics)

        children = self.frame.get_children()
        if children:
            self.frame.remove(children[0])

        self.frame.add(stepState.screenWindow)

        self.handleControlState(ics, direction)

        log.debug("  *** CHANGING TO STEP %s ***" % step)


    def handleControlState(self, controlState, direction='next'):
        if not controlState.getDisplayBanner():
            self.banner.hide()
        else:
            self.banner.show()

        if not controlState.getDisplayHeaderBar():
            self.headerbar.hide()
            pass
        else:
            if controlState.windowIcon:
                iconImg = os.path.join('gui/images', controlState.windowIcon)
            else:
                iconImg = 'gui/images/icon.png'

            self.headerbarIcon.set_from_file(iconImg)

            if controlState.windowTitle:
                text = "<big>%s</big>" % (controlState.windowTitle)
                self.headerbarTitle.set_markup(text)

            if controlState.windowText:
                self.headerbarText.set_label(controlState.windowText)

            self.headerbar.modify_bg(gtk.STATE_NORMAL,
                           self.headerbar.get_colormap().alloc_color("white"))

            self.headerbar.show_all()

        self.setButtonSensitive(self.nextButton,
                                controlState.getNextButtonEnabled())
        self.setButtonSensitive(self.backButton,
                                controlState.getBackButtonEnabled())

        if controlState.getFinishButtonShow():
            self.finishButton.show()
        else:
            self.finishButton.hide()

        self.setButtonSensitive(self.cancelButton,
                                controlState.getCancelButtonEnabled())

        if controlState.getCancelButtonShow():
            self.cancelButton.show()
        else:
            self.cancelButton.hide()

        if controlState.initialFocus:
            controlState.initialFocus.grab_focus()
        else:
            assert direction in ['next', 'back']

            if direction == 'next':
                self.nextButton.grab_focus()
            elif direction == 'back':
                self.backButton.grab_focus()

    def setButtonSensitive(self, button, sensitivity):
        button.set_sensitive(sensitivity)
        # BEGIN workaround for gtk bug #56070.  The problem is that if the mouse
        # is hovering over the button when it is resensitized, the button does
        # not respond to clicks.
        button.hide()
        button.show()
        # END workaround for gtk bug #56070

    def setCursor(self, cursorID):
        cursor = gtk.gdk.Cursor(cursorID)
        gdkWindow = self.nextButton.get_parent_window()
        gdkWindow.set_cursor(cursor)

