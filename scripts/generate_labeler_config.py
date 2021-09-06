#!/usr/bin/env python3

import yaml

PLAYBOOK_PATH = "local.yml"
CONFIG_PATH = ".github/labeler.yml"

SPECIAL_LABELS = { "cs149": "cs149/159", "cs159": "cs149/159" }

def lookup_label(course):
    return SPECIAL_LABELS.get(course, course)

def get_glob(role):
    return f"roles/{role}/**"

def main():
    with open(PLAYBOOK_PATH, encoding="utf-8") as playbook:
        data = yaml.safe_load(playbook)
    roles = data[0]["roles"]
    paths = {}

    for role in roles:
        if not isinstance(role['tags'], list):
            continue
        path_glob = get_glob(role['role'])
        for course in role["tags"]:
            label = lookup_label(course)
            paths.setdefault(label, list())
            paths[label].append(path_glob)
    
    with open(CONFIG_PATH, "w", encoding="utf-8") as labeler_config:
        yaml.safe_dump(paths, labeler_config, explicit_start=True)


if __name__ == "__main__":
    main()