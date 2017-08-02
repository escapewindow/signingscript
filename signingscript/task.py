#!/usr/bin/env python
"""Signingscript task functions."""
import aiohttp
from frozendict import frozendict
import json
import logging
import os
import random
import traceback

import scriptworker.client
from scriptworker.exceptions import ScriptWorkerException
from scriptworker.utils import retry_request

from signingscript.sign import get_suitable_signing_servers, sign_gpg, \
    sign_jar, sign_macapp, sign_signcode, sign_widevine, sign_file, log_shas
from signingscript.exceptions import SigningServerError, TaskVerificationError

log = logging.getLogger(__name__)

FORMAT_TO_SIGNING_FUNCTION = frozendict({
    "gpg": sign_gpg,
    "jar": sign_jar,
    "macapp": sign_macapp,
    "osslsigncode": sign_signcode,
    "sha2signcode": sign_signcode,
    # sha2signcodestub uses a generic sign_file
    "signcode": sign_signcode,
    "widevine": sign_widevine,
    "widevine_blessed": sign_widevine,
    "default": sign_file,
})


# task_signing_formats {{{1
def task_signing_formats(task):
    """Get the list of signing formats from the task signing scopes.

    Args:
        task (dict): the task definition.

    Returns:
        list: the signing formats.

    """
    return [s.split(":")[-1] for s in task["scopes"] if
            s.startswith("project:releng:signing:format:")]


# validate_task_schema {{{1
def validate_task_schema(context):
    """Validate the task json schema.

    Args:
        context (SigningContext): the signing context.

    Raises:
        ScriptWorkerTaxkException: on failed validation.

    """
    with open(context.config['schema_file']) as fh:
        task_schema = json.load(fh)
    log.debug(task_schema)
    scriptworker.client.validate_json_schema(context.task, task_schema)


# get_token {{{1
async def get_token(context, output_file, cert_type, signing_formats):
    """Retrieve a token from the signingserver tied to my ip.

    Args:
        context (SigningContext): the signing context
        output_file (str): the path to write the token to.
        cert_type (str): the cert type used to find an appropriate signing server
        signing_formats (list): the signing formats used to find an appropriate
            signing server

    Raises:
        SigningServerError: on failure

    """
    token = None
    data = {
        "slave_ip": context.config['my_ip'],
        "duration": context.config["token_duration_seconds"],
    }
    signing_servers = get_suitable_signing_servers(
        context.signing_servers, cert_type,
        signing_formats
    )
    random.shuffle(signing_servers)
    for s in signing_servers:
        log.info("getting token from %s", s.server)
        url = "https://{}/token".format(s.server)
        auth = aiohttp.BasicAuth(s.user, password=s.password)
        try:
            token = await retry_request(context, url, method='post', data=data,
                                        auth=auth, return_type='text')
            if token:
                break
        except ScriptWorkerException:
            traceback.print_exc()
            continue
    else:
        raise SigningServerError("Cannot retrieve signing token")
    with open(output_file, "w") as fh:
        print(token, file=fh, end="")


# sign {{{1
async def sign(context, path, signing_formats):
    """Call the appropriate signing function per format, for a single file.

    Args:
        context (SigningContext): the signing context
        path (str): the source file to sign
        signing_formats (list): the formats to sign with

    Returns:
        list: the list of paths generated. This will be a list of one, unless
            there are detached sigfiles.

    """
    signed_file = path
    # Loop through the formats and sign one by one.
    for fmt in signing_formats:
        func = FORMAT_TO_SIGNING_FUNCTION.get(
            fmt, FORMAT_TO_SIGNING_FUNCTION['default']
        )
        signed_file = await func(context, signed_file, fmt)
#        signed_file, files, should_sign_fn = await _execute_pre_signing_steps(context, signed_file, orig_fmt)
#        for from_ in files:
#            to = from_
#            fmt = orig_fmt
#            # build the base command
#            if should_sign_fn is not None:
#                fmt = should_sign_fn(from_, orig_fmt)
#            if not fmt:
#                continue
#            elif fmt in ("widevine", "widevine_blessed"):
#                to = "{}.sig".format(from_)
#                if to not in files:
#                    files.append(to)
#            else:
#                to = from_
#            log.info("Signing {}...".format(from_))
#            await utils.execute_subprocess(signing_command)
#        log.info('Finished signing {}. Starting post-signing steps...'.format(orig_fmt))
#        signed_file = await _execute_post_signing_steps(context, files, signed_file, orig_fmt)
    if not isinstance(signed_file, (tuple, list)):
        signed_file = [signed_file]
    log_shas(context, signed_file)
    return signed_file


# _sort_formats {{{1
def _sort_formats(formats):
    """Order the signing formats.

    Certain formats need to happen before or after others, e.g. gpg after
    any format that modifies the binary.

    Args:
        formats (list): the formats to order.

    Returns:
        list: the ordered formats.

    """
    for fmt in ("widevine", "widevine_blessed", "gpg"):
        if fmt in formats:
            formats.remove(fmt)
            formats.append(fmt)
    return formats


# build_filelist_dict {{{1
def build_filelist_dict(context, all_signing_formats):
    """Build a dictionary of cot-downloaded paths and formats.

    Scriptworker will pre-download and pre-verify the `upstreamArtifacts`
    in our `work_dir`.  Let's build a dictionary of relative `path` to
    a dictionary of `full_path` and signing `formats`.

    Args:
        context (SigningContext): the signing context
        all_signing_formats (list): the superset of valid signing formats,
            based on the task scopes.  If the file signing formats are not
            a subset, throw an exception.

    Raises:
        TaskVerificationError: if the files don't exist on disk, or the
            file signing formats are not a subset of all_signing_formats.

    Returns:
        dict of dicts: the dictionary of relative `path` to a dictionary with
            `full_path` and a list of signing `formats`.

    """
    filelist_dict = {}
    all_signing_formats_set = set(all_signing_formats)
    messages = []
    for artifact_dict in context.task['payload']['upstreamArtifacts']:
        for path in artifact_dict['paths']:
            full_path = os.path.join(
                context.config['work_dir'], 'cot', artifact_dict['taskId'],
                path
            )
            if not os.path.exists(full_path):
                messages.append("{} doesn't exist!".format(full_path))
            formats_set = set(artifact_dict['formats'])
            if not set(formats_set).issubset(all_signing_formats_set):
                messages.append("{} {} illegal format(s) {}!".format(
                    artifact_dict['taskId'], path,
                    formats_set.difference(all_signing_formats_set)
                ))
            filelist_dict[path] = {
                "full_path": full_path,
                "formats": _sort_formats(artifact_dict['formats']),
            }
    if messages:
        raise TaskVerificationError(messages)
    return filelist_dict
