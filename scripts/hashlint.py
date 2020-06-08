#!/usr/bin/env python3

"""
Simple script to validate the various hashes for downloads across the project.
"""

import hashlib
import sys

import requests
import yaml

# https://requests.readthedocs.io/en/master/user/quickstart/#timeouts
REQUEST_TIMEOUT_SEC = 5
URLS = {
    "roles/jgrasp/vars/main.yml": {
        "hash": "jgrasp.hash",
        "urls": ["jgrasp.url"],
    },
    "roles/finch/vars/main.yml": {
        "hash": "finch.hash",
        "urls": ["finch.url"],
    },
    "roles/eclipse/vars/main.yml": {
        "hash": "eclipse.hash",
        "urls": ["eclipse.url", "eclipse.url_backup"],
    },
}


def get_field(data, key):
    """
    Get a field separated by dots
    """

    if isinstance(key, str):
        key = key.split('.')
    else:
        print(type(key))
    while key:
        data = data[key.pop(0)]
    return data


def check_software_hash(session, url, expected, file):
    """
    Checks the hash for the contents of a URL against an expected value
    """

    try:
        response = session.get(url, timeout=REQUEST_TIMEOUT_SEC)
        response.raise_for_status()
        data = response.content
    # pylint: disable=broad-except
    except Exception:
        print(f"{file}: Unable to download {url}", file=sys.stderr)
        return False

    sha1 = hashlib.sha1(data).hexdigest()
    if sha1 != expected:
        print(f"{file}: Expected {expected}. Found {sha1}", file=sys.stderr)
        return False

    print(f"{file}: Validated {sha1=} as expected")

    return True


def main():
    """
    Main
    """

    session = requests.Session()
    # User-Agent is the same as used by Ansible itself
    # https://github.com/ansible/ansible/blob/062e780a68f9acd2ee6f824f252458b8a0351f24/lib/ansible/modules/get_url.py#L167
    # This is particularly relevant for Finch, which will throw a 403 when
    # downloading using the default User-Agent.
    session.headers.update({'User-Agent': 'ansible-httpget'})
    errors = 0
    for file, hash_data in URLS.items():
        with open(file) as software_data_file:
            try:
                software_data = yaml.safe_load(software_data_file)
                expected_hash = get_field(software_data, hash_data['hash'])
                for url_path in hash_data['urls']:
                    url = get_field(software_data, url_path)
                    if not check_software_hash(session, url, expected_hash, file):
                        errors += 1
            except KeyError:
                print(f"{file}: File does not meet expected structure")
                errors += 1

    return errors


if __name__ == '__main__':
    sys.exit(main())
