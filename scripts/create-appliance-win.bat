set PATH="c:\Program Files\Oracle\VirtualBox";%PATH%

REM Change every semester. Fa/Sp for semester, two digits for year.
set semester="Fa18"

set VM=JMU Linux Mint %semester%
set VMDISK=%HOMEDRIVE%%HOMEPATH%\VirtualBox VMs\%VM%\%VM%.vdi
set VMINSTALLDISK=%HOMEDRIVE%%HOMEPATH%\Downloads\linuxmint-19-cinnamon-64bit-v2.iso

VBoxManage createvm --name "%VM%" --ostype Ubuntu_64 --register
VBoxManage modifyvm "%VM%" --cpus 2 --memory 2048 --vram 64
VBoxManage storagectl "%VM%" --name "SATA Controller" --add sata --bootable on --portcount=4

VBoxManage createhd --filename "%VMDISK%" --size 20480 --variant Standard

VBoxManage storageattach "%VM%" --storagectl "SATA Controller" --port 0 --device 0 --type hdd --medium "%VMDISK%"
VBoxManage storageattach "%VM%" --storagectl "SATA Controller" --port 1 --device 0 --type dvddrive --medium "%VMINSTALLDISK%"

VBoxManage modifyvm "%VM%" --audioout on
VBoxManage modifyvm "%VM%" --clipboard bidirectional
VBoxManage modifyvm "%VM%" --mouse usbtablet
VBoxManage modifyvm "%VM%" --usb on --usbehci off --usbxhci off
VBoxManage modifyvm "%VM%" --accelerate3d on
VBoxManage modifyvm "%VM%" --rtcuseutc on
