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

from .constants import Jwt
from .log import Logger

from . import util
import time
import datetime
import uuid
import jws
import base64
import re


class SelfSignedJwt(object):

    NumCharIn128BitHexString = 128/8*2
    numCharIn160BitHexString = 160/8*2
    ThumbprintRegEx = "^[a-f\d]*$"

    def __init__(self, call_context, authority, client_id):
        self._log = Logger('SelfSignedJwt', call_context['log_context'])
        self._call_context = call_context

        self._authortiy = authority
        self._token_endpoint = authority.token_endpoint
        self._client_id = client_id

    def _get_date_now(self):
        return datetime.datetime.now()

    def _get_new_jwt_id(self):
        return uuid.uuid4()

    def _create_x5t_value(self, thumbprint):
        hex_str = thumbprint.replace(':', '').replace(' ', '')
        b64_str = base64.b64encode(hex_str)
        return util.convert_regular_to_urlsafe_b64encoded_string(b64_str)

    def _create_header(self, thumbprint):
        x5t = self._create_x5t_value(thumbprint)
        header = {'typ':'JWT', 'alg':'RS256', 'x5t':x5t}

        self._log.debug("Creating self signed JWT header. x5t: {0}".format(x5t))

        return header

    def _create_payload(self):

        now = self._get_date_now()
        minutes = datetime.timedelta(0,0,0,0,Jwt.SELF_SIGNED_JWT_LIFETIME)
        expires = now + minutes

        self._log.debug('Creating self signed JWT payload. Expires: {0} NotBefore: {1}'.format(expires, now))

        jwt_payload = {}
        jwt_payload[Jwt.AUDIENCE] = self._token_endpoint
        jwt_payload[Jwt.ISSUER] = self._client_id
        jwt_payload[Jwt.SUBJECT] = self._client_id
        jwt_payload[Jwt.NOT_BEFORE] = int(time.mktime(now.timetuple()))
        jwt_payload[Jwt.EXPIRES_ON] = int(time.mktime(expires.timetuple()))
        jwt_payload[Jwt.JWT_ID] = self._get_new_jwt_id()

        return jwt_payload

    def _raise_on_invalid_jwt_signature(self, jwt):

        segments = jwt.split('.')
        if len(seqments) < 3 or not segments[2]:
            raise self._log.create_error('Failed to sign JWT. This is most likely due to an invalid certificate.')

    def _raise_on_invalid_thumbprint(self, thumbprint):

        thumbprint_sizes = [self.NumCharIn128BitHexString, self.numCharIn160BitHexString]
        if len(thumbprint) not in thumbprint_sizes or not re.search(self.ThumbprintRegEx, thumbprint):
            raise self._log.create_error("The thumbprint does not match a known format")

    def _sign_jwt(self, header, payload, certificate):

        jwt = jws.sign(header, payload, certificate)
        self._raise_on_invalid_jwt_signature(jwt)
        return jwt

    def _reduce_thumbprint(self, thumbprint):

        canonical = thumbprint.lower().replace(' ', '').replace(':', '')
        self._raise_on_invalid_thumbprint(canonical)
        return canonical

    def create(certificate, thumbprint):

        thumbprint = self._reduce_thumbprint(thumbprint)
        header = self._create_header(thumbprint)
        payload = self._create_payload()
        jwt = self._sign_jwt(header, payload, certificate)
        return jwt