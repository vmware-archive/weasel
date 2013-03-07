#
# Kiwi: a Framework and Enhanced Widgets for Python
#
# Copyright (C) 2005,2006 Async Open Source
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307
# USA
#
# Author(s): Johan Dahlin <jdahlin@async.com.br
#

"""
Common routines used by other parts of the ui test framework.
"""

import re
import gobject
import gtk
import time
from gtk import gdk

from kiwi.utils import gsignal

from kiwi.log import Logger

log = Logger('common')

try:
    from gtk.gdk import event_handler_set
    event_handler_set # pyflakes
except ImportError:
    try:
        from kiwi._kiwi import event_handler_set
        event_handler_set # pyflakes
    except ImportError:
        event_handler_set = None

def find_in_tree(gobj, *columnValuePairs):
    retval = []

    def _visitor(model, path, titer, accum):
        found = True
        for colIndex, expectedValue in columnValuePairs:
            if colIndex >= model.get_n_columns():
                found = False
                break
            colValue = model.get(titer, colIndex)[0]
            if colValue != expectedValue:
                found = False
                break

        if found:
            accum.append(path)

    model = gobj.get_model()
    if model:
        model.foreach(_visitor, retval)

    return retval
        
FLATTEN_TYPES = [str, int, bool]

def flatten_tree(gobj, indent_level=0):
    retval = []
    
    def _visitor(model, path, titer, accum):
        cols = []
        for colIndex in range(model.get_n_columns()):
            colValue = model.get(titer, colIndex)[0]
            for colType in FLATTEN_TYPES:
                if isinstance(colValue, colType):
                    cols.append(colValue)
        accum.append((' ' * len(path) * 2) + repr(cols))

    model = gobj.get_model()
    if model:
        model.foreach(_visitor, retval)

    if not retval:
        return '(empty)'

    return '\n'.join(retval)

def drawing_event(gobj, eventType, x, y):
    ev = gtk.gdk.Event(eventType)
    ev.x = x
    ev.y = y
    ev.window = gobj.window
    ev.set_screen(gobj.get_screen())
    gtk.main_do_event(ev)

class WidgetIntrospecter(gobject.GObject):
    gsignal('window-added', object, str, object)
    gsignal('window-removed', object, str)

    def __init__(self):
        gobject.GObject.__init__(self)
        self._objects = {}
        self._id_to_obj = {} # GdkWindow -> GtkWindow
        self._windows = {} # toplevels ?
        self._times = []
        self._last_time = 0
        
    def _event_handler(self, event):
        # Separate method so we can use return inside
        self._check_event(event)
        self._times.append(event.get_time())
        gtk.main_do_event(event)
        last_time = self._times.pop()
        if last_time > self._last_time:
            self._last_time = last_time

    def _check_event(self, event):
        if not event.window:
            return

        window = event.window
        event_type = event.type
        window_type = window.get_window_type()
        try:
            widget = window.get_user_data()
        except ValueError:
            widget = self._id_to_obj.get(window)

        if not isinstance(widget, gtk.Window):
            return
        widget_name = widget.get_name()

        if event_type == gdk.MAP:
            if window_type != gdk.WINDOW_TOPLEVEL:
                # For non toplevels we only care about those which has a menu
                # as the child
                child = widget.child
                if not child or not isinstance(child, gtk.Menu):
                    return

                # Hack to get all the children of a popup menu in
                # the same namespace as the window they were launched in.
                parent_menu = child.get_data('parent-menu')
                if parent_menu:
                    main = parent_menu.get_toplevel()
                    widget_name = main.get_name()
            else:
                self._window_added(widget, widget_name)
                self._id_to_obj[window] = widget
        elif (event_type == gdk.DELETE or
              (event_type == gdk.WINDOW_STATE and
               event.new_window_state == gdk.WINDOW_STATE_WITHDRAWN)):
            self._window_removed(widget, widget_name)

    def _window_added(self, window, name):
        if name in self._windows:
            return
        self._windows[name] = window

        # Toplevel
        self.parse_one(window, window)
        ns = self._objects[name]
        self.emit('window-added', window, name, ns)

    def _window_removed(self, window, name):
        if not name in self._windows:
            # Error?
            return

        del self._windows[name]
        del self._objects[name]
        self.emit('window-removed', window, name)

    def _add_widget(self, toplevel, widget, name):
        toplevel_widgets = self._objects.setdefault(toplevel.get_name(), {})
        if name in toplevel_widgets:
            return

        toplevel_widgets[name] = widget

        # Listen to when the widget is removed from the interface, eg when
        # ::parent changes to None. At that time remove the widget and all
        # the children from the namespace.

        def on_widget__notify_parent(widget, pspec, name, widgets,
                                     signal_container):
            # Only take action when the widget is removed from a parent
            if widget.parent is not None:
                return

            for child_name, child in widgets.items():
                if child.is_ancestor(widget):
                    del widgets[child_name]
            widget.disconnect(signal_container.pop())

        signal_container = []
        sig_id = widget.connect('notify::parent', on_widget__notify_parent,
                                name, toplevel_widgets, signal_container)
        signal_container.append(sig_id)

    # Public API

    def register_event_handler(self):
        if not event_handler_set:
            raise NotImplementedError
        event_handler_set(self._event_handler)

    def parse_one(self, toplevel, gobj):
        if not isinstance(gobj, gobject.GObject):
            raise TypeError

        gtype = gobj
        while True:
            name = gobject.type_name(gtype)
            func = getattr(self, name, None)
            if func:
                if func(toplevel, gobj):
                    break
            if gtype == gobject.GObject.__gtype__:
                break

            gtype = gobject.type_parent(gtype)

    #
    # Special widget handling
    #

    def ignore(self, toplevel, gobj):
        pass

    GtkSeparatorMenuItem = GtkTearoffMenuItem = ignore

    def GtkWidget(self, toplevel, widget):
        """
        Called when a GtkWidget is about to be traversed
        """
        self._add_widget(toplevel, widget, widget.get_name())

    def GtkContainer(self, toplevel, container):
        """
        Called when a GtkContainer is about to be traversed

        Parsers all the children and listens for new children, which
        may be added at a later point.
        """
        counter = 0
        
        for child in container.get_children():
            if child.get_name().startswith("Gtk"):
                new_name = None
                try:
                    label = child.get_property("label")
                    if label and ' ' not in label:
                        new_name = "k%s%s" % (child.get_name(), label)
                except TypeError:
                    pass

                if not new_name:
                    # Make sure the default gtk names are unique.
                    new_name = "k%s%d" % (child.get_name(), counter)

                    counter += 1
                    
                    parent = child.get_parent()
                    while parent:
                        pname = parent.get_name().lower()
                        if 'vbox' not in pname and 'hbox' not in pname:
                            # Ignore intermediate layout junk.
                            new_name += parent.get_name()
                        parent = parent.get_parent()

                new_name_filtered = re.sub(r'[^\w]', '_', new_name)
                
                child.set_name(new_name_filtered)
        
        for child in container.get_children():
            self.parse_one(toplevel, child)

        def _on_container_add(container, widget):
            self.parse_one(toplevel, widget)
        container.connect('add', _on_container_add)

    def GtkDialog(self, toplevel, dialog):
        """
        Called when a GtkDialog is about to be traversed

        Just parses the widgets embedded in the dialogs.
        """
        self.parse_one(toplevel, dialog.action_area)
        self.parse_one(toplevel, dialog.vbox)

    def GtkMenuItem(self, toplevel, item):
        """
        Called when a GtkMenuItem is about to be traversed

        It does some magic to tie a stronger connection between toplevel
        menuitems and submenus, which later will be used.
        """
        submenu = item.get_submenu()
        if submenu:
            submenu.set_data('parent-menu', item)
            for child_item in submenu.get_children():
                child_item.set_data('parent-menu', item)
            self.parse_one(toplevel, submenu)

    def GtkToolButton(self, toplevel, item):
        item.child.set_name(item.get_name())

gobject.type_register(WidgetIntrospecter)
