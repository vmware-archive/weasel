#! /usr/bin/python

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
signalconnect module

This module provides a generic way for Weasel windows to connect glade
widget signals to handlers (implemented as methods of the window objects)

This basically replaces the gtk.glade.XML function autoconnect(). That
function suffers from the fatal flaw that it doesn't expose handlerIDs.

It makes the critical assumption that there should only ever be one active
instance of a particular window.  It relies on this assumption by storing
numeric handlerIDs in a module-level dict keyed on the window class name.

'''

import re
from log import log

# classToHandlerIDsMap is a dict that maps classes to handlerID dicts.
# handlerID dicts map (widget,signalName) pairs to numeric handlerIDs
# Typically this data structure will look something like this:
# {
# <CosNetworkWindow at 0xee51d0>: 
#               {
#               (<GtkButton at 0x14c00f0>, 'clicked'): 1464L
#               }
# <DataStoreWindow at 0xf04bf0>:
#               {
#               (<GtkCheckButton at 0x174bbe0>, 'toggled'): 1462L,
#               (<GtkRadioButton at 0x174bb90>, 'toggled'): 1461L,
#               (<GtkButton at 0x174bb40>, 'clicked'): 1460L,
#               (<GtkButton at 0x174baf0>, 'clicked'): 1459L
#               }
# }
classToHandlerIDsMap = {}

#------------------------------------------------------------------------------
def getSignalHandlerID(windowClass, widget, signalName):
    '''returns a numeric handlerID'''
    return classToHandlerIDsMap[windowClass][(widget, signalName)]

#------------------------------------------------------------------------------
def connectSignalHandlerByDict(windowInstance, windowClass, xml,
                               widgetSignalToMethodMap):
    '''Connects multiple named handler methods to a widget signals.

    Ensures only one instance of the specified class can ever maintain a
    connection to a particular (widget, signalName) pair.

    widgetSignalToMethodMap must be a dict of the form
    {(widgetName, signalName) : methodName, ...}
    '''
    for (widgetName, signalName), methodName in widgetSignalToMethodMap.items():
        connectSignalHandlerByName(windowInstance, windowClass, xml,
                                   widgetName, signalName, methodName)

#------------------------------------------------------------------------------
def connectSignalHandlerByName(windowInstance, windowClass, xml,
                               widgetName, signalName, methodName):
    '''Connects the named handler method to a widget's signal.

    Ensures only one instance of the specified class can ever maintain a
    connection to a particular (widget,signalName) pair.
    '''
    global classToHandlerIDsMap
    widget = xml.get_widget(widgetName)
    if not widget:
        log.error('Widget %s was not found during signal connect' % widgetName)
        return
    disconnectSignalHandler(windowClass, widget, signalName)
    method = getattr(windowInstance, methodName)
    handlerID = widget.connect(signalName, method)
    if windowClass not in classToHandlerIDsMap:
        classToHandlerIDsMap[windowClass] = {}
    classToHandlerIDsMap[windowClass][(widget, signalName)] = handlerID

#------------------------------------------------------------------------------
def disconnectSignalHandler(windowClass, widget, signalName):
    global classToHandlerIDsMap
    if windowClass not in classToHandlerIDsMap:
        return
    handlerIDs = classToHandlerIDsMap[windowClass]
    key = (widget, signalName)
    if key not in handlerIDs:
        return
    handlerID = handlerIDs[key]
    widget.disconnect(handlerID)
    del handlerIDs[key]

#------------------------------------------------------------------------------
def disconnectAllSignalHandlers(windowClass):
    '''Given a window class, disconnect every signal handler for that
    class
    '''
    global classToHandlerIDsMap
    if windowClass not in classToHandlerIDsMap:
        return
    handlerIDs = classToHandlerIDsMap[windowClass]
    for (widget, signalName), handlerID in handlerIDs.items():
        widget.disconnect(handlerID)
        del handlerIDs[(widget, signalName)]
