#!/usr/bin/env bash

# Settings that can be set in the environment
ISO_FOLDER=${ISO_FOLDER:-"${HOME}/Downloads"}
VBOX_VM_DIR=${VBOX_VM_DIR:-"${HOME}/VirtualBox VMs"}

# Change these every semester as needed
mint_version="19.1" # Numeric Mint version (not codename)
semester="Sp19"   # Two characters for semester, two digits for year

vm="JMU Linux Mint ${semester}"
vm_disk="${VBOX_VM_DIR}/${vm}/${vm}.vdi"
vm_install_disk="${ISO_FOLDER}/linuxmint-${mint_version}-cinnamon-64bit.iso"

# Basic vm settings
VBoxManage createvm --name "${vm}" --ostype Ubuntu_64 --register
VBoxManage modifyvm "${vm}" --cpus 2 --memory 2048 --vram 64

# Initialize storage
VBoxManage storagectl "${vm}" --name "SATA Controller" --add sata --bootable on --portcount=4
VBoxManage createhd --filename "${vm_disk}" --size 20480 --variant Standard

# Attach storage to the vm
VBoxManage storageattach "${vm}" --storagectl "SATA Controller" --port 0 --device 0 --type hdd --medium "${vm_disk}"
VBoxManage storageattach "${vm}" --storagectl "SATA Controller" --port 1 --device 0 --type dvddrive --medium "${vm_install_disk}"

# Enable needed vm features
VBoxManage modifyvm "${vm}" --audioout on
VBoxManage modifyvm "${vm}" --clipboard bidirectional
VBoxManage modifyvm "${vm}" --mouse usbtablet
VBoxManage modifyvm "${vm}" --usb on --usbehci off --usbxhci off
VBoxManage modifyvm "${vm}" --accelerate3d on
VBoxManage modifyvm "${vm}" --rtcuseutc on
VBoxManage modifyvm "${vm}" --pae on
