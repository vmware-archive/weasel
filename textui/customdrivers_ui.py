#!/usr/bin/env python
#-*- coding: utf-8 -*-

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

'''Custom Driver
'''

import userchoices
import shutil
import cdutil
import util
import os
import customdrivers
import packages
from consts import CDROM_DEVICE_PATH
import dispatch
import textengine
from textrunner import TextRunner, SubstepTransitionMenu as TransMenu
from log import log

from eula_ui import fmt

title = "Custom Drivers"

from customdrivers import DRIVER_NAME, DRIVER_VERSION, DRIVER_DESCRIPTION

DRIVER_MOUNT_DIR = "/mnt/source"
INSERT_DRIVER_CD_STRING = """\
Insert an ESX Driver CD with the ESX drivers that you wish
to use.
"""
INSERT_ESX_CD_STRING = "Re-insert the ESX Install CD."

INVALID_VERSION_STRING = """\
The driver CD provided is not the correct version for this version of ESX.
"""
INVALID_DRIVER_CD_STRING = """\
The CD provided is not a valid VMware ESX Driver CD."
"""
INVALID_ESX_CD_STRING = """\
The CD inserted in the drive does not appear to be an ESX Install CD.
"""
INVALID_CUSTOM_DRIVER_STRING = """
The custom driver %(name)s has invalid entries.\
"""

askCustomDriversText = """\
Choose whether to install any custom drivers for this ESX installation.

Do you want to install %(any)s custom drivers?
"""

prologAcceptText = """\
    To continue with the installation, please read and accept the
    end user license agreement.
"""

changeMediaCustomText = """\
Remove the ESX installation media and insert the media containing
the custom drivers.

 1) OK
 <) Back

"""

promptMediaCustomText = """\
Insert an ESX Driver CD with the ESX drivers that you
wish to use.
#(See INSERT_DRIVER_CD_STRING)
#* Cancel
#* OK
"""

askAreYouSureText = """\
Going to Load Drivers

The installer will now load any drivers required for ESX.  Once this
step is completed, additional custom drivers cannot be loaded.

Load system drivers now?
"""

helpEulaText = """
You can not install any custom drivers unless you accept the terms outlined in
the End User License.

 <) Back

"""

helpText = """
If you need ESX drivers which are not part of the ESX installation
CD, then you should load them now, before proceeding with the rest
of the installation.  Drivers may be provided for new hardware by the
hardware vendor.  You may load drivers from several CDs.

If you discover that you need drivers later during this installation,
you will need to restart the installer.

For each CD, you can specify multiple drivers by a comma-separated list.
"""

helpSelectablesText = """\
Specify the drivers that you want to add as a comma-separated list
of numbers.  Drivers that you have already selected will not be shown.
If no drivers are listed, then all drivers on the media have been
selected.
"""

prologSelectDriversText = """\
Select the custom drivers to %s by entering a comma separated list."""

errorNoDriversText = """
There are no drivers to remove.

 <) Back

"""

# The ESX install media and drivers supplemental CDs are
# Dicts below are populated as follows:
#   xml - distinguishing XML file in the CD's root directory
#   name - human readable description
#   mount - mount point used by this module (not required by CD)
media = {
    'drivers': {
        'xml': 'drivers.xml',
        'name': 'ESX Custom Drivers CD',
        'mount': '/mnt/source',
        # TODO: finalize mount point
        # this varies from consts.MEDIA_DEVICE_MOUNT_POINT
    },
    'install': {
        'xml': 'packages.xml',
        'name': 'ESX Install CD',
        'mount': '/mnt/source',
    },
    'ejected': {
        'xml': None,
        'name': 'ejected media',
        'mount': None,
    },
}

_currentMediaKey = None

SCROLL_LIMIT = 10

class CustomDriversWindow(TextRunner):
    "Select ESX custom device drivers."

    def __init__(self, filename=None):
        super(CustomDriversWindow, self).__init__()
        global _currentMediaKey

        self.start = self.askCustomDrivers
        self.substep = self.start       # initial TextRunner substep

        # cumulativeDriversDict uses package name (currently RPM name) as key,
        # and have as value tuples of:
        #  (driverName, version, description, driverBinList, pciTable, 
        #   removeList)
        self.cumulativeDriversDict = {} # drivers to install
        _currentMediaKey = 'install'

        if not filename:
           filename = os.path.join(
                os.path.dirname(__file__), os.path.pardir, "drivereula.txt")

        self.textlines = ['']

        try:
            rawtext = open(filename).read()
        except Exception, msg:
            log.error(msg)
            log.error("Couldn't load driver eula")
        try:
            formattedtext = fmt(rawtext)
            self.textlines = formattedtext
        except Exception, msg:
            log.error(msg)
            log.error("Couldn't convert eula")

        self.scrollable = None


    def askCustomDrivers(self):
        """Ask if user wants to install custom drivers.
        Also check if custom drivers already exist, if they do show EULA"""
        ui = {
            'title': title,
            'menu': {
                '1': self.changeMediaToDrivers,
                '<': self.stepBack,
                '?': self.help,
            }
        }
        if not self.cumulativeDriversDict:
            quantity = "any"
            ui['menu']['2'] = self.lastChance
        else:
            quantity = "any additional"
            ui['menu']['2'] = self.scrollEula

        ui['body'] = askCustomDriversText % {'any':quantity} + \
                     TransMenu.YesNoBackHelp

        self.setSubstepEnv(ui)

    def lastChance(self):
        "Display 'are you sure' text and ask for final confirmation."

        ui = {
            'title': title,
            'body': askAreYouSureText + TransMenu.YesNoBackHelp,
            'menu': {
                '1': self.addSupplementaryDrivers,
                '2': self.start,
                '<': self.start,
                '?': self.help,
            }
        }
        self.setSubstepEnv(ui)

    def scrollEula(self):
        self.setScrollEnv(self.textlines, SCROLL_LIMIT)
        self.scrollDisplay = self.scrollDriverEula
        self.setSubstepEnv( {'next': self.scrollDisplay} )

    def acceptEula(self):
        if not self.userinput == 'accept':
            self.errorEula()
            return

        self.setSubstepEnv({'next': self.lastChance})

    def errorEula(self):
        self.errorPushPop("Driver Eula (Error)", helpEulaText)

    def scrollDriverEula(self):
        "Show the Driver EULA"

        self.buildScrollDisplay(self.scrollable, "Driver Eula",
            self.acceptEula, "'accept': accept license", allowStepBack=True,
            prolog=prologAcceptText)

    def changeMediaToDrivers(self):
        "Switch from install CD to drivers CD."

        # create RPM staging directory
        if not os.path.exists(customdrivers.DRIVER_DEPOT_DIR):
            os.makedirs(customdrivers.DRIVER_DEPOT_DIR)

        cm = ChangeMedia(_currentMediaKey, 'drivers')
        result = cm.run()
        assert result in (dispatch.DISPATCH_BACK, dispatch.DISPATCH_NEXT), \
            "unexpected step result from ChangeMedia"
        if result != dispatch.DISPATCH_NEXT:
            # User wants to re-think this
            self.setSubstepEnv({'next': self.askCustomDrivers})
        else:
            self.setSubstepEnv({'next': self.selectCustomDrivers})


    def selectCustomDrivers(self):
        "Select drivers through SelectableDrivers object."

        selectedList = self.cumulativeDriversDict.keys()
        selectable = SelectableDrivers(media['drivers'],
            self.cumulativeDriversDict, selectedList)
            # third param should be list of selected drivers
        result = selectable.run()
        assert result in (textengine.DISPATCH_BACK, textengine.DISPATCH_NEXT)
        if result != textengine.DISPATCH_NEXT:
            self.setSubstepEnv({'next': self.askCustomDrivers})  # rethink
        else:
            self.setSubstepEnv({'next': self.confirmSelected})  # eh?
            # should go to list of current drivers to load


    def confirmSelected(self):
        "Show drivers to be added."

        pkgsSelected = self.cumulativeDriversDict.keys()
        pkgsSelected.sort()

        scrollable = []
        for pkgName in pkgsSelected:
            driverName = self.cumulativeDriversDict[pkgName][DRIVER_NAME]
            version = self.cumulativeDriversDict[pkgName][DRIVER_VERSION]
            description = self.cumulativeDriversDict[pkgName][DRIVER_DESCRIPTION]
            scrollable.append("  * %s vers. %s\n    %s" % \
                (driverName, version, description))

        self.setScrollEnv(scrollable, SCROLL_LIMIT)
        self.scrollDisplay = self.scrollConfirmDisplay
        self.setSubstepEnv({'next': self.scrollDisplay})

    def scrollConfirmDisplay(self):
        "display drivers selected and ask user to confirm/add/remove"
        self.buildScrollDisplay(self.scrollable, title,
            self.parseConfirmDisplay, "1: OK, 2: Add, 3: Remove",
            prolog="These drivers have been selected for installation.")

    def parseConfirmDisplay(self):
        "parse userinput from scrollConfirmDisplay "
        menu = {
            '1': self.scrollEula,
            '2': self.changeMediaToDrivers,
            '3': self.removeDrivers,
        }
        # If we've removed all drivers we want to add, then we don't need to
        # display the EULA.
        if not self.cumulativeDriversDict:
            menu['1'] = self.lastChance

        try:
            userinput = self.userinput
            if userinput not in menu:
                raise ValueError('Unrecognized input: %s' % userinput)
        except ValueError, ex:
            log.error(ex[0])
            self.errorPushPop(title, ex[0]+TransMenu.Back)
            return
        self.setSubstepEnv({'next': menu[userinput]})

    def removeDrivers(self):
        "Remove drivers."

        pkgsSelected = self.cumulativeDriversDict.keys()
        pkgsSelected.sort()

        if not pkgsSelected:
            self.errorPushPop(title, errorNoDriversText)
            return

        scrollable = []
        self.pkgRemoveNames = []
        for nDriver, pkgName in enumerate(pkgsSelected):
            driverName = self.cumulativeDriversDict[pkgName][DRIVER_NAME]
            version = self.cumulativeDriversDict[pkgName][DRIVER_VERSION]
            description = self.cumulativeDriversDict[pkgName][DRIVER_DESCRIPTION]
            scrollable.append("%2d. %s vers. %s\n    %s" % \
                (nDriver+1, driverName, version, description))
            self.pkgRemoveNames.append(pkgName)

        self.setScrollEnv(scrollable, SCROLL_LIMIT)
        self.scrollDisplay = self.scrollRemoveDisplay
        self.setSubstepEnv({'next': self.scrollDisplay})

    def scrollRemoveDisplay(self):
        "display drivers and ask user to select for removal"
        self.buildScrollDisplay(self.scrollable, title,
            self.selectRemoveDrivers, "<numbers>: driver choices ",
            prolog=prologSelectDriversText % "remove")

    def selectRemoveDrivers(self):
        "extract removal list from numeric userinput"
        try:
            indices = self.getScrollMultiChoices()
        except (IndexError, ValueError), msg:
            body = '\n'.join(['Input error', msg[0], TransMenu.Back])
            self.errorPushPop(title, body)
            return

        removePkgList = []

        for number in indices:
            pkgName = self.pkgRemoveNames[number]
            self.cumulativeDriversDict.pop(pkgName)
            fileName = os.path.join(customdrivers.DRIVER_DEPOT_DIR,
                                    os.path.basename(pkgName))
            try:
                os.remove(fileName)
            except OSError, ex:
                log.error("attempt remove non-existent file %s")

        self.setSubstepEnv({'next': self.confirmSelected})

    def addSupplementaryDrivers(self):
        "Add requested drivers to supplementary driver list."

        for pkgName in self.cumulativeDriversDict:
            userchoices.addSupplementaryDriver(pkgName,
                *self.cumulativeDriversDict[pkgName])

            pkgFileName = \
                os.path.join(customdrivers.DRIVER_DEPOT_DIR,
                             os.path.basename(pkgName))
            pkg = packages.Package(pkgFileName, 'required')
            userchoices.addPackageObjectToInstall(pkg)

        userchoices.setDriversLoaded(True)

        self.setSubstepEnv({'next': self.stepForward})

        # umount the driver dir otherwise we risk locking the drive door
        util.umount(DRIVER_MOUNT_DIR)

    def help(self):
        "Emit help text."
        self.helpPushPop(title + ' (Help)', helpText + TransMenu.Back)

class SelectableDrivers(TextRunner):
    "drivers on ESX Drivers media which may be selected for installation"

    def __init__(self, driversMedia, driversStagingDict, skipList):
        super(SelectableDrivers, self).__init__()

        self.media = driversMedia
        self.staging = driversStagingDict
        self.skipList = skipList
        self.start = self.showSelectable

        self.mediaPkgsDict = {}       # packages on current disc
        self.pkgNames = []

    def showSelectable(self):
        "build basic list of selectable drivers"

        xmlFileName = os.path.join(self.media['mount'], "drivers.xml")
        errMsg = None
        msg = None
        try:
            driverXml = customdrivers.CustomDriversXML(xmlFileName)
            self.mediaPkgsDict = driverXml.driverDict
        except customdrivers.InvalidVersion, msg:
            errMsg = INVALID_VERSION_STRING
        except customdrivers.InvalidDriversXml, msg:
            errMsg = INVALID_DRIVER_CD_STRING
        except customdrivers.InvalidCustomDriverError, msg:
            errMsg = INVALID_CUSTOM_DRIVER_STRING % {'name':msg}
        except Exception, msg:
            errMsg = "Unknown error processing custom drivers media"
        if errMsg:
            log.error(errMsg)
            log.error(str(msg))
            body = '\n'.join(['Invalid Driver CD', errMsg, TransMenu.Back])
            self.errorPushPop(title, body)
            return

        pkgsOnMedia = self.mediaPkgsDict.keys()
        pkgsSelectable = []
        for driverName in pkgsOnMedia:
            if driverName in self.skipList:
                continue
            else:
                pkgsSelectable.append(driverName)
        pkgsSelectable.sort()

        scrollable = []

        for nDriver, pkgName in enumerate(pkgsSelectable):
            driverName = self.mediaPkgsDict[pkgName][DRIVER_NAME]
            version = self.mediaPkgsDict[pkgName][DRIVER_VERSION]
            description = self.mediaPkgsDict[pkgName][DRIVER_DESCRIPTION]
            scrollable.append("%2d. %s vers. %s\n    %s" % \
                (nDriver+1, driverName, version, description)) # use 1-indexed
            self.pkgNames.append(pkgName)

        self.setScrollEnv(scrollable, SCROLL_LIMIT)
        self.setSubstepEnv({'next': self.scrollDisplay })

    def scrollDisplay(self):
        self.buildScrollDisplay(self.scrollable, title,
            self.selectDrivers, "<numbers>: driver choices",
            allowStepBack=True, prolog=prologSelectDriversText % "install")

    def selectDrivers(self):
        "extract list of drivers to load from numeric userinput"
        try:
            indices = self.getScrollMultiChoices()
        except (IndexError, ValueError), msg:
            body = '\n'.join(['Input error', msg[0], TransMenu.Back])
            self.errorPushPop(title, body)
            return

        fromMediaMount = self.media['mount']
        for number in indices:
            pkgName = self.pkgNames[number]
            self.staging[pkgName] = self.mediaPkgsDict[pkgName]

            # copy RPM to staging area
            fromFileName = os.path.join(fromMediaMount, pkgName)
            toFileName = \
                os.path.join(customdrivers.DRIVER_DEPOT_DIR,
                             os.path.basename(pkgName))
            shutil.copy(fromFileName, toFileName)
            log.info("staging RPM %s" % pkgName)

        # copy over the content
        self.setSubstepEnv({'next': self.stepForward})

    def help(self):
        "Emit help text."
        self.helpPushPop(title + ' (Help)', helpSelectablesText + TransMenu.Back)


class ChangeMedia(TextRunner):
    "change between driver and installer media"

    def __init__(self, fromMediaKey, toMediaKey):
        super(ChangeMedia, self).__init__()

        self.start = self.ejectInstruct
        self.substep = self.start       # initialize
        assert fromMediaKey in media, "unrecognized fromMedia type"
        assert toMediaKey in media and toMediaKey is not 'ejected', \
            "unrecognized toMedia type"
        self.fromMediaKey = fromMediaKey
        self.toMediaKey = toMediaKey
        self.fromMedia = media[fromMediaKey]
        self.toMedia = media[toMediaKey]
        self.mountedPath = ""

    def ejectInstruct(self):
        "Force eject, ask user to put in new media."
        global _currentMediaKey
        # It's better to aggressively eject to make sure that we don't lock the drive
        status = umountEject(self.fromMedia['mount'])
        # TODO: really ought to check that eject status

        if self.fromMediaKey == self.toMediaKey:
            fromStr = "current media"
            toStr = "new " + self.toMedia['name']
        else:
            fromStr = self.fromMedia['name']
            toStr = self.toMedia['name']

        _currentMediaKey = 'ejected' # should be conditioned on status

        msg = "Remove %s, and insert %s." % (fromStr, toStr)
        text = '\n'.join([msg, TransMenu.OkBack])

        ui = {
            'title': title,
            'body': text,
            'menu': {
                '1': self.mountNew,
                '<': self.stepBack,
            }
        }
        self.setSubstepEnv(ui)

    def checkMedia(self):
        """Check to see if target (to) media is already mounted.
        If not prompt user.
        """
        global _currentMediaKey
        cmTitle = 'Change Media'
        toMedia = self.toMedia
        fromMedia = self.fromMedia
        toXmlFileName = os.path.join(toMedia['mount'], toMedia['xml'])
        #fromXmlFileName = os.path.join(fromMedia['mount'], fromMedia['xml'])

        if os.path.exists(toXmlFileName):
            # already mounted
            _currentMediaKey = self.toMediaKey
            self.setSubstepEnv({'next': self.stepForward})
            return

        # Looks like we have the wrong disk, lets eject it.
        status = umountEject(self.mountedPath)
        _currentMediaKey = 'ejected' # should be conditioned on status

        msg = "Retry... Insert %s." % toMedia['name']
        text = '\n'.join([msg, TransMenu.OkBack])
        ui = {
            'title': cmTitle,
            'body': text,
            'menu': {
                '1': self.mountNew,
                '<': self.stepBack,
            }
        }
        self.setSubstepEnv(ui)

    # Need to mount new media
    def mountNew(self):
        "mount the new media"
        util.mount(CDROM_DEVICE_PATH, self.toMedia['mount'])
        # We've mounted something, lets save the path so we can eject it later.
        self.mountedPath = self.toMedia['mount']
        # After mounting, check that correct media is in the drive.
        self.setSubstepEnv({'next': self.checkMedia})

# ---- utilities ----

def umountEject(uMountPoint):
    """Attempt to reliably unmount the media and eject it.  This can
    be kludgey.  umount on some systems doesn't free up the resource
    that eject thinks has to be free.
    """
    # TODO AND NOTES:
    # 1. Deliberately inserting the wrong CD can lead to duplicate mounts,
    #    and later umount trouble.  Workaround: select a separate console,
    #    and manually umount.  Need to bullet-proof this better.
    # 2. umount immediately followed by eject has been known to failed
    #    on certain other Busybox/uClibc/2.4kernel systems.  Injecting a sleep
    #    works around the problem.
    import time
    for trial in (1, 2, 3):
        if uMountPoint:  # guard against NoneType, ''
            status = util.umount(uMountPoint)
            if status == 0:  # success
                break
            else:
                args = ["/usr/bin/umount", "-f", uMountPoint]
                status = util.execWithLog(args[0], args)
                log.warn('Forced umount of %s: %d' % (uMountPoint, status))
            time.sleep(1)
            log.warn('customdrivers_ui umount attempt %d failed' % trial)

    status = cdutil.ejectCdrom()
    return status


