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

"""
Kiwi UI Test: command line interface
"""

import os
import optparse

from kiwi.log import set_log_level

def _play(options, filename, args):
    from kiwi.ui.test.runner import play_file

    play_file(filename, options, options.command, args)

def _record(options, filename, args):
    from kiwi.ui.test.recorder import Recorder

    verify_props = []
    if 'KIWI_VERIFY' in os.environ:
        verify_props = [
            value.strip() for value in os.environ['KIWI_VERIFY'].split(',')]
    recorder = Recorder(filename, verify_props)
    recorder.execute(args)
    
def main(args):
    parser = optparse.OptionParser()
    parser.add_option('', '--command', action="store",
                      dest="command")
    parser.add_option('', '--record', action="store",
                      dest="record")
    parser.add_option('-v', '--verbose', action="store_true",
                      dest="verbose")
    parser.add_option('-d', '--duration', action="store",
                      dest="duration", type="float", default=0.01)
    parser.add_option('-p', '--prompt', action="store_true",
                      dest="prompt")
    parser.add_option('-i', '--interact', action="store_true",
                      dest="interact")
    options, args = parser.parse_args(args)

    if 'DISPLAY' not in os.environ:
        import startx
        startx.startX()

    if options.record and options.command:
        raise SystemExit(
            "You can't specify a command and recording at the same time")
    if options.record:
        if options.verbose:
            set_log_level('recorder', 5)
        _record(options, options.record, args[1:])
    else:
        if len(args) < 2:
            raise SystemExit("Error: needs a filename to play")
        if options.verbose:
            set_log_level('player', 5)
        _play(options, args[1], args[2:])

if __name__ == "__main__":
    import sys

    main(sys.argv)
