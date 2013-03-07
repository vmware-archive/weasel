
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

'''Parser for ESX kickstart files.

This module parses files in a kickstart-like format and inserts the data into
the userchoices module.

See grammar.py
'''

import os
import sys
import re
import string
import shlex
import urllib
import urllib2
from grammar import GrammarDetail, \
                    GrammarDefinition, \
                    ArgumentOrientation
from scriptedinstallutil import logStuff, \
                                Result, \
                                makeResult, \
                                interpreters
from scriptedinstallfile import ScriptedInstallFile

from script import Script
from log import log
import userchoices
from remote_files import isURL
from users import cryptPassword, sanityCheckPassword
from systemsettings import WeaselConfig, SystemKeyboards
from timezone import TimezoneList
import devices
from devices import DiskSet, DiskDev, VirtualDiskDev, VMDK_OVERHEAD_SIZE
from datastore import DatastoreSet, checkForClearedVolume
from regexlocator import RegexLocator
import fsset
import packages
import networking
import media
import usbmedia
import esxlicense
import util
import partition
from precheck import _diskUsage
from partition import \
     getEligibleDisks, \
     PartitionRequest, \
     PartitionRequestSet, \
     removeOldVirtualDevices, \
     addDefaultPhysicalRequests, \
     addDefaultVirtualDriveAndRequests, \
     sanityCheckPartitionRequests

class ScriptedInstallPreparser:
   #TODO: Move these class statics somewhere more appropriate.
   TIMEZONES = TimezoneList()

   KEYBOARDS = SystemKeyboards()

   WEASEL_CONFIG = WeaselConfig()
   
   def __init__(self, fileName):

      self.grammarDefinition = GrammarDefinition()
      self._bind_to_grammar()

      self.numCommands = 0
      self.bumpTree = {}
      self.scriptedinstallFiles = []

      self.vmfsVolumes = {}
      self.vmdkDeviceName = None
      self.vmdkDevice = None

      self.onlyCommands = []
      self.earlyPassCommands = []

      self.timezones = ScriptedInstallPreparser.TIMEZONES
      self.keyboards = ScriptedInstallPreparser.KEYBOARDS

      self._refreshDiskSet()
      self.setActiveScriptedInstallFile(fileName)

      self.warnedSpaceSeparatedArgument = False
      self.warnedPhysicalPartition = False

   def getMountPoints(self):
      return [req.mountPoint for req in partition.allUserPartitionRequests()]

   def _refreshDiskSet(self):
      '''Rescan the disks/datastores in case something has changed.'''
      
      self.datastoreSet = DatastoreSet()
      self.disks = DiskSet(forceReprobe=True)
      # diskAliases contains a mapping from aliases (vml, sdX, vmhbaX:Y:Z) to
      # the canonical disk name.
      self.diskAliases = {}
      for disk in self.disks.values():
         self.diskAliases[disk.name] = disk.name
         if disk.path:
            self.diskAliases[disk.path] = disk.name
         if disk.consoleDevicePath:
            self.diskAliases[disk.consoleDevicePath] = disk.name
            m = re.match(r'/dev/(.+)', disk.consoleDevicePath)
            if m:
               self.diskAliases[m.group(1)] = disk.name

   def parseAndValidate(self):
      '''Combines the preParse() and overall validation into a single method.

      >>> sip = ScriptedInstallPreparser("example.bs")
      >>> (result, errors, warnings) = sip.parseAndValidate()
      >>> result == Result.FAIL
      True
      >>> print "\\n".join(warnings)
      warning:example.bs:line 7: package "pkg1" not found.
      warning:example.bs:line 7: package "pkg2" not found.
      warning:example.bs:line 10: interpreter not defined. Defaulting to bash
      warning:authconfig option not specified. Using default settings
      warning:network command not specified. Defaulting to DHCP.
      >>> print "\\n".join(errors)
      error:vmaccepteula command was not specified. You must read and accept the VMware ESX End User License Agreement by including the command in the scripted install script.
      '''

      parseErrors = []
      parseWarnings = []
      instParseErrors = []
      validateErrors = []
      validateWarnings = []
      instParseWarnings = []

      # First-pass, pull out and run the '%pre' script.
      self.onlyCommands = ['%pre']
      (result, preParseErrors, preParseWarnings) = self.preParse()
      if result != Result.FAIL:
         for preScriptChoice in userchoices.getPreScripts():
            preScript = preScriptChoice['script']
            if preScript.run() != 0:
               preParseErrors.append('"%pre" script returned with an error.')
               return makeResult(preParseErrors, preParseWarnings)
         self.bumpTree = {}

         self.scriptedinstallFiles[-1].reset() # XXX do this in preParse?
         self.onlyCommands = ['install', '%include', 'include']
         (result, instParseErrors, instParseWarnings) = self.preParse()
         if result == Result.FAIL:
            return makeResult(instParseErrors, instParseWarnings)

         # In case the %pre script has changed the disk layout, we need to
         # refresh our cached version of the world.
         self._refreshDiskSet()
         
         # reset the file and do the real parse.
         self.scriptedinstallFiles[-1].reset() # XXX do this in preParse?
         self.onlyCommands = []
         (result, parseErrors, parseWarnings) = self.preParse()
         if result != Result.FAIL:
            (result, validateErrors, validateWarnings) = self.validate(
               self.grammarDefinition.grammar, self.bumpTree.keys())

      return makeResult(preParseErrors + parseErrors + validateErrors,
                        preParseWarnings + instParseWarnings +
                        parseWarnings + validateWarnings)


   def _bind_to_grammar(self):
      '''Inserts callbacks we use into the grammar definition.'''
      
      gd = self.grammarDefinition
      gd.bindCallback("auth", "environmentAction", self.doAuth)
      gd.bindCallback("authconfig", "environmentAction", self.doAuth)
      gd.bindCallback("autopart", "environmentAction", self.doAutopart)
      gd.bindCallback("bootloader", "environmentAction", self.doBoot)
      gd.bindCallback("clearpart", "environmentAction", self.doClearpart)
      gd.bindCallback("dryrun", "environmentAction", self.doDryrun)
      gd.bindCallback("esxlocation", "environmentAction", self.doEsxLocation)
      gd.bindCallback("firewall", "environmentAction", self.doFirewall)
      gd.bindCallback("firewallport", "environmentAction", self.doFirewallPort)
      gd.bindCallback("install", "environmentAction", self.doInstall)
      gd.bindCallback("keyboard", "environmentAction", self.doKeyboard)
      gd.bindCallback("network", "environmentAction", self.doNetwork)
      gd.bindCallback("part", "environmentAction", self.doPartition)
      gd.bindCallback("partition", "environmentAction", self.doPartition)
      gd.bindCallback("paranoid", "environmentAction", self.doParanoid)
      gd.bindCallback("reboot", "environmentAction", self.doReboot)
      gd.bindCallback("rootpw", "environmentAction", self.doRootpw)
      gd.bindCallback("timezone", "environmentAction", self.doTimezone)
      gd.bindCallback("upgrade", "environmentAction", self.doUpgrade)
      gd.bindCallback("virtualdisk", "environmentAction", self.doVirtualDisk)
      gd.bindCallback("accepteula", "environmentAction", self.doVMAcceptEULA)
      gd.bindCallback("vmaccepteula", "environmentAction", self.doVMAcceptEULA)
      gd.bindCallback("serialnum", "environmentAction", self.doVMSerialNum)
      gd.bindCallback("vmserialnum", "environmentAction", self.doVMSerialNum)
      gd.bindCallback("zerombr", "environmentAction", self.doZeroMBR)
      gd.bindCallback("%packages", "environmentAction", self.doPackagesSection)
      gd.bindCallback("%pre", "environmentAction", self.doPreSection)
      gd.bindCallback("%post", "environmentAction", self.doPostSection)
      
      gd.bindCallback("%include", "environmentAction", self.doInclude)
      gd.bindCallback("include", "environmentAction", self.doInclude)
      

   def setActiveScriptedInstallFile(self, fileName):
      '''Open a kickstart file and append it to self.scriptedinstallFiles.'''
      
      scriptedinstallFile = ScriptedInstallFile(fileName)
      self.scriptedinstallFiles.append(scriptedinstallFile)
      
      return scriptedinstallFile


   def recognizeCommand(self):
      errors = []
      self.numCommands += 1
      if self.numCommands > 256:
         errors.append('more than 256 commands were included in the' \
                       +' kickstart file(s)')
         return (Result.FAIL, errors)
      return (Result.SUCCESS, [])

   def postValidate(self):
      '''Perform some extra global validation.'''

      errors = []
      warnings = []

      anUpgrade = userchoices.getUpgrade()

      if "auth" not in self.bumpTree and not anUpgrade:
         warnings += [
            'authconfig option not specified. Using default settings']

      if "rootpw" not in self.bumpTree and not anUpgrade:
         errors += ['command "rootpw" required but not found']

      if "network" not in self.bumpTree and not anUpgrade:
         warnings += [
            'network command not specified. Defaulting to DHCP.']
         
         nics = networking.getPhysicalNics()
         if nics:
            nics.sort(lambda x, y: cmp(x.name, y.name))
            device = nics[0]
            userchoices.setCosNetwork(None, None, None, None)
            userchoices.addCosNIC(device,
                                  None,
                                  userchoices.NIC_BOOT_DHCP,
                                  None,
                                  None)

      if "vmaccepteula" not in self.bumpTree and not anUpgrade:
         errors += [
            'vmaccepteula command was not specified. You must read and accept '
            'the VMware ESX End User License Agreement by including '
            'the command in the scripted install script.']

      partErrors = sanityCheckPartitionRequests(checkSizing=True)

      errors += partErrors

      if userchoices.getMediaLocation() and userchoices.getNoEject():
         warnings += [
            'using network based installation but "--noeject" was specified '
            'for reboot command.']

      return makeResult(errors, warnings)


   def preParse(self):
      '''Method validates and loads a file into an in memory structure
      that will be used to produce dispatchers for a scripted 
      operation.  The "onlyCommands" list restricts parsing to only those
      commands in the list (used for the first-pass parse of the '%pre' script.
      '''
      
      assert len(self.scriptedinstallFiles) > 0

      isRootFile = (len(self.scriptedinstallFiles) == 1)
      scriptedinstallFile = self.scriptedinstallFiles[-1]
      log.info('Using ScriptedInstall file: ' + scriptedinstallFile.fileName)

      status = Result.SUCCESS
      errorsBuffer = []
      warningsBuffer = []

      for line in scriptedinstallFile:
         (status, errors, warnings) = self.preParseLine(line)
         
         if warnings:
            warnings = map(
               (lambda x: scriptedinstallFile.fileName + \
                          ':line ' + str(scriptedinstallFile.index + 1) + \
                          ': ' + str(x)), warnings)
            warningsBuffer += warnings

         if errors:
            errors = map( 
               (lambda x: scriptedinstallFile.fileName + \
                          ':line ' + str(scriptedinstallFile.index + 1) + \
                          ': ' + str(x)), errors)
            errorsBuffer += errors

         if ((userchoices.getParanoid() and status != Result.SUCCESS) or
             status == Result.FAIL):
            break

      if isRootFile and not self.onlyCommands:
         if len(self.bumpTree) == 0:
            errorsBuffer.append('scripted install file has no commands')
            status = Result.FAIL
            
         if status != Result.FAIL:
            (_status, errors, warnings) = self.postValidate()
            warningsBuffer += warnings
            errorsBuffer += errors

         warningsBuffer = map(lambda x: 'warning:' + x, warningsBuffer)
         errorsBuffer = map(lambda x: 'error:' + x, errorsBuffer)

         if (userchoices.getParanoid() and
             (warningsBuffer != [] or errorsBuffer != [])):
            errorsBuffer.append('error: got warnings during paranoid mode')

      if isRootFile:
         for cmd in self.onlyCommands:
            if cmd.startswith('%') or cmd == 'include':
               continue
            
            self.earlyPassCommands.append(cmd)

      return makeResult(errorsBuffer, warningsBuffer)


   def preParseLine(self, line):
      '''Method pulls line apart into tokens using shlex then 
      dispatches the correct parsing method based on the 
      command parsed
      
      The command is always the first group of word characters
      found on the line.

      If the onlyCommands list is not empty, then only those commands in
      the list will be parsed.
      '''
      
      assert line is not None
      
      warningsBuffer = []
      tokens = None
      try:
         tokens = shlex.split(line, True)
      except Exception, (msg):
         return (Result.FAIL, [str(msg)], [])

      if not tokens or \
             (self.onlyCommands and tokens[0] not in self.onlyCommands):
         return (Result.SUCCESS, [], [])

      command = tokens.pop(0)

      if command in self.earlyPassCommands:
         # We've already processed this command earlier.
         return (Result.SUCCESS, [], [])

      log.debug('command: ' + command + ' found')
 
      if not self.grammarDefinition.isCommand(command):
         return (Result.WARN, [], ['unknown command "' + command + '"'])
         
      (result, errors) = self.recognizeCommand()
      if not result:
         return(result, errors, [])

      if self.grammarDefinition.isDeprecated(command):
         return(Result.WARN, [], ['command "' + command + '" is deprecated and should not be used.'])
      elif self.grammarDefinition.isUnused(command):
         return(Result.WARN, [], ['command "' + command + '" is currently unused.'])

      commandGrammar = self.grammarDefinition.getCommandGrammar(command)
      assert commandGrammar
      assert commandGrammar['id'] in self.grammarDefinition.grammar

      (result, errors, warnings) = \
          self.addBranch(commandGrammar, tokens)
      
      warningsBuffer += warnings
      
      if not result:
         return (Result.FAIL, errors, warnings)

      if 'environmentAction' in self.grammarDefinition.grammar[command]:
         (result, errors, warnings) = \
             self.grammarDefinition.grammar[command]['environmentAction']()
         
      warningsBuffer += warnings

      return makeResult(errors, warningsBuffer)


   def addBranch(self, commandGrammar, args):
      '''Builds a bumpTree branch object and validates it against a known
      grammar.
   
      If a duplicate branch has been built for the same bumpTree the new
      branch is ignored. 
      '''
      
      assert commandGrammar is not None
      assert args is not None

      (branch, (result, errors, warnings)) = \
         self.buildBranch( commandGrammar, args )

      warningBuffer = warnings

      if not result:
         return (Result.FAIL, errors, warningBuffer)

      (result, errors, warnings) \
                    = self.validate(commandGrammar['args'], branch, 'argument')

      warningBuffer += warnings

      if not result:
         return (Result.FAIL, errors, warningBuffer)

      cmdname = commandGrammar['id']
      options = self.grammarDefinition.grammar[cmdname].get('options', [])
      
      if 'multiple' in options:
         if cmdname not in self.bumpTree:
            self.bumpTree[cmdname] = []
         self.bumpTree[cmdname].append(branch)
      else:
         if cmdname in self.bumpTree:
            warningBuffer.append('command "%s" was already specified. Using '
                                 'the latest value.' % cmdname)
         self.bumpTree[cmdname] = branch
      
      return (result, errors, warningBuffer)


   def validate(self, args, branch, grammarDesc='command'):
      '''Method validates the constraints of a grammar against a specified
      branch.
      '''
      
      errors = []
      warnings = []

      keys = args.keys()
      keys.sort()
      for option in keys:
         detail = args[option]['detail']

         log.debug('Validating ' + grammarDesc + ": " + option)

         if 'alias' in args[option] and \
            option != args[option]['alias']:
            alias = args[option]['alias']
         else:
            alias = None

         assert (detail != GrammarDetail.UNUSED) or (option not in branch)

         if detail == GrammarDetail.REQUIRED and option not in branch:
            if (alias and alias not in branch) or (not alias):
               errors.append(grammarDesc +' "' + option + '" required' \
                             +' but not found')
               log.debug(grammarDesc +' Required and not found')
         elif (detail == GrammarDetail.DEPRECATED) and (option in branch):
            warnings.append(option + ' is deprecated');
            log.debug(grammarDesc + 'Deprecated')
         elif (detail == GrammarDetail.OPTIONAL) and \
                 ((option in branch) or \
                 ((alias) and (alias in branch))):
            log.debug(grammarDesc + ' Optional')
            if 'requires' in args[option]:
               requires = args[option]['requires']
               for r in requires:
                  log.debug('Requires: ' + r)
                  if r not in branch:
                     msg = args[option].get(
                        'requiresMsg',
                        '%(grammarDesc)s "%(option)s" requires '
                        '%(grammarDesc)s: "%(dep)s".')
                     errors.append(msg % {
                        'grammarDesc' : grammarDesc,
                        'option' : option,
                        'dep' : r,
                        })
            if 'invalids' in args[option]:
               invalids = args[option]['invalids']
               for i in invalids:
                  if i in branch:
                     errors.append(grammarDesc + ' "' + option + \
                                   '" is invalid when used with' + \
                                   ' argument "' + i + '".')

      return makeResult(errors, warnings)

   def buildBranch( self, commandGrammar, args ):
      '''Method iterates over the arguments passed and adds them
      to a hash of hashs based on there validity. The following
      rules are checked...
   
         1) The argument must exist in the commands grammar
         2) The value of an argument must exist if a valueRegex 
            is specified in the commands grammar
         3) Duplicate arguments or aliases to arguments are ignored
      '''
      
      errors = []
      warnings = []
      branch = {}

      def _groupArguments(args):
         '''Be backwards compatible with anaconda and allow option values to be
         separated by a space.  Rather than trying to deal with '=' and spaces
         at the same time, this does a preprocessing step that turns space
         separated args into '=' separated args.  The input should be a list of
         arguments split up by shlex.split.  The function will return a new list
         with the arguments formatted for _partitionArguments.
         '''
         retval = []

         rargs = list(args) # make a copy
         while rargs:
            token = rargs.pop(0)
            if '=' in token or token not in commandGrammar['args']:
               # The argument is already in the correct form with an '='
               # separator or it's an extra argument.
               retval.append(token)
               continue

            argGrammar = commandGrammar['args'][token]
            if 'valueRegex' in argGrammar or 'valueValidator' in argGrammar:
               # The token is an option that takes a value.
               if 'noneValue' in argGrammar:
                  # The --firstdisk value is optional, so we always need to
                  # assume it's the default.  The only way to specify it is
                  # with an '=' separator.
                  value = argGrammar['noneValue']
               elif rargs:
                  if not self.warnedSpaceSeparatedArgument:
                     warnings.append(
                        "Separating option values with a "
                        "space is no longer supported.")
                     warnings.append(
                        "Use an equal sign instead, for "
                        "example, '--option=value'.")
                     self.warnedSpaceSeparatedArgument = True
                  value = rargs.pop(0)
               else:
                  value = None
               if value is not None:
                  retval.append("%s=%s" % (token, value))
                  continue

            retval.append(token)

         return retval

      def _partitionArguments(args):
         '''Partition the given argument list into a list of tuples for each
         recognized flag argument and a list of any extra arguments.
         '''
         
         argTuples = []
         extraArgs = []
         
         for arg in args:
            assert arg is not None
         
            key = arg
            value = None
            
            if '=' in arg:
               key, value = arg.split('=', 1)
               
            if key not in commandGrammar['args']:
               extraArgs.append(arg)
               continue
            
            argTuples.append((key, value, commandGrammar['args'][key]))
            
         return (argTuples, extraArgs)

      def _collectHangingArgs(argTuples, extraArgs):
         '''Process the hanging args from the grammar given the arguments left
         over after the flags have been pulled out.
         '''
         
         if 'hangingArg' not in commandGrammar:
            return
         
         hangingArgs = commandGrammar['hangingArg']
         for arg in hangingArgs:
            try:
               if hangingArgs[arg]['orientation'] == ArgumentOrientation.FRONT:
                  value = extraArgs.pop(0)
               else:
                  value = extraArgs.pop()
                     
               argTuples.append((arg, value, hangingArgs[arg]))
            except IndexError:
               if hangingArgs[arg]['detail'] == GrammarDetail.REQUIRED:
                  errors.append(arg + ' not specified for ' +
                                commandGrammar['id'] + ' command.')
                  continue


      argTuples, extraArgs = _partitionArguments(_groupArguments(args))

      _collectHangingArgs(argTuples, extraArgs)

      for arg in extraArgs:
         log.warn('bogus token found: "' + arg + '"')
         warnings.append('unknown argument "' + arg + \
                         '" to command "' + commandGrammar['id'] \
                         + '"')

      for key, value, argGrammar in argTuples:
         #TODO: break the body of this down some more
         
         hasValueRegex = ('valueRegex' in argGrammar)
         hasValueValidator = ('valueValidator' in argGrammar)
         if value is None:
            value = argGrammar.get('noneValue')
         if (not value) and (hasValueRegex or hasValueValidator):
            log.warn('valid token found but no valid value was set: ' \
                       + key)
            msg = 'argument "' + key + \
                  '" to command "' + commandGrammar['id'] \
                  + '" is missing a value.'

            warnings.append(msg)
            continue

         if value and not (hasValueRegex or hasValueValidator):
            log.warn('token does not take a value: ' \
                       + key)
            msg = 'argument "' + key + \
                  '" to command "' + commandGrammar['id'] \
                  + '" does not take a value.'

            warnings.append(msg)
            continue

         if (hasValueRegex):
            regex = argGrammar['valueRegex']
            match = re.match( '^(' + regex + ')$',
                              value,
                              argGrammar.get('regexFlags', 0))

            if not match:
               log.warn('invalid token value set for argument: ' \
                          + key + '=' + repr(value))
               fmt = argGrammar.get(
                  'regexMsg',
                  'argument "%(key)s" to command "%(command)s" set but an '
                  'invalid value was specified.')
               msg = fmt % {
                  'key' : key,
                  'command' : commandGrammar['id'],
                  'value' : value
               }

               if argGrammar.get('onRegexMismatch', 'warn') == 'warn':
                  warnings.append(msg)
               else:
                  errors.append(msg)

               if 'defaultValue' in argGrammar:
                  value = argGrammar['defaultValue']
               else:
                  continue

         if hasValueValidator:
            (_result, verrors, vwarnings) = argGrammar['valueValidator'](
               key, value)
            errors += verrors
            warnings += vwarnings
         
         #
         # key is in grammar and value is valid (set or None)
         #

         alias = None
         if 'alias' in argGrammar:
            alias = argGrammar['alias']

         if (key in branch) or (alias and (alias in branch)):
            warnings.append('duplicate argument "' + key + \
                            '" specified for command "' + \
                            commandGrammar['id'] + '".')
         else:
            branch[key] = value

      if commandGrammar['id'] not in ["rootpw", "bootloader"]:
         log.debug('Branch Created: ' + str(branch))

      return (branch, makeResult(errors, warnings))

   def doInclude(self):
      lastFileName = self.scriptedinstallFiles[-1].fileName

      branch = self.bumpTree['include'][-1]
      
      filename = branch['filename']
      
      if not isURL(filename) and filename[0] not in ['/', '.']:
         # stay compatible with the way 3.5 did it
         log.warn('implicit relative paths get rewritten as paths from the '
                  ' root of the local disk')
         filename = '/' + filename
      try:
         scriptedinstallFile = self.setActiveScriptedInstallFile(filename)
      except IOError, e:
         return(Result.FAIL, [str(e)], [])

      (result, errors, warnings) = self.preParse()
      self.scriptedinstallFiles.remove(scriptedinstallFile)
      
      return makeResult(errors, warnings)


   ##################################################################
   ##################################################################
   #         Environment setup for specific commands                #
   ##################################################################
   ##################################################################

   def doAuth(self):
      warnings = []

      branch = self.bumpTree['auth']

      #TODO: this seems silly. is there a better way?
      nis = activeDirectory = False
      nisServer = nisDomain = krb5Realm = krb5KDC = krb5Server \
          = ldapServer = ldapBaseDN = activeDirectoryDomain \
          = activeDirectoryServer = ''

#      if '--disableshadow' in branch:
#         warnings.append('--disableshadow is no longer supported; using shadow')

      nis = '--enablenis' in branch
      if '--nisdomain' in branch and '--enablenis' not in branch:
         warnings.append('--nisdomain was specified but ' + \
                         '--enablenis was not specified.' + \
                         ' Turning on NIS.')
         nis = True

      if '--nisserver' in branch: nisServer = branch['--nisserver']

      if '--nisdomain' in branch: nisDomain = branch['--nisdomain']

      if '--krb5realm' in branch: krb5Realm = branch['--krb5realm']

      if '--krb5kdc' in branch: krb5KDC = branch['--krb5kdc']

      if '--krb5adminserver' in branch: 
         krb5Server = branch['--krb5adminserver']

      if '--ldapserver' in branch: ldapServer = branch['--ldapserver']

      if '--ldapbasedn' in branch: ldapBaseDN = branch['--ldapbasedn']

      userchoices.setAuth( nis=nis,
                           kerberos='--enablekrb5' in branch,
                           ldap='--enableldap' in branch,
                           ldapAuth='--enableldapauth' in branch,
                           ldapTLS='--enableldaptls' in branch,
                           nisServer=nisServer,
                           nisDomain=nisDomain,
                           kerberosRealm=krb5Realm,
                           kerberosKDC=krb5KDC,
                           kerberosServer=krb5Server,
                           ldapServer=ldapServer,
                           ldapBaseDN=ldapBaseDN,)

      if warnings:
         return (Result.WARN, [], warnings)

      return (Result.SUCCESS, [], [])


   def doBoot(self):
      warnings = []
      errors = []
      branch = self.bumpTree['bootloader']

      kernelParams = ''
      if '--append' in branch: kernelParams = branch['--append']

      driveOrder = None
      if '--driveorder' in branch:
         driveOrderNames = []
         for token in branch['--driveorder'].split(','):
            driveOrderNames.append(token.strip())
         if len(driveOrderNames) > 1:
            warnings.append('bootloader --driveorder= specified with '
                          'multiple drives. Ignoring all but the first.')
         driveOrderName = driveOrderNames[0]
         if driveOrderName not in self.diskAliases:
            errors.append('bootloader --driveorder= specified, but '
                          'drive "%s" was not found on the system.' %
                          driveOrderName)
         else:
            # setBoot expects a list of disks.
            driveOrder = [self.disks[self.diskAliases[driveOrderName]]]

      location = userchoices.BOOT_LOC_MBR
      if '--location' not in branch:
         warnings.append('bootloader --location not specified. ' + \
                         'Defaulting to MBR.')
      else:
         location = branch['--location']


      password = ''
      passwordType = userchoices.BOOT_PASSWORD_TYPE_PLAIN
      if '--password' in branch:
         password = branch['--password']

         #
         # TODO: these length checks could be enfored at 
         #       the regex level as well
         #
         if len(password) > 30:
            warnings.append('bootloader --password= string is too long. '
                            'Bootloader password will not be set.')
            password = ''

      if '--md5pass' in branch: 
         if password:
            warnings.append('--md5pass and --password specified. ' + \
                            'Defaulting to md5pass.')
         password = branch['--md5pass']
         passwordType = userchoices.BOOT_PASSWORD_TYPE_MD5
         
      upgrade = '--upgrade' in branch
      doNotInstall = False
      if location == 'none': doNotInstall = True

      if errors:
         return makeResult(errors, warnings)

      userchoices.setBoot(upgrade, doNotInstall, location,
                          kernelParams, password, passwordType, driveOrder)

      if warnings:
         return (Result.WARN, [], warnings)

      return (Result.SUCCESS, [], [])


   def doClearpart(self):
      errors = []
      warnings = []
      branch = self.bumpTree['clearpart'][-1]

      specifiedDiskNames = self.disks.keys()

      for disk in self.disks.values():
         if disk.isControllerOnly():
            specifiedDiskNames.remove(disk.name)

      whichParts = userchoices.CLEAR_PARTS_ALL
      if '--exceptvmfs' in branch: 
         whichParts = userchoices.CLEAR_PARTS_NOVMFS
      
      if '--ignoredrives' in branch:
         ignoredDisks = map(string.strip, branch['--ignoredrives'].split(','))

         for diskName in ignoredDisks:
             if diskName not in self.diskAliases:
                errors.append('clearpart --ignoredrives= specified, but ' + \
                              'drive "' + diskName + '" was not found on ' + \
                              'the system.')
             elif self.diskAliases[diskName] not in specifiedDiskNames:
                warnings.append('clearpart --ignoredrives= specified, but ' + \
                                'drive "%s" was already given.' % diskName)
             else:
                specifiedDiskNames.remove(self.diskAliases[diskName])
      elif '--drives' in branch:
         specifiedDiskNames = []
         disks = map(string.strip, branch['--drives'].split(','))
         for diskName in disks:
            if diskName not in self.diskAliases:
               errors.append('clearpart --drives= specified, but ' + \
                             'drive "' + diskName + '" was not found on ' + \
                             'the system.')
            elif self.diskAliases[diskName] in specifiedDiskNames:
               warnings.append('clearpart --drives= specified, but ' +
                               'drive "%s" was already given.' % diskName)
            elif self.diskAliases[diskName] in \
                   userchoices.getDrivesInUse():
               errors.append('clearpart --drives= specified, but ' +
                             'clearing drive "%s" is not allowed.' % diskName)
            else:
               specifiedDiskNames.append(self.diskAliases[diskName])
      elif '--alldrives' in branch:
         pass
      elif '--firstdisk' in branch:
         filterList = self._firstDiskFilters(branch['--firstdisk'])
         firstDisk = self._firstDisk(filterList)
         if not firstDisk:
            errors.append('clearpart --firstdisk specified, but no suitable '
                          'disk was found.')
         else:
            specifiedDiskNames = [firstDisk.name]
            log.info("clearpart --firstdisk == %s" % str(firstDisk))
      else:
         errors.append('clearpart requires one of the following arguments: '
                       '--alldrives, --firstdisk, --ignoredrives=, --drives=')

      # search through all of the partitions on each of the disks specified and
      # see if there is an existing vmfs partition or if the /boot partition is
      # supposed to be preserved.
      for diskName in specifiedDiskNames:
         for part in self.disks[diskName].partitions:
            if '--overwritevmfs' not in branch and part.nativeType == 0xfb:
               errors.append("clearpart --overwritevmfs not specified and "
                             "partition %d on %s is of type VMFS" % (
                     part.partitionId, diskName))
            for req in userchoices.getPartitionMountRequests():
               if req.consoleDevicePath == part.consoleDevicePath:
                  errors.append("clearpart cannot be used on the same disk as "
                                "esxlocation")

      if errors:
         return (Result.FAIL, errors, warnings)

      prevChoice = userchoices.getClearPartitions()
      if prevChoice:
         specifiedDiskNames += prevChoice['drives']
      userchoices.setClearPartitions(specifiedDiskNames, whichParts)

      return makeResult([], warnings)


   def doDryrun(self):
      userchoices.setDryrun(True)
      return (Result.SUCCESS, [], [])

   
   def doEsxLocation(self):
      errors = []
      warnings = []
      branch = self.bumpTree['esxlocation']

      if "/boot" in self.getMountPoints():
         errors.append("/boot partition already specified")

      disk = None
      part = None
      clearDrives = userchoices.getClearPartitions().get('drives', [])
      if '--uuid' in branch:
         uuid = branch['--uuid']
         
         diskPartTuple = self.disks.findFirstPartitionMatching(uuid=uuid)
         if not diskPartTuple:
            errors.append("esxlocation partition with UUID '%s' not found" %
                          uuid)
         else:
            disk, part = diskPartTuple
      else:
         diskNames = []
         if '--drive' in branch:
            diskNames = [branch['--drive']]
         elif '--disk' in branch:
            diskNames = [branch['--disk']]
         elif '--firstdisk' in branch:
            filterList = self._firstDiskFilters(branch['--firstdisk'])
            disksToSearch = self._orderDisks(filterList, vmfsSupport=False)
            if not disksToSearch:
               errors.append('esxlocation --firstdisk specified, but no '
                             'suitable disk was found.')
            else:
               diskNames = [disk.name for disk in disksToSearch]
         else:
            errors.append('esxlocation requires --disk, --firstdisk, or --uuid')

         for name in diskNames:
            if name not in self.diskAliases:
               errors.append('esxlocation --disk= specified, but drive "%s" '
                             'was not found on the system.' % name)
               continue
            canonicalName = self.diskAliases[name]
            disk = self.disks[canonicalName]
            # Find the first linux partition that is large enough to serve as
            # the /boot partition.
            part = disk.findFirstPartitionMatching(
               fsTypes=('ext2', 'ext3'),
               minimumSize=partition.BOOT_MINIMUM_SIZE)
            if part and part.partitionType == partition.PRIMARY:
               break
            part = None
      
         if not errors and not part:
            errors.append("esxlocation could not find a Linux primary "
                          "partition of atleast %d MBs in size on disks -- "
                          "%s" % (
                  partition.BOOT_MINIMUM_SIZE, ",".join(diskNames)))

      if disk and disk.name in clearDrives:
         errors.append('esxlocation specified, but drive "%s" '
                       'is scheduled to be cleared.' % disk.name)

      if errors:
         return makeResult(errors, warnings)

      log.info("esxlocation is %s" % part.consoleDevicePath)
      part.mountPoint = "/boot"
      
      req = PartitionRequest(mountPoint=part.mountPoint,
                             minimumSize=part.getSizeInMegabytes(),
                             fsType=part.fsType,
                             consoleDevicePath=part.consoleDevicePath,
                             clearContents='--clearcontents' in branch)
      userchoices.addPartitionMountRequest(req)
      
      return makeResult(errors, warnings)


   def doFirewall(self):
      errors = []
      warnings = []
      branch = self.bumpTree['firewall']

      incoming = userchoices.ESXFIREWALL_BLOCK
      outgoing = userchoices.ESXFIREWALL_BLOCK

      if '--disabled' in branch:
         incoming = userchoices.ESXFIREWALL_ALLOW
         outgoing = userchoices.ESXFIREWALL_ALLOW

      if '--allowIncoming' in branch:
         incoming = userchoices.ESXFIREWALL_ALLOW
      if '--allowOutgoing' in branch:
         outgoing = userchoices.ESXFIREWALL_ALLOW

      userchoices.setESXFirewall(incoming, outgoing)
      
      return(Result.SUCCESS, [], [])

   def doFirewallPort(self):
      errors = []
      warnings = []
      branch = self.bumpTree['firewallport'][-1]

      # check for services first...
      if '--enableService' in branch:
         # TODO: check the service name against services.xml
         userchoices.addServiceRule(branch['--enableService'],
                                    userchoices.PORT_STATE_ON)
         return makeResult(errors, warnings)
      elif '--disableService' in branch:
         userchoices.addServiceRule(branch['--disableService'],
                                    userchoices.PORT_STATE_OFF)
         return makeResult(errors, warnings)

      if ('--port' not in branch or
          '--proto' not in branch or
          '--dir' not in branch):
         errors.append('firewallport requires --port, --proto, and --dir '
                       'options')
         return makeResult(errors, warnings)

      # handle other ports here.
      if '--open' in branch:
         state = userchoices.PORT_STATE_OPEN
      elif '--close' in branch:
         state = userchoices.PORT_STATE_CLOSED
      else:
         errors.append('firewallport --open or --close must be specified.')
      if branch['--dir'] == 'in' and '--name' not in branch:
         errors.append(
            'firewallport --name must be specified for inbound ports.')
      if not (1 <= int(branch['--port']) <= 65535):
         errors.append('invalid firewall port "%s" specified. Must be between '
                       '1 and 65535.' % branch['--port'])

      if branch['--dir'] == 'in':
         direction = userchoices.PORT_DIRECTION_IN
      elif branch['--dir'] == 'out':
         direction = userchoices.PORT_DIRECTION_OUT

      if branch['--proto'] == 'tcp':
         proto = userchoices.PORT_PROTO_TCP
      elif branch['--proto'] == 'udp':
         proto = userchoices.PORT_PROTO_UDP

      if errors:
         return makeResult(errors, warnings)

      userchoices.addPortRule(state,
                              int(branch['--port']),
                              proto,
                              direction,
                              branch.get('--name', None))

      return makeResult(errors, warnings)

   def doInstall(self):
      errors = []
      warnings = []
      branch = self.bumpTree['install']

      url = ''
      log.debug('doInstall branch: '+str(branch))
      if 'nfs' in branch:
         log.info('Installation media: NFS')
         server = branch['--server']
         directory = urllib.quote(branch['--dir'])
         url = 'nfs://%s%s' % (server, directory)
      elif 'url' in branch:
         log.info('Installation media: URL')
         url = branch['urlstring']
      elif 'cdrom' in branch:
         log.info('CD-ROM install specified. CD-ROM is the default. Ignoring.')
      elif 'usb' in branch:
         log.info('Installation media: USB')
         mediaFound = usbmedia.findUSBMedia()
         if not mediaFound:
            errors.append('Cannot locate installation data on any attached '
                          'USB media.')
         else:
            log.info('  USB media found -- %s' % str(mediaFound[0]))
            media.runtimeActionUnmountMedia()
            userchoices.setMediaDescriptor(mediaFound[0])
            userchoices.addDriveUse(mediaFound[0].diskName, 'media')
      else:
         log.info('Installation media: Not specified')
         warnings.append('installation method not specified. ' 
                         'Defaulting to cdrom install')

      if 'nfs' not in branch and '--server' in branch:
         warnings.append('--server argument ignored')
      if 'nfs' not in branch and '--dir' in branch:
         warnings.append('--dir argument ignored')

      if url:
         log.info('setting media location')
         userchoices.setMediaLocation(url)
      
      return makeResult(errors, warnings)


   def doKeyboard(self):
      branch = self.bumpTree['keyboard']

      keyboardStr = branch['keyboardtype']
      kb = (self.keyboards.getKeyboardSettingsByName(keyboardStr) or
            self.keyboards.getKeyboardSettingsByKeytable(keyboardStr))

      if not kb:
         return (Result.WARN,
                 [],
                 ['invalid keyboard type "%s" was specified. Using default.' %
                  keyboardStr])

      userchoices.setKeyboard(kb.keytable,
                              kb.name,
                              kb.model,
                              kb.layout,
                              kb.variant,
                              kb.options)

      return (Result.SUCCESS, [], [])


   def doNetwork(self):
      warnings = []
      errors = []
      branch = self.bumpTree['network']

      if '--bootproto' not in branch:
         warnings.append('no bootproto set. Defaulting to DHCP.')
         bootproto = userchoices.NIC_BOOT_DHCP
      else:
         bootproto = branch['--bootproto']

      if bootproto == userchoices.NIC_BOOT_DHCP:
         if '--ip' in branch:
            errors.append( \
               'bootproto was set to DHCP but "--ip=" was set.')
         if '--netmask' in branch:
            errors.append( \
               'bootproto was set to DHCP but "--netmask=" was set.')
         if '--gateway' in branch:
            errors.append( \
               'bootproto was set to DHCP but "--gateway=" was set.')
      else:
         if '--ip' not in branch:
            errors.append('bootproto was set to static but "--ip=" was not set.')

      deviceName = None
      device = None
      if '--device' in branch:
         deviceName = branch['--device']
         if ':' in deviceName:
            # assume it is a MAC address
            device = networking.findPhysicalNicByMacAddress(deviceName)
         else:
            device = networking.findPhysicalNicByName(deviceName)
         if not device:
            errors.append('bootproto --device= specified, but "%s" was not '
                          'found on the system.' % deviceName)
      else:
         nicChoice = userchoices.getDownloadNic()
         if nicChoice and nicChoice['device']:
            # XXX At least use the download device as the default here, I'm not
            # so sure about copying the other configuration bits.
            device = nicChoice['device']
            log.info('no network device given, using boot NIC -- %s' % device)
         if not device:
            try:
               defaultDevice = networking.getPhysicalNics()[0]
            except IndexError:
               errors.append('network command specified, but no NIC found')
               return makeResult(errors, warnings)
            device = networking.getPluggedInAvailableNIC(defaultDevice)
            log.info('no network device boot option given, using first plugged '
                     'in NIC -- %s' % device)
            deviceName = device.name

      if device and not device.isLinkUp:
         warnings.append('bootproto --device=%s specified, but the link was not '
                       'active.  Check that the cable is plugged in.'
                       % deviceName)

      if errors:
         return makeResult(errors, warnings)


      hostname = nameserver1 = nameserver2 = gateway = netmask = ip = None
      if bootproto == userchoices.NIC_BOOT_DHCP:
         if '--hostname' in branch:
            warnings.append('bootproto was set to DHCP but ' + \
                            '"--hostname=" was set. Hostnames are' + \
                            ' ignored with DHCP.')
         if '--nameserver' in branch:
            warnings.append('bootproto was set to DHCP but ' + \
                            '"--nameserver=" was set. Nameservers' + \
                            ' are ignored with DHCP.')

      else:
 
         ip = branch['--ip']
 
         if '--hostname' not in branch:
            warnings.append('bootproto was set to static but ' + \
                            '"--hostname=" was not set. Setting ' + \
                            'hostname to "localhost".')
            hostname = 'localhost'
         else:
            hostname = branch['--hostname']

         if '--nameserver' not in branch:
            warnings.append('bootproto was set to static but ' + \
                            '"--nameserver=" was not set. Not using' + \
                            ' a nameserver.')
         else:
            nameserver = branch['--nameserver'].split(',')
            nameserver1 = nameserver[0]
            if len(nameserver) > 1:
               nameserver2 = nameserver[1]

         if '--netmask' not in branch:
            netmask = networking.utils.calculateNetmask(ip)
            warnings.append('--bootproto was set to static but ' + \
                            '"--netmask=" was not set. Setting ' + \
                            'netmask to %s.' % netmask)
         else:
            netmask = branch['--netmask']

         if '--gateway' not in branch:
            gateway = networking.utils.calculateGateway(ip, netmask)
            warnings.append('bootproto was set to static but ' + \
                            '"--gateway=" was not set. Setting ' + \
                            'gateway to %s.' % gateway)
         else:
            gateway = branch['--gateway']

         networking.utils.sanityCheckIPSettings(ip, netmask, gateway)

      vlanID = None
      if '--vlanid' in branch: vlanID = branch['--vlanid']

      if '--addvmportgroup' in branch:
         addVmPortGroup = branch['--addvmportgroup'].lower()
         userchoices.setAddVmPortGroup((addVmPortGroup in ['1', 'true']))

      userchoices.setCosNetwork(gateway, nameserver1, nameserver2, hostname)

      userchoices.addCosNIC(device, vlanID, bootproto, ip, netmask)

      return makeResult(errors, warnings)


   def doParanoid(self):
      userchoices.setParanoid(True)
      return (Result.SUCCESS, [], [])

   def _firstDiskFilters(self, names):
      '''Return a list of filter functions that perform a match operation on
      DiskDev objects.  The 'names' argument is a comma-separated list of
      strings to match in the DiskDevs.  Two strings, "local" and "remote", are
      built-in and refer to whether or not the disk is locally connected or
      not.  The strings can be mixed and matched in any way.'''
      
      def makeGenericMatcher(name):
         '''Returns a matcher function that looks for the given string in the
         DiskDev object'''
         def _matcher(disk):
            return (name in (disk.vendor, disk.model, disk.driverName))
         return _matcher
         
      filterList = []
      
      filterMap = {
         'local' : lambda disk: disk.local,
         'remote' : lambda disk: not disk.local
         }
      
      nameList = map(string.strip, names.split(','))

      for name in nameList:
         filterList.append(filterMap.get(name, makeGenericMatcher(name)))

      return filterList

   def _orderDisks(self, filterList, vmfsSupport=True):
      '''Return a list produced by running the given list of filter functions
      over the list of eligible disks.'''
      
      eligibleDisks = getEligibleDisks(vmfsSupport=vmfsSupport)

      userOrder = []

      for diskFilter in filterList:
         userOrder += filter(diskFilter, eligibleDisks)

      log.debug("  BEGIN firstdisk order")
      for disk in userOrder:
         log.debug("    %s" % str(disk))
      log.debug("  END firstdisk order")

      return userOrder
   
   def _firstDisk(self, filterList):
      '''Return the first disk in the list produced by running the given
      list of filter functions over the list of eligible disks.'''

      userOrder = self._orderDisks(filterList)

      if userOrder:
         return userOrder[0]

      return None

   def _checkVirtualDisk(self, vmfsVolume, imagePath, size):
      '''Check that a virtualdisk that is "size" MB large can be placed on the
      given vmfsVolume.  If an existing vmdk file is there, it's size is
      subtracted from the free space since it will be deleted.'''
      errors = []

      onDisk = None
      existingSize = 0
      if (vmfsVolume not in self.vmfsVolumes and
          self.datastoreSet.getEntryByName(vmfsVolume) == None):
         errors.append('virtualdisk "--onvmfs=" specified, but vmfs volume '
                       '"%s" was not found on the system.' % vmfsVolume)
      else:
         if vmfsVolume in self.vmfsVolumes:
            (freeSize, onDisk) = self.vmfsVolumes[vmfsVolume]
            userchoices.setEsxDatastoreDevice(onDisk)
         else:
            # Check for an existing cos-vmdk directory, which might happen
            # if a user needs to retry an upgrade.  Since we'll be deleting
            # the vmdk during the install, discount the space it's taking up
            # now when checking for the available free space.
            path = os.path.join("/vmfs/volumes", vmfsVolume, imagePath)
            if os.path.exists(path):
               existingSize = _diskUsage(path) / util.SIZE_MB / util.SIZE_MB
               
            dsEntry = self.datastoreSet.getEntryByName(vmfsVolume)
            freeSize = (dsEntry.getFreeSize() / util.SIZE_MB / util.SIZE_MB)
            onDisk = dsEntry.driveName
            userchoices.setVmdkDatastore(vmfsVolume)

         log.debug("checking vmdk sizing (r %s; f %s; e %s)" % (
               size, freeSize, existingSize))
         # check to see the virtual disk isn't bigger than the allocated
         # partition
         if (size + VMDK_OVERHEAD_SIZE) > (freeSize + existingSize):
            errors.append(
               'virtualdisk size is too large.  %dMB is required, but the '
               'minimum free size on %s is %dMB.' % (
                  size + VMDK_OVERHEAD_SIZE, vmfsVolume, freeSize))

      # double check to make certain the virtual disk isn't bigger than
      # anything that could fit on the device
      # XXX I think we can remove this or roll it into the check above.
      if not errors and \
             size > (devices.runtimeActionFindMaxVmdkSize() + existingSize):
         errors.append(
            'virtualdisk size is too large.  %dMB is required, but the '
            'minimum free size on %s is %dMB.' % (
                  size + VMDK_OVERHEAD_SIZE, vmfsVolume,
                  devices.runtimeActionFindMaxVmdkSize() + existingSize))

      return (errors, onDisk)

   def doAutopart(self):
      errors = []
      warnings = []

      branch = self.bumpTree['autopart']

      diskName = None
      vmfsVolume = None
      if '--drive' in branch:
         diskName = branch['--drive']
      elif '--disk' in branch:
         diskName = branch['--disk']
      elif '--firstdisk' in branch:
         filterList = self._firstDiskFilters(branch['--firstdisk'])
         firstDisk = self._firstDisk(filterList)
         if not firstDisk:
            errors.append('autopart --firstdisk specified, but no suitable '
                          'disk was found.')
         else:
            diskName = firstDisk.name
            log.info("autopart --firstdisk == %s" % str(firstDisk))
      elif '--onvmfs' in branch:
         vmfsVolume = branch['--onvmfs']
         if (vmfsVolume not in self.vmfsVolumes and
             self.datastoreSet.getEntryByName(vmfsVolume) == None):
            errors.append('autopart "--onvmfs=" specified, but vmfs volume '
                          '"%s" was not found on the system.' % vmfsVolume)

      imagePath = None
      imageName = None
      if '--vmdkpath' in branch:
         m = re.match('^(' + RegexLocator.vmdkpath + ')$', branch['--vmdkpath'])
         assert m is not None

         imagePath = m.group(2)[:-1]
         imageName = m.group(3)
      
      if not diskName and not vmfsVolume and not errors:
         errors.append('autopart requires --disk, --firstdisk, or --onvmfs')

      extraSpace = 0 # extra space for the root partition in the vmdk.
      if '--extraspace' in branch:
         extraSpace = int(branch['--extraspace'])

      if diskName and diskName not in self.diskAliases:
         errors.append('autopart --disk= specified, but drive "%s" was not '
                       'found on the system.' % diskName)

      if not errors:
         # Check for conflicting mount points from other commands.  If this
         # autopart is just for the vmdk, only check the virtual requests and
         # not the physical.
         allMountPoints = self.getMountPoints()
         allRequests = partition.getDefaultVirtualRequests()
         if not vmfsVolume:
            allRequests += partition.DEFAULT_PHYSICAL_REQUESTS
         for partSpec in allRequests:
            if partSpec[partition.REQUEST_MOUNTPOINT] in allMountPoints:
               errors.append('autopart partitions conflict with other '
                             'partition requests.')
               break

      if errors:
         return makeResult(errors, warnings)

      if diskName:
         drive = self.disks[self.diskAliases[diskName]]
         addDefaultPhysicalRequests(drive, True)
         addDefaultVirtualDriveAndRequests(drive.name,
                                           extraVirtualDiskSpace=extraSpace,
                                           imagePath=imagePath,
                                           imageName=imageName)
      elif vmfsVolume:
         size = partition.getRequestsSize(partition.getDefaultVirtualRequests())
         size += extraSpace
         errors, diskName = self._checkVirtualDisk(
            vmfsVolume,
            fsset.vmfs3FileSystem.systemUniqueName("esxconsole"),
            size)
         if errors:
            return makeResult(errors, warnings)
            
         addDefaultVirtualDriveAndRequests(diskName,
                                           vmfsVolume=vmfsVolume,
                                           extraVirtualDiskSpace=extraSpace,
                                           imagePath=imagePath,
                                           imageName=imageName)

      return makeResult(errors, warnings)


   def doPartition(self):
      errors = []
      warnings = []

      branch = self.bumpTree['part'][-1]
      mntPoint = branch['mountpoint']

      size = int(branch['--size'])

      grow = False
      maxSize = 0
      grow = ('--grow' in branch)

      if '--maxsize' in branch:
         maxSize = int(branch['--maxsize'])
         if maxSize < size:
            errors.append('"--maxsize=" was set less than "--size=".')

      if not grow and '--maxsize' in branch:
         warnings.append('--maxsize specified but --grow is not defined, '
                         'defaulting to grow to partition to --maxsize')
         grow = True

      virtualDisk = False
      if '--ondisk' in branch:
         onDisk = branch['--ondisk']
      elif '--ondrive' in branch:
         onDisk = branch['--ondrive']
      elif '--onfirstdisk' in branch:
         filterList = self._firstDiskFilters(branch['--onfirstdisk'])
         firstDisk = self._firstDisk(filterList)
         if not firstDisk:
            errors.append('part --onfirstdisk specified, but no suitable '
                          'disk was found.')
         else:
            onDisk = firstDisk.name
            log.info("part firstdisk == %s" % str(firstDisk))
      elif '--onvirtualdisk' in branch:
         onDisk = branch['--onvirtualdisk']
         virtualDisk = True
      else:
         errors.append(
            '"--ondisk" or "--onvirtualdisk" required, but not found.')

      if errors:
         return makeResult(errors, warnings)

      if virtualDisk:
         if onDisk != self.vmdkDeviceName:
            errors.append('part "--onvirtualdisk=" specified, but vmdk "%s" '
                          'was not found on the system.' % onDisk)
      else:
         if onDisk not in self.diskAliases:
            errors.append('part "--ondisk=" specified, but drive "%s" was not '
                          'found on the system.' % onDisk)
         else:
            onDisk = self.diskAliases[onDisk]


      if '--fstype' not in branch:
         warnings.append('--fstype not specified, defaulting to "ext3"')
         fsType = 'ext3'
      else:
         fsType = branch['--fstype']

      fsTypes = fsset.getSupportedFileSystems()
      if fsType not in fsTypes:
         fsTypeNames = fsTypes.keys()
         fsTypeNames.sort()
         errors.append('the value specified for "--fstype=" is invalid.  '
                       'Must be one of: %s.' % ", ".join(fsTypeNames))
         fsTypeObj = None
      else:
         fsTypeObj = fsTypes[fsType]()
         if not fsTypeObj.vmdkable and '--onvirtualdisk' in branch:
            errors.append(
               '%s partition cannot be inside of a virtual disk image.' %
               fsTypeObj.name)

      if fsType == 'vmfs3':
         # XXX not sure what all the constraints are on a volume name
         try:
            #mntPoint = mntPoint.strip()
            fsset.vmfs3FileSystem.sanityCheckVolumeLabel(mntPoint)
            if 'drives' in userchoices.getClearPartitions():
               clearDrives = userchoices.getClearPartitions()['drives']
            else:
               clearDrives = []

            dsEntry = self.datastoreSet.getEntryByName(mntPoint)
            volumeIsCleared = checkForClearedVolume(clearDrives,
                                                    self.datastoreSet,
                                                    mntPoint)
            if mntPoint in self.vmfsVolumes or \
                   (dsEntry is not None and not volumeIsCleared):
               errors.append('vmfs volume already exists.')
            else:
               self.vmfsVolumes[mntPoint] = (size, onDisk)
               fsTypeObj.volumeName = mntPoint
         except ValueError, msg:
            errors.append(str(msg))
         mntPoint = None
      elif mntPoint.lower() == 'none':
         mntPoint = None
      elif mntPoint == 'swap':
         if fsType != 'swap':
            errors.append('swap partition does not have "swap" fstype.')
         mntPoint = None
      elif not mntPoint.startswith('/'):
         errors.append('mount point is invalid.')
      elif mntPoint in self.getMountPoints():
         errors.append('mount point already exists.')
      elif mntPoint == '/boot' and '--onvirtualdisk' in branch:
         errors.append('cannot place "/boot" on a virtual disk.')
      elif fsTypeObj and not fsTypeObj.isMountable():
         warnings.append('mount point was specified for type "%s".' % fsType)
         mntPoint = None

      badBlocks = '--badblocks' in branch



      if not errors and fsType == "vmfs3" and \
             not self.disks[onDisk].supportsVmfs:
         errors.append('vmfs3 not supported on drive "%s"' % onDisk)
      
      if errors:
         return makeResult(errors, warnings)

      if virtualDisk:
         disk = self.vmdkDevice
         if userchoices.checkVirtualPartitionRequestsHasDevice(onDisk):
            reqset = userchoices.getVirtualPartitionRequests(onDisk)
         else:
            reqset = PartitionRequestSet(deviceObj=disk)
            userchoices.setVirtualPartitionRequests(onDisk, reqset)
      else:
         if not self.warnedPhysicalPartition and \
                fsTypeObj and fsTypeObj.vmdkable and (
            not mntPoint or not mntPoint.startswith('/boot')):
            self.warnedPhysicalPartition = True
            warnings.append('Service Console partitions, other '
                            'than /boot, should be placed in the virtualdisk')
            
         disk = self.disks[onDisk]
         if userchoices.checkPhysicalPartitionRequestsHasDevice(onDisk):
            reqset = userchoices.getPhysicalPartitionRequests(onDisk)
         else:
            reqset = PartitionRequestSet(deviceName=disk.name)
            userchoices.setPhysicalPartitionRequests(onDisk, reqset)

      primaryPartition = ('--asprimary' in branch)

      reqset.append(PartitionRequest(mountPoint=mntPoint,
                                     fsType=fsTypeObj,
                                     drive=disk,
                                     minimumSize=size,
                                     maximumSize=maxSize,
                                     grow=grow,
                                     primaryPartition=primaryPartition,
                                     badBlocks=badBlocks))

      return makeResult(errors, warnings)


   def doUpgrade(self):
      userchoices.setUpgrade(True)
      
      return makeResult([], [])

   
   def _firstDatastore(self, filterList, size):
      '''Return the first datastore on a disk that matches the given filter
      list and has the given amount of free space available.'''

      volumeDisks = []
      for disk in self.disks.values(): # Sort based on device ordering
         for vol in self.datastoreSet.getEntriesByDriveName(disk.name):
            if (vol.getFreeSize() / util.SIZE_MB / util.SIZE_MB) < size:
               continue
            
            volumeDisks.append((vol, disk))
      
      userOrder = []

      for diskFilter in filterList:
         userOrder += filter(lambda pair: diskFilter(pair[1]), volumeDisks)

      log.debug("  BEGIN firstvmfs order")
      for vol, disk in userOrder:
         log.debug("    %s - %s" % (vol.name, str(disk)))
      log.debug("  END firstvmfs order")

      if userOrder:
         return userOrder[0][0]

      return None

   def doVirtualDisk(self):
      errors = []
      warnings = []

      branch = self.bumpTree['virtualdisk']
      name = branch['name']

      if '--path' in branch:
         m = re.match('^(' + RegexLocator.vmdkpath + ')$', branch['--path'])
         assert m is not None

         imagePath = m.group(2)[:-1]
         imageName = m.group(3)
      else:
         try:
            # The default vmdk path includes the system UUID so it will be
            # unique on shared storage.
            imagePath = fsset.vmfs3FileSystem.systemUniqueName(name)
            imageName = "%s.vmdk" % name

            log.info("creating virtualdisk %s/%s" % (imagePath, imageName))
         except ValueError, e:
            errors.append(str(e))
            return makeResult(errors, warnings)
      
      size = int(branch['--size'])

      if '--onvmfs' in branch:
         vmfsVolume = branch['--onvmfs']
      elif '--onfirstvmfs' in branch:
         filterList = self._firstDiskFilters(branch['--onfirstvmfs'])
         vmfsVolumeObj = self._firstDatastore(filterList,
                                              size + VMDK_OVERHEAD_SIZE)
         if not vmfsVolumeObj:
            errors.append("no suitable VMFS volume found for virtualdisk "
                          "--onfirstvmfs")
         else:
            vmfsVolume = vmfsVolumeObj.name
      else:
         errors.append("virtualdisk requires --onvmfs or --onfirstvmfs")

      if errors:
         return makeResult(errors, warnings)

      errors, onDisk = self._checkVirtualDisk(vmfsVolume, imagePath, size)
      
      clearDrives = userchoices.getClearPartitions().get('drives', [])
      if vmfsVolume not in self.vmfsVolumes and onDisk in clearDrives:
         errors.append('virtualdisk specified, but drive "%s" '
                       'is scheduled to be cleared.' % onDisk)
      
      if errors:
         return makeResult(errors, warnings)
      
      removeOldVirtualDevices()
      vdd = VirtualDiskDev(name,
                           size=size,
                           vmfsVolume=vmfsVolume,
                           imagePath=imagePath,
                           imageName=imageName,
                           physicalDeviceName=onDisk)
      self.vmdkDeviceName = name
      self.vmdkDevice = vdd
      
      userchoices.addVirtualDevice(vdd)
      
      return makeResult(errors, warnings)


   def doReboot(self):
      branch = self.bumpTree['reboot']
      userchoices.setReboot(True)
      userchoices.setNoEject('--noeject' in branch)
      
      return (Result.SUCCESS, [], [])


   def doRootpw(self):

      branch = self.bumpTree['rootpw']
      password = branch['password']

      errors = []
      warnings = []

      crypted = False
      if '--iscrypted' in branch: crypted = True

      if crypted:
         if ((password.startswith('$1$') and
             re.match('^(' + RegexLocator.md5 + ')$', password) is None) or
             (not password.startswith('$1$') and len(password) != 13)):
            errors.append('crypted password is not valid.')

      if not crypted:
         try:
            sanityCheckPassword(password)
         except ValueError, msg:
            errors.append(str(msg))

      if errors:
         return (Result.FAIL, errors, warnings)

      if not crypted:
         password = cryptPassword(password, True)

      if not password.startswith('$1$'):
         userchoices.setRootPassword(password, \
                                     userchoices.ROOTPASSWORD_TYPE_CRYPT) 
      else:
         userchoices.setRootPassword(password, \
                                     userchoices.ROOTPASSWORD_TYPE_MD5) 

      if warnings:
         return (Result.WARN, [], warnings)

      return (Result.SUCCESS, [], [])


   def doTimezone(self):

      branch = self.bumpTree['timezone']
      assert 'timezone' in branch
      
      timeZoneStr = branch['timezone']

      # TODO: need to validate the timezones against a known list

      utc = True

      try:
         tz = self.timezones.findByZoneName(timeZoneStr)
      except IndexError:
         return (Result.WARN,
                 [],
                 ['invalid timezone "%s" was specified. Using default.' %
                  timeZoneStr])

      userchoices.setTimezone(tz.zoneName, isUTC=utc)

      return (Result.SUCCESS, [], [])


   def doVMAcceptEULA(self):
      userchoices.setAcceptEULA(True)
      return (Result.SUCCESS, [], [])

   def doVMSerialNum(self):
      warnings = []
      errors = []
      branch = self.bumpTree['vmserialnum']

      serialNumber = branch['--esx']
      try:
         esxlicense.checkSerialNumber(serialNumber)
      except esxlicense.LicenseException, e:
         errors.append(str(e))
         return makeResult(errors, warnings)

      userchoices.setSerialNumber(serialNumber)
      return makeResult(errors, warnings)
      

   def doZeroMBR(self):
      userchoices.setZeroMBR(True)
      return (Result.SUCCESS, [], [])


   def doPackagesSection(self):
      warnings = []
      errors = []
      branch = self.bumpTree['%packages']
      
      scriptedinstallFile = self.scriptedinstallFiles[-1]
      listing = scriptedinstallFile.getLinesUntilNextKeyword().split('\n')

      userchoices.setIgnoreDeps('--ignoredeps' in branch)
      userchoices.setResolveDeps('--resolvedeps' in branch)

      pkgs = packages.Packages()
      pkgs.readPackages()
      knownPackages = pkgs.getPackageNames()
      for pkg in map(string.strip, listing):
         if pkg == "" or pkg.startswith("#"):
            # Ignore empty lines and comments.
            continue
         
         isRemove = False
         if pkg.startswith('-'):
            pkg = pkg[1:].strip()
            isRemove = True
         if pkg not in knownPackages:
            warnings.append('package "%s" not found.' % pkg)
         elif isRemove:
            matches = pkgs.getPackagesByName(pkg)
            if matches[0].requirement == "required":
               warnings.append('package "%s" is required and cannot be '
                               'removed' % pkg)
            else:
               userchoices.addPackageNotToInstall(pkg)
         else:
            userchoices.addPackageToInstall(pkg)

      return makeResult(errors, warnings)


   def doPreSection(self):
      preScript, result = self.doMultilineCommand('%pre')
      if preScript and '%pre' in self.onlyCommands:
         # Only add the script if we're in the prepass.
         userchoices.addPreScript(preScript)

      return result


   def doPostSection(self):
      postScript, result = self.doMultilineCommand('%post')
      if postScript:
         userchoices.addPostScript(postScript)

      return result


   def doMultilineCommand(self, cmd):
      branch = self.bumpTree[cmd][-1]
      
      assert branch is not None, 'internal error: branch is None'

      errors = []
      warnings = []
      if '--interpreter' in branch:
         interp = interpreters[branch['--interpreter']]
      else:
         warnings.append('interpreter not defined. Defaulting to bash') 
         interp = interpreters['bash']

      scriptedinstallFile = self.scriptedinstallFiles[-1]
      script = scriptedinstallFile.getLinesUntilNextKeyword()

      if len(script) > 0:
         inChroot = False
         if cmd == '%post' and '--nochroot' not in branch:
            inChroot = True

         timeoutInSecs = 0
         if cmd == '%post' and '--timeout' in branch:
            try:
               timeoutInSecs = int(branch['--timeout'])
            except ValueError:
               errors.append('invalid timeout value for %post')

         ignoreFailure = False
         if (cmd == '%post' and
             branch.get('--ignorefailure', 'false').lower() == 'true') or \
             cmd == '%pre':
            ignoreFailure = True
         
         scriptFile = Script(script,
                             interp,
                             inChroot,
                             timeoutInSecs,
                             ignoreFailure)
      else:
         scriptFile = None

      log.debug('scripts: ' + repr(scriptFile))

      return (scriptFile, makeResult(errors, warnings))




#####################################################################
#                  Launcher code for Debugging                      #
#####################################################################
#####################################################################

class Usage(Exception): #pragma: no cover
   def __init__(self, msg):
      self.msg = msg


def main(argv=None): #pragma: no cover
   if not argv:
      argv = sys.argv
   try:
      try:
         opts, args = getopt.getopt(argv[1:], "f", ["file"])
      except getopt.error, msg:
         raise Usage(msg)

      scriptedinstall = ScriptedInstallPreparser(args[0])
      
      log.info('Preparsing ...')
      (result, errors, warnings) = scriptedinstall.preParse()
      logStuff(result, errors, warnings, 'Preparse problems...')
      log.info('Completed parsing all scriptedinstall files')

      if not result:
         log.error('Load failed due to previous errors')
      else: 
         log.info('Validating ...')
         (result, errors, warnings) = \
                            scriptedinstall.validate(scriptedinstall.grammarDefinition.grammar, 
                                               scriptedinstall.bumpTree.keys())

         logStuff(result, errors, warnings, 'Validation problems...')

         if not result:
            log.error('Validation failed due to previous errors')

      log.debug(scriptedinstall.bumpTree.items())
      
   except Usage, err:
      log.error(err.msg)
      return 2


import getopt

if __name__ == "__main__": #pragma: no cover
   import doctest
   doctest.testmod()
   
   sys.exit(main())
