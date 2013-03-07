
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

import gobject
import pygtk
import pango
pygtk.require('2.0')
import gtk
import gtk.gdk
import sys
import string

class Signals:
    delete_event = "delete_event"
    insert_text = "insert-text"
    delete_text = "delete-text"
    focus_in = "focus-in-event"


class IP_Entry( gtk.Entry ):
    def __init__(self):
        gtk.Entry.__init__(self,max=15)

        # Until we can get this class to do what Bryan wants it to do, we'll
        # default to plain old gtk.Entry behavior.
        return

        font_desc = pango.FontDescription('monospace')
        self.modify_font(font_desc)
        self.set_width_chars(15)
        self.set_text('   .   .   .   ')
        self.show()

        self.insertTextHandlerID =\
            self.connect(Signals.insert_text, self.handleInsertText)
        self.deleteTextHandlerID =\
            self.connect_after(Signals.delete_text, self.handleDeleteText)

        self.connect(Signals.focus_in, self.handleFocusIn)
        #self.connect('key-press-event', self.handleKeypress)


    # TODO: get this to skip to the next widget, after the last octet.
    def handleKeypress(self, w, e):
        if gtk.gdk.keyval_name(e.keyval) == 'Tab':
            # Hopefully, that's more portable than relying on 65289 for 'tab'.
            pos = w.get_position()
            if pos < 3:
                self.moveCursor(4)
            elif pos < 7:
                self.moveCursor(8)
            elif pos < 11:
                self.moveCursor(12)
            else:
                self.moveCursor(0) # FIXME: We really want to go to next widget
            return True
        else:
            return False


    def handleFocusIn(self, w, e):
        if self.get_text() == '   .   .   .   ':
            self.moveCursor(0)
            # That doesn't work, if the IP_Entry is the only widget in its 
            # window :-(
        return False


    def delete_text_sterile(self, start, end):
        """
        Like gtk.Editable.delete_text, but disables our delete_text handler.
        """
        self.disableHandlers()
        self.delete_text(start,end)
        self.enableHandlers()


    def handleDeleteText(self,w,start,end):
        ltxt = list(w.get_text())
        ltxt.insert(start, (end-start)*' ')
        ltxt = list(''.join(ltxt))
        ltxt[3]=ltxt[7]=ltxt[11]='.'
        self.disableHandlers()
        w.set_text(''.join(ltxt))
        self.enableHandlers()
        self.moveCursor( start )
        if start in (4,8,12):
            self.moveCursor( start-1 )
            
        return False


    def disableHandlers(self):
            self.handler_block(self.insertTextHandlerID)
            self.handler_block(self.deleteTextHandlerID)
    def enableHandlers(self):
            self.handler_unblock(self.insertTextHandlerID)
            self.handler_unblock(self.deleteTextHandlerID)


    def moveCursor(self, pos):
        """
        gtk.Editable.set_position() does not actually move the cursor; it takes
        some extra voodoo.
        """
        self.disableHandlers()
        gobject.idle_add(lambda: self.set_position(pos))
        self.enableHandlers()

    def isValidIP(self, txt):
        if '.'!=txt[3]  or  '.'!=txt[7]  or  '.'!=txt[11]:
            return False
        if len(txt) > 15:
            return False
        for pos in 0, 4, 8, 12:
            try:
                triple = txt[pos:pos+3]
                if (triple!='   ') and (not 0 <= int(triple) <= 255):
                    return False
            except:
                return False

        return True


    def handleInsertText(self, w, newText, newTextLength, position):
        pos = w.get_position()

        # Figure out what the result of inserting this text would be, and if it
        # doesn't validate, reject it.
        ltxt = list(self.get_text())
        del ltxt[pos:pos+newTextLength]
        ltxt.insert(pos,newText)
        simulatedTxt = ''.join(ltxt)
        if not self.isValidIP(simulatedTxt):
            pass  # Rejected, 'cuz no room (need deletion).
        else:
            w.delete_text_sterile(pos,pos+newTextLength)
            if pos+newTextLength in (3,7,11):
                self.moveCursor(pos+newTextLength+1)
        return False


def padOut(txt):
    result = []
    for i in txt.split('.'):
        result.append( ' '*(3-len(i)) + i )
    return '.'.join(result)


if __name__ == "__main__":

  class Outer:

    def delete_event(self,widget,event,data=None):
        return False

    def destroy(self,widget,data=None):
        gtk.main_quit()


    def __init__(self):
        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.window.connect(Signals.delete_event,self.delete_event)
        self.window.set_border_width(10)
        self.window.set_title("ipEntry experiment")

        self.box = gtk.VBox(False,0)
        self.window.add( self.box )


        # An extra widget.  Without this, moveCursor(0) doesn't seem to work on
        # the IP_Entry.
        cb = gtk.CheckButton()
        self.box.pack_start( cb,True,False,10 )
        cb.show()

        ipEntry = IP_Entry()
        self.box.pack_start( ipEntry,True,False,10)
        self.box.show()
        self.window.show()

    def main(self):
        gtk.main()

  Outer().main()
