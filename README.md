# JMU UUG virtual machine build script

This is a set of Ansible roles that can be used to configure a Linux Mint or
Ubuntu system for JMU computer science courses. It is primarily used to deliver
the Unix Users Group virtual machine, but can be run outside that VM using
instructions later in this document. Extended end user documentation about
using these tasks and the VM is available
[separately](https://jmunixusers.github.io/presentations/vm/).

## Installed packages and features

### Common
* Filezilla
* JDK/JRE 10-11
* SFTP connection to stu
* Shortcuts to re-run tasks
* Unzip
* Vim
* Vim-Gnome
* VM management script
* JMU wireless printing

### CS101
* Eclipse (with checkstyle plugin)
* Finch robot
* Mint packages (basic-prog-pkgs role)
  * artha
  * bless
  * chromium-browser
  * geany
  * idle-python3.6
  * libreoffice
  * logisim
  * meld
  * sqlitebrowser
  * thonny
  * wireshark

### CS149
* Eclipse (with checkstyle plugin)
* jGRASP

### CS159
* Eclipse (with checkstyle plugin)

### CS261
* Mint packages (adv-prog-pkgs role)
  * Compilers and interpreters
    * build-essential
    * g++
    * gcc
    * gdb
    * logisim
    * valgrind
  * Code editors
    * astyle
    * bvi
    * check
    * gedit
    * indent
    * nano
  * Source control
    * git
    * gitg
    * mercurial
    * meld
* y86 tools
    * Assembler (`yas`)
    * Reference solution (`y86ref`)
    * Reference solution manual page (`y86ref(1)`)
    * Simulator (`ysim`)

### CS354
* Gazebo9
* ROS Melodic
* Rosdep/catkin initialization
* Rviz

### CS361
* Mint packages (adv-prog-pkgs role)
  * Compilers and interpreters
    * build-essential
    * g++
    * gcc
    * gdb
    * logisim
    * valgrind
  * Code editors
    * astyle
    * bvi
    * check
    * gedit
    * indent
    * nano
  * Source control
    * git
    * gitg
    * mercurial
    * meld

### CS430
* Ruby
  * ruby
* Haskell
  * haskell-platform
* Prolog
  * swi-prolog

## Manual use of these Ansible roles

```
apt-get install ansible git
git clone https://github.com/jmunixusers/cs-vm-build
cd cs-vm-build
ansible-playbook -i hosts -c local -K -t TAGS local.yml
```
or directly from GitHub:

```
ansible-pull -U https://github.com/jmunixusers/cs-vm-build --purge -i hosts -K -t TAGS
```
where TAGS is a comma separated list (with no spaces) of
cs101, cs149, cs159, cs261, cs354, and/or cs361 as appropriate.

This was developed on and for Linux Mint, but can be adapted to any Debian-based
distribution with minimal changes. Adaptions for distributions that do not use
apt will require more extensive modifications.

## Building the UUG VM

To build the UUG VM, configure a system with `git`,
[Oracle VirtualBox](https://www.virtualbox.org/),
[Hashicorp Packer](https://www.packer.io/),
and approximately 20GB of free disk space. VM builds are tested regularly on
Linux and Windows hosts, but feedback on other platforms is always welcome.

Once the prerequisites are installed, change into the `cs-vm-build/packer`
directory and execute `packer build oem-build.json`. This will take a
considerable amount of time, depending on host resources available, but should
output progress indicators along the way.

The build process can be customized by passing parameters to the `packer build`
command using the `-var` flag. The supported parameters are:

- `git_repo` - the repository containing the setup scripts to run before
exporting the VM appliance. Defaults to https://github.com/jmunixusers/cs-vm-build.
- `git_branch` - the branch of the above repository to choose. Defaults to `master`.
- `headless` - whether or not to show the desktop session during installation.
Defaults to `true`.

## Contributing

Feedback and involvement is always welcome in JMU UUG projects. The issue
tracker on this repository is a great place to start, whether you're looking for
previous design discussions, want to ask a question, or would like to contribute
additional functionality. The UUG can also be reached via
[Twitter](https://www.twitter.com/JMUnixUsers) or check our upcoming
[meeting schedule](https://beinvolved.jmu.edu/organization/uug). For more
suggestions on getting involved, please see the [CONTRIBUTING](CONTRIBUTING.md)
document.

## License

This project is licensed under the MIT license. See LICENSE for more
information.
