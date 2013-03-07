
###############################################################################
# Copyright (c) 2008-2009 VMware, Inc.
#
# This file is part of Weasel.
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

import exception
import userchoices
import remote_files
import networking.utils
from log import log
from common_windows import MessageWindow
from packages import checkMediaRootIsValid
from signalconnect import connectSignalHandlerByDict


class HTTPInstallMediaWindow:
    SCREEN_NAME = 'httpmedia'
    
    def __init__(self, controlState, xml):
        controlState.displayHeaderBar = True
        controlState.windowIcon = 'network_media.png'
        controlState.windowTitle = "World Wide Web (HTTP) Installation"
        controlState.windowText = "Enter the URL for the ESX installation media"

        self.xml = xml

        connectSignalHandlerByDict(self, HTTPInstallMediaWindow, self.xml,
          { ('HttpProxyCheckButton', 'toggled'): 'toggleProxy',
            ('HttpProxyUserCheckButton', 'toggled'): 'toggleUserProxy',
          })

    def getNext(self):
        url = self.xml.get_widget('HttpUrlEntry').get_text().strip()

        try:
            networking.utils.sanityCheckUrl(url,
                                            expectedProtocols=['http','https'])
        except ValueError, msg:
            MessageWindow(None, 'Invalid Url', msg[0])
            raise exception.StayOnScreen

        if self.xml.get_widget('HttpProxyCheckButton').get_active():
            errors, proxy, port, proxyUser, proxyPass = self.getProxyValues()
            if errors:
                title, details = errors[0]
                MessageWindow(None, title, details)
                raise exception.StayOnScreen

            # Note: if a user clicks Next, Back, Back, the proxy will still be
            #       set, but that should be OK, because they'll have to come
            #       through either the HTTP or FTP screen again
            userchoices.setMediaProxy(proxy, port, proxyUser, proxyPass)
        else:
            userchoices.unsetMediaProxy()

        if not checkMediaRootIsValid(url):
            MessageWindow(None, 'Network Error',
                'There was an error trying to connect to the network server.')
            raise exception.StayOnScreen

        userchoices.setMediaDescriptor(None)
        userchoices.setMediaLocation(url)

    def getProxyValues(self):
        '''Returns errors, proxy, port, proxyUser, proxyPass.
        errors - a list of (title, detail) tuples.  Empty if input was valid
        '''
        errors = []
        proxy = self.xml.get_widget('HttpProxyEntry').get_text().strip()
        port = self.xml.get_widget('HttpProxyPortEntry').get_text().strip()
        try:
            networking.utils.sanityCheckIPorHostname(proxy)
        except ValueError, msg:
            errors.append(('HTTP Proxy Name Error', str(msg)))

        try:
            networking.utils.sanityCheckPortNumber(port)
        except ValueError, msg:
            errors.append(('HTTP Proxy Port Number Error', str(msg)))

        if self.xml.get_widget('HttpProxyUserCheckButton').get_active():
            proxyUser = self.xml.get_widget('HttpProxyUsernameEntry').get_text()
            proxyUser = proxyUser.strip()
            proxyPass = self.xml.get_widget('HttpProxyPasswordEntry').get_text()

            if not proxyUser:
                errors.append(('Invalid user name',
                    'You need to specify a proxy user name and password'))
        else:
            proxyUser = ''
            proxyPass = ''

        return errors, proxy, port, proxyUser, proxyPass


    def toggleProxy(self, widget, *args):
        proxyTable = self.xml.get_widget('HttpProxyTable')
        proxyTable.set_sensitive(widget.get_active())

    def toggleUserProxy(self, widget, *args):
        proxyTable = self.xml.get_widget('HttpProxyUserTable')
        proxyTable.set_sensitive(widget.get_active())


