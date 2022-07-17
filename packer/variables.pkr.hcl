variable "mint_version" {
  type = object({
    name    = string
    version = string
    beta    = bool
  })
  default = {
    name    = "Una"
    version = "20.3"
    beta    = false
  }
}

variable "ubuntu_version" {
  type = object({
    name          = string
    version       = string
    minor_version = string
  })
  default = {
    name          = "jammy"
    version       = "22.04"
    minor_version = ""
  }
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
  default = "Sp22"
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

locals {
  build_id = "${legacy_isotime("2006-01-02")}"
  ubuntu_info = {
    mirror_url = "${var.mirror.base}/${var.mirror.ubuntu_path}/${var.ubuntu_version.name}"
    iso_file   = "ubuntu-${var.ubuntu_version.version}${var.ubuntu_version.minor_version}-desktop-amd64.iso"
  }
  mint_info = {
    mirror_url = "${var.mirror.base}/${var.mirror.mint_path}/${var.mint_version.beta ? "testing" : "stable/${var.mint_version.version}"}"
    iso_file   = "linuxmint-${var.mint_version.version}-cinnamon-64bit${var.mint_version.beta ? "-beta" : ""}.iso"
  }
  artifact_dir_prefix = "${path.cwd}/artifacts_"
}
