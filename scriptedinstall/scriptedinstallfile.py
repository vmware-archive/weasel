
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

import re
import sys
from itertools import takewhile

sys.path.append('..')
from log import log
import remote_files

class ScriptedInstallFile:

   def __init__(self, fileName):
      self.fileName = fileName
      if remote_files.isURL(self.fileName):
         fp = remote_files.remoteOpen(self.fileName)
         self.lines = fp.readlines()
      else:
         self.lines = open(fileName).readlines()
      self.lines = [line.replace('\r\n', '\n') for line in self.lines]
      self.index = -1
      self.keyWords = '^(%post|%pre|%packages|%vmlicense_text)'

   def __iter__(self):
      return self

   def next(self):
      r'''
      Iterate over the lines in the file.

      >>> sif = ScriptedInstallFile("example.bs")
      >>> sif.next()
      '\n'
      >>> sif.next()
      'install cdrom\n'

      Raises StopIteration when it reaches the end-of-file.
      
      >>> sif = ScriptedInstallFile("/dev/null")
      >>> sif.next()
      Traceback (most recent call last):
      ...
      StopIteration
      '''
      
      self.index += 1 
      try:
         return self.lines[self.index]
      except IndexError:
         self.index -= 1
         raise StopIteration()

   def reset(self):
      '''Reset the file pointer to the beginning of the file.

      >>> sif = ScriptedInstallFile("example.bs")
      >>> sif.next()
      '\n'
      >>> sif.reset()
      >>> sif.next()
      '\n'
      '''
      
      self.index = -1

   def _doesNotStartWithAKeyword(self, line):
      return not re.match(self.keyWords, line)

   def getLinesUntilNextKeyword(self):
      r'''
      Return a string containing all the lines in the file up to the next
      keyword or end-of-file.  Possible keywords are:

        %post
        %pre
        %packages
        %vmlicense_text

      >>> sif = ScriptedInstallFile("example.bs")
      >>> _ignore = [x for x in takewhile(lambda x: x != '%packages\n', sif)]
      >>> sif.getLinesUntilNextKeyword()
      'pkg1\npkg2\n\n'
      >>> sif.next()
      '%post\n'
      >>> sif.getLinesUntilNextKeyword()
      'echo "Hello, World!"\n\n'
      >>> sif.next()
      Traceback (most recent call last):
      ...
      StopIteration
      '''
      
      section = ''

      for line in takewhile(self._doesNotStartWithAKeyword, self):
         section += line

      if self.index < len(self.lines) - 1:
         self.index -= 1

      log.debug('section-contents: ' + repr(section))

      return section

if __name__ == "__main__": #pragma: no cover
   import doctest
   doctest.testmod()
