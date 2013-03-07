
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

import os
import gtk
import iscsisetup_gui
import iscsinetwork_gui
from consts import DialogResponses
from log import log

_iscsiDialogs = [{}, {}] # [iscsinetwork, iscsisetup]

def go(storageWidgetUpdater, controlState):
    """
    Manage the two pop-up iSCSI configuration dialogs.

    #TODO: Suppose COS and iSCSI NICs are, in the first pass through the
    #      installer, set to be different.  But then the user backs up
    #      and changes the COS NIC to be the same as the iSCSI NIC.  Right
    #      now, we aren't detecting that (other than displaying the
    #      possibly inconsistent network settings in the review screen).
    #      Should we pop up a warning, and if so when?  (There's a similar
    #      problem if we go from COSNIC=iSCSINIC to COSNIC!=iSCSINIC.)
    """
    CLASS_WINDOW_NAME = 0
    CLASS = 1
    stepList = (('iscsinetwork', iscsinetwork_gui.iSCSINetworkWindow),
                ('iscsisetup',   iscsisetup_gui.iSCSISetupWindow))
    currStep = 0
    response = None
    while response not in [DialogResponses.CANCEL, DialogResponses.FINISH]:
        if not _iscsiDialogs[currStep]:
            _iscsiDialogs[currStep]['widget'] = gtk.Dialog(
                    title=stepList[currStep][0],
                    parent=controlState.gui.getWindow())

            windowName = stepList[currStep][CLASS_WINDOW_NAME]
            xml = gtk.glade.XML(
                os.path.join(os.path.dirname(__file__),
                             "glade/" + windowName + ".glade"))
            window = xml.get_widget(windowName)
            _iscsiDialogs[currStep]['xml'] = xml
                
            child = window.get_children()[0]
            window.remove(child)
            _iscsiDialogs[currStep]['widget'].vbox.pack_start(child)

        # This constructor is evaluated for its side effects, which
        # include initializing some of the subwidgets of window.
        try:
            stepList[currStep][CLASS](controlState,
                                  _iscsiDialogs[currStep]['xml'],
                                  _iscsiDialogs[currStep]['widget'])
        except RuntimeError, msg:
            log.debug("iscsi_detour.go(): " + str(msg))
            return
            # At this point, the iSCSI screen (which hasn't appeared and never
            # will) has popped up a message with more detail about what went
            # wrong.

        _iscsiDialogs[currStep]['widget'].show()
        response = _iscsiDialogs[currStep]['widget'].run()
        _iscsiDialogs[currStep]['widget'].hide()
        if response == DialogResponses.NEXT:
            currStep += 1
        elif response == DialogResponses.BACK:
            currStep -= 1
        elif response == DialogResponses.FINISH:
            # Should show iSCSI LUNs after this:
            storageWidgetUpdater()
            # TODO: need to call device.DiskSet.probeDisks() ??
