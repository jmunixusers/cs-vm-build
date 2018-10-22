# JMU UUG virtual machine build script
This is an attempt to use Ansible to build the computer science student
virtual machine. Extended end user documentation using these tasks and the VM
is available [separately](https://jmunixusers.github.io/presentations/vm/).

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
cs101, cs149, cs159, cs261, and/or cs354 as appropriate.

This was developed on and for Linux Mint, but can be adapted to any Debian-based
distribution with minimal changes. Adaptions for distributions that do not use
apt will require more extensive modifications.

## Installed packages and features

### Common
* Filezilla
* JDK/JRE 8 & 10-11
* SFTP connection to stu
* Shortcuts to re-run tasks
* Unzip
* Vim
* Vim-Gnome
* VM management script
* Wireless printing

### CS101
* Eclipse
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
* DrJava
* Eclipse
* jGRASP

### CS159
* Eclipse

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
* Gazebo7
* ROS Kinetic
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

## License

This project is licensed under the MIT license. See LICENSE for more
information.
