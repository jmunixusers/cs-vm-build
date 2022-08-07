#!/usr/bin/env python3

"""
Simple script to validate the various hashes for downloads across the project.
"""

import asyncio
import hashlib
import json
import sys

from collections import namedtuple
from pathlib import Path

# Importing these types using in the string type hints is helpful for some
# editors to actually support hinting for these types.
# pylint: disable=unused-import
from typing import Any, Dict, List, Set, Tuple, Type

import aiohttp
import jinja2
import yaml

CACHE_FILE = Path.home() / ".cache" / "hashlint" / "cache.json"
URLS = {
    "roles/eclipse/vars/main.yml": {
        "hash": "eclipse.hash",
        "urls": ["eclipse.url", "eclipse.url_backup"],
    },
}


CheckData = namedtuple("CheckData", ["url", "expected_hash", "source_file"])


class CacheItem:
    """
    An item stored in the URL/ETag cache.
    """

    def __init__(self, url, etag, last_modified, file_hash):
        self.url = url
        self.etag = etag
        self.last_modified = last_modified
        self.hash = file_hash

    def __repr__(self):
        url = self.url
        etag = self.etag
        last_modified = self.last_modified
        return f"<Cache {url=!r} {etag=!r} {last_modified=!r} hash={self.hash!r}>"

    def to_json(self) -> Dict[str, Dict[str, str]]:
        """
        Return the cache item as a JSON serializable dictionary.
        """
        return {
            str(self.url): {
                "ETag": self.etag,
                "Last-Modified": self.last_modified,
                "hash": self.hash,
            }
        }

    @classmethod
    def from_json(cls, data) -> "List[Type[CacheItem]]":
        """
        Load an item from the cache.
        """
        return [
            cls(
                key, cache_data["ETag"], cache_data["Last-Modified"], cache_data["hash"]
            )
            for key, cache_data in data.items()
        ]

    @classmethod
    async def from_http_response(
        cls, response: aiohttp.ClientResponse
    ) -> "Type[CacheItem]":
        """
        Parse a cache item from an HTTP response
        """
        headers = response.headers
        url = response.url
        data = await response.read()
        file_hash = hashlib.sha1(data).hexdigest()

        return cls(url, headers.get("ETag"), headers.get("Last-Modified"), file_hash)


class Cache:
    """
    A cache of all downloaded items.
    """

    def __init__(self):
        self._items = []

    def __getitem__(self, url):
        return next(item for item in self._items if item.url == url)

    def __setitem__(self, url, item):
        if matches := [cached for cached in self._items if cached.url == url]:
            match = matches[0]
            self._items.remove(match)
        self._items.append(item)

    def __bool__(self):
        return bool(self._items)

    def __contains__(self, url):
        return bool([item for item in self._items if item.url == url])

    def __iter__(self):
        return iter([item.url for item in self._items])

    def __repr__(self):
        return f"<Cache items={self._items!r}>"

    @classmethod
    def from_json(cls, data: Dict[str, Dict[str, str]]) -> 'Type[Cache]':
        """
        Load a cache from a dictionary.
        """
        cache = cls()
        cache._items = list(CacheItem.from_json(data))
        return cache

    def to_json(self) -> Dict[str, Dict[str, str]]:
        """
        Return the cache as a JSON serializable dictionary.
        """
        cache = {}
        for item in self._items:
            cache.update(item.to_json())
        return cache


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
    session: aiohttp.ClientSession, check_data: CheckData, cache: Cache
) -> bool:
    """
    Checks the hash for the contents of a URL against an expected value.
    """

    headers = {}
    if check_data.url in cache:
        cache_item = cache[check_data.url]
        if cache_item.etag:
            headers["If-None-Exists"] = cache_item.etag
        if cache_item.last_modified:
            headers["If-Modified-Since"] = cache_item.last_modified

    try:
        async with session.get(
            check_data.url, headers=headers, timeout=600
        ) as response:
            if response.status == 200:
                cache_item = await CacheItem.from_http_response(response)
                cache[check_data.url] = cache_item
    except aiohttp.ClientError:
        print(
            f"{check_data.source_file}: Unable to download {check_data.url}",
            file=sys.stderr,
        )
        return False

    sha1 = cache_item.hash
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


def load_cache() -> Cache:
    """
    Load the cache from disk.
    """
    if CACHE_FILE.exists():
        with open(CACHE_FILE, encoding="utf-8") as cache:
            return Cache.from_json(json.load(cache))
    return Cache()


def write_cache(cache: Cache):
    """
    Save the cache to disk.
    """
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as cache_file:
        json.dump(cache.to_json(), cache_file, indent=4)


def get_urls() -> Tuple[Set[str], int]:
    """
    Load the list of URLs to validate hashes for as well as the number of errors
    encountered parsing the list.
    """
    errors = 0
    to_check = set()
    for file, hash_data in URLS.items():
        with open(file, encoding="utf-8") as software_data_file:
            software_data = yaml.safe_load(software_data_file)
        try:
            to_check |= urls_for_file(file, software_data, hash_data)
        except KeyError:
            print(f"{file}: File does not meet expected structure")
            errors += 1
    return to_check, errors


async def main():
    """
    Main
    """

    cache = load_cache()
    print(f"Cache loaded: {cache}")

    to_check, errors = get_urls()

    # User-Agent is the same as used by Ansible itself
    # https://github.com/ansible/ansible/blob/062e780a68f9acd2ee6f824f252458b8a0351f24/lib/ansible/modules/get_url.py#L167
    # This is particularly relevant for Finch, which will throw a 403 when
    # downloading using the default User-Agent.
    headers = {"User-Agent": "ansible-httpget"}
    async with aiohttp.ClientSession(headers=headers, raise_for_status=True) as session:
        tasks = [
            asyncio.create_task(check_software_hash(session, check_data, cache))
            for check_data in to_check
        ]
        # The gather must occur within the `with` otherwise the session may be closed
        # when the threads attempt to use it to download the file
        for result in await asyncio.gather(*tasks):
            # This relies on the fact that True gets coerced to 1 and that False gets
            # coerced to 0 when converted to an integer. The check method returns True
            # on success and we need to count failures.
            errors += not result

    write_cache(cache)
    print(f"Wrote cache: {cache}")
    return errors


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
