#-------------------------------------------------------------------------
# 
# Copyright Microsoft Open Technologies, Inc.
#
# All Rights Reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http: *www.apache.org/licenses/LICENSE-2.0
#
# THIS CODE IS PROVIDED *AS IS* BASIS, WITHOUT WARRANTIES OR CONDITIONS
# OF ANY KIND, EITHER EXPRESS OR IMPLIED, INCLUDING WITHOUT LIMITATION
# ANY IMPLIED WARRANTIES OR CONDITIONS OF TITLE, FITNESS FOR A
# PARTICULAR PURPOSE, MERCHANTABILITY OR NON-INFRINGEMENT.
#
# See the Apache License, Version 2.0 for the specific language
# governing permissions and limitations under the License.
#
#--------------------------------------------------------------------------

import requests
import re

from . import util
from . import log
from . import argument

from .constants import HttpError

AUTHORIZATION_URI = 'authorization_uri'
RESOURCE = 'resource'
WWW_AUTHENTICATE_HEADER = 'www-authenticate'


class AuthenticationParameters(object):

    def __init__(self, authorization_uri, resource):

        self._authorization_uri = authorization_uri
        self._resource = resource

    @property
    def authorization_uri(self):
        return self._authorization_uri

    @property
    def resource(self):
        return self._resource


# The 401 challenge is a standard defined in RFC6750, which is based in part on RFC2617.
# The challenge has the following form.
# WWW-Authenticate : Bearer authorization_uri="https://login.windows.net/mytenant.com/oauth2/authorize",Resource_id="00000002-0000-0000-c000-000000000000"

# This regex is used to validate the structure of the challenge header.
# Match whole structure: ^\s*Bearer\s+([^,\s="]+?)="([^"]*?)"\s*(,\s*([^,\s="]+?)="([^"]*?)"\s*)*$
# ^                        Start at the beginning of the string.
# \s*Bearer\s+             Match 'Bearer' surrounded by one or more amount of whitespace.
# ([^,\s="]+?)             This captures the key which is composed of any characters except comma, whitespace or a quotes.
# =                        Match the = sign.
# "([^"]*?)"               Captures the value can be any number of non quote characters.  At this point only the first key value pair as been captured.
# \s*                      There can be any amount of white space after the first key value pair.
# (                        Start a capture group to retrieve the rest of the key value pairs that are separated by commas.
#    \s*                   There can be any amount of whitespace before the comma.
#    ,                     There must be a comma.
#    \s*                   There can be any amount of whitespace after the comma.
#    (([^,\s="]+?)         This will capture the key that comes after the comma.  It's made of a series of any character except comma, whitespace or quotes.
#    =                     Match the equal sign between the key and value.
#    "                     Match the opening quote of the value.
#    ([^"]*?)              This will capture the value which can be any number of non quote characters.
#    "                     Match the values closing quote.
#    \s*                   There can be any amount of whitespace before the next comma.
# )*                       Close the capture group for key value pairs.  There can be any number of these.
# $                      The rest of the string can be whitespace but nothing else up to the end of the string.
#
#
# In other some other languages the regex above would be all that was needed. However, in JavaScript the RegExp object does not
# return all of the captures in one go.  So the regex above needs to be broken up so that captures can be retrieved
# iteratively.
#

def parse_challenge(challenge):

    # This regex checks the structure of the whole challenge header.  The complete
    # header needs to be checked for validity before we can be certain that
    # we will succeed in pulling out the individual parts.
    bearer_challenge_structure_validation = re.compile("""^\s*Bearer\s+([^,\s="]+?)="([^"]*?)"\s*(,\s*([^,\s="]+?)="([^"]*?)"\s*)*$""")

    # This regex pulls out the key and value from the very first pair.
    first_key_value_pair_regex = re.compile( """^\s*Bearer\s+([^,\s="]+?)="([^"]*?)"\s*""")

    # This regex is used to pull out all of the key value pairs after the first one.
    # All of these begin with a comma.
    all_other_key_value_pair_regex = re.compile("""(?:,\s*([^,\s="]+?)="([^"]*?)"\s*)""")

    if not bearer_challenge_structure_validation.search(challenge):
        raise ValueError("The challenge is not parseable as an RFC6750 OAuth2 challenge")

    challenge_parameters = {}
    match = first_key_value_pair_regex.search(challenge)
    if match:
        challenge_parameters[match.group(1)] = match.group(2)

    for match in all_other_key_value_pair_regex.finditer(challenge):
        challenge_parameters[match.group(1)] = match.group(2)

    return challenge_parameters

def create_authentication_parameters_from_header(challenge):

    argument.validate_string_param(challenge, 'challenge')

    challenge_parameters = parse_challenge(challenge)
    authorization_uri = challenge_parameters.get(AUTHORIZATION_URI)

    if not authorization_uri:
        raise ValueError("Could not find 'authorization_uri' in challenge header.")

    resource = challenge_parameters.get(RESOURCE)
    return AuthenticationParameters(authorization_uri, resource)

def create_authentication_parameters_from_response(response):

    if not response:
        raise AttributeError('Missing required parameter: response')

    if not hasattr(response, 'status_code') or not response.status_code:
        raise AttributeError('The response parameter does not have the expected HTTP status_code field')

    if not hasattr(response, 'headers') or not response.headers:
        raise AttributeError('There were no headers found in the response.')

    if response.status_code != HttpError.UNAUTHORIZED:
        raise ValueError('The response status code does not correspond to an OAuth challenge.  ' +
      'The statusCode is expected to be 401 but is: {0}'.format(response.status_code))

    challenge = response.headers.get(WWW_AUTHENTICATE_HEADER)
    if not challenge:
        raise ValueError("The response does not contain a WWW-Authenticate header that can be "
                         "used to determine the authority_uri and resource.")

    return create_authentication_parameters_from_header(challenge)

def validate_url_object(url):
    if not url or not hasattr(url, 'geturl'):
        raise AttributeError('Parameter is of wrong type: url')

def create_authentication_parameters_from_url(url, callback, correlation_id):

    argument.validate_callback_type(callback)
    try:
        if isinstance(url, str):
            challenge_url = url
        else:
            validate_url_object(url)
            challenge_url = url.get_url()

        log_context = log.create_log_context(correlation_id)
        logger = log.Logger('AuthenticationParameters', log_context)

        logger.debug("Attempting to retrieve authentication parameters from: {0}".format(challenge_url))

        class _options(object):
            _call_context = { 'log_context': log_context }

        options = util.create_request_options(_options())
        try:
            response = requests.get(challenge_url, headers=options['headers'])
        except Exception as exp:
            logger.error("Authentication parameters http get failed.", exp)
            callback(exp, None)
            return

        try:
            parameters = create_authentication_parameters_from_response(response)
        except Exception as exp:
            logger.error("Unable to parse response in to authentication parameters.", exp)
            callback(exp, None)
            return

        callback(None, parameters)

    except Exception as exp:
        callback(exp, None)
