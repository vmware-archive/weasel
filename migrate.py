
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
import os
import glob
import stat
import util
import string
import shutil
import consts

import migration

from log import log

# TODO: Any required files need to be added to the precheck.

PATHS_TO_MIGRATE_PRE_PACKAGES = [
    "/etc/vmware",
    ]

# Names of files and directories to copy from the old installation to the new.
PATHS_TO_MIGRATE = [
    "/etc/logrotate.conf",

    "/etc/localtime",
    "/etc/ntp.conf",
    
    "/etc/syslog.conf",

    "/etc/sysconfig/ntpd",
    "/etc/sysconfig/xinetd",
    "/etc/sysconfig/console",
    "/etc/sysconfig/i18n",
    "/etc/sysconfig/clock",
    "/etc/sysconfig/crond",
    "/etc/sysconfig/syslog",
    "/etc/sysconfig/keyboard",
    "/etc/sysconfig/mouse",

    "/etc/ssh",

    "/etc/nsswitch.conf",
    "/etc/yp.conf",
    "/etc/krb.conf",
    "/etc/krb.realms",
    "/etc/krb5.conf",
    "/etc/login.defs",

    "/etc/pam.d/*",

    "/etc/hosts.allow",
    "/etc/hosts.deny",

    "/etc/ldap.conf",
    "/etc/openldap",

    "/etc/sudoers",

    "/etc/snmp",

    "/usr/local/etc",    # ntp stores a bunch of stuff in here.

    "/etc/rc.d/rc*.d/*",
    "/etc/xinetd.conf",

    "/etc/motd",
    # SW iSCSI Configuration
    "/etc/initiatorname.vmkiscsi",
    "/etc/vmkiscsi.conf",
    ]

CMDS_TO_RUN = [
    "/usr/sbin/tzdata-update",
    ]

class NamedList(list):
    '''Extension of the list type that lets you reference indexes by name,
    which is useful for processing formatted text configuration files.

    This class is used in conjunction with TextConfigFile classes to represent
    individual lines in the config file.

    >>> class MyNamedList(NamedList):
    ...     STRUCT = ['first', 'second']
    >>> l = MyNamedList(['a', 'b'])
    >>> l.first
    'a'
    >>> l.second
    'b'
    '''
    
    STRUCT = [] # Set by subclass to the list of attribute names for each index
    
    def __getattr__(self, key):
        if key not in self.STRUCT:
            raise AttributeError(key)

        return self[self.STRUCT.index(key)]

    def __setattr__(self, key, value):
        if key not in self.STRUCT:
            return list.__setattr__(self, key, value)
        
        self[self.STRUCT.index(key)] = value

class TextConfigFile:
    '''Base class for text-based configuration files that are line-oriented.

    Many unix configuration files, like /etc/passwd and /etc/group, are made up
    of individual lines separated by a token.  This class, along with NamedList,
    provide a common means to load and process these files.

    >>> import sys
    >>> log.warn = sys.stdout.write
    >>> class MyConfig(TextConfigFile):
    ...     class MyConfigData(NamedList):
    ...         STRUCT = ['first', 'second']
    ...     ELEMENT_TYPE = MyConfigData
    >>> # Construct a MyConfig object from a three line config file.
    >>> mc = MyConfig("""
    ... a b
    ... c d
    ... this will not match
    ... """)
    skipping config line -- this will not match
    >>> mc.elements
    [['a', 'b'], ['c', 'd']]
    '''

    # Optionally set by subclass to the separator string for a line.
    SEPARATOR = r'\s+'

    # Set by the TextConfigFile subclass to the NamedList subclass that will
    # represent each line found in the file.
    ELEMENT_TYPE = NamedList
    
    @classmethod
    def fromFile(cls, path):
        '''Construct an object of the class type with the contents of the given
        file path.'''

        fh = open(path)
        contents = fh.read()
        fh.close()
        
        return cls(contents)
    
    def __init__(self, contentString):
        '''Construct an config file object from the given contents.

        The contents are split into individual lines and then split into
        individual fields based on the SEPARATOR regex.  If the number of fields
        matches the length of the ELEMENT_TYPE.STRUCT list, a new element of
        ELEMENT_TYPE will be constructed with the fields.
        '''
        
        self.elements = []
        
        for line in map(string.strip, contentString.split('\n')):
            if not line:
                continue
            
            rawFields = re.split(self.SEPARATOR, line)
            fields = self._addDefaultFields(rawFields)
            if len(fields) == len(self.ELEMENT_TYPE.STRUCT):
                self.elements.append(self.ELEMENT_TYPE(fields))
            else:
                log.warn("skipping config line -- %s" % line)

    def __getitem__(self, key):
        return self.elements[key]

    def _addDefaultFields(self, fields):
        return fields

def cloneFile(src, dst):
    '''Clone a file, including its owner ids.'''
    log.debug("cloning file %s -> %s" % (src, dst))
    dirs = os.path.dirname(dst)
    if not os.path.exists(dirs):
        os.makedirs(dirs)
    preserveFile(dst)
    shutil.copy2(src, dst)
    st = os.stat(src)
    os.chown(dst, st[stat.ST_UID], st[stat.ST_GID])

def cloneDir(src, dst):
    log.debug("cloning dir %s -> %s" % (src, dst))
    if not os.path.exists(dst):
        os.makedirs(dst)
    st = os.stat(src)
    shutil.copystat(src, dst)
    os.chown(dst, st[stat.ST_UID], st[stat.ST_GID])

def cloneLink(src, dst):
    log.debug("cloning link %s -> %s" % (src, dst))
    if os.path.lexists(dst):
        os.remove(dst)
    st = os.lstat(src)
    linkDst = os.readlink(src)
    os.symlink(linkDst, dst)
    os.lchown(dst, st[stat.ST_UID], st[stat.ST_GID])

def cloneTree(src, dst):
    log.debug("cloning tree %s -> %s" % (src, dst))
    for root, dirs, files in os.walk(src):
        subDirs = root[len(src):].lstrip('/')
        for name in dirs:
            cloneDir(os.path.join(root, name),
                     os.path.join(dst, subDirs, name))
        for name in files:
            clonePath(os.path.join(root, name),
                      os.path.join(dst, subDirs, name))

def clonePath(src, dst):
    if os.path.isdir(src):
        cloneTree(src, dst)
    elif os.path.islink(src):
        cloneLink(src, dst)
    else:
        cloneFile(src, dst)

def resolveLink(prefix, path):
    '''Resolve a sym link in the ESX3 file system.'''
    count = 0
    while os.path.islink(path):
        # We have to resolve links ourselves instead of using os.path.realpath
        # because we need to prefix '/mnt/sysimage/esx3-installation' onto any
        # absolute paths.
        linkPath = os.readlink(path)
        if not os.path.isabs(linkPath):
            path = os.path.join(os.path.dirname(path), linkPath)
        else:
            # Absolute links should be made relative to the esx3 mount in the
            # installer.
            path = os.path.join(prefix, linkPath.lstrip('/'))
        path = os.path.normpath(path)
        if not os.path.lexists(path):
            log.warn("link destination does not exist -- %s" % path)
            return None
        count += 1
        if count > 10:
            log.warn("sym link loop")
            return None
    return path
        
def expandGlobPath(path):
    '''Expand a given path into a list of files to be migrated.

    The path can be a shell glob that specifies either files or directories.
    For a file, if there is a custom handler in migration.MIGRATION_HANDLERS,
    it will be called to scan the file and perform any migration work.  If
    the migration handler discovers any other files referenced they will be
    added to the list returned by this function.

    If the path is a directory, its contents will be walked and added to the
    list of files returned.
    '''
    retval = []

    prefix = consts.HOST_ROOT + consts.ESX3_INSTALLATION.lstrip('/')
    oldPathGlob = prefix + path
    paths = glob.glob(oldPathGlob)
    for oldPath in paths:
        strippedPath = oldPath[len(prefix):]
        newPath = os.path.join(consts.HOST_ROOT, strippedPath.lstrip('/'))
        
        if path in migration.MIGRATION_HANDLERS:
            log.debug("custom migration handler -- %s" % path)
            handler = migration.MIGRATION_HANDLERS[path]
            accum = []
            # If the oldPath is a link, we need to resolve it so that the
            # custom handler can open the file up.
            actualOldPath = resolveLink(consts.HOST_ROOT +
                                        consts.ESX3_INSTALLATION.lstrip('/'),
                                        oldPath)
            if not actualOldPath:
                log.warn("  skipping unresolved sym link -- %s" % oldPath)
                continue
            doClone = handler(actualOldPath, newPath, accum)

            # Need to recursively expand paths returned by the migration
            # handler in case they need processing as well.  For example, if
            # a config file includes another config file, the second file will
            # need to be run through the custom migration handler as well.
            for extraPath in accum:
                retval.extend(expandGlobPath(extraPath))

            if not doClone:
                log.debug("custom handler migrated file -- %s" % path)
                continue
        
        retval.append(path)
        if os.path.isdir(oldPath):
            for name in os.listdir(oldPath):
                subdir = oldPath[
                    len(consts.HOST_ROOT + consts.ESX3_INSTALLATION.lstrip('/')):]
                retval.extend(expandGlobPath(os.path.join(subdir, name)))
    
    return retval

def migratePath(path):
    '''Attempt to migrate a file from the ESX v3 installation to the new one.'''

    allPaths = expandGlobPath(path)
    if not allPaths:
        log.info("not migrating globbed path -- %s" % path)
    
    for expandedPath in allPaths:
        oldPath = consts.HOST_ROOT + consts.ESX3_INSTALLATION + expandedPath
        newPath = consts.HOST_ROOT + expandedPath
        
        if not os.path.exists(oldPath) and not os.path.islink(oldPath):
            log.info("not migrating expanded path '%s' from '%s'" % (
                expandedPath, path))
            continue

        if os.path.isdir(oldPath):
            # The expandGlobPath has already walked down the tree, so we just
            # want to clone the directory's permissions and what not.
            cloneDir(oldPath, newPath)
        else:
            clonePath(oldPath, newPath)

def preserveFile(path):
    '''Preserve a file in the new installation and return its name or None if
    the file does not exist.'''
    
    retval = None
    if os.path.exists(path) and not path.endswith(".esx4"):
        retval = path + ".esx4"
        cloneFile(path, retval)
    return retval

def hostActionPrePackages(_context):
    for path in PATHS_TO_MIGRATE_PRE_PACKAGES:
        migratePath(path)

def hostAction(_context):
    for path in PATHS_TO_MIGRATE:
        migratePath(path)

    for cmd in CMDS_TO_RUN:
        util.execCommand(cmd, root=consts.HOST_ROOT)

CLEANUP_TEMPLATE = """\
#! /bin/sh

usage()
{
    echo "usage: $0 [-hf]"
    echo "Removes references to ESX v3 in grub.conf and /etc/fstab."
    echo "Also removes ESX v3 files in /boot."
    echo
    echo "Options:"
    echo "  -h      Show this help message."
    echo "  -f      Force, run the script in non-interactive mode."
    exit 0
}

exitmsg()
{
    if test $? -eq 0; then
        echo "Cleanup of ESX v3 successful.  Please reboot your system."
    fi
}

args=`getopt hf $*`

if test $? != 0; then
    usage
fi

set -- $args

force="no"

for i
do
    case "$i" in
    -h)
        usage
        ;;
    -f)
        force="yes"
        ;;
    esac
done

if test $force != "yes"; then
    read -p "Are you sure you want to remove ESX v3 references and files? (y/N) " answer
    if test "$answer" != "y" && test "$answer" != "yes"; then
	exit 0
    fi
fi

trap exitmsg EXIT

rm /usr/sbin/rollback-to-esx3
sed -i -e '/^# BEGIN migrated entries/,/^# END migrated entries/d' /etc/fstab

"""

ROLLBACK_TEMPLATE = """\
#! /bin/sh

usage()
{
    echo "usage: $0 [-hf]"
    echo "Reconfigure the bootloader to boot into ESX v3 on the next reboot."
    echo
    echo "Options:"
    echo "  -h      Show this help message."
    echo "  -f      Force, run the script in non-interactive mode."
    exit 0
}

exitmsg()
{
    if test $? -eq 0; then
        echo "Rollback to ESXv3 successful.  Please reboot your system."
    fi
}

args=`getopt hf $*`

if test $? != 0; then
    usage
fi

set -- $args

force="no"

for i
do
    case "$i" in
    -h)
        usage
        ;;
    -f)
        force="yes"
        ;;
    esac
done

if test $force != "yes"; then
    echo "Warning: Any changes made to the virtual machines on this host will"
    echo "not be rolled back.  If you upgraded the virtual hardware of the"
    echo "machines, they will not work after the rollback."
    read -p "Are you sure you want to rollback to ESX v3? (y/N) " answer
    if test "$answer" != "y" && test "$answer" != "yes"; then
	exit 0
    fi
fi

trap exitmsg EXIT

rm -rf /boot/config-2.6.*
rm -rf /boot/initrd-2.6.*
rm -rf /boot/initrd.img
rm -rf /boot/System.map-2.6.*
rm -rf /boot/vmlinuz-2.6.*
rm -rf /boot/vmlinuz
rm -rf /boot/trouble
cp /boot/grub/grub.conf.esx3 /boot/grub/grub.conf

"""

CLEANUP_PATH = os.path.join(consts.HOST_ROOT, "usr/sbin/cleanup-esx3")
ROLLBACK_PATH = os.path.join(consts.HOST_ROOT, "usr/sbin/rollback-to-esx3")

def hostActionCleanupScripts(_context):
    '''Write out the scripts used to cleanup the old installation or rollback
    to it.'''
    fp = open(CLEANUP_PATH, "w")
    fp.write(CLEANUP_TEMPLATE)
    fp.close()

    os.chmod(CLEANUP_PATH, 0700)
    
    fp = open(ROLLBACK_PATH, "w")
    fp.write(ROLLBACK_TEMPLATE)
    fp.close()

    os.chmod(ROLLBACK_PATH, 0700)

if __name__ == "__main__":
    import doctest
    doctest.testmod()
