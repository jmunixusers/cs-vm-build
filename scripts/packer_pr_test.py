#!/usr/bin/env python3

"""
Make automated testing of pull requests that require packer builds at least
a little bit easier. Handles fetching the information about the pull
request and passing it to packer. It also makes a best-guess effort at
determining the proper host audio device to select.
"""

import json
import os
import platform
import subprocess
import sys
import tempfile

from typing import Dict, List, Tuple

try:
    import click
    import github
except ImportError:
    print(
        "This helper script requires click and PyGithub. Install them with pip.",
        file=sys.stderr,
    )
    sys.exit(1)


CONFIG = {"QUIET_MODE": True, "BASE_REPO": "jmunixusers/cs-vm-build"}


def determine_audio_setting() -> str:
    """
    Determine a good default audio device type for building the virtual machine.

    Based on the OS type, will choose what is likely the best audio driver. If there are
    multiple options and interactive mode is used, the user will be prompted to confirm that
    choice if their platform has multiple audio options.
    """

    # Built around the supported OSes that can be returned by platform.system
    #  https://docs.python.org/3/library/platform.html
    # as well as the various audio platforms that can be used by packer's virtualbox-iso
    # builder
    #  https://www.packer.io/docs/builders/virtualbox-iso#hardware-configuration
    os_audio = {
        "Darwin": ["coreaudio"],
        "Windows": ["dsound"],
        "Linux": ["pulse", "alsa", "oss"],
        "_default_": ["null", "coreaudio", "dsound", "oss", "alsa", "pulse"],
    }
    try:
        setting_choices = os_audio[platform.system()]
    except KeyError:
        setting_choices = os_audio["_default_"]

    if len(setting_choices) == 1 or CONFIG["QUIET_MODE"]:
        return setting_choices[0]

    return click.prompt(
        "Which audio device type should be used?",
        type=click.Choice(setting_choices),
        default=setting_choices[0],
    )


def build_authentication_info(token: str) -> Dict[str, str]:
    """
    Builds a set of kwargs to pass to the PyGithub client class for authentication.
    """

    args = {}
    if token:
        args["login_or_token"] = token
    return args


def lookup_pull_request(pr_id: int, **kwargs) -> github.PullRequest.PullRequest:
    """
    Finds the information on the given pull request.

    If kwargs are provided, they will be passed to the PyGithub main class; this can be used
    to authenticate to the API. In the typical case, authentication will likely not be required
    since the API actions that are performed are just read actions on public repositories.
    """

    github_client = github.Github(**kwargs)
    repository = github_client.get_repo(CONFIG["BASE_REPO"])
    return repository.get_pull(pr_id)


def determine_pr_clone_info(pull_request: github.PullRequest.PullRequest) -> Tuple[str, str]:
    """Gets the URL and branch to clone a pull request."""

    return pull_request.head.repo.clone_url, pull_request.head.ref


def write_var_file(output_file, clone_info: Tuple[str, str], audio: str):
    """
    Write the packer var file configuration.
    """

    pr_config = {}
    pr_config["audio"] = audio
    pr_config["git_repo"] = clone_info[0]
    pr_config["git_branch"] = clone_info[1]
    json.dump(pr_config, output_file, indent=4)


def build_packer_command(
    packer_cmd: str, var_files: str, pr_var_file: str, template: str
) -> List[str]:
    """
    Build the array of arguments needed to invoke packer.
    """

    command = [packer_cmd, "build"]
    for filename in var_files:
        command.append(f"-var-file={filename}")
    command.append(f"-var-file={pr_var_file}")
    command.append(template)
    return command


@click.command("packer-pr-test")
@click.option(
    "--packer-cmd",
    "-p",
    default="packer",
    help="The path to the packer executable (or the name on $PATH)",
)
@click.option(
    "--var-file",
    multiple=True,
    type=click.Path(exists=True),
    help="Additional files to be passed to the -var-file packer argument",
)
@click.option(
    "--interactive/--non-interactive",
    default=(not CONFIG["QUIET_MODE"]),
    help="Whether or not to ask for confirmation on various things.",
)
@click.option(
    "--base-repo",
    "-r",
    default=CONFIG["BASE_REPO"],
    help="The repo against which pull requests are opened.",
)
@click.option(
    "--github-access-token",
    envvar="GITHUB_ACCESS_TOKEN",
    help="The (optional) token to use to authenticate to the GitHub API",
)
@click.argument(
    "pull-request-id",
    type=click.INT,
)
@click.argument(
    "template-file",
    type=click.Path(exists=True),
)
# pylint: disable=too-many-arguments
def main(
    interactive,
    packer_cmd,
    base_repo,
    github_access_token,
    var_file,
    pull_request_id,
    template_file,
):
    """
    Make automated testing of pull requests that require packer builds at least
    a little bit easier. Handles fetching the information about the pull
    request and passing it to packer. It also makes a best-guess effort at
    determining the proper host audio device to select.

    Interactive mode can be enabled with --interactive which will prompt for a
    few things that usually would just have defaults selected.
    """

    CONFIG["QUIET_MODE"] = not interactive
    CONFIG["BASE_REPO"] = base_repo

    try:
        api_auth = build_authentication_info(github_access_token)
        pull_request = lookup_pull_request(pull_request_id, **api_auth)
    except github.RateLimitExceededException:
        click.echo("Exceeded Github rate limit. Please try authenticating.", err=True)
        return 1
    except github.BadCredentialsException:
        click.echo("Github did not accept the provided credentials.", err=True)
        return 1
    except github.UnknownObjectException:
        click.echo(
            f"Pull request {CONFIG['BASE_REPO']}#{pull_request_id} could not be found", err=True
        )
        return 1

    clone_data = determine_pr_clone_info(pull_request)
    audio_device = determine_audio_setting()

    # We can't delete the file when we're done with it since packer needs it; however, it
    # is important that we close it so that other processes can open.
    with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as config_file:
        write_var_file(config_file, clone_data, audio_device)

    packer_args = build_packer_command(packer_cmd, var_file, config_file.name, template_file)
    click.echo(f"Command: {' '.join(packer_args)}")
    if CONFIG["QUIET_MODE"] or click.confirm("Execute command?", default=True):
        try:
            subprocess.run(packer_args, check=True)
        except subprocess.CalledProcessError:
            return 1
        finally:
            os.remove(config_file.name)

    return 0


if __name__ == "__main__":
    # pylint: disable=no-value-for-parameter
    sys.exit(main())
