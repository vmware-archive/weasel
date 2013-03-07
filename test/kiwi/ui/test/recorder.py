#
# Kiwi: a Framework and Enhanced Widgets for Python
#
# Copyright (C) 2005,2006,2008 Async Open Source
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
User interface event recorder and serializer.

This module provides an interface for creating, listening to
and saving events.
It uses the gobject introspection base class
L{kiwi.ui.test.common.WidgetIntrospecter} to gather widgets, windows and
other objects.

The user interfaces are saved in a format so they can easily be played
back by simply executing the script through a standard python interpreter.
"""

import atexit
import sys
import time

from gtk import gdk
import gtk

from kiwi.log import Logger
from kiwi.ui.test.common import WidgetIntrospecter, flatten_tree

try:
    from gobject import add_emission_hook
    add_emission_hook # pyflakes

    # XXX needed for add_emission_hook('delete-event'), something is not
    # initialized correctly.
    gtk.Window().destroy()
except ImportError:
    try:
        from kiwi._kiwi import add_emission_hook
        add_emission_hook # pyflakes
    except ImportError:
        add_emission_hook = None

_events = []

log = Logger('recorder')

def register_event_type(event_type):
    """
    Add an event type to a list of event types.

    @param event_type: a L{Event} subclass
    """
    if event_type in _events:
        raise AssertionError("event %s already registered" % event_type)
    _events.append(event_type)

def get_event_types():
    """
    Returns the collection of event types.
    @returns: the event types.
    """
    return _events

class SkipEvent(Exception):
    pass

class Event(object):
    """
    Event is a base class for all events.
    An event represent a user change of an interactive widget.
    @cvar object_type: subclass for type, L{Recorder} uses this to
      automatically attach events to objects when they appear
    """
    object_type = None
    def __init__(self, obj, name=None):
        """
        Create a new Event object.
        @param object: a gobject subclass
        @param name: name of the object, if None, the
          method get_name() will be called
        """
        self.obj = obj
        if name is None:
            name = obj.get_name()
        self.name = name

        topobj = self.get_toplevel(obj)
        if isinstance(topobj, gtk.Window):
            self.toplevel_name = topobj.get_name()
        else:
            raise SkipEvent

    # Override in subclass
    def get_toplevel(self, widget):
        """
        This fetches the toplevel widget for a specific object,
        by default it assumes it's a wiget subclass and calls
        get_toplevel() for the widget
    
        Override this in a subclass.
        """
        return widget.get_toplevel()

    def serialize(self):
        """
        Serialize the widget, write the code here which is
        used to reproduce the event, for a button which is clicked
        the implementation looks like this:

        >>> def serialize(self):
        >>> ... return '%s.clicked' % self.name

        @returns: string to reproduce event
        Override this in a subclass.
        """
        pass

class SignalEvent(Event):
    """
    A SignalEvent is an L{Event} which is tied to a GObject signal,
    L{Recorder} uses this to automatically attach itself to a signal
    at which point this object will be instantiated.

    @cvar signal_name: signal to listen to
    """
    signal_name = None
    def __init__(self, obj, name, args):
        """
        Create a new SignalEvent object.
        @param object:
        @param name:
        @param args:
        """
        Event.__init__(self, obj, name)
        self.args = args

    def connect(cls, obj, signal_name, cb):
        """
        Calls connect on I{object} for signal I{signal_name}.

        @param object: object to connect on
        @param signal_name: signal name to listen to
        @param cb: callback
        """
        obj.connect(signal_name, cb, cls, obj)
    connect = classmethod(connect)

#
# Special Events
#

class WindowDeleteEvent(Event):
    """
    This event represents a user click on the close button in the
    window manager.
    """

    def serialize(self):
        return '%s.delete()\n>>> runner.waitclose("%s")' % (
            self.name, self.name)
        
#
# Signal Events
#

class MenuItemActivateEvent(SignalEvent):
    """
    This event represents a user click on a menu item.
    It could be a toplevel or a normal entry in a submenu.
    """
    signal_name = 'activate'
    object_type = gtk.MenuItem

    def serialize(self):
        return '%s.%s.activate()' % (self.toplevel_name, self.name)
register_event_type(MenuItemActivateEvent)

class ImageMenuItemButtonReleaseEvent(SignalEvent):
    """
    This event represents a click on a normal menu entry
    It's sort of a hack to use button-press-event, instea
    of listening to activate, but we'll get the active callback
    after the user specified callbacks are called, at which point
    it is already too late.
    """
    signal_name = 'button-release-event'
    object_type = gtk.ImageMenuItem

    def get_toplevel(self, widget):
        parent = widget
        while True:
            widget = parent.get_data('parent-menu')
            if not widget:
                break
            parent = widget
        toplevel = parent.get_toplevel()
        return toplevel

    def serialize(self):
        return '%s.%s.activate()' % (self.toplevel_name, self.name)
register_event_type(ImageMenuItemButtonReleaseEvent)

class ToolButtonReleaseEvent(SignalEvent):
    """
    This event represents a click on a normal toolbar button
    Hackish, see L{ImageMenuItemButtonReleaseEvent} for more details.
    """
    signal_name = 'button-release-event'
    object_type = gtk.Button

    def serialize(self):
        return '%s.%s.activate()' % (self.toplevel_name, self.name)
register_event_type(ToolButtonReleaseEvent)

class EntrySetTextEvent(SignalEvent):
    """
    This event represents a content modification of a GtkEntry.
    When the user deletes, clears, adds, modifies the text this
    event will be created.
    """
    signal_name = 'notify::text'
    object_type = gtk.Entry

    def __init__(self, obj, name, args):
        SignalEvent.__init__(self, obj, name, args)
        self.text = self.obj.get_text()

    def serialize(self):
        return '%s.%s.set_text("%s")' % (
            self.toplevel_name, self.name, self.text)
register_event_type(EntrySetTextEvent)

class EntryActivateEvent(SignalEvent):
    """
    This event represents an activate event for a GtkEntry, eg when
    the user presses enter in a GtkEntry.
    """

    signal_name = 'activate'
    object_type = gtk.Entry

    def serialize(self):
        return '%s.%s.activate()' % (self.toplevel_name, self.name)
register_event_type(EntryActivateEvent)

# Also works for Toggle, Radio and Check
class ButtonClickedEvent(SignalEvent):
    """
    This event represents a button click.
    Note that this will also work for GtkToggleButton, GtkRadioButton
    and GtkCheckButton.
    """
    signal_name = 'clicked'
    object_type = gtk.Button

    def serialize(self):
        return '%s.%s.clicked()' % (self.toplevel_name, self.name)
register_event_type(ButtonClickedEvent)

# Also works for Toggle, Radio and Check
class TreeViewChangedEvent(SignalEvent):
    """
    This event represents a button click.
    Note that this will also work for GtkToggleButton, GtkRadioButton
    and GtkCheckButton.
    """
    signal_name = 'cursor_changed'
    object_type = gtk.TreeView

    def __init__(self, obj, name, args):
        SignalEvent.__init__(self, obj, name, args)

        (model, treeIter) = obj.get_selection().get_selected()
        self.path = model.get_path(treeIter)

    def serialize(self):
        return '%s.%s.set_cursor(%s)' % (
            self.toplevel_name, self.name, repr(self.path))
register_event_type(TreeViewChangedEvent)

class DrawingAreaPressEvent(SignalEvent):
    """
    This event represents a button press in a GtkDrawingArea.
    """
    signal_name = 'button_press_event'
    object_type = gtk.DrawingArea

    def __init__(self, obj, name, args):
        SignalEvent.__init__(self, obj, name, args)

        ev = gtk.get_current_event()
        self.x = ev.x
        self.y = ev.y

    def serialize(self):
        return 'drawing_event(%s.%s, gtk.gdk.BUTTON_PRESS, %f, %f)' % (
            self.toplevel_name, self.name, self.x, self.y)
register_event_type(DrawingAreaPressEvent)

class DrawingAreaReleaseEvent(SignalEvent):
    """
    This event represents a button release in a GtkDrawingArea.
    """
    signal_name = 'button_release_event'
    object_type = gtk.DrawingArea

    def __init__(self, obj, name, args):
        SignalEvent.__init__(self, obj, name, args)

        ev = gtk.get_current_event()
        self.x = ev.x
        self.y = ev.y

    def serialize(self):
        return 'drawing_event(%s.%s, gtk.gdk.BUTTON_RELEASE, %f, %f)' % (
            self.toplevel_name, self.name, self.x, self.y)
register_event_type(DrawingAreaReleaseEvent)

class VerifyEvent:
    property_name = None
    
    def __init__(self, obj):
        self.name = obj.get_name()
        self.directives = set()
        if self.property_name:
            self.value = repr(obj.get_property(self.property_name))
            if self.value == "''":
                # Empty strings tend to not be important, so ignore them by
                # default.
                self.directives.add("SKIP")
        else:
            self.value = None
        self.toplevel_name = obj.get_toplevel().get_name()

    def serializeDirectives(self):
        retval = ""
        if self.directives:
            retval = " #doctest: +%s" % (',+'.join(self.directives))

        return retval
        
    def serialize(self):
        return '%s.%s.get_property("%s")%s\n%s' % (
            self.toplevel_name, self.name, self.property_name,
            self.serializeDirectives(), self.value)

class VerifySensitive(VerifyEvent):
    property_name = "sensitive"

class VerifyFocus(VerifyEvent):
    property_name = "is-focus"

    def serialize(self):
        if self.value == "True":
            return '%s.%s.get_property("%s")\n%s' % (
                self.toplevel_name, self.name, self.property_name, self.value)
        else:
            return None

class VerifyLabel(VerifyEvent):
    property_name = "label"

class VerifyList(VerifyEvent):
    def __init__(self, obj):
        VerifyEvent.__init__(self, obj)

        self.value = flatten_tree(obj)

    def serialize(self):
        return 'print flatten_tree(%s.%s)\n%s' % (
            self.toplevel_name, self.name, self.value)

class ComboBoxChangedEvent(SignalEvent):
    signal_name = 'changed'
    object_type = gtk.ComboBox

    def __init__(self, combo, name, args):
        SignalEvent.__init__(self, combo, name, args)
        self.activeIndex = combo.get_active()
        self.activeText = combo.get_active_text()

    def serialize(self):
        return '%s.%s.set_active(%d)\n>>> %s.%s.get_active_text()\n%s' % (
            self.toplevel_name, self.name, self.activeIndex,
            self.toplevel_name, self.name,
            self.activeText)
register_event_type(ComboBoxChangedEvent)
    
# XXX: ComboMixin -> ???

# class KiwiComboBoxChangedEvent(SignalEvent):
#     """
#     This event represents a a selection of an item
#     in a L{kiwi.ui.widgets.combobox.ComboBoxEntry} or
#     L{kiwi.ui.widgets.combobox.ComboBox}.
#     """
#     signal_name = 'changed'
#     object_type = ComboMixin
#     def __init__(self, combo, name, args):
#         SignalEvent.__init__(self, combo, name, args)
#         self.label = combo.get_selected_label()

#     def serialize(self):
#         return '%s.select_item_by_label("%s")' % (self.name, self.label)

# register_event_type(KiwiComboBoxChangedEvent)

class Recorder(WidgetIntrospecter):
    """
    Recorder takes care of attaching events to widgets, when the appear,
    and creates the events when the user is interacting with some widgets.
    When the tracked program is closed the events are serialized into
    a script which can be played back with help of
    L{kiwi.ui.test.player.Player}.
    """

    def __init__(self, filename, verify_props=None):
        """
        Create a new Recorder object.
        @param filename: name of the script
        """
        WidgetIntrospecter.__init__(self)
        self.register_event_handler()
        self.connect('window-removed', self.window_removed)

        self._verify_props = verify_props
        self._filename = filename
        self._events = []
        self._listened_objects = []
        self._event_types = self._configure_event_types()
        self._args = None

        # This is sort of a hack, but there are no other realiable ways
        # of actually having something executed after the application
        # is finished
        atexit.register(self.save)

        # Register a hook that is called before normal delete-events
        # because if it's connected using a normal callback it will not
        # be called if the application returns True in it's signal handler.
        if add_emission_hook:
            add_emission_hook(gtk.Window, 'delete-event',
                              self._emission_window__delete_event)

    def execute(self, args):
        self._start_timestamp = time.time()
        self._args = args

        # Run the script
        sys.argv = args
        wrappedGlobals = globals().copy()
        wrappedGlobals['__file__'] = sys.argv[0]
        wrappedGlobals['__name__'] = '__main__'
        execfile(sys.argv[0], wrappedGlobals, wrappedGlobals)

    def _emission_window__delete_event(self, window, event, *args):
        self._add_event(WindowDeleteEvent(window))

        # Yes, please call us again
        return True

    def _configure_event_types(self):
        event_types = {}
        for event_type in get_event_types():
            if event_type.object_type is None:
                raise AssertionError
            elist = event_types.setdefault(event_type.object_type, [])
            elist.append(event_type)

        return event_types

    def _add_event(self, event, offset=0):
        if self._times:
            etime = self._times[-1]
        else:
            etime = self._last_time
        etime += offset
        log.info("%d: Added event %s" % (etime, event.serialize()))
        self._events.append((event, etime))

    def _add_verify_event(self, event):
        self._add_event(event, offset=1)
        if self._verify_props and event.property_name not in self._verify_props:
            # Add the SKIP option so this test is not run.  The user can edit
            # the file if they want the test to happen.
            event.directives.add("SKIP")
        
    def _listen_event(self, obj, event_type):
        if not issubclass(event_type, SignalEvent):
            raise TypeError("Can only listen to SignalEvents, not %r"
                            % event_type)

        if event_type.signal_name is None:
            raise ValueError("signal_name cannot be None")

        # This is horrible, but there's no good way of passing in
        # more than one variable to the script and we really want to be
        # able to connect it to any kind of signal, regardless of
        # the number of parameters the signal has
        def on_signal(obj, *args):
            event_type, orig = args[-2:]
            try:
                self._add_event(event_type(orig, None, args[:-2]))
            except SkipEvent:
                pass
        event_type.connect(obj, event_type.signal_name, on_signal)

    def window_removed(self, wi, window, name):
        # It'll already be trapped if we can use an emission hook
        # skip it here to avoid duplicates
        if not add_emission_hook:
            return
        self._add_event(WindowDeleteEvent(window))

    def parse_one(self, toplevel, gobj):
        WidgetIntrospecter.parse_one(self, toplevel, gobj)

        # mark the object as "listened" to ensure we'll always
        # receive unique objects
        if gobj in self._listened_objects:
            return
        self._listened_objects.append(gobj)

        hasEvents = False
        for object_type, event_types in self._event_types.items():
            if not isinstance(gobj, object_type):
                continue

            for event_type in event_types:
                # These 3 hacks should move into the event class itself
                if event_type == MenuItemActivateEvent:
                    if not isinstance(gobj.get_parent(), gtk.MenuBar):
                        continue
                elif event_type == ToolButtonReleaseEvent:
                    if not isinstance(gobj.get_parent(), gtk.ToolButton):
                        continue
                elif event_type == ButtonClickedEvent:
                    if isinstance(gobj.get_parent(), gtk.ToolButton):
                        continue
                if issubclass(event_type, SignalEvent):
                    self._listen_event(gobj, event_type)
                    hasEvents = True

        if hasEvents:
            self._add_verify_event(VerifySensitive(gobj))
            self._add_verify_event(VerifyFocus(gobj))
        if isinstance(gobj, gtk.Label):
            self._add_verify_event(VerifyLabel(gobj))
        if isinstance(gobj, gtk.TreeView):
            self._add_verify_event(VerifyList(gobj))

    def save(self):
        """
        Collect events and serialize them into a script and save
        the script.
        This should be called when the tracked program has
        finished executing.
        """

        if not self._events:
            return

        try:
            fd = open(self._filename, 'w')
        except IOError:
            raise SystemExit("Could not write: %s" % self._filename)

        fd.write(">>> None # -*- Mode: doctest -*-\n")
        fd.write(">>> None # run: %s\n" % repr(self._args))
        fd.write(">>> import gtk\n")
        fd.write(">>> from kiwi.ui.test.runner import runner\n")
        fd.write(">>> from kiwi.ui.test.common import flatten_tree, "
                 "drawing_event\n")
        fd.write(">>> runner.start()\n")

        windows = {}

        self._events.sort(lambda x, y: cmp(x[1], y[1]))
        last = self._events[0][1]
        # fd.write('>>> runner.sleep(%2.1f)\n' % (last - self._start_timestamp,))

        lastEvent = None
        for event, timestamp in self._events:
            if not isinstance(lastEvent, VerifyEvent):
                fd.write('>>> runner.sleep()\n')
            
            toplevel = event.toplevel_name
            if not toplevel in windows:
                fd.write('>>> %s = runner.waitopen("%s")\n' % (toplevel,
                                                               toplevel))
                windows[toplevel] = True

            if isinstance(event, WindowDeleteEvent):
                fd.write(">>> %s\n" % event.serialize())
                if not event.name in windows:
                    # Actually a bug
                    lastEvent = event
                    last = timestamp
                    continue
                del windows[event.name]
            else:
                flattened = event.serialize()
                if flattened:
                    fd.write(">>> %s\n" % flattened)

            lastEvent = event
            last = timestamp

        # fd.write('>>> runner.quit()\n')
        fd.close()
