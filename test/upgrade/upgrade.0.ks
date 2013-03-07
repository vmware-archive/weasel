
# Auto-generated kickstart file for upgrades.

upgrade
install cdrom

autopart --onvmfs='Storage 2'  --extraspace=4000

vmaccepteula

reboot

%post
echo Hello, World



