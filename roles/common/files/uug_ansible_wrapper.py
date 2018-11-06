#!/usr/bin/env python3
"""
This tools creates a simple GUI for running ansible-pull with a
predetermined set of tags. It displays the output from the ansible-pull
command in a VTE within the GUI. It allows the user to override some things
in a configuration file (~/.config/vm_config). The branch to pull and the
URL to pull from can be changed in the program's Settings.
"""

import logging
import os
import re
import socket
import subprocess
import sys

import json

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Vte', '2.91')
from gi.repository import Gtk, Vte
from gi.repository import GLib
from gi.repository import GdkPixbuf

# If no tags are passed to ansible-pull, all of them will be run and I am
# uncertain of the outcome of passing -t with no tags. To avoid this, always
# ensure that common is run by adding it to this list and disabling the
# checkbox
# Map of course names to the Ansible tags
COURSES = {
    'CS 101': 'cs101',
    'CS 149': 'cs149',
    'CS 159': 'cs159',
    'CS 261': 'cs261',
    'CS 354': 'cs354',
    'CS 361': 'cs361',
}
USER_CONFIG_PATH = os.path.join(os.environ['HOME'], ".config", "vm_config")
USER_CONFIG = {
    'git_branch': None,
    'git_url': "https://github.com/jmunixusers/cs-vm-build",
    # All roles the user has ever chosen
    'roles_all_time': ["common"],
    # Roles to be used for this particular run
    'roles_this_run': ["common"],
}
NAME = "JMU CS VM Configuration"
VERSION = "Spring 2019"
DEFAULT_GIT_REMOTE = "https://github.com/jmunixusers/cs-vm-build"

def main():
    """
    Sets up logging and starts the GUI
    """

    # Configure logging. Log to a file and create it if it doesn't exist. If
    # it cannot be opened, then fall back to logging on the console
    user_log_file = os.path.join(
        os.environ['HOME'], ".cache", "uug_ansible_wrapper.log"
    )
    try:
        logging.basicConfig(
            format="%(asctime)s - %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d-%H-%M",
            filename=user_log_file,
            filemode="w+",
            level=logging.INFO
        )
    except OSError:
        logging.basicConfig(
            format="%(levelname)s: %(message)s", level=logging.INFO
        )
        logging.error(
            "Unable to open log file at %s. Logging on console"
            " instead", user_log_file
        )

    # The default value for the branch is the current distro release name.
    # Set this before parsing the configuration. If it can't be detected,
    # it should get set to None
    USER_CONFIG['git_branch'] = get_distro_release_name()

    # Parse the user's previous settings
    parse_user_config()

    # If common got removed from the configuration, add it back to prevent
    # potentially bad things from happening
    if "common" not in USER_CONFIG['roles_this_run']:
        USER_CONFIG['roles_this_run'].append("common")

    # If a branch still isn't set, offer "master"
    if not USER_CONFIG['git_branch']:
        unable_to_detect_branch()

    # Show the window and ensure when it's closed that the script terminates
    win = AnsibleWrapperWindow()
    win.connect("delete-event", Gtk.main_quit)
    win.show_all()
    Gtk.main()


class AnsibleWrapperWindow(Gtk.Window):
    """
    The main window for the program. Includes a series of checkboxes for
    courses as well as a VTE to show the output of the Ansible command
    """

    checkboxes = []

    def __init__(self):
        Gtk.Window.__init__(self, title=NAME)

        # Attempt to use tux as the icon. If it fails, that's okay
        try:
            self.set_icon_from_file("/opt/jmu-tux.svg")
        except GLib.GError as err:
            logging.warning("Unable to set Tux icon", exc_info=err)

        # Create a box to contain all elements that will be added to the window
        self.vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(self.vbox)

        self.create_toolbar()

        contents = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        contents.set_border_width(10)

        label = Gtk.Label(
            "Select the course configurations to add/update"
            "(at this time courses cannot be removed)."
        )
        label.set_alignment(0.0, 0.0)

        contents.pack_start(label, False, False, 0)

        courses_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        # This button doesn't do anything. Common is always run
        refresh = Gtk.CheckButton("Base configuration")
        refresh.set_tooltip_text("This option is required")
        refresh.set_active(True)
        refresh.set_sensitive(False)
        courses_box.pack_start(refresh, False, False, 0)

        # Add a checkbox for every course; sorting is necessary because
        # dictionaries do not guarantee that order is preserved
        for (course, tag) in sorted(COURSES.items()):
            checkbox = Gtk.CheckButton(course)
            checkbox.set_tooltip_text("Configure for %s" % course)
            courses_box.pack_start(checkbox, False, False, 0)
            if tag in USER_CONFIG['roles_this_run']:
                checkbox.set_active(True)
            checkbox.connect("toggled", self.on_course_toggled, tag)
            self.checkboxes.append(checkbox)
        contents.pack_start(courses_box, False, False, 0)

        # Add run and cancel buttons
        button_box = Gtk.Box(spacing=6)
        self.run_button = Gtk.Button.new_with_label("Run")
        self.run_button.set_tooltip_text("Configure the VM")
        self.run_button.connect("clicked", self.on_run_clicked)
        button_box.pack_start(self.run_button, True, True, 0)
        self.cancel_button = Gtk.Button.new_with_mnemonic("_Quit")
        self.cancel_button.connect("clicked", Gtk.main_quit)
        button_box.pack_end(self.cancel_button, True, True, 0)
        contents.pack_end(button_box, False, True, 0)

        # Add the terminal to the window
        self.terminal = Vte.Terminal()
        # Prevent the user from entering text or ^C
        self.terminal.set_input_enabled(False)
        # Ensure that if text is written, the user sees it
        self.terminal.set_scroll_on_output(True)
        # Ensure that all lines can be seen (default is only 512)
        self.terminal.set_scrollback_lines(-1)
        self.terminal.connect("child-exited", self.sub_command_exited)
        contents.pack_end(self.terminal, True, True, 0)
        self.vbox.pack_end(contents, True, True, 0)

    @classmethod
    def on_course_toggled(cls, button, name):
        """
        Adds the course to or removes the course from the list of courses to
        provision based on whether the checkbox was checked or unchecked
        respectively.
        :param button: The checkbox that triggered the action
        :param name: The name of the course associated with button
        """

        if button.get_active():
            USER_CONFIG['roles_this_run'].append(name)
        else:
            USER_CONFIG['roles_this_run'].remove(name)

    def create_toolbar(self):
        """
        Initializes the window's toolbar.
        """

        menu_bar = Gtk.MenuBar()

        # Create the File menu
        file_menu = Gtk.Menu()
        file_item = Gtk.MenuItem("File")
        file_item.set_submenu(file_menu)

        # Add settings and quit items to the File menu
        settings = Gtk.MenuItem("Settings\u2026")
        settings.connect("activate", self.show_settings)
        file_menu.append(settings)
        quit_item = Gtk.MenuItem("Quit")
        quit_item.connect("activate", Gtk.main_quit)
        file_menu.append(quit_item)

        menu_bar.append(file_item)

        # Create the Help menu
        help_menu = Gtk.Menu()
        help_item = Gtk.MenuItem("Help")
        help_item.set_submenu(help_menu)

        # Add about item to the Help menu
        about = Gtk.MenuItem("About")
        about.connect("activate", self.show_about_dialog)
        help_menu.append(about)

        menu_bar.append(help_item)

        self.vbox.pack_start(menu_bar, False, False, 0)

    def show_settings(self, _):
        """
        Displays a dialog for changing the program's settings.
        """

        dialog = Gtk.Dialog(
            title="Settings", parent=self, flags=Gtk.DialogFlags.MODAL
        )
        grid = Gtk.Grid()
        branch_label = Gtk.Label("Branch:")
        branch_label.set_justify(Gtk.Justification.RIGHT)
        branch_label.set_halign(Gtk.Align.END)

        url_label = Gtk.Label("URL:")
        url_label.set_justify(Gtk.Justification.RIGHT)
        url_label.set_halign(Gtk.Align.END)

        branch_field = Gtk.Entry()
        url_field = Gtk.Entry()
        branch_field.set_text(USER_CONFIG['git_branch'])
        url_field.set_text(USER_CONFIG['git_url'])
        branch_field.set_width_chars(40)
        url_field.set_width_chars(40)

        grid.add(branch_label)
        grid.attach_next_to(
            branch_field, branch_label, Gtk.PositionType.RIGHT, 1, 1
        )
        grid.attach_next_to(
            url_label, branch_label, Gtk.PositionType.BOTTOM, 1, 1
        )
        grid.attach_next_to(url_field, url_label, Gtk.PositionType.RIGHT, 1, 1)
        dialog.get_content_area().pack_end(grid, False, False, 0)
        dialog.add_button(Gtk.STOCK_OK, Gtk.ResponseType.OK)
        dialog.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        dialog.set_default_size(400, 100)
        grid.set_row_spacing(6)
        grid.set_column_spacing(6)
        grid.set_border_width(6)
        grid.show_all()

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            USER_CONFIG['git_branch'] = branch_field.get_text()
            USER_CONFIG['git_url'] = url_field.get_text()
            write_user_config()
        dialog.destroy()

    def show_about_dialog(self, _):
        """
        Displays the About dialog.
        """

        about_dialog = Gtk.AboutDialog()
        try:
            about_dialog.set_logo(
                GdkPixbuf.Pixbuf.new_from_file_at_size(
                    "/opt/jmu-tux.svg", 96, 96
                )
            )
        except Exception as err:
            logging.error("Error", exc_info=err)
        about_dialog.set_transient_for(self)
        about_dialog.set_program_name(NAME)
        about_dialog.set_copyright("Copyright \xa9 2018 JMU Unix Users Group")
        about_dialog.set_comments(
            "A tool for configuring virtual machines for use in the "
            "JMU Department of Computer Science, "
            "maintained by the Unix Users Group"
        )
        about_dialog.set_authors(["JMU Unix Users Group"])
        about_dialog.set_website("https://github.com/jmunixusers/cs-vm-build")
        about_dialog.set_website_label("Project GitHub page")
        about_dialog.set_version(VERSION)
        about_dialog.set_license_type(Gtk.License.MIT_X11)
        about_dialog.connect("response", on_dialog_close)
        about_dialog.show()

    def sub_command_exited(self, _, exit_status):
        """
        Displays a dialog informing the user whether the pkexec and
        ansible-pull commands completely successfully or not.
        """

        for checkbox in self.checkboxes:
            checkbox.set_sensitive(True)
        self.cancel_button.set_sensitive(True)
        self.run_button.set_sensitive(True)
        if exit_status == 0:
            success_msg = (
                "Your machine has been configured for: %s" %
                (",".join(USER_CONFIG['roles_this_run']))
            )
            show_dialog(
                self, Gtk.MessageType.INFO, Gtk.ButtonsType.OK, "Complete",
                success_msg
            )
            logging.info("ansible-pull succeeded")
        # 126 should be the exit code if the pkexec dialog is dismissed and
        # 127 is the exit code if authentication fails. All other exit codes
        # come from the called application
        # At the moment, this doesn't seem to work. Even though on the command
        # line these exit codes seem to be correct, 32256 is what gets passed
        # to this function when the dialog closes and 32512 is what gets passed
        # when authentication fails.
        # Because of that, we will accept those values for these scenarios and
        # hopefully can remove the 32xxx values at some point in the future
        elif exit_status == 126 or exit_status == 32256:
            pkexec_err_msg = "Unable to authenticate due to the dialog being"\
                             " closed. Please try again."
            show_dialog(
                self, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK,
                "Unable to authenticate", pkexec_err_msg
            )
            logging.warning("User dismissed authentication dialog")
        elif exit_status == 127 or exit_status == 32512:
            pkexec_err_msg = "Unable to authenticate due to an incorrect" \
                             " password or insufficient permissions." \
                             " Plese try again."
            show_dialog(
                self, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK,
                "Unable to authenticate", pkexec_err_msg
            )
            logging.error("Unable to authenticate user")
        else:
            ansible_err_msg = (
                "There was an error while running the configuration tasks. "
                "Please try again."
                "\nIf this issue continues to occur, copy"
                " /opt/vmtools/logs/last_run.log and"
                " <a href='%s'>create an issue</a>" % (USER_CONFIG['git_url'])
            )
            show_dialog(
                self, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, "Error",
                ansible_err_msg
            )
            logging.error("ansible-pull failed")

    def on_run_clicked(self, _):
        """
        Performs various checks and then runs the commands in VTE. The run
        and quit buttons are disabled as are all the checkboxes.
        """

        if not is_online():
            no_internet_msg = (
                "It appears that you are not able to access the Internet. "
                "This tool requires that you be online. "
                "Please check your settings and try again."
            )
            show_dialog(
                self, Gtk.MessageType.ERROR, Gtk.ButtonsType.CANCEL,
                "No Internet connection", no_internet_msg
            )
            return

        if not validate_branch():
            invalid_branch(self)
            return
        
        system_version = get_distro_release_name()
        chosen_branch = USER_CONFIG['git_branch']
        chosen_remote = USER_CONFIG['git_url']
        branch_mismatch = system_version != chosen_branch
        looks_minty = re.compile(r"[a-z]+a").fullmatch(system_version)
    
        output = subprocess.run(
            ["/usr/bin/git", "ls-remote", '--heads', USER_CONFIG['git_url']],
            stdout=subprocess.PIPE
        )
    
        ls_remote = output.stdout.decode("utf-8")
       
        system_exists = system_version in ls_remote
        chosen_exists = chosen_branch in ls_remote
        
        if chosen_remote == DEFAULT_GIT_REMOTE:
            if (chosen_branch == "master"):
                warning_prompt = (
                    "You are currently on an unstable development branch (master) of the configuration tool. "
                    "You should consider switching to the release branch for your Linux Mint version. "
                    "The recommended configuration settings for your release version of Linux Mint are:" 
                    "\nRelease: %(0)s and URL: %(1)s" % {
                        '0': get_distro_release_name(),
                        '1': DEFAULT_GIT_REMOTE
                    }
                )
                show_dialog(
                    self, Gtk.MessageType.WARNING, Gtk.ButtonsType.OK,
                    "Current branch is the development branch master", warning_prompt
                )
            elif branch_mismatch and looks_minty and system_exists and chosen_exists:
                warning_prompt = (
                    "You are using a version of the configuration tool meant for a different release of Linux Mint. " 
                    "You should consider upgrading branches. "
                    "The recommended configuration settings for your release version of Linux Mint are:"
                    "\nRelease: %(0)s and URL: %(1)s" % {
                        '0': system_version,
                        '1': DEFAULT_GIT_REMOTE
                    }
                )
                show_dialog(
                    self, Gtk.MessageType.WARNING, Gtk.ButtonsType.OK,
                    "Current branch is outdated", warning_prompt
                )
                return
            elif branch_mismatch and looks_minty and system_exists and (not chosen_exists):
                no_version_msg = (
                    "Your current Linux Mint version does not exist as a branch on the specified remote url. "
                    "You should consider switching to the master branch. "
                    "The recommended configuration settings for your release version of Linux Mint are:" 
                    "\nRelease: %(0)s and URL: %(1)s" % {
                        '0': system_version,
                        '1': DEFAULT_GIT_REMOTE
                    }
                )
                show_dialog(
                    self, Gtk.MessageType.WARNING, Gtk.ButtonsType.OK,
                    "Linux Mint version not found on URL", no_version_msg
                )
                return
            elif system_exists and (not chosen_exists):
                bad_branch_msg = (
                    "Your currently chosen branch does not exist on the chosen url. "
                    "You should fix your remote url or switch to a branch that exist on that url. "
                    "The recommended configuration settings for your release version of Linux Mint are:" 
                    "\nRelease: %(0)s and URL: %(1)s" % {
                        '0': system_version,
                        '1': DEFAULT_GIT_REMOTE
                    }
                )
                show_dialog(
                    self, Gtk.MessageType.WARNING, Gtk.ButtonsType.OK,
                    "branch does not exist on specified remote URL", bad_branch_msg
                )
                return
            elif (not system_exists) and (not chosen_exists):
                bad_branch_msg = (
                    "We do not support your current OS and the branch chosen does not exist on the chosen remote URL. "
                    "You should consider switching to the master branch. "
                    "The recommended configuration settings for your release version of Linux Mint are:" 
                    "\nRelease: %(0)s and URL: %(1)s" % {
                        '0': "master",
                        '1': DEFAULT_GIT_REMOTE
                    }
                )
                show_dialog(
                    self, Gtk.MessageType.WARNING, Gtk.ButtonsType.OK,
                    "OS not supported and branch not found", bad_branch_msg
                )
                return
        
        for checkbox in self.checkboxes:
            checkbox.set_sensitive(False)

        self.cancel_button.set_sensitive(False)
        self.run_button.set_sensitive(False)

        write_user_config()

        logging.info(
            "Running ansible-pull with flags: %s",
            ",".join(USER_CONFIG['roles_this_run'])
        )

        # spawn_sync will not perform a path lookup; however, pkexec will
        cmd_args = [
            '/usr/bin/pkexec',
            'ansible-pull',
            '--url',
            USER_CONFIG['git_url'],
            '--checkout',
            USER_CONFIG['git_branch'],
            '--purge',
            '--inventory',
            'hosts',
            '--tags',
            ",".join(USER_CONFIG['roles_this_run']),
        ]

        try:
            self.terminal.spawn_sync(
                Vte.PtyFlags.DEFAULT, os.environ['HOME'], cmd_args, [],
                GLib.SpawnFlags.DO_NOT_REAP_CHILD, None, None
            )
        except GLib.Error as error:
            logging.error("Unable to run ansible command.", exc_info=error)
            self.sub_command_exited(None, 1)


def on_dialog_close(action, _):
    """
    Destroys the dialog.
    """

    action.destroy()


def show_dialog(parent, dialog_type, buttons_type, header, message):
    """
    Shows a dialog to the user with the provided header, message, and
    buttons. The message is always displayed with format_secondary_markup
    and therefore will passed through Pango. It should be escaped properly.
    :param parent: The parent GTK window to associate with the dialog
    :param dialog_type: The type of GTK dialog to display
    :param buttons_type: The GTK buttons type to use for the dialog
    :param header: The text to display in the dialog's header
    :param message: The text to display in the main part of the dialog
    :returns: The user's response to the dialog
    """

    dialog = Gtk.MessageDialog(parent, 0, dialog_type, buttons_type, header)
    dialog.format_secondary_markup(message)
    response = dialog.run()
    dialog.destroy()
    return response


def parse_simple_config(path, data):
    """
    Parses a simple INI-like config. Only lines with assignments are permitted
    and it can't handle sections like INI has. Lines with # as the first
    non-space character are comments.
    :param path: The path to the configuration file
    :param data: The dictionary to store the data in
    """

    try:
        with open(path, "r") as config:
            for line in config:
                # Allow comments at beginning of lines
                if line.lstrip().startswith("#"):
                    continue
                # Ignore any line without an assignment
                if "=" not in line:
                    logging.warning("Config entry has no assignment: %s", line)
                    continue
                # Store the key and value. The string before the first = is
                # the key, and everything else ends up in the value (even if
                # there are multiple = on the line).
                try:
                    split = line.split("=")
                    key = split[0]
                    val = "".join(split[1:])
                    data[key.strip()] = val.strip()
                except ValueError:
                    logging.warning("Invalid entry in config file: %s", line)
                    continue
    except FileNotFoundError as fne:
        logging.info("Ignoring user configuration. It is not present")


def parse_json_config(path, config):
    """
    Loads the data in the file at the provided path into a dictionary.
    :param path: The path to the JSON file
    :param config: The dictionary to update with data from the JSON file
    """

    try:
        with open(path, "r") as config_file:
            config.update(json.load(config_file))
    except FileNotFoundError as fne:
        logging.info(
            "User configuration file not present. Ignoring.", exc_info=fne
        )
    except json.decoder.JSONDecodeError as jde:
        logging.info("User configuration is invalid. Ignoring.", exc_info=jde)


def write_json_config(path, config):
    """
    Writes a dictionary to a file at the provided at path in JSON format.
    :param path: The path of the file to write the dictionary to
    :param config: The dictionary to write. Must be serializable as JSON
    """

    with open(path, "w") as config_file:
        # Make the written file relatively readable & writable by users
        json.dump(config, config_file, indent=4, sort_keys=True)


def parse_user_config():
    """
    Loads a user's configuration.
    """

    parse_json_config(USER_CONFIG_PATH, USER_CONFIG)

    USER_CONFIG['roles_all_time'] = list(set(USER_CONFIG['roles_all_time']))
    USER_CONFIG['roles_this_run'] += USER_CONFIG['roles_all_time']
    # Remove duplicates from roles for this run
    USER_CONFIG['roles_this_run'] = list(set(USER_CONFIG['roles_this_run']))

    logging.info("Read config: %s from %s", USER_CONFIG, USER_CONFIG_PATH)


def parse_os_release():
    """
    Loads the data in /etc/os-release.
    :returns: A dictionary with the data parsed from /etc/os-release
    """

    config = {}
    parse_simple_config("/etc/os-release", config)
    return config


def get_distro_release_name():
    """
    Attempts to get the release name of the currently-running OS. It reads
    /etc/os-release and then regardless of whether or not a release has
    been found, if the user has specified a preferred branch, that will be
    returned.
    :returns: The name of the Linux distro's release
    """

    release = ""

    os_release_config = parse_os_release()
    if 'VERSION_CODENAME' in os_release_config:
        release = os_release_config['VERSION_CODENAME']
    else:
        logging.debug(
            "VERSION_CODENAME is not in /etc/os_release. "
            "Full file contents: %s", os_release_config
        )

    if release.lstrip() == "" or release is None:
        logging.warning("No valid release was detected")

    return release


def validate_branch():
    """
    Checks the branch passed in against the branches available on remote.
    Returns true if branch exists on remote. This may be subject to false
    postivies, but that should not be an issue.
    :returns: Whether the chosen branch exists on the git remote
    """

    output = subprocess.run(
        ["/usr/bin/git", "ls-remote", USER_CONFIG['git_url']],
        stdout=subprocess.PIPE
    )

    ls_remote_output = output.stdout.decode("utf-8")

    return USER_CONFIG['git_branch'] in ls_remote_output


def invalid_branch(parent):
    """
    Displays a dialog if the branch choses does not exist on the remote
    :param parent: The parent GTK window for the error dialog
    """

    bad_branch_msg = (
        "The release chosen does not exist at the project URL."
        " Please check the settings listed below and try again."
        "\nRelease: %(0)s\nURL: %(1)s\nIf you're using a current"
        " release of Linux Mint, you may submit"
        " <a href='%(1)s'>an issue</a> requesting support for"
        " the release listed above" % {
            '0': USER_CONFIG['git_branch'],
            '1': USER_CONFIG['git_url']
        }
    )
    show_dialog(
        parent, Gtk.MessageType.ERROR, Gtk.ButtonsType.CANCEL,
        "Invalid Release", bad_branch_msg
    )
    return


def unable_to_detect_branch():
    """
    Displays a dialog to ask the user if they would like to use the master
    branch. If the user clicks yes, release is set to master. If the user
    says no, the script exits
    """

    logging.info("Branch could not be detected. Offering master")
    master_prompt = (
        "The version of your OS could not be determined."
        " Would you like to use the master branch? This can be very dangerous."
    )
    response = show_dialog(
        None, Gtk.MessageType.ERROR, Gtk.ButtonsType.YES_NO,
        "OS detection error", master_prompt
    )

    if response != Gtk.ResponseType.YES:
        logging.info("The user chose not to use master")
        sys.exit(1)
    else:
        USER_CONFIG['git_branch'] = "master"
        logging.info("Release set to master")


def is_online(hostname="packages.linuxmint.com"):
    """
    Checks if the user is able to reach a selected hostname.
    :param hostname: The hostname to test against.
    Default is packages.linuxmint.com.
    :returns: True if able to connect or False otherwise.
    """

    try:
        host = socket.gethostbyname(hostname)
        test_connection = socket.create_connection((host, 80), 2)
        test_connection.close()
        return True
    except OSError as err:
        logging.warning("%s is unreachable.", hostname, exc_info=err)
        return False


def write_user_config():
    """
    Writes the user's configuration out to the configuration file. This
    allows configuration changes to persist across invocations.
    """

    # Add all new roles to cummulative roles and also remove duplicates before
    # writing -- must be a list since sets cannot be serialized with JSON
    USER_CONFIG['roles_this_run'] = list(set(USER_CONFIG['roles_this_run']))
    USER_CONFIG['roles_all_time'] += USER_CONFIG['roles_this_run']
    # Since there could now be duplicates in roles_all_time, remove them
    USER_CONFIG['roles_all_time'] = list(set(USER_CONFIG['roles_all_time']))

    logging.info(
        "Writing user configuration %s to %s", USER_CONFIG, USER_CONFIG_PATH
    )

    write_json_config(USER_CONFIG_PATH, USER_CONFIG)


if __name__ == "__main__":
    main()
