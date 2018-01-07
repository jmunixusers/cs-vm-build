#!/usr/bin/env python3
"""
   This tools creates a simple GUI for running ansible-pull with a
   predetermined set of tags. It displays the output from the ansible-pull
   command in a VTE within the GUI. It allows the user to override some things
   in a configuration file (~/.config/vm_config). The branch to pull can be
   overriden by setting FORCE_BRANCH and the URL to pull from can be overriden
   with FORCE_GIT_URL
"""

import logging
import os
import socket
import subprocess
import sys

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Vte', '2.91')
from gi.repository import Gtk, Vte
from gi.repository import GLib

# If no tags are passed to ansible-pull, all of them will be run and I am
# uncertain of the outcome of passing -t with no tags. To avoid this, always
# ensure that common is run by adding it to this list and disabling the
# checkbox
TAGS = ["common"]
# Map of course names to the Ansible tags
COURSES = {'CS 101': 'cs101', 'CS 149': 'cs149', 'CS 159': 'cs159',
           'CS 261': 'cs261', 'CS 354': 'cs354'}
USER_CONFIG_PATH = os.path.join(os.environ['HOME'], ".config", "vm_config")
USER_CONFIG = {}
CURRENT_CONFIG = {'RELEASE': None, 'URL': None}


def main():
    """Sets up logging and starts the GUI"""
    # Configure logging. Log to a file and create it if it doesn't exist. If
    # it cannot be opened, then fall back to logging on the console
    user_log_file = os.path.join(os.environ['HOME'], ".cache",
                                 "uug_ansible_wrapper.log")
    try:
        logging.basicConfig(format="%(asctime)s - %(levelname)s: %(message)s",
                            datefmt="%Y-%m-%d-%H-%M",
                            filename=user_log_file,
                            filemode="w+",
                            level=logging.INFO)
    except OSError:
        logging.basicConfig(format="%(levelname)s: %(message)s",
                            level=logging.INFO)
        logging.error("Unable to open log file at %s. Logging on console"
                      " instead", user_log_file)

    # Set the url, release, and user config ahead of showing the window so
    # they can be displayed in labels
    parse_user_config()
    CURRENT_CONFIG['URL'] = get_remote_url()
    try:
        CURRENT_CONFIG['RELEASE'] = get_distro_release_name()
    except ValueError:
        logging.warning("The branch was unable to be detected.")
        unable_to_detect_branch()

    # Show the window and ensure when it's closed that the script terminates
    win = CheckboxWindow()
    win.connect("delete-event", Gtk.main_quit)
    win.show_all()
    Gtk.main()


class CheckboxWindow(Gtk.Window):
    """The main window for the program. Includes a series of checkboxes for
       courses as well as a VTE to show the output of the Ansible command"""

    def __init__(self):
        Gtk.Window.__init__(self, title="JMU CS VM Configuration")

        # Attempt to use tux as the icon. If it fails, that's okay
        try:
            self.set_icon_from_file("/opt/jmu-tux.svg")
        except GLib.GError as err:
            logging.warning("Unable to set Tux icon", exc_info=err)

        self.set_border_width(10)

        # Create a box to contain all elements that will be added to the window
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.add(vbox)

        label = Gtk.Label("Select the courses you need configured on the VM")
        label.set_alignment(0.0, 0.0)
        vbox.pack_start(label, False, False, 0)

        courses_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        # This button doesn't do anything. Common is always run
        refresh = Gtk.CheckButton("Refresh base configuration")
        refresh.set_tooltip_text("This option is required")
        refresh.set_active(True)
        refresh.set_sensitive(False)
        courses_box.pack_start(refresh, False, False, 0)
        # Add a checkbox for every course; sorting is necessary because
        # dictionaries do not guarantee that order is preserved
        for (course, tag) in sorted(COURSES.items()):
            checkbox = Gtk.CheckButton(course)
            checkbox.set_tooltip_text("Configure for %s" % course)
            checkbox.connect("toggled", self.on_button_toggled, tag)
            courses_box.pack_start(checkbox, False, False, 0)
        vbox.pack_start(courses_box, False, False, 0)

        # Add informational labels to the bottom of the window
        label_box = Gtk.Box(spacing=6)
        url_label = Gtk.Label("URL: %s" % CURRENT_CONFIG['URL'])
        label_box.pack_start(url_label, False, False, 6)
        branch_label = Gtk.Label("Branch: %s" % CURRENT_CONFIG['RELEASE'])
        label_box.pack_start(branch_label, False, False, 6)
        vbox.pack_end(label_box, False, False, 0)

        # Add run and cancel buttons
        button_box = Gtk.Box(spacing=6)
        self.run_button = Gtk.Button.new_with_label("Run")
        self.run_button.set_tooltip_text("Configure the VM")
        self.run_button.connect("clicked", self.on_run_clicked)
        button_box.pack_start(self.run_button, True, True, 0)
        self.cancel_button = Gtk.Button.new_with_mnemonic("_Quit")
        self.cancel_button.connect("clicked", Gtk.main_quit)
        button_box.pack_end(self.cancel_button, True, True, 0)
        vbox.pack_end(button_box, False, True, 0)

        # Add the terminal to the window
        self.terminal = Vte.Terminal()
        self.terminal.connect("child-exited", self.sub_command_exited)
        vbox.pack_end(self.terminal, True, True, 0)

    @classmethod
    def on_button_toggled(cls, button, name):
        """Adds the name of the button that triggered this call to the list of
           tags that will be passed to ansible-pull"""
        if button.get_active():
            TAGS.append(name)
        else:
            TAGS.remove(name)

    def sub_command_exited(self, _, exit_status):
        """Displays a dialog informing the user whether the gksudo and
           ansible-pull commands completely successfully or not"""
        self.cancel_button.set_sensitive(True)
        self.run_button.set_sensitive(True)
        if exit_status == 0:
            success_msg = "Your machine has been configured for: %s" \
                          % (",".join(TAGS))
            show_dialog(self, Gtk.MessageType.INFO, Gtk.ButtonsType.OK,
                        "Complete", success_msg)
            logging.info("ansible-pull succeeded")
        # 65280 should be the exit code if the gksudo dialog is dismissed
        elif exit_status == 65280:
            gksudo_err_msg = "Either an incorrect password was entered or" \
                             " the password dialog was closed." \
                             " Please try again"
            show_dialog(self, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK,
                        "Unable to authenticate", gksudo_err_msg)
            logging.warning("Unable to authenicate user")
        else:
            ansible_err_msg = "There was an error while running the" \
                              " configuration tasks. Please try again." \
                              "\nIf this issue continues to occur, copy" \
                              " /opt/vmtools/logs/last_run.log and" \
                              " <a href='%s'>create an issue</a>" \
                              % (CURRENT_CONFIG['URL'])
            show_dialog(self, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK,
                        "Error", ansible_err_msg)
            logging.error("ansible-pull failed")

    def on_run_clicked(self, _):
        """Begins the process of running the command in the VTE and disables
           the run and cancel buttons so that they cannot be used while the
           command is running"""
        if not is_online():
            no_internet_msg = "It appears that you are not able to access" \
                              " the Internet. This tools requires that you" \
                              " be online please check your settings and try" \
                              " again"
            show_dialog(self, Gtk.MessageType.ERROR, Gtk.ButtonsType.CANCEL,
                        "No Internet connection", no_internet_msg)
            return

        if not validate_branch():
            invalid_branch(self)
            return

        gksudo_msg = "<b>Enter your password to configure your VM</b>" \
                     "\nTo configure your virtual machine, administrator" \
                     " privileges are required."

        self.cancel_button.set_sensitive(False)
        self.run_button.set_sensitive(False)

        logging.info("Running ansible-pull with flags: %s", ",".join(TAGS))

        self.terminal.spawn_sync(Vte.PtyFlags.DEFAULT,
                                 os.environ['HOME'],
                                 ["/usr/bin/gksudo", "--message",
                                  gksudo_msg, "--",
                                  "ansible-pull", "-U", CURRENT_CONFIG['URL'],
                                  "-C", CURRENT_CONFIG['RELEASE'],
                                  "--purge", "-i", "hosts",
                                  "-t", ",".join(TAGS)],
                                 [],
                                 GLib.SpawnFlags.DO_NOT_REAP_CHILD,
                                 None,
                                 None,
                                )


def show_dialog(parent, dialog_type, buttons_type, header, message):
    """Shows a dialog to the user with the provided header, message, and
       buttons. The message is always displated with format_secondary_markup
       and therefore will passed through Pango. It should be escaped properly
    """
    dialog = Gtk.MessageDialog(parent, 0, dialog_type, buttons_type, header)
    dialog.format_secondary_markup(message)
    response = dialog.run()
    dialog.destroy()
    return response


def parse_simple_config(path, data):
    """Loads the user's configuration into the user_config global variable"""
    try:
        with open(path, "r") as config:
            for line in config:
                # Allow comments
                if line.strip().startswith("#"):
                    continue
                # Ignore any line without an assignment
                if "=" not in line:
                    continue
                # Ignore lines with too many/few = signs
                try:
                    (key, val) = line.split("=")
                    data[key.strip()] = val.strip()
                except ValueError:
                    logging.warning("Invalid entry in config file: %s", line)
                    continue
    except FileNotFoundError:
        logging.info("Ignoring user configuration. It is not present")


def parse_user_config():
    """Loads a user's configuration"""
    parse_simple_config(USER_CONFIG_PATH, USER_CONFIG)


def parse_os_release():
    """Loads the data in /etc/os-release"""
    config = {}
    parse_simple_config("/etc/os-release", config)
    return config


def get_distro_release_name():
    """Attempts to get the release name of the currently-running OS. It reads
       /etc/os-release and then regardless of whether or not a release has
       been found, if FORCE_BRANCH exists in ~/.config/vm_config that will be
       returned. If nothing is found, a ValueError is raised."""
    release = ""

    os_release_config = parse_os_release()
    if 'VERSION_CODENAME' in os_release_config:
        release = os_release_config['VERSION_CODENAME']
    else:
        logging.debug("VERSION_CODENAME is not in /etc/os_release."
                      "Full file contents: %s", os_release_config)

    if 'FORCE_BRANCH' in USER_CONFIG:
        user_branch = USER_CONFIG['FORCE_BRANCH']
        if user_branch:
            release = user_branch
        else:
            logging.warning("User set a branch ('%s') but it is invalid",
                            user_branch)

    if release == "" or release == " " or release is None:
        logging.warning("No valid release was detected")
        raise ValueError("Version could not be detected")

    return release


def get_remote_url():
    """Checks if the user has specified a FORCE_GIT_URL in their config file.
       If so, that is returned. Otherwise, the default jmunixusers URL is
       returned"""
    if 'FORCE_GIT_URL' in USER_CONFIG:
        return USER_CONFIG['FORCE_GIT_URL']
    return "https://github.com/jmunixusers/cs-vm-build"


def validate_branch():
    """Checks the branch passed in against the branches available on remote.
       Returns true if branch exists on remote. This may be subject to false
       postivies, but that should not be an issue"""
    output = subprocess.run(["/usr/bin/git", "ls-remote",
                             CURRENT_CONFIG['URL']],
                            stdout=subprocess.PIPE)

    ls_remote_output = output.stdout.decode("utf-8")

    return CURRENT_CONFIG['RELEASE'] in ls_remote_output


def invalid_branch(parent):
    """Displays a dialog if the branch choses does not exist on the remote"""
    bad_branch_msg = "The release chosen does not exist at the project URL." \
                     " Please check the settings listed below and try again." \
                     "\nRelease: %(0)s\nURL: %(1)s\nIf you're using a current"\
                     " release of Linux Mint, you may submit"\
                     " <a href='%(1)s'>an issue</a> requesting support for" \
                     " the release listed above" \
                     % {'0': CURRENT_CONFIG['RELEASE'],
                        '1': CURRENT_CONFIG['URL']}
    show_dialog(parent, Gtk.MessageType.ERROR, Gtk.ButtonsType.CANCEL,
                "Invalid Release", bad_branch_msg)
    return


def unable_to_detect_branch():
    """Displays a dialog to ask the user if they would like to use the master
       branch. If the user clicks yes, release is set to master. If the user
       says no, the script exits"""
    master_prompt = "The version of your OS could not be determined." \
                    " Would you like to use the master branch?" \
                    " This is very dangerous"
    response = show_dialog(None, Gtk.MessageType.ERROR, Gtk.ButtonsType.YES_NO,
                           "OS detection error", master_prompt)
    if response != Gtk.ResponseType.YES:
        logging.info("The user chose not to use master")
        sys.exit(1)
    else:
        CURRENT_CONFIG['RELEASE'] = "master"
        logging.info("Release set to master")


def is_online():
    """Checks if the user is able to reach a selected hostname."""
    # Since the user will probably be pulling a significant amount of data
    # from this host, it should be a decent host to use to check connectivity
    test_hostname = "packages.linuxmint.com"
    try:
        host = socket.gethostbyname(test_hostname)
        test_connection = socket.create_connection((host, 80), 2)
        test_connection.close()
        return True
    except OSError as err:
        logging.warning("%s is unreachable.", test_hostname, exc_info=err)
        return False


if __name__ == "__main__":
    main()
