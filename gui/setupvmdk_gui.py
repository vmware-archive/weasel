
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

# Display the cos location window
import gobject
import gtk
import partition
import devices
import userchoices
import fsset
import storage_widgets
import exception
import util
import packages
import systemsettings

from log import log
from common_windows import CommonWindow
from common_windows import MessageWindow
from storage_widgets import STORAGEVIEW_DISK_ENTRY
from signalconnect import connectSignalHandlerByDict


sizeValues = [ "MB", "GB", "TB" ]

_partitionHandlersInitialized = False
_resetPartitions = True
_datastoreDevice = None

class SetupVmdkWindow:
    SCREEN_NAME = 'setupvmdk'
    
    def __init__(self, controlState, xml):
        controlState.displayHeaderBar = True
        controlState.windowIcon = 'partitioning.png'
        controlState.windowTitle = "Service Console Virtual Disk Image"
        controlState.windowText = \
            "Configure the service console virtual disk image"

        global _resetPartitions, _datastoreDevice

        # reset the vmdk partitions if the datastore device has been changed
        if userchoices.getEsxDatastoreDevice() != _datastoreDevice:
            _resetPartitions = True

        _datastoreDevice = userchoices.getEsxDatastoreDevice()

        self.xml = xml
        self.diskSet = devices.DiskSet()

        self.maxVmdkSize = devices.runtimeActionFindMaxVmdkSize()

        self.consoleVMSizeLabel = xml.get_widget("SetupvmdksizeLabel")
        self.view = xml.get_widget("SetupvmdkTreeView")
        self.scrolled = xml.get_widget("SetupvmdkScrolledWindow")

        # Download the package data so we can figure out the minimum partition
        # sizes
        weaselConfig = systemsettings.WeaselConfig()
        packagesXML = packages.getPackagesXML(weaselConfig.packageGroups)
        packageData = packages.PackageData(packagesXML.fullInstallDepot)

        self.fileSizes = packageData.fileDict

        self.requests = None
        self.newButton = xml.get_widget("SetupvmdkNewButton")
        self.deleteButton = xml.get_widget("SetupvmdkDeleteButton")

        if _resetPartitions:
            self._resetPartitions()
            _resetPartitions = False
            
        self.setupVirtualDevice()

        connectSignalHandlerByDict(self, SetupVmdkWindow, self.xml,
          { ('SetupvmdkNewButton', 'clicked') : 'newPartition',
            ('SetupvmdkEditButton', 'clicked') : 'editPartition',
            ('SetupvmdkDeleteButton', 'clicked') : 'deletePartition',
            ('SetupvmdkResetButton', 'clicked') : 'resetPartitions',
          })

        self.partitionWindow = PartitionWindow(xml, self)

        self.setButtons()


    def setConsoleVMSize(self):
        size = self.requests.getMinimumSize()
        self.consoleVMSizeLabel.set_text(util.formatValue(size * util.SIZE_MB))

    def setButtons(self):
        '''Set the sensitivity of the partition nav buttons'''

        # it's possible that the requests haven't been set up yet
        if not self.requests:
            self.deleteButton.set_sensitive(False)
            return

        self.deleteButton.set_sensitive(True)

        # add a 1MB fudge factor
        if self.requests.getMinimumSize() + 1 >= self.maxVmdkSize:
            self.newButton.set_sensitive(False)
        else:
            self.newButton.set_sensitive(True)


    def setupVirtualDevice(self):
        # If the virtual device has already been set up before, use the
        # the requests in it, otherwise start with a fresh set
        virtualDevs = userchoices.getVirtualDevices()
        assert len(virtualDevs) == 1

        virtualDev = virtualDevs[0]['device']

        # Update these since they might have been changed by the prev screen.
        virtualDev.physicalDeviceName = userchoices.getEsxDatastoreDevice()
        virtualDev.vmfsVolume = userchoices.getVmdkDatastore()

        self.requests = userchoices.getVirtualPartitionRequests(virtualDev.name)

        self.setConsoleVMSize()
        # TODO: If the datastore was changed and it is too small to fit the
        # current vmdk partitioning scheme we need to do a reset.
        
        storage_widgets.setupPartitioningView(self.view)
        storage_widgets.populatePartitioningModel(self.view, self.scrolled,
                                                  self.requests)

    def newPartition(self, *args):
        log.debug("New clicked")
        if len(self.requests) >= partition.MAX_PARTITIONS:
            MessageWindow(None, "Partition Error",
                "You can not add any additional partitions to this "
                "disk.")
            return
        self.partitionWindow.newEntry()

    def editPartition(self, *args):
        log.debug("Edit clicked")
        (model, diskIter) = self.view.get_selection().get_selected()
        if not diskIter:
            MessageWindow(None, "Partition Selection Error",
                "You must select a partition request to edit.")
        else:
            self.partitionWindow.editEntry(
                model.get(diskIter, STORAGEVIEW_DISK_ENTRY)[0])
            self.partitionWindow.show()

    def deletePartition(self, *args):
        log.debug("Delete clicked")
        (model, diskIter) = self.view.get_selection().get_selected()
        if not diskIter:
            MessageWindow(None, "Partition Selection Error",
                "You must select a partition request to delete.")
        else:
            window = MessageWindow(None, "Delete Partition Request",
                "Are you sure you want to remove this partition?",
                type='yesno')

            if window.affirmativeResponse:
                request = model.get(diskIter, STORAGEVIEW_DISK_ENTRY)[0]
                self.requests.remove(request)
                model.remove(diskIter)

                self.setConsoleVMSize()
                storage_widgets.populatePartitioningModel(self.view,
                    self.scrolled, self.requests)

                self.setButtons()

    def resetPartitions(self, *args):
        window = MessageWindow(None, "Reset Virtual Disk Image Partitions",
            "Resetting will cause any changes you have made "
            "to the Service Console partitions to be lost.\n\nAre you sure "
            "you would like to reset the partitions?", type='okcancel')

        if not window.affirmativeResponse:
            return

        self._resetPartitions()

    def _resetPartitions(self):
        partition.removeOldVirtualDevices()
        # Add the default virtual disk and the requests for it
        partition.addDefaultVirtualDriveAndRequests(
            physicalDeviceName=userchoices.getEsxDatastoreDevice(),
            vmfsVolume=userchoices.getVmdkDatastore())
        self.setupVirtualDevice()
        self.setButtons()

    def getNext(self):
        virtualDevs = userchoices.getVirtualDevices()
        assert len(virtualDevs) == 1

        # set the size of the vmdk
        virtualDevs[0]['device'].size = self.requests.getMinimumSize()

        errors = partition.sanityCheckPartitionRequests(checkSizing=True)
        if errors:
            msg = '\n\n'.join(errors)
            MessageWindow(None,
                          "Invalid Partition Layout",
                          "The following error(s) were detected with the "
                          "current partition layout:\n\n%s" % msg)
            raise exception.StayOnScreen


class PartitionWindow(CommonWindow):
    def __init__(self, xml, parent):
        CommonWindow.__init__(self)

        self.dialog = xml.get_widget("partition")
        self.xml = xml
        self.parent = parent

        # used to keep track if we're editing a partition or creating a new
        # one
        self.currentRequest = None

        connectSignalHandlerByDict(self, PartitionWindow, self.xml,
          { ('PartitionOkButton', 'clicked') : 'okClicked',
            ('PartitionCancelButton', 'clicked') : 'cancelClicked',
            ('PartitionfsComboBox', 'changed') : 'checkFs',
          })


        populateSizeEntries(xml.get_widget("PartitionsizeComboBox"))
        populateMountPoints(xml.get_widget("PartitionMountpointComboBoxEntry"))
        populateFsEntries(xml.get_widget("PartitionfsComboBox"))

        self.addFrameToWindow()

    def checkFs(self, widget, *args):
        """Make the mount point combo entry box insensitive if the
           file system type is un-mountable.
        """
        mountPointWidget = \
            self.xml.get_widget("PartitionMountpointComboBoxEntry")
        fsClass = widget.get_model()[widget.get_active()][1]

        if fsClass.mountable:
            mountPointWidget.set_sensitive(True)
        else:
            mountPointWidget.set_sensitive(False)

    def editEntry(self, entry):
        """Take a partition request and reconstruct our PartitionWindow
           from the request settings.
        """

        # XXX - might want to stick this into a hash
        mountPoint = self.xml.get_widget("PartitionMountpointComboBoxEntry")
        fsCombo = self.xml.get_widget("PartitionfsComboBox")
        minSizeEntry = self.xml.get_widget("PartitionminsizeEntry")
        minSizeCombo = self.xml.get_widget("PartitionsizeComboBox")
        maxSizeLabel = self.xml.get_widget("SetupvmdkmaxsizeLabel")

        mountPoint.child.set_text(entry.mountPoint)

        # Set the filesystem and mount point sensitivity
        for count, fsType in enumerate(fsCombo.get_model()):
            if fsType[1].name == entry.fsType.name:
                log.debug("Filesystem = " + entry.fsType.name)
                fsCombo.set_active(count)
                break
        self.checkFs(fsCombo)

        size, unit = util.formatValue(entry.minimumSize * util.SIZE_MB).split()
        minSizeEntry.set_text(size)
        minSizeCombo.set_active(sizeValues.index(unit))

        self.setMaxSize(entry.minimumSize)

        self.currentRequest = entry
        self.show()

    def newEntry(self):
        self.currentRequest = None
        self.setMaxSize()
        self.show()

    def setMaxSize(self, entrySize=0):
        '''Set the maximum size label'''
        maxSizeLabel = self.xml.get_widget("SetupvmdkmaxsizeLabel")
        size = self.parent.maxVmdkSize - self.parent.requests.getMinimumSize() \
            + entrySize
        maxSizeLabel.set_text(util.formatValue(size * util.SIZE_MB))

    def show(self):
        self.dialog.show_all()

    def hide(self):
        self.dialog.hide_all()

    def okClicked(self, *args):
        mountPoint = self.xml.get_widget("PartitionMountpointComboBoxEntry")
        mountPoint = mountPoint.child.get_text().strip()

        # instantiate a copy of the fs class selected
        widget = self.xml.get_widget("PartitionfsComboBox")
        fsClass = widget.get_model()[widget.get_active()][1]
        fsType = fsClass()

        if fsClass.mountable:
            if not mountPoint.startswith('/'):
                MessageWindow(None, "Mount Point Error",
                    "You have specified an invalid mount point.")
                return

            # don't allow trailing slashes
            if mountPoint != '/':
                mountPoint = mountPoint.rstrip('/')

            if mountPoint == '/boot':
                MessageWindow(None, "Mount Point Error",
                    "ESX reserves the '/boot' mount point for booting "
                    "the system.  Choose a different mount point for "
                    "this partition.")
                return
            elif mountPoint in partition.INVALID_MOUNTPOINTS:
                MessageWindow(None, "Mount Point Error",
                    "The '%s' directory can not be on a separate partition. "
                    "Choose a different mount point for this "
                    "partition." % mountPoint)
                return

            # check if we have an existing request with the same mount point
            # we can skip this check if we're editing an existing request
            # and it's the same value

            if not self.currentRequest or \
               self.currentRequest.mountPoint != mountPoint:
                for request in self.parent.requests:
                    if request.mountPoint == mountPoint:
                        MessageWindow(None, "Mount Point Error",
                            "The mount point you have specified for this "
                            "partition already exists.  Choose a "
                            "different mount point.")
                        return
        else:
            mountPoint = ""


        # figure out whether we're using MB/GB/TB
        minSize = self.xml.get_widget("PartitionminsizeEntry")
        minSizeCombo = self.xml.get_widget("PartitionsizeComboBox")

        minSize = getSizeFromWidgets(minSize, minSizeCombo)

        if minSize < fsType.minSizeMB:
            MessageWindow(None, "Size Error",
                "You must specify a partition size greater than or equal to %d "
                "MB." % fsType.minSizeMB)
            return

        request = partition.PartitionRequest(mountPoint=mountPoint,
            minimumSize=minSize, maximumSize=minSize, grow=False, fsType=fsType)

        # calculate the size of our current requests and subtract the current
        # request if we're editing
        size = self.parent.requests.getMinimumSize()

        if self.currentRequest:
            size -= self.currentRequest.minimumSize

        if size + minSize > self.parent.maxVmdkSize:
            MessageWindow(None, "Partition Error",
                "There is not enough room to add the requested partition.")
        else:
            # remove our current request before adding a new one
            if self.currentRequest:
                self.parent.requests.remove(self.currentRequest)

            self.parent.requests.append(request)
            self.parent.requests.sort()

            self.parent.setConsoleVMSize()

            storage_widgets.populatePartitioningModel(self.parent.view,
                self.parent.scrolled, self.parent.requests)

            self.parent.setButtons()
            self.hide()

    def cancelClicked(self, *args):
        log.debug("Cancel")
        self.hide()


def getSizeFromWidgets(entry, combo):
    '''Takes an entry and combo widget and determines the size in MB'''

    size = entry.get_text().strip()
    unit = combo.get_model()[combo.get_active()][0]

    assert unit in ["MB", "GB", "TB"]

    try:
        size = util.valueInMegabytesFromUnit(float(size), unit)
    except ValueError:
        MessageWindow(None, "Value Error",
            "You need to specify a value for the size of the "
            "partition request.")
        return -1
    return size


def populateSizeEntries(entry, default="MB"):
    """Fill a combobox w/ MB / GB / TB size entries"""

    if not entry.get_model():
        liststore = gtk.ListStore(gobject.TYPE_STRING)
        for size in sizeValues:
            liststore.append([size,])

        entry.set_model(liststore)
        renderer = gtk.CellRendererText()

        entry.pack_start(renderer, False)
        entry.add_attribute(renderer, 'text', 0)

        assert default in sizeValues
        entry.set_active(sizeValues.index(default))

def populateMountPoints(comboEntry):
    optionalPartitions = [ ("/", 3500), ("/home", 1500), ("/tmp", 1000),
                           ("/usr", 2000), ("/var", 1500) ]

    if not comboEntry.get_model():
        liststore = gtk.ListStore(gobject.TYPE_STRING)

        for partition in optionalPartitions:
            liststore.append([partition[0],])

        comboEntry.set_model(liststore)
        comboEntry.set_text_column(0)


def populateFsEntries(entry):
    """Fill a combo box w/ File System type entries"""

    if not entry.get_model():
        liststore = gtk.ListStore(gobject.TYPE_STRING,
                                  gobject.TYPE_PYOBJECT)
        fsTable = fsset.getSupportedFileSystems()
        fsTypes = fsTable.keys()
        fsTypes.sort()

        for fsType in fsTypes:
            # only add fs types which can be in a vmdk
            if fsTable[fsType].vmdkable:
                liststore.append([fsType, fsTable[fsType]])
                log.debug("Adding %s" % (fsTable[fsType]))

        entry.set_model(liststore)
        renderer = gtk.CellRendererText()

        entry.pack_start(renderer, False)
        entry.add_attribute(renderer, 'text', 0)

        entry.set_active(0)

