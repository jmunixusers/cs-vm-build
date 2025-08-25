variable "mint_version" {
  type = object({
    version    = string
    build_type = string
  })
  default = {
    version    = "22.1"
    build_type = null
  }
}

variable "ubuntu_version" {
  type = object({
    version         = string
    patched_version = string
  })
  # The default value for this is stored in ubuntu-version.auto.pkrvars.hcl, which will be
  # updated by the GitHub Actions workflow that automatically updates the Ubuntu version.
}

variable "mirror" {
  type = object({
    base        = string
    ubuntu_path = string
    mint_path   = string
  })
  default = {
    base        = "https://mirror.cs.jmu.edu/pub"
    ubuntu_path = "ubuntu-iso"
    mint_path   = "linuxmint/images"
  }
}

variable "audio" {
  type    = string
  default = "pulse"
}

variable "git_branch" {
  type    = string
  default = "main"
}

variable "git_repo" {
  type    = string
  default = "https://github.com/jmunixusers/cs-vm-build"
}

variable "headless" {
  type    = bool
  default = true
}

variable "semester" {
  type    = string
  default = "Sp25"
}

variable "ssh_pass" {
  type    = string
  default = "oem"
}

variable "ssh_user" {
  type    = string
  default = "oem"
}

variable "vm_name" {
  type    = string
  default = "JMU CS"
}

variable "aarch64_boot_wait" {
  type        = string
  default     = "25s"
  description = "The length of time to wait after boot before entering commands"

  validation {
    condition     = can(regex("\\d+s", var.aarch64_boot_wait))
    error_message = "The value should be a number of seconds followed by 's'."
  }
}

variable "qemu_accelerator" {
  type        = string
  default     = "kvm"
  description = <<EOF
    The QEMU accelerator to use; keep this as 'kvm' unless building on macOS, in
    which case it's probably best to use 'hvf'.
  EOF
}

variable "qemu_firmware_directory" {
  type        = string
  default     = "/usr/share/AAVMF/"
  description = <<EOF
    The directory where the QEMU EFI code and variables are stored. On Fedora and
    similar distributions, this is likely /usr/share/edk2/aarch64. On Debian
    derivates, this is likely /usr/share/qemu-efi-aarch64.
  EOF
}

locals {
  build_id = formatdate("YYYY-MM-DD", timestamp())
  ubuntu_info = {
    mirror_url = "${var.mirror.base}/${var.mirror.ubuntu_path}/${var.ubuntu_version.version}"
    iso_file   = "ubuntu-${var.ubuntu_version.patched_version}-desktop-amd64.iso"
  }
  mint_info = {
    mirror_url = "${var.mirror.base}/${var.mirror.mint_path}/${var.mint_version.build_type == "beta" ? "testing" : "stable/${var.mint_version.version}"}"
    iso_file   = "linuxmint-${var.mint_version.version}-cinnamon-64bit${var.mint_version.build_type != null ? "-${var.mint_version.build_type}" : ""}.iso"
  }
  ubuntu_aarch64_info = {
    mirror_url = "http://cdimage.ubuntu.com/${var.ubuntu_version.version}/daily-live/current"
    iso_file   = "${var.ubuntu_version.version}-desktop-arm64.iso"
  }
  artifact_dir_prefix = "${path.cwd}/artifacts_"
}
