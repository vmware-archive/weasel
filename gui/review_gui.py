
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
import pango
from htmltextview import HtmlTextView
import review
import media

class ReviewWindow:
    SCREEN_NAME = 'review'
    
    def __init__(self, controlState, xml):
        controlState.displayHeaderBar = True
        controlState.windowIcon = 'abouttoinstall.png'
        controlState.windowTitle = "Summary of installation settings"
        controlState.windowText = \
            "Review the summary of the installation settings"

        htmlTextView = HtmlTextView()
        htmlTextView.set_wrap_mode(gtk.WRAP_NONE)
        context = htmlTextView.get_pango_context()
        initialFont = context.get_font_description()
        # The review uses monospace, so get the font description for that at the
        # same size as the default font used by the text view.
        metrics = context.get_metrics(pango.FontDescription(
                'monospace, %d' % (initialFont.get_size() / pango.SCALE)))

        # Generate the list of tab stops from the column widths specified in
        # the review module.
        tabPosition = 0
        ta = pango.TabArray(len(review.COLUMN_WIDTHS), True)
        for index, charWidth in enumerate(review.COLUMN_WIDTHS):
            tabPosition += pango.PIXELS(
                metrics.get_approximate_char_width() * charWidth)
            ta.set_tab(index, pango.TAB_LEFT, tabPosition)

        htmlTextView.set_tabs(ta)
        
        buf = review.produceText()
        htmlTextView.display_html(buf)

        viewPort = xml.get_widget('ReviewViewPort')
        assert(viewPort)
        for child in viewPort.get_children():
            viewPort.remove(child)
        viewPort.add(htmlTextView)

        htmlTextView.show()

    def getNext(self):
        # Make sure the media is mounted before the user leaves the machine
        # unattended for the actual install.
        media.runtimeActionMountMedia()
