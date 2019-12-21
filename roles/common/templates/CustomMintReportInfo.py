# The file name is required to be non-snake-case because of the requirements
# of mintreport scirpt names
# pylint: disable=invalid-name

# NOTE: This file is parsed by Jinja2 as part of an Ansible playbook.
# The following values were interpretted:
#   tux_icon_name: {{ tux_icon_name }}
#   global_profile_path: {{ global_profile_path }}
#   uug_ansible_wrapper: {{ uug_ansible_wrapper }}

"""
Custom mintreport script for ensuring the JMU CS VM Config Tool has been run on
the system.
"""

import os
import subprocess

import gi
gi.require_version('Gtk', '3.0')
# pygobject best practice, unfortunately, is to do the import after caling the
# require_version() function. This triggers a pylint message.
# pylint: disable=wrong-import-position
from gi.repository import Gtk

# Mintreport is not available on Ubuntu or PyPi so the linter will complain
# pylint: disable=import-error
from mintreport import InfoReport, InfoReportAction

# Since we don't have much choice in the structure of this class since we're
# specializing a required class, we need to ignore related pylint errors.
# pylint: disable=no-self-use,unused-argument
class Report(InfoReport):
    """
    Override of mintreport's InfoReport
    """

    def __init__(self):

        self.title = "Run JMU CS Config Tool"
        self.icon = "{{ tux_icon_name }}"
        self.has_ignore_button = False

    def is_pertinent(self):
        """
        Validates whether this report should be shown the mintreport
        """

        return not os.path.exists('{{ global_profile_path }}')

    def get_descriptions(self):
        """
        Provides a description of the report as a series of strings, each is a
        different line/paragraph in the window
        """

        # Return the descriptions
        descriptions = []
        descriptions.append(
            "The JMU CS Config Tool has not been run on this machine yet."
        )
        descriptions.append(
            "The config tool allows you to install software and customizations"
            " for specific JMU CS courses while also ensuring your machine is"
            " up-to-date."
        )
        return descriptions

    def get_actions(self):
        """
        Provides the action to run the tool
        """

        # Return available actions
        actions = []
        action = InfoReportAction(label="Run tool", callback=self.callback)
        action.set_style(Gtk.STYLE_CLASS_SUGGESTED_ACTION)
        actions.append(action)
        return actions

    def callback(self, data):
        """
        The callback to execute when the user clicks the action
        """

        subprocess.run(
            ["{{ uug_ansible_wrapper }}"],
            start_new_session=True, check=False
        )
        return True

if __name__ == "__main__":
    report = Report()
