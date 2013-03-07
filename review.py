
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

import util
import fsset
import datastore
import partition
import userchoices
import networking

from xml.sax.saxutils import escape as unsafeHtmlEscape

# The widths of the columns used in the review text.  The first column is for
# the key names, the second is for the values, and the remaining are for the
# partition size/mount-point.  Currently, the partitions are the only item
# requiring more than one column so this works fine for now.  If we add another
# item that requires more columns of different sizes we'll have to figure
# something else out.
COLUMN_WIDTHS = [38, 10, 12, 20]

# The main template for the text to be displayed.  It's mostly a list of
# key/value pairs.  Any columnar alignment is done with tabs that are expected
# to be interpreted by the display code.
TEMPLATE = """
<span style="font-family: monospace">
%(keyStart)sLicense:%(keyEnd)s%(ralign)s%(license)s<br/>

%(keyStart)sKeyboard:%(keyEnd)s%(ralign)s%(keyboard)s<br/>

%(keyStart)sCustom Drivers:%(keyEnd)s%(drivers)s

%(keyStart)sESX Storage Device:%(keyEnd)s<br/>
%(subKeyStart)sName:%(subKeyEnd)s%(ralign)s%(esxDriveName)s<br/>
%(subKeyStart)sBoot Loader Location:%(subKeyEnd)s%(ralign)s%(bootLocation)s<br/>

%(keyStart)sDatastore:%(keyEnd)s<br/>
%(subKeyStart)sName:%(subKeyEnd)s%(ralign)s%(datastoreName)s<br/>
%(subKeyStart)sType:%(subKeyEnd)s%(ralign)s%(datastoreType)s<br/>
%(subKeyStart)sStorage Device:%(subKeyEnd)s%(ralign)s%(datastoreDev)s<br/>
%(subKeyStart)sService Console Partitions:%(subKeyEnd)s%(datastoreParts)s

%(keyStart)sNetworking for Service Console:%(keyEnd)s<br/>
%(subKeyStart)sNetwork Adapter:%(subKeyEnd)s%(ralign)s%(cosNic)s<br/>
%(subKeyStart)sVLAN ID:%(subKeyEnd)s%(ralign)s%(cosVlanID)s<br/>
%(cosNetworkTemplate)s

%(keyStart)sTime zone:%(keyEnd)s%(ralign)s%(timezone)s<br/>

%(keyStart)sNTP Server:%(keyEnd)s%(ralign)s%(ntpServer)s<br/>

%(mediaTemplate)s

</span>
"""

STATIC_NET_TEMPLATE = """
%(subKeyStart)sNetwork Settings:%(subKeyEnd)s%(ralign)sSet manually<br/>
%(subKeyStart)sIP Address:%(subKeyEnd)s%(ralign)s%(ip)s<br/>
%(subKeyStart)sSubnet Mask:%(subKeyEnd)s%(ralign)s%(netmask)s<br/>
%(subKeyStart)sGateway:%(subKeyEnd)s%(ralign)s%(gateway)s<br/>
%(subKeyStart)sPrimary DNS:%(subKeyEnd)s%(ralign)s%(nameserver1)s<br/>
%(subKeyStart)sSecondary DNS:%(subKeyEnd)s%(ralign)s%(nameserver2)s<br/>
%(subKeyStart)sHostname:%(subKeyEnd)s%(ralign)s%(hostname)s<br/>
"""

DHCP_NET_TEMPLATE = """
%(subKeyStart)sNetwork Settings:%(subKeyEnd)s%(ralign)sSet automatically using DHCP<br/>
"""

BASIC_MEDIA = """
%(keyStart)sMedia Location:%(keyEnd)s%(ralign)s%(mediaLocation)s<br/>
"""

DRIVE_MEDIA = """
%(keyStart)sMedia Location:%(keyEnd)s<br/>
%(subKeyStart)sDrive:%(subKeyEnd)s%(ralign)s%(mediaDrive)s<br/>
%(mediaISO)s
%(subKeyStart)sVersion:%(subKeyEnd)s%(ralign)s%(mediaVersion)s<br/>
"""

# Indentation levels as a number of spaces.
INDENT_LEVEL = [1, 5, 9]

def htmlEscape(rawStr):
    # XXX The sax escape function does not like 'None' values, so just to be
    # safe, always use str() on our input.
    return unsafeHtmlEscape(str(rawStr))

def _indentLevel(n):
    return '<verbatim value="' + INDENT_LEVEL[n]*' ' + '"/>'

def produceText():
    values = {
        "keyStart" : '%s<span style="font-weight: bold">' % _indentLevel(0),
        "keyEnd" : "</span>",
        
        "subKeyStart" : ('%s<span style="color: rgb(111, 111, 111); '
                         'font-weight: bold">' % _indentLevel(1)),
        "subKeyEnd" : "</span>",

        "ralign" : '<tabs count="1" />',
        
        "i1" : _indentLevel(1),
        "i2" : _indentLevel(2),

        "datastoreName" : '',
        "datastoreType" : '(none)',
        "datastoreDev" : '(none)',
        }

    reviewList = [
        reviewLicense,
        reviewKeyboard,
        reviewCustomDrivers,
        reviewBoot,
        reviewStorage,
        reviewCosNetwork,
        reviewTimezone,
        reviewTimedate,
        reviewInstallationSource,
        ]

    for func in reviewList:
        func(values)

    return TEMPLATE % values

def reviewLicense(values):
    choice = userchoices.getSerialNumber()
    if choice:
        values['license'] = \
            'Fully Licensed with serial number: %s' % str(choice['esx'])
    else:
        values['license'] = 'Evaluation mode'

def reviewKeyboard(values):
    choice = userchoices.getKeyboard()
    if choice:
        values['keyboard'] = htmlEscape(choice['name'])
    else:
        values['keyboard'] = 'default'

def reviewCustomDrivers(values):
    choices = userchoices.getSupplementaryDrivers()
    if not choices:
        values['drivers'] = '%(ralign)s(none)<br/>' % values
    else:
        values['drivers'] = ''
        for driver in choices:
            values['drivers'] += '%(ralign)s' % values
            values['drivers'] += '%s<br/>' % htmlEscape(driver['filename'])

def reviewBoot(values):
    choice = userchoices.getBoot()
    location = choice.get('location', userchoices.BOOT_LOC_MBR)
    if location == userchoices.BOOT_LOC_MBR:
        locationStr = 'Master Boot Record'
    elif location == userchoices.BOOT_LOC_PARTITION:
        locationStr = 'ESX partition'
    else:
        locationStr = 'Not installed'
    values['bootLocation'] = locationStr
    
def reviewStorage(values):
    allReqs = partition.PartitionRequestSet()

    values['esxDriveName'] = ""

    newVmfs = False
    devices = userchoices.getPhysicalPartitionRequestsDevices()
    for dev in devices:
        reqs = userchoices.getPhysicalPartitionRequests(dev)
        reqs.fitRequestsOnDevice()
        bootPart = reqs.findRequestByMountPoint('/boot')
        if bootPart:
            values['esxDriveName'] = htmlEscape(dev)

        for req in reqs:
            if isinstance(req.fsType, fsset.vmfs3FileSystem):
                newVmfs = True
                
        allReqs += reqs

    if newVmfs:
        values['datastoreType'] = 'New'
    else:
        values['datastoreType'] = 'Existing'

    vdevices = userchoices.getVirtualDevices()
    for vdevChoice in vdevices:
        vdev = vdevChoice['device']
        values['datastoreName'] = htmlEscape(vdev.vmfsVolume)
        if vdev.physicalDeviceName:
            values['datastoreDev'] = htmlEscape(vdev.physicalDeviceName)
        else:
            datastoreSet = datastore.DatastoreSet()
            cosVolume = datastoreSet.getEntryByName(vdev.vmfsVolume)
            values['datastoreDev'] = htmlEscape(cosVolume.driveName)

    vdeviceNames = userchoices.getVirtualPartitionRequestsDevices()
    for vdevName in vdeviceNames:
        reqs = userchoices.getVirtualPartitionRequests(vdevName)
        reqs.fitRequestsOnDevice()
        allReqs += reqs

    values['datastoreParts'] = ""
    allReqs.sort(sortByMountPoint=True)
    for req in allReqs:
        size = util.formatValue(req.apparentSize * util.SIZE_MB)
        if req.mountPoint:
            mountPoint = htmlEscape(req.mountPoint)
        else:
            mountPoint = ""

        values['datastoreParts'] += (
            '<tabs count="1" />%s'
            '<tabs count="1" /><verbatim value="%10s" />'
            '<tabs count="1" />%s<br/>' % (req.fsType.name, size, mountPoint))

def reviewCosNetwork(values):
    reviewNetwork(values, 'cos')

def reviewNetwork(values, networkType):
    """
    networkType is either 'cos' or 'vmk'.

    Used by reviewCosNetwork() and reviewIscsi()
    """
    if networkType == 'cos':
        nics = userchoices.getCosNICs()
        net = userchoices.getCosNetwork()
        xtraNetItems = ('gateway', 'nameserver1', 'nameserver2', 'hostname')
    elif networkType == 'vmk':
        nics = userchoices.getVmkNICs()
        net = userchoices.getVmkNetwork()
        xtraNetItems = ('gateway',)
    else:
        raise ValueError("Illegal arg to reviewNetwork")

    for nic in nics:
        values[networkType + 'Nic'] = htmlEscape(str(nic['device'].name))
        if nic['vlanID']:
            values[networkType + 'VlanID'] = str(nic['vlanID'])
        else:
            values[networkType + 'VlanID'] = '(none)'

        if nic['bootProto'] == 'static':
            values['ip'] = nic['ip']
            values['netmask'] = nic['netmask']
            for value in ['gateway', 'nameserver1', 'nameserver2', 'hostname']:
                if not net[value]:
                    values[value] = '(none)'
                else:
                    values[value] = net[value]
            
            values[networkType + 'NetworkTemplate'] = \
                STATIC_NET_TEMPLATE % values
        else:
            values[networkType + 'NetworkTemplate'] = \
                DHCP_NET_TEMPLATE % values

def reviewTimezone(values):
    choice = userchoices.getTimezone()

    values['timezone'] = htmlEscape(choice.get('tzName', 'default'))

def reviewTimedate(values):
    choice = userchoices.getTimedate()
    if choice and choice['ntpServer']:
        values['ntpServer'] = choice['ntpServer']
    else:
        values['ntpServer'] = "(none)"

def reviewInstallationSource(values):
    try:
        location = userchoices.getMediaLocation()
        if not location:
            media = userchoices.getMediaDescriptor()
            if media:
                values['mediaDrive'] = htmlEscape(media.getName())
                values['mediaVersion'] = htmlEscape(media.version)
                if media.isoPath:
                    values['isoPath'] = htmlEscape(media.isoPath)
                    values['mediaISO'] = (
                        '%(subKeyStart)sISO:%(subKeyEnd)s'
                        '%(ralign)s%(isoPath)s<br/>' % values)
                else:
                    values['mediaISO'] = ''
                values['mediaTemplate'] = DRIVE_MEDIA % values
            else:
                values['mediaLocation'] = 'DVD-ROM'
                values['mediaTemplate'] = BASIC_MEDIA % values
        else:
            rawLocation = location['mediaLocation']
            values['mediaLocation'] = htmlEscape(
                networking.utils.cookPasswordInFileResourceURL(rawLocation))
            values['mediaTemplate'] = BASIC_MEDIA % values
    except KeyError:
        values['mediaTemplate'] = ''
