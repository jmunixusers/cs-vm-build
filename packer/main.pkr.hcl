packer {
  required_version = ">= 1.9.0"
  required_plugins {
    qemu = {
      source  = "github.com/hashicorp/qemu"
      version = "~> 1"
    }
    virtualbox = {
      version = "~> 1"
      source  = "github.com/hashicorp/virtualbox"
    }
  }
}

source "qemu" "kvm" {
  cpus         = 2
  memory       = 4096
  disk_size    = 20480
  machine_type = "virt"
  accelerator  = var.qemu_accelerator

  format         = "qcow2"
  headless       = "${var.headless}"
  http_directory = "http"
  qemu_binary    = "qemu-system-aarch64"

  efi_firmware_code = "${var.qemu_firmware_directory}/AAVMF_CODE.fd"
  efi_firmware_vars = "${var.qemu_firmware_directory}/AAVMF_VARS.fd"
  qemuargs = [
    ["-boot", "strict=off"],
    ["-cpu", "host"],
    ["-display", var.headless ? "none" : "gtk"],
    ["-device", "virtio-rng-pci"],
    ["-device", "virtio-gpu"],
    ["-device", "nec-usb-xhci,id=xhci"],
    ["-device", "usb-kbd,bus=xhci.0"],
    ["-device", "usb-tablet,bus=xhci.0"]
  ]
  qemu_img_args {
    create  = ["-o", "preallocation=falloc"]
    convert = ["-o", "compression_type=zstd"]
  }
  disk_cache         = "unsafe"
  disk_compression   = "true"
  disk_detect_zeroes = "unmap"
  disk_discard       = "unmap"
  disk_interface     = "virtio"
  net_device         = "virtio-net"
  ssh_username       = var.ssh_user
  ssh_password       = var.ssh_pass
  ssh_timeout        = "100m"

  boot_wait = var.aarch64_boot_wait
  boot_command = [
    # Enter the command line
    "c<wait><wait>",
    # Configure the kernel
    "linux /casper/vmlinuz",
    " ds=nocloud;s=http://{{ .HTTPIP }}:{{ .HTTPPort }}/",
    " keymap=us fsck.mode=skip",
    " noprompt splash --<enter><wait><wait>",
    # Configure initrd & boot
    "initrd /casper/initrd ",
    "<enter>boot<enter>"
  ]
  shutdown_command = "echo -e \"${var.ssh_pass}\\n\" | sudo -S poweroff"
}

source "virtualbox-iso" "base-build" {
  cpus          = 2
  memory        = 4096
  disk_size     = 20480
  guest_os_type = "Ubuntu_64"
  gfx_vram_size = 128

  format                   = "ova"
  firmware                 = "efi"
  gfx_controller           = "vmsvga"
  gfx_accelerate_3d        = true
  hard_drive_discard       = true
  hard_drive_interface     = "virtio"
  hard_drive_nonrotational = true
  headless                 = "${var.headless}"
  http_directory           = "http"
  iso_interface            = "virtio"
  nic_type                 = "virtio"
  rtc_time_base            = "UTC"
  sata_port_count          = 2
  sound                    = "${var.audio}"
  ssh_username             = "${var.ssh_user}"
  ssh_password             = "${var.ssh_pass}"
  ssh_timeout              = "100m"

  boot_wait = "5s"
  boot_command = [
    # Enter the command line
    "c<wait><wait>",
    # Configure the kernel
    "linux /casper/vmlinuz",
    " boot=casper",
    " auto url=http://{{ .HTTPIP }}:{{ .HTTPPort }}/oem-preseed.cfg",
    " automatic-ubiquity only-ubiquity",
    " debug-ubiquity oem-config/enable=true",
    " keymap=us fsck.mode=skip",
    " noprompt splash --<enter><wait><wait>",
    # Configure initrd & boot
    # Different distributions name (and compress) the initrd differently. Fortunately,
    # GRUB is mostly smart and if the file doesn't exist, it just won't apply that directive.
    # So to prevent duplication, we specify both and let GRUB ignore the wrong one.
    "initrd /casper/initrd<enter>",
    "initrd /casper/initrd.lz<enter><wait>",
    "<enter>boot<enter>"
  ]
  shutdown_command = "echo -e \"${var.ssh_pass}\\n\" | sudo -S poweroff"

  vboxmanage = [
    ["modifyvm", "{{ .Name }}", "--audioin", "off"],
    ["modifyvm", "{{ .Name }}", "--clipboard-mode", "bidirectional"],
    ["modifyvm", "{{.Name}}", "--nat-localhostreachable1", "on"],
    ["modifyvm", "{{ .Name }}", "--mouse", "usbtablet"],
    ["modifyvm", "{{ .Name }}", "--pae", "on"],
    ["modifyvm", "{{ .Name }}", "--vrde", "off"],
    ["storagectl", "{{ .Name }}", "--name", "IDE Controller", "--remove"],
    ["storagectl", "{{ .Name }}", "--name", "VirtIO Controller", "--hostiocache", "on"]
  ]
  vboxmanage_post = [
    ["modifyvm", "{{.Name}}", "--nat-localhostreachable1", "off"],
    ["modifyvm", "{{.Name}}", "--usb-xhci", "on"],
    ["storageattach", "{{ .Name }}", "--storagectl", "VirtIO Controller", "--port", "1", "--type", "dvddrive", "--medium", "emptydrive"]
  ]
}

build {
  source "source.virtualbox-iso.base-build" {
    name             = "mint"
    vm_name          = "${var.vm_name} Linux Mint ${var.semester} Build ${local.build_id}"
    iso_url          = "${local.mint_info.mirror_url}/${local.mint_info.iso_file}"
    iso_checksum     = "file:${local.mint_info.mirror_url}/sha256sum.txt"
    output_filename  = "image-${lower(var.semester)}-mint"
    output_directory = "${local.artifact_dir_prefix}mint"
    export_opts = [
      "--manifest",
      "--vsys", "0",
      "--description", "Build date: ${local.build_id}\nPacker version: ${packer.version}",
      "--product", "${var.vm_name} Linux Mint ${var.semester}",
      "--producturl", "https://linuxmint.com/",
      "--vendor", "JMU Unix Users Group",
      "--vendorurl", "${var.git_repo}",
      "--version", "${var.mint_version.version}",
      "--vmname", "${var.vm_name} Linux Mint ${var.semester}"
    ]
  }

  source "source.virtualbox-iso.base-build" {
    name             = "ubuntu"
    vm_name          = "${var.vm_name} Ubuntu ${var.semester} Build ${local.build_id}"
    iso_url          = "${local.ubuntu_info.mirror_url}/${local.ubuntu_info.iso_file}"
    iso_checksum     = "file:${local.ubuntu_info.mirror_url}/SHA256SUMS"
    output_filename  = "image-${lower(var.semester)}-ubuntu"
    output_directory = "${local.artifact_dir_prefix}ubuntu"
    export_opts = [
      "--manifest",
      "--vsys", "0",
      "--description", "Build date: ${local.build_id}\nPacker version: ${packer.version}",
      "--product", "${var.vm_name} Ubuntu ${var.semester}",
      "--producturl", "https://ubuntu.com/",
      "--vendor", "JMU Unix Users Group",
      "--vendorurl", "${var.git_repo}",
      "--version", "${var.ubuntu_version.version}",
      "--vmname", "${var.vm_name} Ubuntu ${var.semester}"
    ]
  }

  source "source.qemu.kvm" {
    name             = "ubuntu-aarch64"
    vm_name          = "image.qcow2"
    iso_url          = "${local.ubuntu_aarch64_info.mirror_url}/${local.ubuntu_aarch64_info.iso_file}"
    iso_checksum     = "file:${local.ubuntu_aarch64_info.mirror_url}/SHA256SUMS"
    output_directory = "${local.artifact_dir_prefix}ubuntu-aarch64"
  }

  provisioner "shell" {
    execute_command = "echo 'oem' | sudo -S sh -c '{{ .Vars }} {{ .Path }}'"
    environment_vars = [
      "DEBIAN_FRONTEND=noninteractive"
    ]
    inline = [
      "echo STOPPING APT",
      "systemctl stop unattended-upgrades.service || true",
      "while(pgrep -a apt-get); do sleep 1; done",
      "echo UPDATE",
      "apt-get update",
      "echo INSTALL",
      "apt-get install -V -y git ansible",
      "git clone -b ${var.git_branch} ${var.git_repo}",
      "cd /home/oem/cs-vm-build/scripts",
      "./oem-build",
      "/usr/sbin/oem-config-prepare"
    ]
  }

  post-processor "checksum" {
    checksum_types      = ["sha256"]
    keep_input_artifact = true
    output              = "${local.artifact_dir_prefix}${source.name}/image-${lower(var.semester)}-${source.name}.{{ .ChecksumType }}sum"
  }
}
