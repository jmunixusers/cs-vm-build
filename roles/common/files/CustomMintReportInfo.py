import os
import gettext
import gi
import subprocess

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from mintreport import InfoReport, InfoReportAction

class Report(InfoReport):

    def __init__(self):

        self.title = "Run JMU CS Config Tool"
        self.icon = "edu.jmu.uug.tux"
        self.has_ignore_button = False

    def is_pertinent(self):
        return not os.path.exists('/opt/csvmprofile')

    def get_descriptions(self):
        # Return the descriptions
        descriptions = []
        descriptions.append("The JMU CS Config Tool has not been run on this machine yet.")
        descriptions.append("The config tool allows you to install software and customizations for specific JMU CS courses while also ensuring your machine is up-to-date.")
        return descriptions

    def get_actions(self):
        # Return available actions
        actions = []
        action = InfoReportAction(label="Run tool", callback=self.callback)
        action.set_style(Gtk.STYLE_CLASS_SUGGESTED_ACTION)
        actions.append(action)
        return actions

    def callback(self, data):
        subprocess.run(["/opt/vmtools/bin/uug_ansible_wrapper.py"], start_new_session=True)
        return True

if __name__ == "__main__":
    report = Report()
