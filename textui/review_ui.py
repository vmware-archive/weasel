
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

import htmllib
import StringIO
import formatter

from itertools import izip, cycle

import media
import review

from textengine import waitinput
from textrunner import TextRunner

SCROLL_LIMIT = 20

title = "Review"

listGuide = """\
[1: start the install, <enter>: forward, '<': back, '!': cancel, '?': help]"""

helpText = """\
Review your configuration and then press '1' to start the installation.

 <) Back

"""

class MyHTMLParser(htmllib.HTMLParser):
    def do_verbatim(self, attrs):
        for key, value in attrs:
            if key == 'value':
                self.formatter.add_literal_data(value)

    def do_tabs(self, attrs):
        for key, value in attrs:
            if key == 'count':
                self.formatter.add_literal_data('\t' * int(value))

def customTabStops(line, widths):
    """Convert single tabs into a particular number of spaces, based on the
    lengths given in the widths list.

    >>> customTabStops('foo\tbar\tbaz', [8, 6])
    'foo     bar   baz     '
    """
    
    retval = ''
    columns = line.split('\t')
    for col, width in izip(columns, cycle(widths)):
        retval += col.ljust(width)
    return retval

class ReviewWindow(TextRunner):
    def __init__(self):
        super(ReviewWindow, self).__init__()
        
        self.substep = self.start

        output = StringIO.StringIO()
        writer = formatter.DumbWriter(output)
        af = formatter.AbstractFormatter(writer)
        parser = MyHTMLParser(af)
        text = review.produceText()
        scrubbedText = text.replace('<br/>', '<br>')
        parser.feed(scrubbedText)

        self.textlines = []
        for line in output.getvalue().split('\n'):
            self.textlines.append(customTabStops(line, review.COLUMN_WIDTHS))

    def start(self):
        self.setScrollEnv(self.textlines, SCROLL_LIMIT)
        self.setSubstepEnv( {'next': self.scrollDisplay } )

    def help(self):
        self.pushSubstep()
        ui = {
            'title': title + ' (Help)',
            'body': helpText,
            'menu': { '*': self.popSubstep }
        }
        self.setSubstepEnv(ui)

    def scrollDisplay(self):
        # TODO:  Can this be migrated to TextRunner?
        lo = self.startStride
        hi = self.startStride + self.stride

        if lo == 0:
            backMethod = self.stepBack
        else:
            backMethod = self.scrollBack
        
        ui = {
            'title': title,
            'body': '\n'.join(self.scrollable[lo:hi]) + '\n' \
                + listGuide,
            'menu': {
                '': self.scrollForward,
                '<': backMethod,
                '1': self.checkMedia,
                '?': self.help,
                # '!': cancel added by TextRunner.run()
            }
        }
        self.setSubstepEnv(ui)

    def checkMedia(self):
        # Make sure the media is mounted before the user leaves the machine
        # unattended for the actual install.
        media.runtimeActionMountMedia()

        self.setSubstepEnv( {'next': self.stepForward } )
