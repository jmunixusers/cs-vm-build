# JMU UUG virtual machine build script
This is an attempt to use Ansible to build the computer science student virtual machine. Don't use this on any machine you care about.

If you choose to risk your machine, this can be run with either:

```
apt-get install ansible git
git clone https://github.com/jmunixusers/cs-vm-build
cd cs-vm-build
ansible-playbook -i hosts -c local -K -t TAGS local.yml
```
or directly from GitHub:
```
ansible-pull -U https://github.com/jmunixusers/cs-vm-build -i hosts -K -t TAGS
```
where TAGS is a comma separated list of cs101, cs149, cs159, cs261, or cs354 as appropriate.

This was developed on and for Linux Mint, but is not known to have any problems with other Debian-based distributions.

## Installed packages and features

### Common
* SFTP connection to stu
* JDK/JRE 8
* Wireless printing

### CS101
* Mint packages (basic-prog-pkgs role)
  * artha
  * bless
  * geany
  * idle
  * meld
  * pinta
  * python-pygame
  * wireshark
  * libreoffice
  * logisim
* Aptana
* Finch robot

### CS149
* JGrasp
* DrJava

### CS159
* Eclipse

### CS261
* Mint packages (adv-prog-pkgs role)
  * Compilers and interpreters
    * build-essential
    * gcc
    * g++
    * gdb
    * lua5.3
    * python3
    * ruby
    * valgrind
    * logisim
    * lsb-core
  * Source control
    * subversion
    * git
    * gitg
    * mercurial
    * meld
  * Code editors
    * vim
    * vim-gnome
    * gedit
    * nano
    * check
    * bvi
    * astyle
    * indent

### CS354
* ROS Kinetic
* Gazebo7
* Rviz
* Rosdep/catkin initialization
