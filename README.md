# uugvm-ansible
This is my clumsy attempt to play with Ansible. Don't use this on any machine you care about.

If you choose to risk your machine, this can be run with either:

```
apt-get install ansible git
git clone https://github.com/ripleymj/uugvm-ansible
cd uugvm-ansible
ansible-playbook -i hosts -K -t TAGS local.yml
```
or directly from GitHub:
```
ansible-pull -U https://github.com/ripleymj/uugvm-ansible -i hosts -K -t TAGS
```
where TAGS is a comma separated list of cs101, cs261, or cs354 as appropriate.

This was developed on and for Linux Mint, but is not known to have any problems with other Debian-based distributions.
