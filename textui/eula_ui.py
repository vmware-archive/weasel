'''End User License Agreement.
'''

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

from log import log
import userchoices
import textengine
from textrunner import TextRunner
import textwrap, re

title = "End User License Agreement"

helpText = """\
You cannot install ESX unless you accept the terms outlined in the
End User License Agreement.

 <) Back

"""

disagreeAlert = """\
You can not install ESX unless you accept the terms outlined in
the End User License.
"""

prologAcceptText = """\
    To continue with the installation, please read and accept the
    end user license agreement.
"""

SCROLL_LIMIT = 18

def fmt(textin):
    """Format the EULA.  Caution:  Regular expression for formatting
    may depend on format of EULA text file.
    """

    # regex below assumes single line per paragraph.
    splitter = re.compile(r"[\t\r\n ]*\r?\n")

    # regex below assume multi-line paragraphs, but doesn't split out empty
    # first line followed by non-empty line.
    #splitter = re.compile(r"\r?\n[\t\r\n ]*\r?\n")

    textout = []
    for fragment in splitter.split(textin):
        textout += textwrap.wrap(fragment, 75)
        textout.append('')      # blank line
    while textout[-1] == '':
        textout.pop()           # remove trailing blank lines

    return textout

class EulaWindow(TextRunner):
    def __init__(self, filename=None):
        super(EulaWindow, self).__init__()
        self.substep = self.start
        if not filename:
            #filename = os.path.join(os.path.pardir, "eula.txt")
            filename = os.path.join(
                os.path.dirname(__file__), os.path.pardir, "eula.txt")
        self.userinput = None
        self.uiTitle = title
        try:
            rawtext = open(filename).read()
        except Exception, msg:
            log.error(msg)
            log.error("Couldn't load eula")
        try:
            formattedtext = fmt(rawtext)
            self.textlines = formattedtext
        except Exception, msg:
            log.error(msg)
            log.error("Couldn't convert eula")
        self.scrollable = None

    def start(self):
        self.setScrollEnv(self.textlines, SCROLL_LIMIT)
        self.setSubstepEnv( {'next': self.scrollDisplay } )

    def accept(self):
        if self.userinput == 'accept':
            accepted = True     # TODO: what was this for?
        else:
            self.error()
            return
        # register the choice
        userchoices.setAcceptEULA(True)
        self.setSubstepEnv({'next': self.stepForward})

    def error(self):
        "Error, but use same text as help."
        self.errorPushPop(self.uiTitle + ' (Error)', helpText)

    def help(self):
        self.helpPushPop(self.uiTitle + ' (Help)', helpText)

    def scrollDisplay(self):
        self.buildScrollDisplay(self.scrollable, self.uiTitle,
            self.accept, "'accept': accept license", allowStepBack=True,
            prolog=prologAcceptText)

