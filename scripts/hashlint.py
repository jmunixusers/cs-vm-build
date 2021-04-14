#!/usr/bin/env python3

"""
Simple script to validate the various hashes for downloads across the project.
"""

import asyncio
import hashlib
import sys

from collections import namedtuple
from typing import Any, Dict

import aiohttp
import jinja2
import yaml

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


CheckData = namedtuple("CheckData", ["url", "expected_hash", "source_file"])


def get_field(data: Dict[str, Dict[str, Any]], key: str) -> Any:
    """
    Get a field from nested dictionary, with the field denoted with dot-separated keys.

    For example, "a.b.c" -> data['a']['b']['c']
    """

    keys = key.split(".")

    while keys:
        data = data[keys.pop(0)]

    return data


async def check_software_hash(
    session: aiohttp.ClientSession, check_data: CheckData
) -> bool:
    """
    Checks the hash for the contents of a URL against an expected value.
    """

    try:
        async with session.get(check_data.url) as response:
            data = await response.read()
    except aiohttp.ClientError:
        print(
            f"{check_data.source_file}: Unable to download {check_data.url}",
            file=sys.stderr,
        )
        return False

    sha1 = hashlib.sha1(data).hexdigest()
    if sha1 != check_data.expected_hash:
        print(
            f"{check_data.source_file}: Expected {check_data.expected_hash}. Found {sha1}",
            file=sys.stderr,
        )
        return False

    print(
        f"{check_data.source_file}: Validated {sha1=} as expected from {check_data.url}"
    )

    return True


def process_variable(source: str, variable: str, value: str) -> str:
    """
    Process the string and substitute the variable and value.
    """

    template = jinja2.Template(source)
    return template.render(**{variable: value})


def urls_for_file(file: str, ansible_data: Dict[str, Any], lookup_data: Dict[str, Any]):
    """
    Return a set of all URLs in the given file key in the URLs mapping.
    """

    hash_data = get_field(ansible_data, lookup_data["hash"])
    if not isinstance(hash_data, dict):
        # We never actually care about the architecture name, so forcing this
        # to be a dictionary is a useful way to make the code cleaner later
        hash_data = {"_": hash_data}

    # Pull the unprocessed URLs from the Ansible variables; the assumption is that the
    # only jinja2-looking part of the URL, if there is one, is the `ansible_architecture`
    # which should be fine since `{{ }}` probably won't be in a URL and jinja2 is perfectly
    # content to be given templates that don't contain a given variable
    raw_urls = [get_field(ansible_data, url_path) for url_path in lookup_data["urls"]]

    checks = set()
    for url in raw_urls:
        for arch, expected_hash in hash_data.items():
            new_url = process_variable(url, "ansible_architecture", arch)
            checks.add(CheckData(new_url, expected_hash, file))
    return checks


async def main():
    """
    Main
    """

    # User-Agent is the same as used by Ansible itself
    # https://github.com/ansible/ansible/blob/062e780a68f9acd2ee6f824f252458b8a0351f24/lib/ansible/modules/get_url.py#L167
    # This is particularly relevant for Finch, which will throw a 403 when
    # downloading using the default User-Agent.
    headers = {"User-Agent": "ansible-httpget"}
    errors = 0
    to_check = set()
    for file, hash_data in URLS.items():
        with open(file) as software_data_file:
            software_data = yaml.safe_load(software_data_file)
            try:
                to_check |= urls_for_file(file, software_data, hash_data)
            except KeyError:
                print(f"{file}: File does not meet expected structure")
                errors += 1

    async with aiohttp.ClientSession(headers=headers, raise_for_status=True) as session:
        tasks = [
            asyncio.create_task(check_software_hash(session, check_data))
            for check_data in to_check
        ]
        # The gather must occur within the `with` otherwise the session may be closed
        # when the threads attempt to use it to download the file
        for result in await asyncio.gather(*tasks):
            # This relies on the fact that True gets coerced to 1 and that False gets
            # coerced to 0 when converted to an integer. The check method returns True
            # on success and we need to count failures.
            errors += not result

    return errors


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
