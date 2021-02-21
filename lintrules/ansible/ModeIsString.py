from typing import Any, Dict, Union

import ansiblelint.utils
from ansiblelint.rules import AnsibleLintRule

class ModeIsString(AnsibleLintRule):
    id = "mode-is-string"
    shortdesc = "mode must be a string"
    description = "File and directory modes must be strings"
    tags = ['idiom']

    def matchtask(self, task: Dict[str, Any]) -> Union[bool, str]:
        # Tasks without a mode should not be matched
        if "action" not in task:
            return False

        invalid_mode_keys = []
        # There are various mode-like keys, including "mode" and
        # "directory_mode"
        for key, value in task["action"].items():
            if key.endswith("mode") and not isinstance(value, str):
                invalid_mode_keys.append(key)

        if not invalid_mode_keys:
            return False

        return f"The value for {invalid_mode_keys} should be a string"
