#!/usr/bin/env python3
"""
This tools creates a simple GUI for running ansible-pull with a
predetermined set of tags. It displays the output from the ansible-pull
command in a VTE within the GUI. It allows the user to override some things
in a configuration file (~/.config/vm_config). The branch to pull and the
URL to pull from can be changed in the program's Settings.
"""

# pylint: disable=too-many-lines

import ast
import functools
import logging
import os
import pathlib
import re
import subprocess
import urllib.error
import urllib.request
import webbrowser
from tempfile import TemporaryDirectory

import yaml
from xdg import BaseDirectory

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Vte", "2.91")
# pygobject best practice, unfortunately, is to do the import after calling the
# require_version() function. This triggers a pylint message.
# pylint: disable=wrong-import-position
from gi.repository import Gtk, Vte, GLib

DEFAULT_GIT_REMOTE = "https://github.com/jmunixusers/cs-vm-build"

# If no tags are passed to ansible-pull, all of them will be run and I am
# uncertain of the outcome of passing -t with no tags. To avoid this, always
# ensure that common is run by adding it to this list and disabling the
# checkbox
# Map of course names to the Ansible tags
COURSES = {
    "CS 101": "cs101",
    "CS 149": "cs149",
    "CS 159": "cs159",
    "CS 261": "cs261",
    "CS 361": "cs361",
    "CS 430": "cs430",
    "CS 432": "cs432",
}
EXPERIMENTAL_COURSES = {}
USER_CONFIG = {
    "git_branch": None,
    "git_url": DEFAULT_GIT_REMOTE,
    # All roles the user has ever chosen
    "roles_all_time": ["common"],
    # Roles to be used for this particular run
    "roles_this_run": ["common"],
    # Allow experimental courses to be shown
    "allow_experimental": False,
}
APP_NAME = "cs-vm-build"
NAME = "JMU CS VM Configuration"
VERSION = "2022.08"


def main():
    """
    Sets up logging and starts the GUI
    """

    # Configure logging. Log to a file and create it if it doesn't exist. If
    # it cannot be opened, then fall back to logging on the console
    user_log_file = (
        pathlib.Path(BaseDirectory.save_cache_path(APP_NAME)) / "ansible-wrapper.log"
    )
    try:
        logging.basicConfig(
            format="%(asctime)s - %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d-%H-%M",
            filename=user_log_file,
            filemode="w+",
            level=logging.INFO,
        )
    except OSError:
        logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.INFO)
        logging.error(
            "Unable to open log file at %s. Logging on console instead",
            user_log_file,
        )

    # The default value for the branch is the current distro release name.
    # Set this before parsing the configuration. If it can't be detected,
    # it should get set to None. If the branch does not currently exist, it
    # should be set to main.
    distro_name = get_distro_release_name()
    if branch_exists(distro_name):
        USER_CONFIG["git_branch"] = distro_name
    else:
        USER_CONFIG["git_branch"] = "main"

    # Parse the user's previous settings
    parse_user_config()

    # If common got removed from the configuration, add it back to prevent
    # potentially bad things from happening
    if "common" not in USER_CONFIG["roles_this_run"]:
        USER_CONFIG["roles_this_run"].append("common")

    if not USER_CONFIG["git_branch"]:
        USER_CONFIG["git_branch"] = "main"

    # Show the window and ensure when it's closed that the script terminates
    win = AnsibleWrapperWindow()
    win.connect("delete-event", Gtk.main_quit)
    win.show_all()

    if not validate_branch_settings(win):
        logging.warning("Non-optimal user branch settings.")

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
            self.set_icon_name("{{ common_tux_icon_name }}")
        except GLib.GError as err:
            logging.warning("Unable to set Tux icon", exc_info=err)

        # Create a box to contain all elements that will be added to the window
        self.vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(self.vbox)

        self.create_toolbar()

        contents = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        contents.set_border_width(10)

        instruction_text = (
            "Select the course configurations to add/update"
            " (at this time courses cannot be removed)."
        )
        label = Gtk.Label(label=instruction_text)
        label.set_xalign(0.0)
        label.set_yalign(0.0)

        contents.pack_start(label, False, False, 0)

        self.courses_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.add_all_courses()
        contents.pack_start(self.courses_box, False, False, 0)

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

    def add_all_courses(self):
        """
        Add all courses the window through the checkbox list.
        """
        # Remove the existing elements
        for child in self.courses_box.get_children():
            child.destroy()
        self.checkboxes.clear()

        # This button doesn't do anything. Common is always run
        refresh = Gtk.CheckButton(label="Base configuration")
        refresh.set_tooltip_text("This option is required")
        refresh.set_active(True)
        refresh.set_sensitive(False)
        self.courses_box.pack_start(refresh, False, False, 0)

        def add_course(course, tag, experimental=False):
            if experimental and not USER_CONFIG["allow_experimental"]:
                return
            checkbox = Gtk.CheckButton(label=course)
            checkbox.set_tooltip_text(f"Configure for {course}")
            self.courses_box.pack_start(checkbox, False, False, 0)
            if tag in USER_CONFIG["roles_this_run"]:
                checkbox.set_active(True)
            checkbox.connect("toggled", self.on_course_toggled, tag)
            self.checkboxes.append(checkbox)

        # Add a checkbox for every course; sorting is necessary because
        # dictionaries do not guarantee that order is preserved
        for (course, tag) in sorted(COURSES.items()):
            add_course(course, tag, experimental=False)
        if USER_CONFIG["allow_experimental"]:
            for (course, tag) in sorted(EXPERIMENTAL_COURSES.items()):
                add_course(f"{course} ⚠️Experimental⚠️", tag, experimental=True)
        self.courses_box.show_all()

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
            USER_CONFIG["roles_this_run"].append(name)
        else:
            USER_CONFIG["roles_this_run"].remove(name)

    def create_toolbar(self):
        """
        Initializes the window's toolbar.
        """

        menu_bar = Gtk.MenuBar()

        # Create the File menu
        file_menu = Gtk.Menu()
        file_item = Gtk.MenuItem(label="File")
        file_item.set_submenu(file_menu)

        # Add settings and quit items to the File menu
        settings = Gtk.MenuItem(label="Settings\u2026")
        settings.connect("activate", self.show_settings)
        file_menu.append(settings)
        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", Gtk.main_quit)
        file_menu.append(quit_item)

        menu_bar.append(file_item)

        # Create the Help menu
        help_menu = Gtk.Menu()
        help_item = Gtk.MenuItem(label="Help")
        help_item.set_submenu(help_menu)

        # Add about item to the Help menu
        about = Gtk.MenuItem(label="About")
        about.connect("activate", self.show_about_dialog)
        help_menu.append(about)

        # Add a documentation link to the help menu
        docs = Gtk.MenuItem(label="Documentation")
        docs.connect(
            "activate",
            lambda _: webbrowser.open("http://www.jmunixusers.org/presentations/vm/"),
        )
        help_menu.append(docs)

        menu_bar.append(help_item)

        self.vbox.pack_start(menu_bar, False, False, 0)

    def show_settings(self, _):
        """
        Displays a dialog for changing the program's settings.
        """

        dialog = SettingsDialog(parent=self)
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.add_all_courses()
        dialog.destroy()

    def show_about_dialog(self, _):
        """
        Displays the About dialog.
        """

        about_dialog = Gtk.AboutDialog()
        about_dialog.set_logo_icon_name("{{ common_tux_icon_name }}")
        about_dialog.set_transient_for(self)
        about_dialog.set_program_name(NAME)
        about_dialog.set_copyright("Copyright \xa9 2018-2022 JMU Unix Users Group")
        about_dialog.set_comments(
            "A tool for configuring virtual machines for use in the "
            "JMU Department of Computer Science, "
            "maintained by the Unix Users Group"
        )
        about_dialog.set_authors(["JMU Unix Users Group"])
        about_dialog.set_website("http://github.com/jmunixusers/cs-vm-build")
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
            success_msg = "Your machine has been configured for " + ", ".join(
                sorted(USER_CONFIG["roles_this_run"])
            )
            show_dialog(
                self,
                Gtk.MessageType.INFO,
                Gtk.ButtonsType.OK,
                "Complete",
                success_msg,
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
        elif exit_status in (126, 32256):
            pkexec_err_msg = (
                "Authentication failed because the dialog was closed. Please try again."
            )
            show_dialog(
                self,
                Gtk.MessageType.ERROR,
                Gtk.ButtonsType.OK,
                "Unable to authenticate",
                pkexec_err_msg,
            )
            logging.warning("User dismissed authentication dialog")
        elif exit_status in (127, 32512):
            pkexec_err_msg = (
                "Unable to authenticate due to an incorrect"
                " password or insufficient permissions."
                " Plese try again."
            )
            show_dialog(
                self,
                Gtk.MessageType.ERROR,
                Gtk.ButtonsType.OK,
                "Unable to authenticate",
                pkexec_err_msg,
            )
            logging.error("Unable to authenticate user")
        else:
            ansible_err_msg = (
                "There was an error while running the configuration tasks. "
                "Please try again."
                "\nIf this issue continues to occur, copy"
                " {{ common_ansible_log_file }} and"
                f" <a href='{USER_CONFIG['git_url']}'>create an issue</a>"
            )
            show_dialog(
                self,
                Gtk.MessageType.ERROR,
                Gtk.ButtonsType.OK,
                "Error",
                ansible_err_msg,
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
                self,
                Gtk.MessageType.ERROR,
                Gtk.ButtonsType.CANCEL,
                "No Internet connection",
                no_internet_msg,
            )
            return

        if not branch_exists(USER_CONFIG["git_branch"]):
            invalid_branch(self)
            return

        for checkbox in self.checkboxes:
            checkbox.set_sensitive(False)

        self.cancel_button.set_sensitive(False)
        self.run_button.set_sensitive(False)

        write_user_config()

        logging.info(
            "Running ansible-pull with flags: %s",
            ",".join(USER_CONFIG["roles_this_run"]),
        )

        with TemporaryDirectory() as temp_dir:
            # spawn_sync will not perform a path lookup; however, pkexec and env will
            cmd_args = [
                "/usr/bin/pkexec",
                "env",
                "PYTHONUNBUFFERED=1",
                "ansible-pull",
                "--url",
                USER_CONFIG["git_url"],
                "--checkout",
                USER_CONFIG["git_branch"],
                "--directory",
                temp_dir,
                "--inventory",
                "hosts",
                "--tags",
                ",".join(USER_CONFIG["roles_this_run"]),
            ]

            try:
                # Disabling because breaking up the URL in this comment would just make things
                # less readable.
                # pylint: disable=line-too-long
                # These arguments do not match at all with any documentation that I have
                # seen, nor do they match the output of Vte.Terminal.spawn_async.get_arguments().
                # The PyGObject docs are just outright wrong for the ordering of the
                # arguments to this function in every possible way:
                #   https://lazka.github.io/pgi-docs/#Vte-2.91/classes/Pty.html#Vte.Pty.spawn_async
                # Other docs seem to not show that there are actually two arguments between
                # the spawn_flags and the timeout argument:
                #   https://lazka.github.io/pgi-docs/Vte-2.91/classes/Terminal.html#Vte.Terminal.spawn_async
                # So it's hard to know what we're actually passing, but I believe
                # that everything up until spawn flags matches the lazka.github.io link.
                # Then it's _two_ arguments for child_setup, the timeout, and then the
                # cancellable and callback arguments. There is also the user_data argument
                # which is not passed.
                # For some reason, this function also outright rejects any keyword arguments
                # and requires that everything be passed as positional parameters, so there
                # is not a way to make sense of the arguments to this call that I am aware of.
                # Unfortunately, the more reasonable spawn_sync has been deprecated. The
                # documentation surrounding this function likely will not improve until and
                # unless GTK stops treating Python support like an afterthought.
                self.terminal.spawn_async(
                    Vte.PtyFlags.DEFAULT,
                    os.environ["HOME"],
                    cmd_args,
                    [],
                    GLib.SpawnFlags.DO_NOT_REAP_CHILD,
                    None,
                    None,
                    -1,
                    None,
                    None,
                )
            except GLib.Error as error:
                logging.error("Unable to run ansible command.", exc_info=error)
                self.sub_command_exited(None, 1)


class SettingsDialog(Gtk.Dialog):
    """
    Settings dialog window for the configuration tool.
    """

    def __init__(self, parent):
        Gtk.Dialog.__init__(self, "Settings", parent, 0)
        self.add_buttons(
            Gtk.STOCK_CANCEL,
            Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK,
            Gtk.ResponseType.OK,
        )

        self._settings = {}
        self.set_default_size(400, 100)

        # Use a grid so that the labels and entries can be aligned correctly.
        grid = Gtk.Grid()
        grid.set_row_spacing(6)
        grid.set_column_spacing(6)
        grid.set_border_width(6)

        branch_label = self._create_label("Release track:")
        url_label = self._create_label("Source URL:")
        ignore_main_label = self._create_label("Development:")
        experimental_label = self._create_label("Experimental:")

        branch_entry = self._create_entry(USER_CONFIG["git_branch"])
        url_entry = self._create_entry(USER_CONFIG["git_url"])
        experimental_check = self._create_checkbox(
            "Allow running unsupported/experimental courses",
            USER_CONFIG["allow_experimental"],
        )
        ignore_main_check = self._create_checkbox(
            "Allow running from development branch",
            USER_CONFIG.get("ignore_main", False),
        )

        self._register_setting("git_branch", branch_entry)
        self._register_setting("git_url", url_entry)
        self._register_setting("allow_experimental", experimental_check)
        self._register_setting("ignore_main", ignore_main_check)

        self._add_row(grid, 0, branch_label, branch_entry)
        self._add_row(grid, 1, url_label, url_entry)
        self._add_row(grid, 2, ignore_main_label, ignore_main_check)
        self._add_row(grid, 3, experimental_label, experimental_check)

        self.get_content_area().pack_end(grid, False, False, 0)

        grid.show_all()

        def handle_response(_, response):
            if response != Gtk.ResponseType.OK:
                return

            for key in self._settings:
                USER_CONFIG[key] = self.get_setting(key)
            write_user_config()

        self.connect("response", handle_response)

    @staticmethod
    def _add_row(grid, row, label, widget):
        """
        Add a row to the list of settings widgets in the Dialog.
        """
        grid.attach(label, 0, row, 1, 1)
        grid.attach(widget, 1, row, 1, 1)

    def _register_setting(self, key, widget):
        """
        Registers a setting and its associated GTK widget. This allows it to
        be retrieved by the settings key later.
        """

        self._settings[key] = widget

    def get_setting(self, key):
        """
        Retrieves the value associated with a particular setting. This allows
        for the caller to get the value the user chose.
        """

        widget = self._settings.get(key, None)
        if widget is None:
            return None

        if isinstance(widget, Gtk.Entry):
            # The docs say that the string returned from get_text() should not
            # be freed, modified, nor stored. It is unclear if this is a
            # relic from C++, but to be safe, we'll make a copy of the string
            # and return that to the caller.
            return str(widget.get_text())
        if isinstance(widget, Gtk.CheckButton):
            return widget.get_active()

        # Add more widget types here as appropriate
        return None

    def get_all_settings(self):
        """
        Retrieves a mapping of all settings.
        """
        return {key: self.get_setting(key) for key in self._settings}

    @staticmethod
    def _create_label(text):
        """
        Helps with creating a GTK Label. Sets the text to the given text and then
        right-justifies the text.
        """

        label = Gtk.Label(label=text)
        label.set_justify(Gtk.Justification.RIGHT)
        label.set_halign(Gtk.Align.END)
        return label

    @staticmethod
    def _create_entry(text, width=40):
        """
        Creates a GTK Entry widget with the given width and default text.
        """

        entry = Gtk.Entry()
        entry.set_text(text)
        entry.set_width_chars(width)
        return entry

    @staticmethod
    def _create_checkbox(text, checked):
        """
        Creates a GTK Check Button widget
        """

        checkbox = Gtk.CheckButton(label=text)
        checkbox.set_active(checked)
        return checkbox


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

    dialog = Gtk.MessageDialog(
        parent=parent,
        message_type=dialog_type,
        buttons=buttons_type,
        text=header,
    )
    dialog.format_secondary_markup(message)
    response = dialog.run()
    dialog.destroy()
    return response


def parse_json_config(path: pathlib.Path, config):
    """
    Loads the data in the file at the provided path into a dictionary.
    :param path: The path to the JSON file
    :param config: The dictionary to update with data from the JSON file
    """

    try:
        with open(path, "r", encoding="utf-8") as config_file:
            config.update(yaml.safe_load(config_file))
    except FileNotFoundError as fne:
        logging.info("User configuration file not present. Ignoring.", exc_info=fne)
    except yaml.YAMLError as jde:
        logging.info("User configuration is invalid. Ignoring.", exc_info=jde)


def write_json_config(path: pathlib.Path, config):
    """
    Writes a dictionary to a file at the provided at path in JSON format.
    :param path: The path of the file to write the dictionary to
    :param config: The dictionary to write. Must be serializable as JSON
    """

    path.parent.mkdir(parents=True, exist_ok=True)

    class IndentingSafeDumper(yaml.SafeDumper):
        """
        PyYAML Dumper that increments indentation for lists and objects
        correctly.
        """

        def increase_indent(self, flow=False, indentless=False):
            return super().increase_indent(flow=flow, indentless=False)

    with open(path, "w", encoding="utf-8") as config_file:
        # Make the written file relatively readable & writable by users
        yaml.dump(
            config,
            config_file,
            Dumper=IndentingSafeDumper,
            default_flow_style=False,
            encoding="utf-8",
            explicit_start=True,
        )


def parse_user_config():
    """
    Loads a user's configuration.
    """

    config_dir = BaseDirectory.load_first_config(APP_NAME)
    if config_dir:
        config_path = pathlib.Path(config_dir) / "settings.yml"
        parse_json_config(config_path, USER_CONFIG)
    else:
        logging.info("User configuration has not been created yet")

    USER_CONFIG["roles_all_time"] = list(set(USER_CONFIG["roles_all_time"]))
    USER_CONFIG["roles_this_run"] += USER_CONFIG["roles_all_time"]
    # Remove duplicates from roles for this run
    USER_CONFIG["roles_this_run"] = list(set(USER_CONFIG["roles_this_run"]))

    logging.info("Read config: %s from %s", USER_CONFIG, config_dir)


@functools.lru_cache
def parse_os_release():
    """
    Loads the data in /etc/os-release.
    :returns: A dictionary with the data parsed from /etc/os-release
    """

    # Set os_release_file to the first item in the list that exists
    os_release_file = [
        file for file in ["/etc/os-release", "/usr/lib/os-release"]
        if os.path.exists(file)
    ][0]
    os_release_contents = {}
    # os-release(5) specifies that it is expected that the strings in
    # this file are UTF-8 encoding
    with open(os_release_file, encoding="utf-8") as os_release:
        # This method of parsing is based on the example at
        # https://www.freedesktop.org/software/systemd/man/os-release.html
        for line in os_release:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if match := re.match(r"([A-Z][A-Z_0-9]+)=(.*)", line):
                key, value = match.groups()
                # Parse string values correctly
                if value and value[0] in ["'", '"']:
                    value = ast.literal_eval(value)
                os_release_contents[key] = value

    return os_release_contents


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
    if "VERSION_CODENAME" in os_release_config:
        release = os_release_config["VERSION_CODENAME"]
    else:
        logging.debug(
            "VERSION_CODENAME is not in /etc/os_release. Full file contents: %s",
            os_release_config,
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
    chosen_branch = USER_CONFIG["git_branch"]
    chosen_remote = USER_CONFIG["git_url"]
    main_okay = USER_CONFIG.get("ignore_main", False)
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
            chosen_remote,
        )
        return True

    # These are branches that should be handled specially
    if chosen_branch == "main" and system_exists and not main_okay:
        # The user wants to run main, but there is a release for their distro
        header = "Unstable release selected"
        warning_prompt = (
            "You have selected an unstable development branch (main) of the"
            " configuration tool. It is recommended to use the release branch"
            " of this tool that corresponds to your Linux Mint version."
            " Consider changing your settings to match the following:"
            f"\nRelease: {system_version}\nURL: {USER_CONFIG['git_url']}"
        )

        display_ignorable_warning(header, warning_prompt, parent, "ignore_main")
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
            f"\nRelease: {system_version}\nURL: {USER_CONFIG['git_url']}"
        )
    elif system_exists and not chosen_exists:
        header = "Chosen release unavailable"
        warning_prompt = (
            "You have selected a release of the configuration tool that does"
            " not exist on the git URL you have specified. It is recommended"
            " that you switch to the release branch that corresponds to your"
            " Linux Mint release on the UUG git repository."
            " Consider changing your settings to match the following:"
            f"\nRelease: {system_version}\nURL: {DEFAULT_GIT_REMOTE}"
        )
    elif looks_minty and not (branch_mismatch or chosen_exists):
        header = "Chosen release not available"
        warning_prompt = (
            "You have selected a release of the configuration tool that does"
            " not exist on the git URL you have specified; however, your"
            " current version of Linux Mint is not yet supported. It is"
            " recommended that you switch to the main (testing) branch."
            " Consider changing your settings to match the following:"
            f"\nRelease: main\nURL: {USER_CONFIG['git_url']}"
        )
    elif branch_mismatch and looks_minty and not system_exists:
        # The user wants to use a minty-looking branch, but it doesn't match
        # the system and we don't support what they want to run.
        header = "Incompatible Linux Mint release"
        warning_prompt = (
            "You have selected a version of the configuration tool meant for"
            " a different Linux Mint release; however, we are unable to"
            " completely support your Linux Mint release at this time."
            " It is recommended to switch to the main (testing) branch."
            " Consider changing your settings to match the following:"
            f"\nRelease: main\nURL: {USER_CONFIG['git_url']}"
        )
    elif branch_mismatch and not (system_exists or chosen_exists):
        header = "Chosen release unavailable"
        warning_prompt = (
            "You have selected a version of the configuration tool that does"
            " not support your version of Linux Mint; however, there is not"
            " a release that supports your version of Linux Mint available"
            " yet. It is recommended to switch to the main (testing) branch."
            " Consider changing your settings to match the following:"
            f"\nRelease: main\nURL: {USER_CONFIG['git_url']}"
        )

    if header and warning_prompt:
        show_dialog(
            parent,
            Gtk.MessageType.WARNING,
            Gtk.ButtonsType.OK,
            header,
            warning_prompt,
        )

    return warning_prompt is None


def branch_exists(branch_name):
    """
    Checks whether a particular branch exists at the currently-configured
    git URL.

    :param branch_name: The branch name to search for on the remote
    :returns: True if the branch exists and False if it does not
    """

    remote_url = USER_CONFIG["git_url"]
    cmd = [
        "/usr/bin/env",  # Use git wherever it is, don't depend on /usr/bin
        "git",
        "ls-remote",  # ls-remote allows listing refs on a given remote
        "--heads",  # only list heads (branches, not tags/PRs)
        "--exit-code",  # Exit with status 2 if no matching refs are found
        remote_url,
        branch_name,  # Find refs with the same name as the branch we want
    ]
    output = subprocess.run(cmd, stdout=subprocess.PIPE, check=False)
    logging.debug("ls-remote result for %s: %s", branch_name, output.stdout)
    logging.debug("ls-remote code for %s: %s", branch_name, output.returncode)
    return output.returncode == 0


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
        parent,
        Gtk.DialogFlags.MODAL,
        Gtk.MessageType.WARNING,
        Gtk.ButtonsType.OK_CANCEL,
        title,
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
        f"\nRelease: %{USER_CONFIG['git_branch']}"
        f"\nURL: {USER_CONFIG['git_url']}\nIf you're using a current"
        " release of Linux Mint, you may submit"
        f" <a href='{USER_CONFIG['git_url']}>an issue</a> requesting support for"
        " the release listed above"
    )
    show_dialog(
        parent,
        Gtk.MessageType.ERROR,
        Gtk.ButtonsType.CANCEL,
        "Invalid Release",
        bad_branch_msg,
    )


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
            logging.error(
                "Response from %s was not %s as expected. Received: %s",
                url,
                expected,
                response_data,
            )
            return False
    except urllib.error.URLError as url_err:
        logging.error("Unable to connect to %s", url, exc_info=url_err)
        return False


def write_user_config():
    """
    Writes the user's configuration out to the configuration file. This
    allows configuration changes to persist across invocations.
    """

    # Add all new roles to cummulative roles and also remove duplicates before
    # writing -- must be a list since sets cannot be serialized with JSON
    USER_CONFIG["roles_this_run"] = list(set(USER_CONFIG["roles_this_run"]))
    USER_CONFIG["roles_all_time"] += USER_CONFIG["roles_this_run"]
    # Since there could now be duplicates in roles_all_time, remove them
    USER_CONFIG["roles_all_time"] = list(set(USER_CONFIG["roles_all_time"]))

    config_path = (
        pathlib.Path(BaseDirectory.save_config_path("cs-vm-build")) / "settings.yml"
    )
    logging.info("Writing user configuration %s to %s", USER_CONFIG, config_path)

    write_json_config(config_path, USER_CONFIG)


if __name__ == "__main__":
    main()
