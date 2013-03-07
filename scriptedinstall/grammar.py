
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
import urlparse

sys.path.append( '..' )

from regexlocator import RegexLocator
from scriptedinstallutil import makeResult
from networking.utils import \
     sanityCheckIPString, \
     sanityCheckHostname, \
     sanityCheckIPorHostname, \
     sanityCheckGatewayString, \
     sanityCheckNetmaskString, \
     sanityCheckMultipleIPsString, \
     sanityCheckVlanID, \
     sanityCheckUrl

class GrammarDetail:
   REQUIRED, OPTIONAL, DEPRECATED, UNUSED, ALIAS, CONDITIONAL = range(6)


class ArgumentOrientation:
   '''
   Enumeration used to specify where non-flag arguments are located.
   
   FRONT    The argument is the first one after the command, flag arguments
            will follow afterward.
   BACK     The argument is the last.
   
   '''
   FRONT, BACK = range(2)

def validateSize(flagName, size):
   '''Test whether a string is a valid size value (i.e. a number greater than
   zero).

   >>> validateSize('test', '100')
   (1, [], [])
   >>> validateSize('test', 'foo')
   (0, ['"test=" is not a number.'], [])
   >>> validateSize('test', '0')
   (0, ['"test=" must be a value greater than zero.'], [])
   >>> validateSize('test', '-100')
   (0, ['"test=" must be a value greater than zero.'], [])
   '''
   errors = []
   
   try:
      size = int(size)
      if size <= 0:
         errors.append('"%s=" must be a value greater than zero.' % flagName)
   except ValueError:
      errors.append('"%s=" is not a number.' % flagName)

   return makeResult(errors, [])

def validateInstallURL(flagName, url):
   '''Test whether a string is a valid URL for the "install" command.

   >>> validateInstallURL('url', 'http://foobar.com:80/path')
   (1, [], [])
   >>> validateInstallURL('url', 'nfs')
   (1, [], [])
   >>> validateInstallURL('url', 'ftp://127.0.0.1/path')
   (1, [], [])
   >>> validateInstallURL('url', 'foo://hostname/path')
   (0, ['url is not one of the supported schemes: http, ftp', 'Hostname must be at least one character.'], [])
   >>> validateInstallURL('url', 'http://300.2.3.4/path')
   (0, ['IP string contains an invalid octet.'], [])
   '''

   if url == "nfs": # Takes care of 'install nfs --dir=... --server=...'
      return makeResult([], [])

   errors = []

   try:
      sanityCheckUrl(url)
   except ValueError, msg:
      errors.append(str(msg))
   
   return makeResult(errors, [])

def adaptToValidator(sanityFunction):
   r'''Adapt a sanityCheck function so it can be used as a valueValidator.

   The sanityCheck function should take a single argument and throw a
   ValueError exception if the argument is invalid.

   >>> validator = adaptToValidator(sanityCheckHostname)
   >>> validator('test', '1234')
   (0, ['"test=" Hostname must start with a valid character in the range \'a-z\' or \'A-Z\'.'], [])
   '''
   
   def validator(flagName, value):
      errors = []

      try:
         sanityFunction(value)
      except ValueError, msg:
         errors.append('"%s=" %s' % (flagName, str(msg)))

      return makeResult(errors, [])

   return validator

# Create validators for network-related data.
validateHostname = adaptToValidator(sanityCheckHostname)
validateIPString = adaptToValidator(sanityCheckIPString)
validateIPorHostname = adaptToValidator(sanityCheckIPorHostname)
validateGatewayString = adaptToValidator(sanityCheckGatewayString)
validateNetmaskString = adaptToValidator(sanityCheckNetmaskString)
validateMultipleIPsString = adaptToValidator(sanityCheckMultipleIPsString)
validateVlanID = adaptToValidator(sanityCheckVlanID)

class GrammarDefinition:
   '''
   Container for the scripted installation grammar definition, which consists
   of a set of commands and their arguments.  The syntax is a command name
   followed by zero or more required or optional arguments.
   '''
   
   def __init__(self):
      self.grammar = self.getScriptedInstallGrammar()
      self._self_check()

   def _self_check(self):
      '''
      Check the grammar to make sure it is sane.
      '''
      
      for command, value in self.grammar.items():
         assert 'detail' in value
         if self.isDeprecated(command) or self.isUnused(command):
            continue

         assert 'descr' in value, "'descr' missing from %s" % command
         assert 'grammar' in value, "'grammar' missing from %s" % command
         assert set(value.keys()).issubset([
            'descr',
            'detail',
            'grammar',
            'alias',
            'options',
            'requiresMsg',
            'requires']), \
            "'%s' has extra attributes" % command
         
         cmdGrammar = self.getCommandGrammar(command)
         assert 'id' in cmdGrammar, "'id' missing from %s" % command
         assert 'args' in cmdGrammar, "'args' missing from %s" % command
         for arg, argGrammar in cmdGrammar['args'].items():
            assert 'detail' in argGrammar
            assert set(argGrammar.keys()).issubset([
               'detail',
               'valueRegex',
               'regexFlags',
               'valueValidator',
               'regexMsg',
               'noneValue',
               'defaultValue',
               'invalids',
               'requires',
               'onRegexMismatch',
               'alias',
               'requiresMsg',
               ]), \
               "'%s.%s' has extra attributes" % (command, arg)

   def isCommand(self, command):
      return command in self.grammar

   def isDeprecated(self, command):
      '''
      Return true if a command in the grammar is deprecated.

      >>> gd = GrammarDefinition()
      >>> gd.isDeprecated("firstboot")
      True
      >>> gd.isDeprecated("auth")
      False
      '''
      
      assert command in self.grammar
      assert 'detail' in self.grammar[command]

      return self.grammar[command]['detail'] == GrammarDetail.DEPRECATED
   
   def isUnused(self, command):
      '''
      Return true if a command in the grammar is unused, meaning we will
      support it in the future.

      >>> gd = GrammarDefinition()
      >>> gd.isUnused("lang")
      True
      >>> gd.isUnused("auth")
      False
      '''
      
      assert command in self.grammar
      assert 'detail' in self.grammar[command]

      return self.grammar[command]['detail'] == GrammarDetail.UNUSED
   
   def addRequirement(self, command, requirement):
      if command not in self.grammar:
         return False
      
      if requirement not in self.grammar:
         return False

      requirements = self.grammar[command].get('requires', [])
      requirements.append(requirement)
      # set it incase get() returned []
      self.grammar[command]['requires'] = requirements
      
      return True

   
   def getCommandGrammar(self, command):
      '''
      Return the grammar for the given command.

      >>> gd = GrammarDefinition()
      >>> gd.getCommandGrammar("reboot")
      {'args': {'--noeject': {'detail': 1}}, 'id': 'reboot'}
      '''
      
      assert command in self.grammar
      assert 'grammar' in self.grammar[command]

      return self.grammar[command]['grammar']()

   def bindCallback(self, command, action, func):
      '''
      Insert a callback into the grammar.

      >>> gd = GrammarDefinition()
      >>> cb = lambda: "Hello, World!"
      >>> gd.bindCallback("install", "environmentAction", cb)
      >>> gd.grammar["install"]["environmentAction"]()
      'Hello, World!'
      '''

      self.grammar[command][action] = func

   def getScriptedInstallGrammar(self):
      '''
      Returns a dictionary containing all of the commands in the grammar mapped
      to their definitions.  The command grammar definition consists of a
      dictionary with the following keys:

        descr        English description of the command.
        detail       The type of command (see GrammarDetail).
        grammar      A function that will return the argument grammar
                     definition for this command.
        alias        The command this command is an alias for.
        options      Tuple of strings that denote optional flags:
                      "multiple" -- the command can be used more than once.
        requires     This command requires another command to be given.
        requiresMsg  Error message to use when a required command is not given.

      The "grammar" function for a supported command returns a dictionary with
      an "args" key that describe the arguments supported by the command.  The
      value for the "args" key is a dictionary with the following keys:

        valueRegex   Indicates that the argument should take a value and it
                     should match this regular expression.
        valueValidator
                     A function that does further validation on the argument
                     value.
        regexMsg     The error/warning message to use when a value does
                     not match.
        onRegexMismatch
                     Set to either "error" or "warning" to indicate what to do
                     in case a value does not match the valueRegex.
                     Defaults to "warning".
        noneValue    The default value is none is given by the user.
        defaultValue
                     When a valueRegex mismatch is detected and it is not an
                     error, this value should be used.
        invalids     A list of other arguments that become invalid when this
                     argument is used.
        requires     A list of other arguments that need to be used with this
                     argument.
        requiresMsg  Error message to use when a required argument is not
                     given.
        alias        This argument is an alias for another.

      >>> gd = GrammarDefinition()
      >>> sig = gd.getScriptedInstallGrammar()
      >>> sig["auth"]["detail"] == GrammarDetail.OPTIONAL
      True
      '''
      
      return {
         'auth' : dict(
            descr='setup authentication for the system', 
            detail=GrammarDetail.OPTIONAL, 
            grammar=self.getAuthGrammar,
            alias='authconfig'
         ),
         'authconfig' : dict(
            descr='setup authentication for the system', 
            detail=GrammarDetail.ALIAS, 
            grammar=self.getAuthGrammar,
            alias='auth'
         ),
         'autopart' : dict(
            descr='create the default partition scheme',
            detail=GrammarDetail.OPTIONAL,
            grammar=self.getAutopartGrammar,
         ),
         'autostep' : dict( detail=GrammarDetail.DEPRECATED ),
         'bootloader' : dict(
            descr='setup the GRUB bootloader', 
            detail=GrammarDetail.OPTIONAL,
            grammar=self.getBootloaderGrammar,
         ),
         'clearpart' : dict(
            descr='Clear existing partitions on the disk', 
            detail=GrammarDetail.OPTIONAL, 
            grammar=self.getClearpartGrammar,
            options=['multiple'],
         ),
         'cmdline' : dict( detail=GrammarDetail.DEPRECATED ),
         'device' : dict( detail=GrammarDetail.DEPRECATED ),
         'deviceprobe' : dict( detail=GrammarDetail.DEPRECATED ),
         'dryrun' : dict(
            descr='Do not actually perform the install',
            detail=GrammarDetail.OPTIONAL, 
            grammar=self.getDryrunGrammar,
         ),
         'esxlocation' : dict(
            descr='Specify the location of the /boot partition',
            detail=GrammarDetail.OPTIONAL,
            grammar=self.getEsxLocationGrammar,
         ),
         'firewall' : dict(
            descr='setup inbound/outbound net traffic for the COS', 
            detail=GrammarDetail.OPTIONAL,
            grammar=self.getFirewallGrammar,
         ),
         'firewallport' : dict(
            descr='setup a custom port rule for the COS', 
            detail=GrammarDetail.OPTIONAL,
            grammar=self.getFirewallPortGrammar,
            options=['multiple'],
         ),
         'firstboot' : dict( detail=GrammarDetail.DEPRECATED ),
         'harddrive' : dict( detail=GrammarDetail.DEPRECATED ),
         'ignoredisk' : dict( detail=GrammarDetail.DEPRECATED ),
         'install' : dict(
            descr='specify installation method for the system',
            detail=GrammarDetail.OPTIONAL,
            grammar=self.getInstallGrammar,
         ),
         'interactive' : dict(detail=GrammarDetail.DEPRECATED),
         'keyboard' : dict(
            descr='specify a keyboard type for the system', 
            detail=GrammarDetail.OPTIONAL,
            grammar=self.getKeyboardGrammar,
         ),
         'lang' : dict(detail=GrammarDetail.UNUSED,),
         'langsupport' : dict(detail=GrammarDetail.UNUSED,),
         'lilo' : dict(detail=GrammarDetail.DEPRECATED,),
         'lilocheck' : dict(detail=GrammarDetail.DEPRECATED,),
         'logvol' : dict(detail=GrammarDetail.DEPRECATED,),
         'mouse' : dict(detail=GrammarDetail.DEPRECATED,),
         'network' : dict(
            descr='setup a network address for the COS',
            detail=GrammarDetail.OPTIONAL,
            grammar = self.getNetworkGrammar,
         ),
         'part' : dict(
            descr='setup partioning for physical disks',
            detail=GrammarDetail.OPTIONAL,
            grammar=self.getPartitionGrammar,
            alias='partition',
            options=['multiple'],
         ),
         'partition' : dict(
            descr='setup partitioning for physical disks',
            detail=GrammarDetail.ALIAS,
            grammar=self.getPartitionGrammar,
            alias='part',
            options=['multiple'],
         ),
         'paranoid' : dict(
            descr='fail on warnings',
            detail=GrammarDetail.OPTIONAL, 
            grammar=self.getParanoidGrammar,
         ),
         'raid' : dict(detail=GrammarDetail.DEPRECATED,),
         'reboot' : dict(
            descr='reboot the machine after the install is finished',
            detail=GrammarDetail.OPTIONAL, 
            grammar=self.getRebootGrammar,
         ),
         'rootpw' : dict(
            descr='setup the Root Password for the system',
            detail=GrammarDetail.OPTIONAL,
            grammar=self.getRootpwGrammar,
         ),
         'skipx' : dict(detail=GrammarDetail.DEPRECATED,),
         'text' : dict(detail=GrammarDetail.DEPRECATED),
         'timezone' : dict(
            descr='Specify the timezone for the system',
            detail=GrammarDetail.OPTIONAL,
            grammar=self.getTimezoneGrammar,
         ),
         'upgrade' : dict(
            descr='Switch to upgrade mode',
            detail=GrammarDetail.OPTIONAL,
            grammar=self.getUpgrade,
         ),
         'virtualdisk' : dict(
            descr='Create a virtual disk on a vmfs partition',
            detail=GrammarDetail.OPTIONAL,
            grammar=self.getVirtualDisk,
         ),
         'vmaccepteula' : dict(
            descr='Accept the VMware EULA',
            detail=GrammarDetail.REQUIRED,
            grammar=self.getVMAcceptEULAGrammar,
            alias='accepteula',
         ),
         'accepteula' : dict(
            descr='Accept the VMware EULA',
            detail=GrammarDetail.ALIAS,
            grammar=self.getVMAcceptEULAGrammar,
            alias='vmaccepteula',
         ),
         'vmserialnum' : dict(
            descr='Setup licensing for ESX',
            detail=GrammarDetail.OPTIONAL,
            grammar=self.getVMSerialNumGrammar,
            alias='serialnum',
         ),
         'serialnum' : dict(
            descr='Setup licensing for ESX',
            detail=GrammarDetail.ALIAS,
            grammar=self.getVMSerialNumGrammar,
            alias='vmserialnum',
         ),
         'vnc' : dict(detail=GrammarDetail.DEPRECATED),
         'volgroup' : dict(detail=GrammarDetail.DEPRECATED),
         'xconfig' : dict(detail=GrammarDetail.DEPRECATED),
         'xdisplay' : dict(detail=GrammarDetail.DEPRECATED),
         'vmlicense' : dict(detail=GrammarDetail.DEPRECATED),
         'zerombr' : dict(
            descr='Zero the Master Boot Record',
            detail=GrammarDetail.OPTIONAL,
            grammar=self.getZeroMBRGrammar,
         ),
         #
         # Special scriptedinstall keywords
         #
         '%include' : dict(
            descr='Include a seperate scriptedinstall file', 
            detail=GrammarDetail.OPTIONAL, 
            grammar=self.getIncludeGrammar,
            alias='include',
            options=['multiple'],
         ),
         'include' : dict(
            descr='Include a seperate scriptedinstall file', 
            detail=GrammarDetail.ALIAS, 
            grammar=self.getIncludeGrammar,
            alias='%include',
            options=['multiple'],
         ),
         '%packages' : dict(
            descr='Specify additional packages to install off of the' + \
                  ' install media',
            detail= GrammarDetail.OPTIONAL,
            grammar=self.getPackagesSectionGrammar,
         ),
         '%pre' : dict(
            descr='Special commands to be executed pre-configuration' + \
                  ' and installation',
            detail=GrammarDetail.OPTIONAL,
            grammar=self.getPreSectionGrammar,
            options=['multiple'],
         ),
         '%post' : dict(
            descr='Special commands to be executed post installation',
            detail=GrammarDetail.OPTIONAL,
            grammar=self.getPostSectionGrammar,
            options=['multiple'],
         ),
         '%vmlicense_text' : dict(detail=GrammarDetail.DEPRECATED),
      }


   def getAutopartGrammar(self):
      return {
         'id' : 'autopart',
         'args' : {
                     '--drive' : dict(
                                    detail=GrammarDetail.OPTIONAL,
                                    valueRegex='.+',
                                    alias='--disk',
                                    invalids=('--firstdisk','--onvmfs'),
                                 ),
                     '--disk' : dict(
                                    detail=GrammarDetail.ALIAS,
                                    valueRegex='.+',
                                    alias='--drive',
                                    invalids=('--firstdisk','--onvmfs'),
                                 ),
                     '--firstdisk' : dict(
                                    detail=GrammarDetail.OPTIONAL,
                                    invalids=('--disk','--drive','--onvmfs'),
                                    noneValue='local,remote',
                                    valueRegex='.+',
                                 ),
                     '--onvmfs' : dict(
                                    detail=GrammarDetail.OPTIONAL,
                                    invalids=('--disk','--drive','--firstdisk'),
                                    valueRegex='.+',
                                 ),
                     '--extraspace' : dict(
                                    detail=GrammarDetail.OPTIONAL,
                                    valueValidator=validateSize,
                                 ),
                     '--vmdkpath' : dict(
                                    detail=GrammarDetail.OPTIONAL,
                                    valueRegex=RegexLocator.vmdkpath,
                                 ),
                  },
      }


   def getAuthGrammar(self):
      return {
         'id' : 'auth',
         'args' : {
                     '--disablemd5' : dict(
                                        detail=GrammarDetail.DEPRECATED,
                                        invalids=('--enablemd5',),
                                      ),
                     '--enablemd5' : dict(
                                        detail=GrammarDetail.DEPRECATED,
                                        invalids=('--disablemd5',),
                                     ),
                     '--enablenis' : dict(detail=GrammarDetail.OPTIONAL,
                                          requires=('--nisdomain', '--nisserver'),
                                          ),
                     '--nisdomain' : dict(
                                        detail=GrammarDetail.OPTIONAL,
                                        requires=('--enablenis',),
                                        valueValidator=validateHostname,
                                     ),
                     '--nisserver' : dict(
	                                detail=GrammarDetail.OPTIONAL,
                                        requires=('--enablenis',),
                                        valueValidator=validateIPorHostname,
                                     ),
                     '--useshadow' : dict(
                                        detail=GrammarDetail.DEPRECATED,
                                        invalids=('--disableshadow',),
                                     ),
                     '--enableshadow' : dict(
                                           detail=GrammarDetail.DEPRECATED,
                                           invalids=('--disableshadow',),
                                        ),
                     '--disableshadow' : dict(
                                           detail=GrammarDetail.DEPRECATED,
                                           invalids=('--enableshadow'),
                                         ),
                     '--enablekrb5' : dict(
	                                 detail=GrammarDetail.OPTIONAL,
                                         requires=('--krb5realm', '--krb5kdc',
                                                   '--krb5adminserver'),
                                      ),
                     '--krb5realm' : dict(
	                                detail=GrammarDetail.OPTIONAL, 
                                        requires=('--enablekrb5',), 
                                        valueValidator=validateHostname,
                                     ),
                     '--krb5kdc' : dict(
	                              detail=GrammarDetail.OPTIONAL, 
                                      requires=('--enablekrb5',),
                                      # XXX Anaconda allows multiple kdcs in
                                      # a comma separated list.
                                      valueValidator=validateIPorHostname,
                                   ),
                     '--krb5adminserver' : dict(
                                          detail=GrammarDetail.OPTIONAL, 
                                          requires=('--enablekrb5',),
                                          valueValidator=validateIPorHostname,
                                           ),
                     '--enableldap' : dict(detail=GrammarDetail.OPTIONAL),
                     '--enableldapauth' : dict(
                                             detail=GrammarDetail.OPTIONAL,
                                             requires=('--enableldap',), 
                                          ),
                     '--ldapserver' : dict(
                                         detail=GrammarDetail.OPTIONAL,
                                         requires=('--enableldap',), 
                                         valueValidator=validateIPorHostname,
                                      ),
                     '--ldapbasedn' : dict(
                                         detail=GrammarDetail.OPTIONAL,
                                         requires=('--enableldap',), 
                                         valueRegex='.+',
                                      ),
                     '--enableldaptls' : dict(
                                            detail=GrammarDetail.OPTIONAL,
                                            requires=('--enableldap',),
                                         ),
                     '--enablead' : dict(detail=GrammarDetail.DEPRECATED,
                                         requires=('--addomain', '--addc')),
                     '--addomain' : dict(detail=GrammarDetail.DEPRECATED,
                                         requires=('--enablead',),
                                         valueValidator=validateHostname,
                                         ),
                     '--addc' : dict(detail=GrammarDetail.DEPRECATED,
                                     requires=('--enablead',),
                                     valueValidator=validateIPorHostname,
                                     ),
                  },
      }


   def getBootloaderGrammar(self):
      return {
         'id' : 'bootloader',
         'args' : {
                     '--append' : dict(
                                     detail=GrammarDetail.OPTIONAL,
                                     valueRegex='.*',
                                  ),
                     '--driveorder' : dict(
                                         detail=GrammarDetail.OPTIONAL,
                                         valueRegex='.+',
                                      ),
                     '--location' : dict(
                                       detail=GrammarDetail.OPTIONAL,
                                       valueRegex=RegexLocator.bootloader,
                                       regexMsg='bootloader --location= is invalid: must be "mbr", "partition" or "none". Defaulting to "mbr".',
                                       defaultValue='mbr',
                                    ),
                     '--md5pass' : dict(
                                      detail=GrammarDetail.OPTIONAL,
                                      valueRegex=RegexLocator.md5,
                                      regexMsg='bootloader --md5pass= string is not valid. Bootloader password is not set.',
                                      defaultValue='',
                                   ),
                     '--password' : dict(
                                       detail=GrammarDetail.OPTIONAL,
                                       valueRegex='.*',
                                    ),
                     '--upgrade' : dict(
                                      detail=GrammarDetail.OPTIONAL,
                                   ),
                  },
      }


   def getClearpartGrammar(self):
      return {
         'id' : 'clearpart',
         'args' : {
                     '--exceptvmfs' : dict(
                                   detail=GrammarDetail.OPTIONAL,
                                   invalids=('--all','--linux'),
                                      ),
                     '--overwritevmfs' : dict(
                                   detail=GrammarDetail.OPTIONAL,
                                   ),
                     '--all' : dict(
                                  detail=GrammarDetail.OPTIONAL,
                                  invalids=('--exceptvmfs','--linux'),
                               ),
                     '--drives' : dict(
                                     detail=GrammarDetail.OPTIONAL,
                                     valueRegex='.+',
                                     invalids=('--ignoredrives','--alldrives'),
                                  ),
                     '--ignoredrives' : dict(
                                     detail=GrammarDetail.OPTIONAL,
                                     valueRegex='.+',
                                     invalids=('--drives','--alldrives'),
                                  ),
                     # XXX Is initlabel still needed?  We don't do anything
                     # with it...
                     '--initlabel' : dict(
                                  detail=GrammarDetail.OPTIONAL,
                                     ),
                     '--alldrives' : dict(
                                     detail=GrammarDetail.OPTIONAL,
                                     invalids=('--drives','--ignoredrives'),
                                     ),
                     '--firstdisk' : dict(
                                    detail=GrammarDetail.OPTIONAL,
                                    invalids=('--alldrives',
                                              '--drives',
                                              '--ignoredrives',),
                                    noneValue='local,remote',
                                    valueRegex='.+',
                                 ),
                  },
      }


   def getDryrunGrammar(self):
      return dict(id='dryrun', args={})


   def getEsxLocationGrammar(self):
      return {
         'id' : 'esxlocation',
         'args' : {
                     '--uuid' : dict(
                                    detail=GrammarDetail.OPTIONAL,
                                    valueRegex=RegexLocator.uuid,
                                    invalids=('--disk','--drive',),
                                   ),
                     '--clearcontents' : dict(
                                    detail=GrammarDetail.OPTIONAL,
                                 ),
                     '--drive' : dict(
                                    detail=GrammarDetail.OPTIONAL,
                                    valueRegex='.+',
                                    alias='--disk',
                                    invalids=('--firstdisk','--uuid'),
                                 ),
                     '--disk' : dict(
                                    detail=GrammarDetail.ALIAS,
                                    valueRegex='.+',
                                    alias='--drive',
                                    invalids=('--firstdisk','--uuid'),
                                 ),
                     '--firstdisk' : dict(
                                    detail=GrammarDetail.OPTIONAL,
                                    invalids=('--disk','--drive','--uuid'),
                                    noneValue='local,remote',
                                    valueRegex='.+',
                                 ),
                     }
         }

   def getFirewallGrammar(self):
      return {
         'id' : 'firewall',
         'args' : {
                     '--enabled' : dict(
                                      detail=GrammarDetail.OPTIONAL,
                                      invalids=('--disabled',
                                                '--allowIncoming',
                                                '--allowOutgoing'),
                                   ),
                     '--disabled' : dict(
                                       detail=GrammarDetail.OPTIONAL,
                                       invalids=('--enabled',
                                                 '--blockIncoming',
                                                 '--blockOutgoing',),
                                    ),
                     '--blockIncoming' : dict(
                                  detail=GrammarDetail.DEPRECATED,
                                  invalids=('--allowIncoming',),
                               ),
                     '--blockOutgoing' : dict(
                                  detail=GrammarDetail.DEPRECATED,
                                  invalids=('--allowOutgoing',),
                               ),
                     '--allowIncoming' : dict(
                                   detail=GrammarDetail.OPTIONAL,
                                   invalids=('--blockIncoming',),
                                ),
                     '--allowOutgoing' : dict(
                                   detail=GrammarDetail.OPTIONAL,
                                   invalids=('--blockOutgoing',),
                                ),
                  },
      }

   def getFirewallPortGrammar(self):
      return {
         'id' : 'firewallport',
         'args' : {
                     '--open' : dict(
                                   detail=GrammarDetail.OPTIONAL,
                                   invalids=('--close',),
                                ),
                     '--close' : dict(
                                   detail=GrammarDetail.OPTIONAL,
                                   invalids=('--open',),
                                ),
                     '--port' : dict(
                                   detail=GrammarDetail.OPTIONAL,
                                   valueRegex=RegexLocator.port,
                                   regexMsg='invalid firewall port "%(value)s" specified. Must be between 1 and 65535.',
                                   onRegexMismatch='error',
                                ),
                     '--proto' : dict(
                                   detail=GrammarDetail.OPTIONAL,
                                   valueRegex=RegexLocator.firewallproto,
                                   regexMsg='firewallport --proto must be either "tcp" or "udp".',
                                   onRegexMismatch='error',
                                ),
                     '--dir' : dict(
                                   detail=GrammarDetail.OPTIONAL,
                                   valueRegex=RegexLocator.portdir,
                                   regexMsg='firewallport --dir must be "in" or "out".',
                                   onRegexMismatch='error',
                               ),
                     '--name' : dict(
                                   detail=GrammarDetail.OPTIONAL,
                                   valueRegex=RegexLocator.portname,
                                   regexMsg='firewallport --name is not valid. Must be less than 128 characters.',
                                   onRegexMismatch='error',
                               ),
                     '--enableService' : dict(
                                   detail=GrammarDetail.OPTIONAL,
                                   valueRegex=RegexLocator.anywords,
                                   invalids=('--close','--open','--port',
                                             '--proto','--dir','--name',
                                             '--disableService'),
                               ),
                     '--disableService' : dict(
                                   detail=GrammarDetail.OPTIONAL,
                                   valueRegex=RegexLocator.anywords,
                                   invalids=('--close','--open','--port',
                                             '--proto','--dir','--name',
                                             '--enableService'),
                               ),

                  },

      }


   def getIncludeGrammar(self):
      return {
         'id' : 'include',
         'args' : {},
         'hangingArg' : {
            'filename' : dict(
               detail=GrammarDetail.REQUIRED,
               valueRegex='.+',
               orientation=ArgumentOrientation.BACK)
            }}

   
   def getKeyboardGrammar(self):
      return {
         'id' : 'keyboard',
         'args' : {},
         'hangingArg' : {
                           'keyboardtype' : dict(
                              detail=GrammarDetail.REQUIRED,
                              valueRegex='.+',
                              orientation=ArgumentOrientation.BACK,
                            ),
                        },
      }


   def getInstallGrammar(self): 
      return {
         'id' : 'install',
         'args' : {
                     '--server' : dict(
                                     detail=GrammarDetail.OPTIONAL,
                                     valueValidator=validateIPorHostname,
                                  ),
                     '--dir' : dict(
                                  detail=GrammarDetail.OPTIONAL,
                                  valueRegex=RegexLocator.directory
                               ),
                     'cdrom' : dict(
                                  detail=GrammarDetail.OPTIONAL,
                                  invalids=('nfs','usb','url'),
                               ),
                     'usb' : dict(
                                  detail=GrammarDetail.OPTIONAL,
                                  invalids=('cdrom','nfs','url'),
                               ),
                     'nfs' : dict(
                                detail=GrammarDetail.OPTIONAL,
                                requires=('--dir','--server'),
                                invalids=('cdrom','usb','url'),
                             ),
                     'url' : dict(
                                detail=GrammarDetail.OPTIONAL,
                                requires=('urlstring',),
                                requiresMsg='url was not specified',
                                invalids=('cdrom','usb','nfs'),
                             ),
                  },
         'hangingArg' : {
                           'urlstring' : dict(
                              detail=GrammarDetail.OPTIONAL,
                              orientation=ArgumentOrientation.BACK,
                              valueValidator=validateInstallURL,
                           ),
                        },
      }


   def getNetworkGrammar(self):
      return {
         'id' : 'network',
         'args' : {
                     '--bootproto' : dict(
                                        detail=GrammarDetail.OPTIONAL,
                                        valueRegex=RegexLocator.networkproto
                                     ),
                     '--device' : dict(
                                     detail=GrammarDetail.OPTIONAL,
                                     valueRegex='.+',
                                  ),
                     '--ip' : dict(
                                 detail=GrammarDetail.OPTIONAL,
                                 valueValidator=validateIPString,
                              ),
                     '--gateway' : dict(
                                      detail=GrammarDetail.OPTIONAL,
                                      valueValidator=validateGatewayString,
                                   ),
                     '--nameserver' : dict(
                                   detail=GrammarDetail.OPTIONAL,
                                   valueValidator=validateMultipleIPsString,
                                      ),
                     '--nodns' : dict(
                                    detail=GrammarDetail.OPTIONAL,
                                 ),
                     '--netmask' : dict(
                                      detail=GrammarDetail.OPTIONAL,
                                      valueValidator=validateNetmaskString,
                                   ),
                     '--hostname' : dict(
                                 detail=GrammarDetail.OPTIONAL,
                                 valueValidator=validateHostname,
                                    ),
                     '--vlanid' : dict(
                                     detail=GrammarDetail.OPTIONAL,
                                     valueValidator=validateVlanID
                                  ),
                     '--addvmportgroup' : dict(
                                     detail=GrammarDetail.OPTIONAL,
                                     valueRegex=r'(0|1|true|false)',
                                     regexFlags=re.IGNORECASE,
                                  ),
                  },
      }



   def getPackagesSectionGrammar(self):
      return dict(id='%packages', args={
         '--ignoredeps' : dict(
             detail=GrammarDetail.OPTIONAL,
             invalids=('--resolvedeps',),
             ),
         '--resolvedeps' : dict(
             detail=GrammarDetail.OPTIONAL,
             invalids=('--ignoredeps',),
             ),
         })

   def getPartitionGrammar(self):
      return {
         'id' : 'part',
         'args' : {
                     '--size' : dict(
                                   detail=GrammarDetail.REQUIRED,
                                   valueValidator=validateSize,
                                ),
                     '--grow' : dict(
                                   detail=GrammarDetail.OPTIONAL,
                                ),
                     '--maxsize' : dict(
                                      detail=GrammarDetail.OPTIONAL,
                                      valueValidator=validateSize,
                                   ),
                     '--ondisk' : dict(
                                     detail=GrammarDetail.OPTIONAL,
                                     alias='--ondrive',
                                     valueRegex='.+',
                                     invalids=('--onvirtualdisk',
                                               '--onfirstdisk',),
                     ),
                     '--ondrive' : dict(
                                      detail=GrammarDetail.ALIAS,
                                      alias='--ondisk',
                                      valueRegex='.+',
                                      invalids=('--onvirtualdisk',
                                                '--onfirstdisk',),
                                   ),
                     '--onfirstdisk' : dict(
                                      detail=GrammarDetail.OPTIONAL,
                                      invalids=('--onvirtualdisk',
                                                '--ondisk',),
                                      noneValue='local,remote',
                                      valueRegex='.+',
                                   ),
                     '--fstype' : dict(
                                     detail=GrammarDetail.OPTIONAL,
                                     valueRegex='.+',
                                  ),
                     '--badblocks' : dict(
                                        detail=GrammarDetail.OPTIONAL,
                                     ),
                     '--asprimary' : dict(
                                        detail=GrammarDetail.OPTIONAL,
                                     ),
                     '--onvirtualdisk' : dict(
                                        detail=GrammarDetail.OPTIONAL,
                                        valueRegex='.+',
                                        invalids=('--ondisk', '--ondrive',
                                                  '--onfirstdisk',),
                                     ),
                  },
         'hangingArg' : {
                           'mountpoint' : dict(
                              detail=GrammarDetail.REQUIRED,
                              valueRegex=RegexLocator.mountpoint,
                              orientation=ArgumentOrientation.FRONT,
                              onRegexMismatch='error',
                           )
                        },
      }


   def getParanoidGrammar(self):
      return dict(id='paranoid', args={})


   def getPreSectionGrammar(self):
      return {
         'id' : '%pre',
         'args' : {
                     '--interpreter' : dict(
                                          detail=GrammarDetail.OPTIONAL,
                                          valueRegex=RegexLocator.preInterpreter,
                                          regexMsg='interpreter "%(value)s" not found.',
                                          onRegexMismatch='error',
                               ),
                  },
      }


   def getPostSectionGrammar(self):
      return {
         'id' : '%post',
         'args' : {
                     '--interpreter' : dict(
                                          detail=GrammarDetail.OPTIONAL,
                                          valueRegex=RegexLocator.postInterpreter,
                                          regexMsg='interpreter "%(value)s" not found.',
                                          onRegexMismatch='error',
                                       ),
                     '--nochroot' : dict(
                                          detail=GrammarDetail.OPTIONAL,
                                    ),
                     '--timeout' : dict(
                                          detail=GrammarDetail.OPTIONAL,
                                          valueRegex='\d+',
                                    ),
                     '--ignorefailure' : dict(
                                          detail=GrammarDetail.OPTIONAL,
                                          valueRegex='(true|false)',
                                          regexFlags=re.IGNORECASE,
                                    )
                  },
      }


   def getRebootGrammar(self):
      return {
         'id' : 'reboot', 
         'args' : {
                     '--noeject' : dict( 
                                      detail=GrammarDetail.OPTIONAL,
                                   ),
                  },
      }


   def getRootpwGrammar(self):
      return {
         'id' : 'rootpw',
         'args' : {
                     '--iscrypted' : dict(
                        detail=GrammarDetail.OPTIONAL,
                     ),
                  },
         'hangingArg' : {
                           'password' : dict(
                               orientation=ArgumentOrientation.BACK,
                               detail=GrammarDetail.REQUIRED,
                               valueRegex='.*',
                            ) 
                        }

      }


   def getTimezoneGrammar(self):
      return {
         'id' : 'timezone',
         'args' : {
                     '--utc' : dict(
                                  detail=GrammarDetail.DEPRECATED,
                               ),
                  },
         'hangingArg' : {
                           'timezone' : dict(
                              detail=GrammarDetail.REQUIRED,
                              valueRegex='.+',
                              orientation=ArgumentOrientation.BACK,
                           ),
                        },
      }


   def getUpgrade(self):
      return {
         'id' : 'upgrade',
         'args' : { },
         }


   def getVirtualDisk(self):
      return {
         'id' : 'virtualdisk',
         'args' : {
                     '--size' : dict(
                                   detail=GrammarDetail.REQUIRED,
                                   valueValidator=validateSize,
                                ),
                     '--onvmfs' : dict(
                                     detail=GrammarDetail.OPTIONAL,
                                     invalids=('--onfirstvmfs',),
                                     valueRegex='.+',
                                  ),
                     '--onfirstvmfs' : dict(
                                     detail=GrammarDetail.OPTIONAL,
                                     invalids=('--onvmfs',),
                                     noneValue='local,remote',
                                     valueRegex='.+',
                                  ),
                     '--path' : dict(
                                     detail=GrammarDetail.OPTIONAL,
                                     valueRegex=RegexLocator.vmdkpath,
                                  ),
                  },
         'hangingArg' : {
                           'name' : dict(
                              detail=GrammarDetail.REQUIRED,
                              valueRegex=RegexLocator.vmdkname,
                              orientation=ArgumentOrientation.FRONT,
                              onRegexMismatch='error',
                           )
                        },
      }


   def getVMAcceptEULAGrammar(self):
      return dict(id='vmaccepteula', args={})


   def getVMSerialNumGrammar(self):
      return {
         'id' : 'vmserialnum',
         'args' : {
                     '--esx' : dict(
                                  detail=GrammarDetail.REQUIRED,
                                  valueRegex=RegexLocator.serialnum,
                                  regexMsg='vmserialnum --esx value requires five, five character tuples separated by dashes',
                                  onRegexMismatch='error',
                               ),
                  },
      }


   def getVMLicenseTextSectionGrammar(self):
      return dict(id='%vmlicense_text', args={})


   def getZeroMBRGrammar(self):
      return dict(id='zerombr', args={})


if __name__ == "__main__": #pragma: no cover
   import doctest
   doctest.testmod()
