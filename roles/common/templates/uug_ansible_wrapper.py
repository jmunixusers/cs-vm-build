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
import subprocess
import urllib.request
from tempfile import TemporaryDirectory

import json

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Vte', '2.91')
from gi.repository import Gtk, Vte
from gi.repository import GLib
from gi.repository import GdkPixbuf

DEFAULT_GIT_REMOTE = "https://github.com/jmunixusers/cs-vm-build"

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
    'CS 430': 'cs430'
}
USER_CONFIG_PATH = os.path.join(os.environ['HOME'], ".config", "vm_config")
USER_CONFIG = {
    'git_branch': None,
    'git_url': DEFAULT_GIT_REMOTE,
    # All roles the user has ever chosen
    'roles_all_time': ["common"],
    # Roles to be used for this particular run
    'roles_this_run': ["common"],
}
NAME = "JMU CS VM Configuration"
VERSION = "Spring 2019"


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
    # it should get set to None. If the branch does not currently exist, it
    # should be set to master.
    distro_name = get_distro_release_name()
    if branch_exists(distro_name):
        USER_CONFIG['git_branch'] = distro_name
    else:
        USER_CONFIG['git_branch'] = 'master'

    # Parse the user's previous settings
    parse_user_config()

    # If common got removed from the configuration, add it back to prevent
    # potentially bad things from happening
    if "common" not in USER_CONFIG['roles_this_run']:
        USER_CONFIG['roles_this_run'].append("common")

    if not USER_CONFIG['git_branch']:
        USER_CONFIG['git_branch'] = "master"

    # Show the window and ensure when it's closed that the script terminates
    win = AnsibleWrapperWindow()
    win.connect("delete-event", Gtk.main_quit)
    win.show_all()

    if not validate_branch_settings(win):
        logging.warn("Non-optimal user branch settings.")

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
            self.set_icon_name("{{ tux_icon_name }}")
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
            " (at this time courses cannot be removed)."
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
        ok_button = dialog.add_button(Gtk.STOCK_OK, Gtk.ResponseType.OK)
        dialog.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        def click_ok(_):
            ok_button.clicked()

        branch_field.connect('activate', click_ok)
        url_field.connect('activate', click_ok)
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
            about_dialog.set_logo_icon_name('{{ tux_icon_name }}')
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
                " {{ ansible_log_file }} and"
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
                "Please check your settings, ensure you are not behind a "
                "captive portal, and try again."
            )
            show_dialog(
                self, Gtk.MessageType.ERROR, Gtk.ButtonsType.CANCEL,
                "No Internet connection", no_internet_msg
            )
            return

        if not branch_exists(USER_CONFIG['git_branch']):
            invalid_branch(self)
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

        with TemporaryDirectory() as temp_dir:
            # spawn_sync will not perform a path lookup; however, pkexec will
            cmd_args = [
                '/usr/bin/pkexec',
                'ansible-pull',
                '--url',
                USER_CONFIG['git_url'],
                '--checkout',
                USER_CONFIG['git_branch'],
                '--directory',
                temp_dir,
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
    except FileNotFoundError:
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


def validate_branch_settings(parent):
    """
    Warns the user of an error in the settings of the VM configuration.
    :returns: a boolean indicating if the system should return or continue
    """

    system_version = get_distro_release_name()
    chosen_branch = USER_CONFIG['git_branch']
    chosen_remote = USER_CONFIG['git_url']
    master_okay = USER_CONFIG.get('ignore_master', False)
    branch_mismatch = system_version != chosen_branch
    looks_minty = re.compile(r"[a-z]+a").fullmatch(chosen_branch)

    header = None
    warning_prompt = None

    system_exists = branch_exists(system_version)
    chosen_exists = branch_exists(chosen_branch)

    # We only validate when the default remote is chosen -- if it's not we
    # cannot make any assumptions about branches
    if chosen_remote != DEFAULT_GIT_REMOTE:
        logging.debug(
            "Not checking branches -- unsupported remote (%s) set",
            chosen_remote
        )
        return True

    # These are branches that should be handled specially
    if chosen_branch == "master" and system_exists and not master_okay:
        # The user wants to run master, but there is a release for their distro
        header = "Unstable release selected"
        warning_prompt = (
            "You have selected an unstable development branch (master) of the"
            " configuration tool. It is recommended to use the release branch"
            " of this tool that corresponds to your Linux Mint version."
            " Consider changing your settings to match the following:"
            "\nRelease: %(release)s\nURL: %(url)s" % {
                'release': system_version,
                'url': USER_CONFIG['git_url'],
            }
        )

        display_ignorable_warning(
            header, warning_prompt, parent, 'ignore_master'
        )
        return False

    if branch_mismatch and looks_minty and system_exists:
        # The user wants to use a minty-looking branch, but there is a branch
        # specifically for their distro available
        header = "Incompatiable Linux Mint release"
        warning_prompt = (
            "You have selected a version of the configuration tool meant for"
            " a different Linux Mint release. It is recommended to switch to"
            " the release branch that corresponds to your Linux Mint version."
            " Consider changing your settings to match the following:"
            "\nRelease: %(release)s\nURL: %(url)s" % {
                'release': system_version,
                'url': USER_CONFIG['git_url'],
            }
        )
    elif system_exists and not chosen_exists:
        header = "Chosen release unavailable"
        warning_prompt = (
            "You have selected a release of the configuration tool that does"
            " not exist on the git URL you have specified. It is recommended"
            " that you switch to the release branch that corresponds to your"
            " Linux Mint release on the UUG git repository."
            " Consider changing your settings to match the following:"
            "\nRelease: %(release)s\nURL: %(url)s" % {
                'release': system_version,
                'url': DEFAULT_GIT_REMOTE,
            }
        )
    elif looks_minty and not (branch_mismatch or chosen_exists):
        header = "Chosen release not available"
        warning_prompt = (
            "You have selected a release of the configuration tool that does"
            " not exist on the git URL you have specified; however, your"
            " current version of Linux Mint is not yet supported. It is"
            " recommended that you switch to the master (testing) branch."
            " Consider changing your settings to match the following:"
            "\nRelease: %(release)s\nURL: %(url)s" % {
                'release': 'master',
                'url': USER_CONFIG['git_url'],
            }
        )
    elif branch_mismatch and looks_minty and not system_exists:
        # The user wants to use a minty-looking branch, but it doesn't match
        # the system and we don't support what they want to run.
        header = "Incompatible Linux Mint release"
        warning_prompt = (
            "You have selected a version of the configuration tool meant for"
            " a different Linux Mint release; however, we are unable to"
            " completely support your Linux Mint release at this time."
            " It is recommended to switch to the master (testing) branch."
            " Consider changing your settings to match the following:"
            "\nRelease: %(release)s\nURL: %(url)s" % {
                'release': 'master',
                'url': USER_CONFIG['git_url'],
            }
        )
    elif branch_mismatch and not (system_exists or chosen_exists):
        header = "Chosen release unavailable"
        warning_prompt = (
            "You have selected a version of the configuration tool that does"
            " not support your version of Linux Mint; however, there is not"
            " a release that supports your version of Linux Mint available"
            " yet. It is recommended to switch to the master (testing) branch."
            " Consider changing your settings to match the following:"
            "\nRelease: %(release)s\nURL: %(url)s" % {
                'release': 'master',
                'url': USER_CONFIG['git_url'],
            }
        )

    if header and warning_prompt:
        show_dialog(
            parent, Gtk.MessageType.WARNING, Gtk.ButtonsType.OK, header,
            warning_prompt
        )

    return warning_prompt is None


def branch_exists(branch_name):
    """
    Checks whether a particular branch exists at the currently-configured
    git URL. This uses the output of `git ls-remote --heads` and parses the
    branch names from that.

    :param branch_name: The branch name to search for on the remote
    :returns: True if the branch exists and False if it does not
    """

    output = subprocess.run(
        ["/usr/bin/git", "ls-remote", '--heads', USER_CONFIG['git_url']],
        stdout=subprocess.PIPE
    )

    ls_remote = output.stdout.decode("utf-8")

    remote_refs = []
    for ref in ls_remote.split('\n'):
        remote_refs.append(ref.split('/')[-1])

    logging.info("Available branches: %s", ", ".join(remote_refs))

    return branch_name in remote_refs


def display_ignorable_warning(title, message, parent, settings_key):
    """
    Displays a warning dialog that contains a checkbox allowing it to be
    ignored in the future.
    :param title: The title for the warning dialog
    :param message: The main body of the warning dialog
    :param parent: The parent window of the warning dialog
    :param settings_key: The key to set if the user chooses to ignore
                         the dialog
    """

    dialog = Gtk.MessageDialog(
        None, Gtk.DialogFlags.MODAL, Gtk.MessageType.WARNING,
        Gtk.ButtonsType.OK_CANCEL, title
    )

    dialog.format_secondary_text(message)

    ignore_checkbox = Gtk.CheckButton("Don't show this warning again")

    # Get the hbox that surrounds the text labels so that the checkbox can
    # be aligned with the text, rather than far to the left below the warning
    # icon. This may be somewhat fragile, but the layout of the warning
    # dialog should remain consistent.
    # Get the box for the content above the buttons
    top_content_box = dialog.get_content_area().get_children()[0]
    # Get the box for the two text fields (primary and secondary text). Index
    # 0 is the icon.
    text_box = top_content_box.get_children()[1]
    # Add the checkbox below the two labels
    text_box.pack_end(ignore_checkbox, False, False, 0)

    # show_all() must be used or the widget we added will not appear when
    # run() is called
    dialog.show_all()
    response = dialog.run()

    if response == Gtk.ResponseType.OK and ignore_checkbox.get_active():
        USER_CONFIG[settings_key] = True
        write_user_config()

    dialog.destroy()


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


def is_online(url="http://detectportal.firefox.com", expected=b"success\n"):
    """
    Checks if the user is able to reach a selected hostname.
    :param hostname: The hostname to test against.
    Default is packages.linuxmint.com.
    :returns: True if able to connect or False otherwise.
    """

    try:
        with urllib.request.urlopen(url) as response:
            response_data = response.read()
            if response_data == expected:
                return True
            else:
                logging.error(
                    "Response from %s was not %s as expected. Received: %s",
                    url, expected, response_data
                )
            return False
    except urllib.error.URLError as url_err:
        logging.error(
            "Unable to connect to %s", url, exc_info=url_err
        )
        return False

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
