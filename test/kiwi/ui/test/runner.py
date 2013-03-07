#
# Kiwi: a Framework and Enhanced Widgets for Python
#
# Copyright (C) 2006 Async Open Source
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
# Author(s): Johan Dahlin <jdahlin@async.com.br>
#

"""
Runner - executes recorded scripts
"""

import doctest
import shutil
import gtk
import sys
import time
import operator
import code
import re
from StringIO import StringIO

import gobject
from gtk import gdk

from kiwi.log import Logger
from kiwi.ui.test.common import WidgetIntrospecter

log = Logger('kiwi.ui.test.player')

interactiveModeHeader = '''
____________________Interactive Mode______________________
You can now enter commands that will execute in the
namespace of the doctest.  Ctrl-D to exit.
__________________________________________________________
'''

class NotReadyYet(Exception):
    pass

class MissingWidget(KeyError):
    def __init__(self, msg, win):
        KeyError.__init__(self, msg)
        
        self._win = win

class TestMismatch(Exception):
    pass

class MagicWindowWrapper(object):
    def __init__(self, window, ns):
        self.window = window

        window.set_keep_below(True)
        window.set_keep_below(False)
        
        self.ns = ns

    def delete(self):
        self.window.emit('delete-event', gdk.Event(gdk.DELETE))
        self.window.destroy()

    def __getattr__(self, attr):
        if not attr in self.ns:
            log.error("Could not find widget -- %s" % attr)
            log.error("List of available widgets:")
            for name, widget in self.ns.items():
                label = ""
                try:
                    label = widget.get_property("label")
                except TypeError:
                    pass
                log.error("  %s: %s" % (name, label))
            raise MissingWidget(attr, self)
        return self.ns[attr]

# Override some StringIO methods.
class _SpoofOut(StringIO):
    def getvalue(self):
        result = StringIO.getvalue(self)
        # If anything at all was written, make sure there's a trailing
        # newline.  There's no way for the expected output to indicate
        # that a trailing newline is missing.
        if result and not result.endswith("\n"):
            result += "\n"
        # Prevent softspace from screwing up the next test case, in
        # case they used print with a trailing comma in an example.
        if hasattr(self, "softspace"):
            del self.softspace
        return result

    def truncate(self,   size=None):
        StringIO.truncate(self, size)
        if hasattr(self, "softspace"):
            del self.softspace

def ensureStdout(func):
    '''Ensure that a function is called with the real stdout in sys.stdout.

    The Runner._iterate method can be nested inside other calls to _iterate, so
    we need to make sure the output goes to the console instead of the fake
    captured output for the doctest.'''
    saved_stdout = sys.stdout
    
    def _wrapper(*args, **kwargs):
        try:
            oldStdout = sys.stdout
            sys.stdout = saved_stdout
            return func(*args, **kwargs)
        finally:
            sys.stdout = oldStdout

    return _wrapper

class Runner(object):
    """
    Create a new Runner object.
    @ivar parser:
    """
    def __init__(self, filename):
        self.parser = doctest.DocTestParser()
        self.retval = 0

        self._filename = filename
        self._default_duration = 0.01
        self._prompt = False
        self._interact = False
        self._pos = 0
        self._windows = {}
        self._ns = {}
        self._source_id = -1
        self._stmts = self.parser.get_examples(open(filename).read())
        self._checker = doctest.OutputChecker()
        # Create a fake output target for capturing doctest output.
        self._fakeout = _SpoofOut()
        self._stdout = sys.stdout
        self._options = (doctest.ELLIPSIS |
                         doctest.REPORT_ONLY_FIRST_FAILURE |
                         doctest.REPORT_UDIFF)

        self._updateFile = False

        self._caughtExceptions = [] # list of (exception,traceback) pairs

        wi = WidgetIntrospecter()
        wi.register_event_handler()
        wi.connect('window-added', self._on_wi__window_added)
        wi.connect('window-removed', self._on_wi__window_removed)

    # Callbacks

    def _on_wi__window_added(self, wi, window, name, ns):
        log.info('Window added: %s' % (name,))
        self._windows[name] = MagicWindowWrapper(window, ns)

        self._iterate()

    def _on_wi__window_removed(self, wi, window, name):
        log.info('Window removed: %s' % (name,))
        del self._windows[name]

        self._iterate()

    # Private
    @ensureStdout
    def _run(self, ex):
        if hasattr(doctest, 'SKIP') and ex.options.get(doctest.SKIP, False):
            return
        
        save_stdout = sys.stdout
        sys.stdout = self._fakeout

        try:
            exec compile(ex.source, self._filename,
                         'single', 0, 1) in self._ns
        finally:
            sys.stdout = save_stdout

        got = self._fakeout.getvalue()
        self._fakeout.truncate(0)
        if not self._checker.check_output(ex.want, got, self._options):
            msg = self._checker.output_difference(ex, got, self._options)
            
            wanted = " nothing"
            if ex.want is not None:
                wanted = ":\n%s" % ex.want
            msg2 = "\nERROR at %s:%d\n" \
                "    >>> %s\n" \
                "Expected%s\nGot:\n%s\n" \
                % (self._filename, ex.lineno, ex.source, wanted, got[:-1])
            if self._prompt:
                sys.stderr.write(msg)
                answer = raw_input("Update test file (y/N)? ")
                if answer and answer.lower().startswith("y"):
                    ex.want = got
                    self._updateFile = True
                    return
            if self._interact:
                # import side-effect laden readline only when we need it
                import readline
                readline.parse_and_bind('tab: complete')
                code.interact(interactiveModeHeader, raw_input, self._ns)
                
            self._updateFile = False
            raise TestMismatch(msg)

    @ensureStdout
    def _checkForRenamedWidget(self, example, missingException):
        if not self._prompt:
            return False

        for name, widget in missingException._win.ns.items():
            try:
                label = widget.get_property("label")
                if ("%s\n" % repr(label)) == example.want:
                    print "\nnotice: Widget %s renamed to '%s'." % (
                        str(missingException), name)
                    answer = raw_input("Update test file (y/N)? ")
                    if answer and answer.lower().startswith("y"):
                        example.source = example.source.replace(
                            missingException.message, name)
                        self._updateFile = True
                        return True
            except TypeError:
                continue

        return False
    
    def _iterate(self):
        stmts = self._stmts
        while True:
            if self._pos == len(stmts):
                self.quit()
                break

            ex =  stmts[self._pos]
            self._pos += 1

            log.info('Executing line %d:%r' % (ex.lineno, ex.source[:-1],))
            try:
                self._run(ex)
            except NotReadyYet:
                self._pos -= 1
                break
            except (SystemExit, KeyboardInterrupt):
                log.info("exiting")
                raise
            except MissingWidget, e:
                log.info(str(e))
                if not self._checkForRenamedWidget(ex, e):
                    traceback = sys.exc_info()[2] #2.4 lacks sys.last_traceback
                    self._caughtExceptions.append((e, traceback))
                    self._pos = len(stmts)
                    gtk.main_quit()
                    break
            except Exception, e:
                log.exception("Exception caught by kiwi")
                traceback = sys.exc_info()[2] #2.4 lacks sys.last_traceback
                self._caughtExceptions.append((e, traceback))
                self._pos = len(stmts)
                gtk.main_quit()
                break

            gtk.gdk.flush()
            while gtk.events_pending():
                gtk.main_iteration(False)
                
            log.debug('Executed %r' % (ex.source[:-1],))
            self._last = time.time()

    # Public API

    def quit(self):
        return

    def start(self):
        self._last = time.time()

    def sleep(self, duration=None):
        if not duration:
            duration = self._default_duration
        
        # We don't want to block the interface here which means that
        # we cannot use time.sleep.
        # Instead we schedule another execute iteration in the future
        # and raises NotReadyYet which stops the interpreter until
        # iterate is called again.

        def _iter():
            # Turn ourselves off and allow future calls to wait() to
            # queue new waits.
            self._source_id = -1

            # Iterate, which will call us again
            self._iterate()

            return False

        if self._source_id != -1:
            raise NotReadyYet

        # The delta is the last time we executed a statement minus
        delta = (self._last + duration) - time.time()
        if delta > 0:
            ms = int(delta * 1000)
            self._source_id = gobject.timeout_add(ms, _iter)
            raise NotReadyYet

        # Okay, we've waited enough, let's go back to business

    def waitopen(self, window_name):
        """
        Wait to open an window.
        @param window_name:
        """
        if not window_name in self._windows:
            raise NotReadyYet(window_name)
        return self._windows[window_name]

    def waitclose(self, window_name):
        """
        Wait to close an window.
        @param window_name:
        """
        if window_name in self._windows:
            raise NotReadyYet(window_name)

    def save(self):
        if not self._updateFile:
            return

        subber = re.compile(r'^\s*$', re.MULTILINE)
        
        shutil.copy(self._filename, "%s.old" % self._filename)
        test_file = open(self._filename, 'w')
        for stmt in self._stmts:
            src_lines = filter(operator.truth, stmt.source.split('\n'))
            doc_source = '\n... '.join(src_lines)
            # Need to replace blank lines with <BLANKLINE>
            if stmt.want:
                safe_wanted = subber.sub(
                    '<BLANKLINE>', stmt.want.rstrip()) + '\n'
            else:
                safe_wanted = ''
            test_file.write(">>> %s\n%s" % (doc_source, safe_wanted))
        test_file.close()

runner = None

def play_file(script, options, filename=None, args=None):
    """
    Run an script.
    @param script:
    @param filename:
    @param args:
    """

    global runner

    log.info('Running script %s' % script)
    runner = Runner(script)
    if options:
        runner._default_duration = options.duration
        runner._prompt = options.prompt
        runner._interact = options.interact

    if filename is None:
        fd = open(script)

        for line in fd:
            # Check for run: lines in the doctests
            # run: ....
            pos = line.find('run:')
            if pos != -1:
                rest = line[pos+5:]
                argv = eval(rest, {}, {})
                filename = argv[0]
                args = argv[1:]
    else:
        if args is None:
            args = []

    sys.argv = [filename] + args[:]

    try:
        wrappedGlobals = globals().copy()
        wrappedGlobals['__file__'] = sys.argv[0]
        wrappedGlobals['__name__'] = '__main__'
        execfile(sys.argv[0], wrappedGlobals, wrappedGlobals)
    finally:
        for exception, traceback in runner._caughtExceptions:
            raise exception, None, traceback

        runner.save()
