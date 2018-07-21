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
cs101, cs149, cs159, cs261, or cs354 as appropriate.

This was developed on and for Linux Mint, but can be adapted to any Debian-based
distribution with minimal changes. Adaptions for distributions that do not use
apt will require more extensive modifications.

## Installed packages and features

### Common
* Filezilla
* JDK/JRE 8
* SFTP connection to stu
* Shortcuts to re-run tasks
* Unzip
* Vim
* Vim-Gnome
* Wireless printing

### CS101
* Aptana
* Finch robot
* Mint packages (basic-prog-pkgs role)
  * artha
  * bless
  * geany
  * idle
  * libreoffice
  * logisim
  * meld
  * pinta
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

### CS354
* Gazebo7
* ROS Kinetic
* Rosdep/catkin initialization
* Rviz

## License

This project is licensed under the MIT license. See LICENSE for more
information.
