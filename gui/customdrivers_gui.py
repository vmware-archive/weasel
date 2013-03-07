
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

import gobject
import gtk
import userchoices
import shutil
import exception
import cdutil
import util
import customdrivers
import packages
import os

from signalconnect import connectSignalHandlerByDict
from common_windows import MessageWindow
from common_windows import CommonWindow
from common_windows import populateViewColumns
from consts import MEDIA_DEVICE_MOUNT_POINT, CDROM_DEVICE_PATH
from log import log

INSERT_DRIVER_CD_STRING = "Insert an ESX Driver CD with " + \
                          "the ESX drivers that you wish to use."
ERRORS_DRIVER_CD_STRING = "The driver CD provided contains errors and can " + \
                          "not be used."
INVALID_VERSION_STRING = "The driver CD provided is not the correct " + \
                         "version for this version of ESX."
INVALID_DRIVER_CD_STRING = "The CD provided is not a valid VMware ESX " + \
                           "Server Driver CD."
INVALID_CUSTOM_DRIVER_STRING = "The custom driver %(name)s " + \
                               "has invalid entries."

from customdrivers import DRIVER_NAME, DRIVER_VERSION, DRIVER_BINLIST
from customdrivers import DRIVER_SNIPPETLIST, DRIVER_DESCRIPTION

# driver model globals
DRIVERMODEL_DRIVER = 0
DRIVERMODEL_VERSION = 1
DRIVERMODEL_DESCRIPTION = 2
DRIVERMODEL_PACKAGE = 3

class InvalidDriverCDException(Exception):
    pass

class CustomDriversWindow(object):
    SCREEN_NAME = 'customdrivers'
    
    def __init__(self, controlState, xml):
        controlState.displayHeaderBar = True
        controlState.windowIcon = 'customdrivers.png'
        controlState.windowTitle = 'Custom Drivers'
        controlState.windowText = \
            'Select custom drivers to install for ESX'

        self.xml = xml
        self.foundDriverList = []
        self.driverList = []            # list of drivers to save
        self.driverDict = {}            # cache of driver data

        connectSignalHandlerByDict(self, CustomDriversWindow, self.xml,
          { ('CustomdriversNoRadioButton', 'toggled') : 'toggleDrivers',
            ('CustomdriversAddButton', 'clicked') : 'addDriver',
            ('CustomdriversRemoveButton', 'clicked') : 'removeDriver',
          })

        if userchoices.getDriversLoaded():
            self.xml.get_widget('CustomdriversVBox').set_sensitive(False)

        self.view = self.xml.get_widget('CustomdriversTreeView')
        self.scrolled = self.xml.get_widget('CustomdriversScrolledWindow')

        self.addDrivers = AddDrivers(self)

        _setupAddDriversView(self.view)

        # build up self.driverList in case the user has gone back
        # from the screen and re-entered it
        self.buildDriverList()

        # unmount the cdrom so the user can eject it manually
        util.umount(MEDIA_DEVICE_MOUNT_POINT)

    def buildDriverList(self):
        '''Rebuild self.driverList from any previous entries'''
        drivers = userchoices.getSupplementaryDrivers()

        userchoices.clearSupplementaryDrivers()

        # reconstruct the driver dictionary and the list of drivers
        # we're going to install

        for driver in drivers:
            self.driverDict[driver['filename']] = (driver['driver'],
                driver['version'], driver['description'],
                driver['driverList'], driver['snippetList'],
                driver['removeList'])

            self.driverList.append(
                (driver['driver'], driver['version'], driver['description'],
                 driver['filename']))

    def updateDriverList(self):
        _populateAddDriversModel(self.view, self.scrolled, self.driverList)

    def toggleDrivers(self, widget, *args):
        driverVbox = self.xml.get_widget('CustomdriversModulesVBox')
        driverVbox.set_sensitive(not widget.get_active())

    def addDriver(self, widget, *args):
        try:
            self.scanForDriverDisk()
        except InvalidDriverCDException, e:
            util.umount(MEDIA_DEVICE_MOUNT_POINT)
            cdutil.ejectCdrom()
            MessageWindow(None, "Invalid Driver CD", str(e))

    def removeDriver(self, widget, *args):
        store, selected = self.view.get_selection().get_selected_rows()

        if not selected:
            MessageWindow(None, 'Driver Selection Error',
                'You must select a driver to remove.')
            return

        for entry in selected:
            # remove the entry in the driverList at the storeIndex
            storeIndex = entry[0]
            self.driverList.remove(tuple(store[storeIndex]))

            # remove the file from the ramdisk
            _deleteDriver(tuple(store[storeIndex])[DRIVERMODEL_PACKAGE])

        self.updateDriverList()

        # turn off the remove button if we don't have any drivers left
        if not self.driverList:
            widget = self.xml.get_widget('CustomdriversRemoveButton')
            widget.set_sensitive(False)

    def getNext(self):
        if not userchoices.getDriversLoaded():
            radioButton = self.xml.get_widget('CustomdriversYesRadioButton')
            if radioButton.get_active() and not self.driverList:
                MessageWindow(None, 'Driver Error',
                    'You specified to add custom drivers, however did not '
                    'add any.')
                raise exception.StayOnScreen

            if radioButton.get_active():
                if DriverEula(self).run():
                    self.finishStep()
                else:
                    raise exception.StayOnScreen
            else:
                self.finishStep()

    def finishStep(self):
        radioButton = self.xml.get_widget('CustomdriversYesRadioButton')
        # Warn the user before letting them go forward
        rc = MessageWindow(None, 'Load Drivers',
            'The install wizard will load any drivers required for ESX. '
            'Once this step is completed, additional custom drivers '
            'cannot be loaded.\n\nLoad the system drivers?', type='yesno')

        if not rc.affirmativeResponse:
            raise exception.StayOnScreen
    
        # Add in each of the new driver packages
        if radioButton.get_active():
            for driver in self.driverList:
                packageName = driver[DRIVERMODEL_PACKAGE]

                # unpack the driver dictionary and add the requested
                # driver to the supplementary driver list
                userchoices.addSupplementaryDriver(packageName,
                    *self.driverDict[packageName])

                pkgFileName = os.path.join(customdrivers.DRIVER_DEPOT_DIR,
                                           os.path.basename(packageName))
                pkg = packages.Package(pkgFileName, 'required')

                userchoices.addPackageObjectToInstall(pkg)

        userchoices.setDriversLoaded(True)

    def getBack(self):
        if not userchoices.getDriversLoaded():
            radioButton = self.xml.get_widget('CustomdriversYesRadioButton')

            # Add in each of the new driver packages
            if radioButton.get_active():
                for driver in self.driverList:
                    packageName = driver[DRIVERMODEL_PACKAGE]

                    # unpack the driver dictionary and add the requested
                    # driver to the supplementary driver list
                    userchoices.addSupplementaryDriver(packageName,
                        *self.driverDict[packageName])
            else:
                # remove any entries since the user doesn't want to use
                # them
                for entry in self.driverList:
                    _deleteDriver(entry[DRIVERMODEL_PACKAGE])
                    
                self.driverList = []
                self.updateDriverList()

                widget = self.xml.get_widget('CustomdriversRemoveButton')
                widget.set_sensitive(False)

    def saveDriverDict(self, driverDict):
        for key in driverDict:
            self.driverDict[key] = driverDict[key]

    def scanForDriverDisk(self):
        '''Mount the CD-ROM and check to see if it is a driver CD.'''

        self.foundDriverList = []
        driverDict = {}

        xmlFileName = os.path.join(MEDIA_DEVICE_MOUNT_POINT, "drivers.xml")

        util.umount(MEDIA_DEVICE_MOUNT_POINT)
        cdutil.ejectCdrom()
        window = MessageWindow(None, "Insert CD", INSERT_DRIVER_CD_STRING,
                               type="okcancel")

        if window.affirmativeResponse:
            util.mount(CDROM_DEVICE_PATH, MEDIA_DEVICE_MOUNT_POINT)
            if not os.path.exists(xmlFileName):
                raise InvalidDriverCDException(INVALID_DRIVER_CD_STRING)
        else:
            return

        try:
            driverXml = customdrivers.CustomDriversXML(xmlFileName)
        except customdrivers.InvalidVersion, msg:
            raise InvalidDriverCDException(INVALID_VERSION_STRING)
        except customdrivers.InvalidDriversXml, msg:
            raise InvalidDriverCDException(INVALID_DRIVER_CD_STRING)
        except customdrivers.InvalidCustomDriverError, msg:
            raise InvalidDriverCDException(INVALID_CUSTOM_DRIVER_STRING % \
                    {'name':msg})


        #driverDict = self._skipDuplicateDrivers(driverXml.driverDict)
        driverDict = driverXml.driverDict

        # save each of the drivers so we can construct the add driver window
        for key in driverDict:
            if not os.path.exists(os.path.join(MEDIA_DEVICE_MOUNT_POINT, key)):
                MessageWindow(None, "Missing Driver",
                    "Couldn't find the driver: %s" % key)
                continue

            driverName = driverXml.driverDict[key][DRIVER_NAME]
            version = driverXml.driverDict[key][DRIVER_VERSION]
            description = driverXml.driverDict[key][DRIVER_DESCRIPTION]

            entry = (driverName, version, description, key)
            self.foundDriverList.append(entry)

        self.saveDriverDict(driverXml.driverDict)

        self.addDrivers.show()

    def _skipDuplicateDrivers(self, xmlDriverDict):
        newDriverDict = {}
        for key in xmlDriverDict:
            if self.driverDict.has_key(key):
                print "Didn't add driver %s due to conflict" % key
                log.warn("Didn't add driver %s due to conflict" % key)
                continue
            newDriverDict[key] = xmlDriverDict[key]
        return newDriverDict

def _deleteDriver(packageName):
    targetFileName = \
        os.path.join(customdrivers.DRIVER_DEPOT_DIR,
                     os.path.basename(packageName))
    os.unlink(targetFileName)


class DriverEula(CommonWindow):
    def __init__(self, parent):
        CommonWindow.__init__(self)
        self.xml = parent.xml

        self.acceptedEula = False

        self.dialog = self.xml.get_widget('drivereula')
        assert self.dialog

        self.okButton = self.xml.get_widget('DrivereulaOkButton')
        self.checkButton = self.xml.get_widget('DrivereulaCheckButton')
        self.okButton.set_sensitive(self.checkButton.get_active())

        connectSignalHandlerByDict(self, AddDrivers, self.xml,
          { ('DrivereulaOkButton', 'clicked') : 'okClicked',
            ('DrivereulaCancelButton', 'clicked') : 'cancelClicked',
            ('DrivereulaCheckButton', 'toggled') : 'checkbuttonToggled',
          })

        self.setupEula()
        self.addFrameToWindow()

        self.dialog.set_position(gtk.WIN_POS_CENTER)
        self.dialog.show_all()


    def run(self):
        self.dialog.run()
        self.dialog.hide_all()

        return self.acceptedEula

    def setupEula(self, fn='drivereula.txt'):
        try:
            eulafile = open(fn, 'r')
        except:
            try:
                eulafile = open('/mnt/runtime/etc/' + fn, 'r')
            except:
                log.error("Couldn't load eula")
                return ""

        text = ''.join(eulafile.readlines())
        eulafile.close()

        buf = gtk.TextBuffer(None)
        buf.set_text(text)

        textview = self.xml.get_widget('DrivereulaTextView')
        textview.set_buffer(buf)

    def okClicked(self, widget, *args):
        self.acceptedEula = True

    def cancelClicked(self, widget, *args):
        pass

    def checkbuttonToggled(self, widget, *args):
        self.okButton.set_sensitive(widget.get_active())

class AddDrivers(CommonWindow):
    def __init__(self, parent):
        CommonWindow.__init__(self)

        self.parent = parent
        self.xml = parent.xml

        self.dialog = self.xml.get_widget('adddrivers')
        assert self.dialog

        if not os.path.exists(customdrivers.DRIVER_DEPOT_DIR):
            os.makedirs(customdrivers.DRIVER_DEPOT_DIR)

        connectSignalHandlerByDict(self, AddDrivers, self.xml,
          { ('AdddriversOkButton', 'clicked') : 'importClicked',
            ('AdddriversCancelButton', 'clicked') : 'cancelClicked',
          })

        self.view = self.xml.get_widget('AdddriversTreeView')
        self.scrolled = self.xml.get_widget('AdddriversScrolledWindow')

        _setupAddDriversView(self.view)

        self.addFrameToWindow()

    def show(self):
        # construct the driver list and remove any drivers that we're already
        # going to install
        driverList = self.parent.foundDriverList

        if not driverList or not \
           _checkForDriversToAdd(driverList, self.parent.driverList):
            MessageWindow(None, 'No drivers to import',
                          'There are no available drivers to import.')
            self.hide()
            return

        _populateAddDriversModel(self.view, self.scrolled, driverList,
                                 self.parent.driverList)

        self.dialog.show_all()

    def hide(self):
        self.dialog.hide_all()

    def importClicked(self, widget, *args):
        store, selected = self.view.get_selection().get_selected_rows()

        if not selected:
            MessageWindow(None, 'Driver Selection Error',
                          'You must select a driver to import.')
            return

        for entry in selected:
            packageName = store[entry[0]][DRIVERMODEL_PACKAGE]

            if _checkForCollision(packageName, self.parent.driverList,
                                  self.parent.driverDict):
                MessageWindow(None, 'Driver Import Error',
                         "Couldn't add the %s package due to a conflict." %
                          packageName)
                continue

            fileName = os.path.join(MEDIA_DEVICE_MOUNT_POINT, packageName)
            assert os.path.exists(fileName)

            targetFileName = \
                os.path.join(customdrivers.DRIVER_DEPOT_DIR,
                             os.path.basename(packageName))


            self.parent.driverList.append(tuple(store[entry[0]]))
            self.parent.updateDriverList()

            shutil.copy(fileName, targetFileName)

            self.xml.get_widget('CustomdriversRemoveButton').set_sensitive(True)

        # leave the CDROM unmounted so the user can eject it manually
        util.umount(MEDIA_DEVICE_MOUNT_POINT)
        self.hide()

    def cancelClicked(self, widget, *args):
        # leave the CDROM unmounted so the user can eject it manually
        util.umount(MEDIA_DEVICE_MOUNT_POINT)
        self.hide()


def _checkForCollision(packageName, driverList, driverDict):
    '''Search through snippets and driver bins to see if anything collides'''

    binList = []
    snippetList = []

    # build up a list of current binaries and snippets
    for driver in driverList:
        targetPackageName = driver[DRIVERMODEL_PACKAGE]
        binList += driverDict[targetPackageName][DRIVER_BINLIST]
        snippetList += driverDict[targetPackageName][DRIVER_SNIPPETLIST]

        # XXX - extract snippets here and compare them

    newBinList = set(driverDict[packageName][DRIVER_BINLIST])
    newSnippetList = set(driverDict[packageName][DRIVER_SNIPPETLIST])

    # if we have any binaries or snippets which collide return true
    if newBinList.intersection(set(binList)) or \
       newSnippetList.intersection(set(snippetList)):
        return True

    return False


def _setupAddDriversView(view):
    if not view.get_columns():
        model = gtk.TreeStore(gobject.TYPE_STRING, gobject.TYPE_STRING,
                              gobject.TYPE_STRING, gobject.TYPE_STRING)

        viewColumns = (
         ('Driver', 250),
         ('Version', 120),
         ('Description', 200),
        )

        populateViewColumns(view, viewColumns)
        view.set_model(model)
        view.get_selection().set_mode(gtk.SELECTION_MULTIPLE)

def _checkForDriversToAdd(drivers, skipList):
    '''Determine whether there are any drivers to display'''

    # search through the driver list and determine if any are not
    # in the skip list
    for entry in drivers:
        if entry not in skipList:
            return True
    return False

def _populateAddDriversModel(view, scrolled, drivers, skipList=None):
    model = view.get_model()
    model.clear()

    # sort the driver list by the first element
    drivers.sort(lambda x, y: cmp(x[0], y[0]))

    for entry in drivers:
        if skipList and entry in skipList:
            continue
        driverIter = model.append(None, entry)

    view.expand_all()
    scrolled.show_all()

