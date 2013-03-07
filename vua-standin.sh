#! /bin/sh

# This script acts as a standin for VUA when doing a scripted upgrade through
# esx4upgrade.py.  The only functionality it emulates is the failsafe reboot
# in case of an error.

watchlog()
{
    while true; do
	if grep -q "installation aborted" /var/log/weasel.log; then
	    reboot
	    exit
	fi
	sleep 10
    done
}

watchlog &
