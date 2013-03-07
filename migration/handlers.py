
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

import simple
import services

# Map of file names in the cos to their custom migration handlers.  When
# migrate.py is walking over the list of files to migrate, it will consult this
# mapping to see if any of the files need any special attention.
#
# The handlers take three arguments:
#   oldPath - The full path to the file in the old installation.
#   newPath - The full path to where the file will be copied in the new
#     installation.
#   accum - A list used to accumulate file names that should be migrated to
#     the new installation.  For example, when migrating a config file that
#     references other files, the references can be added to this list to get
#     them copied.  XXX rename to filesToMigrate
#
# The handler should return True if the file being processed should be copied
# from oldPath to newPath.
MIGRATION_HANDLERS = {
    # The init infrastructure is changing, don't transfer it over.
    "/etc/vmware/init" : simple.migrateActionIgnore,

    # The pciid stuff has also changed, don't transfer it over
    "/etc/vmware/pciid" : simple.migrateActionIgnore,
    "/etc/vmware/pci.classlist" : simple.migrateActionIgnore,
    "/etc/vmware/pci.ids" : simple.migrateActionIgnore,
    "/etc/vmware/pci.xml" : simple.migrateActionIgnore,
    "/etc/vmware/pcitable" : simple.migrateActionIgnore,
    "/etc/vmware/pcitable.Linux" : simple.migrateActionIgnore,
    "/etc/vmware/simple.map" : simple.migrateActionIgnore,

    # The license infrastructure is changing, don't transfer it over.
    "/etc/vmware/license.cfg" : simple.migrateActionIgnore,
    "/etc/vmware/vmware.lic" : simple.migrateActionIgnore,

    "/etc/sysconfig/clock" : simple.migrateClock,

    "/etc/pam.d/*" : simple.migrateActionPamD,
    
    "/etc/ssh/sshd_config" : simple.migrateActionSSH,
    
    "/etc/nsswitch.conf" : simple.migrateActionNsSwitch,
    
    "/etc/ntp.conf" : simple.migrateActionNtp,
    "/etc/sysconfig/ntpd" : simple.migrateActionNtpd,

    "/etc/rc.d/rc*.d/*" : services.migrateActionServices,

    "/etc/xinetd.conf" : services.migrateActionXinetdConf,
    }
