
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

import sys

sys.path.append('..')

from log import log


# TODO: this should probably be somewhere else
interpreters = {
   'bash' : '/bin/bash',
   'python' : '/usr/bin/python',
   'perl' : '/usr/bin/perl',
}

class Result:
   FAIL = 0
   SUCCESS = 1
   WARN = 2

def makeResult(errors, warnings):
   '''
   Return a tuple containing the appropriate result code, a list of errors, and
   a list of warnings.

   >>> makeResult([], [])
   (1, [], [])
   >>> makeResult(["error: the computer is on fire"], [])
   (0, ['error: the computer is on fire'], [])
   >>> makeResult(["error: something bad"], ["warning: power failure"])
   (0, ['error: something bad'], ['warning: power failure'])
   >>> makeResult([], ["warning: power failure"])
   (2, [], ['warning: power failure'])
   '''
   
   if len(errors) > 0:
      return (Result.FAIL, errors, warnings)

   if len(warnings) > 0:
      return (Result.WARN, [], warnings)

   return (Result.SUCCESS, [], [])

# TODO: Once I am done debugging I can remove this
def logStuff(result, errors, warnings, desc='Unknown'): #pragma: no cover
   if not result or errors:
      logElements( (errors,), log.error, desc)

   if result == Result.WARN or warnings:
      logElements( (warnings,), log.warning, desc)


# TODO: Once I am done debugging I can remove this
def logElements(elements, func, desc='Unknown'): #pragma: no cover
   log.debug(desc)

   for element in elements:
      typeStr = type( element )
      func(str(typeStr) + ':' + str(element))

if __name__ == "__main__": #pragma: no cover
   import doctest
   doctest.testmod()
