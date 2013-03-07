
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
import shlex
import util
from log import log
import xml.dom.minidom
from xml.dom.minidom import Node

import userchoices

from consts import HOST_ROOT

DEFAULT_LANG = "en_US.UTF-8"

# XML Helper functions
# ----------------------------------------------------------------------------
def fetchTextFromNode(node):
    data = ""
    for subTag in node.childNodes:
        if subTag.nodeType == Node.TEXT_NODE:
            data += subTag.data
    return data

def fetchTextFromElementByTagName(element, tag):
    data = ""
    subElements = element.getElementsByTagName(tag)
    for node in subElements:
        data += fetchTextFromNode(node)

    return data

def fetchTextFromFirstElementByTagName(element, tag):
    subElements = element.getElementsByTagName(tag)
    if subElements:
        return fetchTextFromNode( subElements[0] )
    else:
        return ''
# ----------------------------------------------------------------------------


class SystemSettings:
    pass


class WeaselConfig(SystemSettings):
    def parseConfigFile(self, fname='weasel.xml'):
        fpath = util.GetWeaselXMLFilePath(fname)
        doc = xml.dom.minidom.parse(fpath)

        name = ""
        for node in doc.getElementsByTagName("weasel_config"):
            for depot in node.getElementsByTagName("depot"):
                for group in depot.getElementsByTagName("package_group"):
                    self.packageGroups.append(fetchTextFromNode(group))

    def __init__(self):
        self.packageGroups = []
        self.parseConfigFile()


class RedHatSysconfig:
    def parseFile(self):
        if not self.filename:
            return

        try:
            f = open(self.filename, "r")
            fileContents = f.read()
            f.close()
        except IOError, e:
            log.debug("IOError opening %s (%s)" % (self.filename, e))
            log.debug("It is probably being newly created")
            return

        #removes comments and the quotes around values on the right hand side
        lines = shlex.split(fileContents, True)

        for line in lines:
            key, value = line.split('=', 1)
            self.dict[key] = value

    def getDictionary(self):
        return self.dict

    def setKeyVal(self, key, val):
        self.dict[key] = val

    def write(self):
        if not self.filename:
            return

        try:
            f = open(self.filename, "w")
        except IOError, e:
            log.error("IOError opening %s for write (%s)" % (self.filename, e))
            return

        for key, val in self.dict.items():
            f.write( '%s="%s"\n' % (key,val) )

        f.close()


    def __init__(self, filename=None):
        self.dict = {}
        self.filename = filename

        if self.filename:
            self.parseFile()

class _Keyboard:
    def __init__(self, keytable, name, layout, variant, model, options):
        self.keytable = keytable
        self.name = name
        self.layout = layout
        self.variant = variant
        self.model = model
        self.options = options
    
    def getKeytable(self):
        return self.keytable
    
    def getName(self):
        return self.name

    def setName(self, name):
        self.name = name

    def getLayout(self):
        return self.layout

    def setLayout(self, layout):
        self.layout = layout

    def getVariant(self):
        return self.variant

    def setVariant(self, variant):
        self.variant = variant

    def getModel(self):
        return self.model

    def setModel(self, model):
        self.model = model

    def getOptions(self):
        return self.options

    def setOptions(self, options):
        self.options = options

    def runtimeAction(self):
        # TODO: Figure out loadkeys, anaconda had a special one half written
        # in python that is different from the standard one.
        # args = ["/usr/bin/loadkeys", self.keytable]
        # rc = util.execWithLog(args[0], args)
        # assert rc == 0 # TODO: handle errors
        
        args = ["/usr/bin/setxkbmap",
                "-layout", self.layout,
                "-model", self.model]
        if self.variant:
            args.extend(["-variant", self.variant])
        if self.options:
            args.extend(["-option", self.options])

        rc = util.execWithLog(args[0], args)
        if rc != 0:
            errormsg = 'Cannot set keyboard to layout %s model %s' % \
                (self.layout, self.model)
            log.error(errormsg)
            raise RuntimeError(errormsg)

class SystemKeyboards(SystemSettings):
    KEYBOARD_LAYOUT = 0
    KEYBOARD_VARIANT = 1
    KEYBOARD_MODEL = 2
    KEYBOARD_OPTIONS = 3

    def parseKeyboardList(self, fname='keyboard.xml'):
        fpath = util.GetWeaselXMLFilePath(fname)
        doc = xml.dom.minidom.parse(fpath)

        for keyboard in doc.getElementsByTagName("keyboard"):
            keytable = fetchTextFromElementByTagName(keyboard, "keytable")
            name = fetchTextFromElementByTagName(keyboard, "name")
            layout = fetchTextFromElementByTagName(keyboard, "layout")
            variant = fetchTextFromElementByTagName(keyboard, "variant")
            model = fetchTextFromElementByTagName(keyboard, "model")
            options = fetchTextFromElementByTagName(keyboard, "options")

            if keyboard.getAttribute("default"):
                self.setDefaultKeyboard(name)

            kb = _Keyboard(keytable, name, layout, variant, model, options)
            self.keyboards[name] = kb
            self.keytables[keytable] = kb

    def setDefaultKeyboard(self, name):
        self.defaultKeyboard = name

    def getDefaultKeyboard(self):
        return self.defaultKeyboard

    def getKeyboardNames(self):
        keyboards = self.keyboards.keys()
        keyboards.sort()
        return keyboards

    def getKeyboardSettingsByName(self, name):
        return self.keyboards.get(name, None)

    def getKeyboardSettingsByKeytable(self, keytable):
        return self.keytables.get(keytable, None)
    
    def getKeyboards(self):
        return self.keyboards

    def __init__(self, fname='keyboard.xml'):
        self.keyboards = {}
        self.keytables = {}
        self.defaultKeyboard = None
        self.parseKeyboardList(fname)


def hostActionKeyboard(_context):
    if not userchoices.getKeyboard():
        sk = SystemKeyboards()
        kb = sk.getKeyboardSettingsByName(sk.getDefaultKeyboard())
        userchoices.setKeyboard(kb.keytable,
                                kb.name,
                                kb.model,
                                kb.layout,
                                kb.variant,
                                kb.options)

    choice = userchoices.getKeyboard()
    
    configFile = RedHatSysconfig(
        os.path.join(HOST_ROOT, "etc/sysconfig/keyboard"))
    # KEYBOARDTYPE="(pc|sun)"
    #   Specifies whether the connected keyboard is ps/2 or sun.
    configFile.setKeyVal("KEYBOARDTYPE", "pc") # XXX
    # KEYTABLE="<keytable-name>"
    #   The name of the keytable file from /lib/kbd/keymaps/i386
    configFile.setKeyVal("KEYTABLE", choice['keytable'])
    configFile.write()

def hostActionLang(_context):
    # TODO: Add support for other languages.
    configFile = RedHatSysconfig(os.path.join(HOST_ROOT, "etc/sysconfig/i18n"))
    configFile.setKeyVal("LANG", DEFAULT_LANG)
    configFile.write()

if __name__ == "__main__":
    config = WeaselConfig()
    print config.packageGroups
