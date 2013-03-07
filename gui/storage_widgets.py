
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

import gtk
import gtk.glade
import gobject
import util
from log import log
import userchoices
import datastore
import partition
import devices
import os.path

from common_windows import populateViewColumns
from common_windows import MessageWindow, CommonWindow
from signalconnect import connectSignalHandlerByDict

from util import truncateString
from devices import PATHID_LUN

# defines where 'entry' goes so we can snag it easily
STORAGEVIEW_DISK_ENTRY = 3
SUPPORTED_DISK_ENTRY = 4
DEVMODEL_LENGTH = 35
DEVNAME_LENGTH = 28

STORAGE_TEXT = """The contents of the selected storage device will
be erased before ESX is installed."""

STORAGE_ESX_TEXT = """The contents of the selected storage device will
be erased before ESX is installed.

This storage device contains an existing ESX installation.
Continuing installation on this storage device will cause
any current ESX settings to be lost.  To upgrade the
existing ESX installation without incurring data loss, use
the vSphere Host Update Utility installed with the vSphere
client or vCenter Update Manager."""

STORAGE_DATASTORE_TEXT = \
"""The contents of the selected storage device will be erased
before ESX is installed.

The storage device contains the datastore:\n
<b>%s</b>\n\nAll virtual machines on this datastore will be lost."""

STORAGE_DATASTORE_VMFS2_TEXT = \
"""The contents of the selected storage device will be
erased before ESX is installed.\n

This storage device contains a datastore. All virtual
machines on this datastore will be lost."""

STORAGE_ESX_DATASTORE_TEXT = \
"""The selected storage device contains an existing ESX
installation and the datastore:\n
<b>%s</b>\n
The existing ESX installation will be erased before the
new version is installed, losing any current ESX
settings. The datastore can be retained, however,
preserving any virtual machines.

To upgrade the existing ESX installation without incurring
any data loss,  use the vSphere Host Update Utility
installed along with the vSphere Client or use vCenter
Update Manager."""

STORAGE_ESX_DATASTORE_FULL_TEXT = \
"""The selected storage device contains an existing ESX
installation and datastore. The existing ESX installation
will be erased before the new version is installed, losing
any current ESX settings. The datastore is full and will
also be erased. The datastore could be preserved however,
if it had %d MB more of free space.\n\n

To upgrade the existing ESX installation without incurring
any data loss, use the vSphere Host Update Utility
installed along with the vSphere Client or use vCenter
Update Manager."""

STORAGE_ESX_FULL_DATASTORE_TEXT = \
"""The contents of the selected storage device will be erased
before ESX is installed.\n\n

This storage device contains a datastore. All virtual
machines on this datastore will be lost.\n\n

This storage device also contains an existing ESX
installation. Continuing installation on this storage
device will cause any current ESX settings to be lost."""

COSVMDK_FREESPACE = \
"""A virtual disk file from a previous version of the Console
OS was found on the datastore. Removing this file will
free up more space on the datastore."""

COSVMDK_NO_FREESPACE = \
"""There is not enough free space for the new Console virtual
disk without removing the existing console virtual
disk.  The existing console virtual disk file will be
deleted."""

COSVMDK_TOTALLY_FULL = \
"""There is not enough free space for the new Console virtual
disk.  Choose another disk for installation or reboot and
free up more space on the datastore."""

def setupStorageView(view):
    if not view.get_columns():
        model = gtk.TreeStore(gobject.TYPE_STRING, gobject.TYPE_STRING,
                              gobject.TYPE_STRING, gobject.TYPE_STRING,
                              gobject.TYPE_BOOLEAN)

        storageViewColumns = (
         ("Storage Device", 550),
         ("LUN ID", 60),
         ("Capacity", 80),
        )

        populateViewColumns(view, storageViewColumns,
                            sensitive=SUPPORTED_DISK_ENTRY)
        view.set_model(model)

        def _selectable(path):
            '''Callback for GtkTreeView that determines whether or not a row
            can be selected.'''
            
            treeIter = model.get_iter(path)
            return model.get(treeIter, SUPPORTED_DISK_ENTRY)[0]
        
        sel = view.get_selection()
        sel.set_select_function(_selectable)

def setupVmfsVolumesView(view):
    if not view.get_columns():
        model = gtk.TreeStore(gobject.TYPE_STRING, gobject.TYPE_STRING,
                              gobject.TYPE_STRING)

        storageViewColumns = (
         ("Volume Name", 200),
         ("Capacity", 120),
         ("Free Space", 160),
        )

        populateViewColumns(view, storageViewColumns)
        view.set_model(model)

def setupPartitioningView(view):
    if not view.get_columns():
        model = gtk.TreeStore(gobject.TYPE_STRING, gobject.TYPE_STRING,
                              gobject.TYPE_STRING, gobject.TYPE_PYOBJECT)

        storageViewColumns = (
         ("Mount Point", 270),
         ("Type", 120),
         ("Size", 120),
        )

        populateViewColumns(view, storageViewColumns)
        view.set_model(model)

def populateStorageModel(view, scrolled, diskSet, vmfsSupport=True,
                         esxAndCos=True):
    ''' diskSet can be an instance of devices.DiskSet, or it can be a
    function that, when evaluated, returns a devices.DiskSet.  This is
    to support both static and dynamic usage of this function.
    '''
    if callable(diskSet):
        disks = diskSet()
    else:
        disks = diskSet

    def addEntry(model, iterType, disk, sensitive=True):
        name = truncateString(disk.name, DEVNAME_LENGTH)

        devModel = truncateString(disk.getVendorModelString(), DEVMODEL_LENGTH)
        devModel +=  " (%s)" % name

        lunId = ''
        if len(disk.pathIds) == 4:
            lunId = disk.pathIds[PATHID_LUN]

        diskIter = model.append(iterType,
            [devModel, lunId, disk.getFormattedSize(), entry, sensitive] )

        for pathString in disk.pathStrings:
            if pathString:
                newIterType = model.insert_before(diskIter, None)
                model.set_value(newIterType, 0, pathString)

   
    model = view.get_model()
    model.clear()

    localDiskIter = None
    remoteDiskIter = None

    eligible = partition.getEligibleDisks(vmfsSupport=vmfsSupport,
                                          esxAndCos=esxAndCos)

    for entry in disks.keys():
        if disks[entry].isControllerOnly():
            # Don't display these at all, see bug #273709
            continue

        sensitive = disks[entry] in eligible

        if disks[entry].local:
            if not localDiskIter:
                localDiskIter = model.insert_before(None, None)
                model.set_value(localDiskIter, 0, "Local Storage")
                model.set_value(localDiskIter, SUPPORTED_DISK_ENTRY, True)

            addEntry(model, localDiskIter, disks[entry], sensitive)
        else:
            if not remoteDiskIter:
                remoteDiskIter = model.insert_before(None, None)
                model.set_value(remoteDiskIter, 0, "Remote Storage")
                model.set_value(remoteDiskIter, SUPPORTED_DISK_ENTRY, True)

            addEntry(model, remoteDiskIter, disks[entry], sensitive)

    view.expand_all()
    scrolled.show_all()

    return model


def populateVmfsVolumesModel(view, scrolled, volumes):
    model = view.get_model()
    model.clear()

    iterType = model.insert_before(None, None)
    model.set_value(iterType, 0, "Datastores")

    for entry in volumes:
        name = entry.name

        size = util.formatValue(entry.getSize() / util.SIZE_MB)
        freeSpace = util.formatValue(entry.getFreeSize() / util.SIZE_MB)

        diskIter = model.append(iterType, [name, size, freeSpace])

    view.expand_all()
    scrolled.show_all()
    findFirstSelectableRow(model, view)

def populatePartitioningModel(view, scrolled, requests):
    model = view.get_model()
    model.clear()

    for request in requests:
        maxSize = ''
        grow = ''

        mountPoint = request.mountPoint
        fsType = request.fsType.name
        size = util.formatValue(request.minimumSize * util.SIZE_MB)

        diskIter = model.append(None,
            [mountPoint, fsType, size, request])

    view.expand_all()
    scrolled.show_all()

def getSelectionFromView(view, column=0):
    '''Get the data from a column which is selected in our view.'''

    (model, diskIter) = view.get_selection().get_selected()
    if diskIter and model.get(diskIter, column)[0]:
        return model.get(diskIter, column)[0]
    return None

def findFirstSelectableRow(model, view, sensitiveColumn=None):
    parent = None
    row = model.get_iter_first()

    while row:
        if model.iter_has_child(row):
            parent = row
            #row = model.iter_children(parent)
            row = model.iter_nth_child(parent, 0)
            continue
        elif sensitiveColumn is not None \
                and not model.get(row, sensitiveColumn)[0]:
            row = model.iter_next(row)
        else:
            path = model.get_path(row)
            column = view.get_column(0)
            view.set_cursor(path)
            break

def getPartitionRequestSize(dev):
    size = 0
    size += userchoices.getPhysicalPartitionRequests(dev).getMinimumSize()

    return size

EXISTING_DATA_CLEAR_DRIVE = 0
EXISTING_DATA_PRESERVE_VMFS = 1
EXISTING_DATA_STAY_ON_SCREEN = -1


def promptDeviceHasExistingData(deviceName, allowPreserve=True):
    foundVmfs = False
    foundEsx = False
    foundVmfs2 = False

    datastoreName = ""

    foundEsx = devices.runtimeActionFindExistingEsx(deviceName)

    datastoreSet = datastore.DatastoreSet()

    for part in devices.DiskSet()[deviceName].partitions:
        if part.nativeType == 0xfb:
            foundVmfs = True
            break

    # if we found vmfs2 partitions don't attempt to preserve them
    if foundVmfs:
        datastores = datastoreSet.getEntriesByDriveName(deviceName)
        if len(datastores) > 0:
            datastoreName = datastores[0].name
        else:
            foundVmfs2 = True

    if foundEsx and foundVmfs and allowPreserve and not foundVmfs2:
        return PreserveDatastoreWindow(datastoreName).run()
    elif foundEsx and foundVmfs and not foundVmfs2:
        text = STORAGE_DATASTORE_TEXT % datastoreName
        return ConfirmDatastoreDeletionWindow(text).run()
    elif foundEsx and not foundVmfs2:
        text = STORAGE_ESX_TEXT
    elif foundVmfs:
        text = STORAGE_DATASTORE_VMFS2_TEXT
        if datastoreName:
            text = STORAGE_DATASTORE_TEXT % datastoreName
        return ConfirmDatastoreDeletionWindow(text).run()
    else:
        text = STORAGE_TEXT

    window = MessageWindow(None, '', text, type='okcancel', useMarkup=True)
    if window.affirmativeResponse:
        return EXISTING_DATA_CLEAR_DRIVE

    return EXISTING_DATA_STAY_ON_SCREEN

class StorageDetailsWindow(CommonWindow):
    def __init__(self, drive):
        CommonWindow.__init__(self)
        gladePath = os.path.join(
            os.path.dirname(__file__), 'glade/storage-widgets.glade')
        self.xml = gtk.glade.XML(gladePath)

        self.drive = drive
        self.diskSet = devices.DiskSet()
        self.disk = self.diskSet[drive]
        self.datastoreSet = datastore.DatastoreSet()

        self.dialog = self.xml.get_widget('details')

        self.setLabels()

        self.addFrameToWindow()

        self.dialog.set_position(gtk.WIN_POS_CENTER)
        self.dialog.show_all()

    def setLabels(self):
        typeLabel = 'Local'
        if not self.disk.local:
            typeLabel = 'Remote'

        try:
            targetId = str(self.disk.vmkLun.GetPaths()[0].GetTargetNumber())
        except:
            targetId = "n/a"

        lunId = '0'
        if len(self.disk.pathIds) == 4:
            lunId = str(self.disk.pathIds[PATHID_LUN])

        existingEsxLabel = "No"
        if devices.runtimeActionFindExistingEsx(self.drive):
            existingEsxLabel = "Yes"

        datastoreNames = [ds.name for ds in self.datastoreSet.getEntriesByDriveName(self.drive)]
        datastoreLabel = ', '.join(datastoreNames)

        if not datastoreLabel:
            datastoreLabel = "None"

        settings = {
          'DetailsModelLabel' : self.disk.getVendorModelString(),
          'DetailsDiskLabel' : self.drive,
          'DetailsTypeLabel' : typeLabel,
          'DetailsLunIdLabel' : lunId,
          'DetailsTargetIdLabel' : targetId,
          'DetailsCapacityLabel' : self.disk.getFormattedSize(),
          'DetailsExistingEsxLabel' : existingEsxLabel,
          'DetailsPathLabel' : self.disk.path,
          'DetailsDatastoreLabel' : datastoreLabel,
        }

        for widget, value in settings.iteritems():
            self.xml.get_widget(widget).set_text(value)

    def run(self):
        self.dialog.run()
        self.dialog.hide_all()


class GenericDialogWithCheckButtonWindow(CommonWindow):
    def __init__(self, settings):
        CommonWindow.__init__(self)
        gladePath = os.path.join(
            os.path.dirname(__file__), 'glade/storage-widgets.glade')
        self.xml = gtk.glade.XML(gladePath)

        self.dialog = self.xml.get_widget(settings['dialog'])

        self.text = self.xml.get_widget(settings['text'])

        self.okButton = self.xml.get_widget(settings['okButton'])
        self.cancelButton = self.xml.get_widget(settings['okButton'])
        self.checkButton = self.xml.get_widget(settings['checkButton'])

        self.rc = 1

        connectSignalHandlerByDict(self, self.__class__.__name__, self.xml,
          { (settings['cancelButton'], 'clicked') : 'cancelClicked',
            (settings['okButton'], 'clicked') : 'okClicked',
            (settings['checkButton'], 'toggled') : 'checkbuttonToggled',
          })

        self.addFrameToWindow()

        self.dialog.set_position(gtk.WIN_POS_CENTER)

        self.dialog.connect("key-press-event", self.keypress)

    def run(self):
        self.dialog.run()
        self.dialog.hide()

        return self.rc

    def cancelClicked(self, *args):
        self.rc = -1

    def okClicked(self, *args):
        if self.checkButton.get_active():
            self.rc = 1
        else:
            self.rc = 0

    def checkbuttonToggled(self, *args):
        pass

    def keypress(self, widget, event):
        if event.keyval == gtk.keysyms.Escape:
            log.debug("GenericDialogWithCheckButtonWindow: Escape key pressed")
            self.rc = -1

class PreserveDatastoreWindow(GenericDialogWithCheckButtonWindow):
    def __init__(self, datastoreName):
        settings = {
            'dialog' : 'preservedatastore',
            'text' : 'PreserveLabel',
            'checkButton' : 'PreserveCheckButton',
            'okButton' : 'PreserveOkButton',
            'cancelButton' : 'PreserveCancelButton',
        }

        GenericDialogWithCheckButtonWindow.__init__(self, settings)

        self.text.set_markup(STORAGE_ESX_DATASTORE_TEXT % datastoreName)
        self.dialog.show()

class PreserveCosVmdkWindow(GenericDialogWithCheckButtonWindow):
    def __init__(self, showPreserve=True):
        settings = {
            'dialog' : 'preservevmdk',
            'text' : 'PreservevmdkLabel',
            'checkButton' : 'PreservevmdkCheckButton',
            'okButton' : 'PreservevmdkOkButton',
            'cancelButton' : 'PreservevmdkCancelButton',
        }

        GenericDialogWithCheckButtonWindow.__init__(self, settings)
        self.text.set_text(COSVMDK_FREESPACE)

        if not showPreserve:
            self.checkButton.hide()
            self.text.set_text(COSVMDK_NO_FREESPACE)

        self.dialog.show()

class ConfirmDatastoreDeletionWindow(GenericDialogWithCheckButtonWindow):
    def __init__(self, text):
        settings = {
            'dialog' : 'deletedisk',
            'text' : 'DeletediskLabel',
            'checkButton' : 'DeletediskCheckButton',
            'okButton' : 'DeletediskOkButton',
            'cancelButton' : 'DeletediskCancelButton',
        }

        GenericDialogWithCheckButtonWindow.__init__(self, settings)

        # OK button should not be sensitive by default
        self.okButton.set_sensitive(False)

        self.text.set_markup(text)
        self.dialog.show()

    def okClicked(self, *args):
        # always set the disk to be deleted if the "OK" button was pressed
        self.rc = 0

    def checkbuttonToggled(self, *args):
        self.okButton.set_sensitive(self.checkButton.get_active())


