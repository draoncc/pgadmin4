##########################################################################
#
# pgAdmin 4 - PostgreSQL Tools
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pgadmin.utils.route import BaseTestGenerator
from pgadmin.authenticate import oauth2


class Oauth2DbUsernameClaimConfigTestCase(BaseTestGenerator):
    """pgAdmin warns at startup about an Entra On-Behalf-Of provider that
    sets OAUTH2_DB_USERNAME_CLAIM, which entra servers ignore."""

    scenarios = [
        ('On-Behalf-Of provider with the claim warns', dict(
            providers=[{'OAUTH2_NAME': 'entra',
                        'OAUTH2_ENTRA_OBO_ENABLED': True,
                        'OAUTH2_DB_USERNAME_CLAIM': 'upn'}],
            expected=['entra'])),
        ('Provider without On-Behalf-Of stays quiet', dict(
            providers=[{'OAUTH2_NAME': 'keycloak',
                        'OAUTH2_DB_USERNAME_CLAIM': 'preferred_username'}],
            expected=[])),
        ('On-Behalf-Of provider without the claim stays quiet', dict(
            providers=[{'OAUTH2_NAME': 'entra',
                        'OAUTH2_ENTRA_OBO_ENABLED': True}],
            expected=[])),
        ('Only the On-Behalf-Of providers are named', dict(
            providers=[{'OAUTH2_NAME': 'keycloak',
                        'OAUTH2_DB_USERNAME_CLAIM': 'preferred_username'},
                       {'OAUTH2_NAME': 'entra',
                        'OAUTH2_ENTRA_OBO_ENABLED': True,
                        'OAUTH2_DB_USERNAME_CLAIM': 'email'},
                       {'OAUTH2_NAME': 'entra-two',
                        'OAUTH2_ENTRA_OBO_ENABLED': True,
                        'OAUTH2_DB_USERNAME_CLAIM': 'upn'}],
            expected=['entra', 'entra-two'])),
    ]

    def setUp(self):
        # No PostgreSQL server is needed.
        unittest.TestCase.setUp(self)

    def runTest(self):
        app = MagicMock()
        fake_config = SimpleNamespace(OAUTH2_CONFIG=self.providers)

        with patch.object(oauth2, 'config', fake_config):
            oauth2.warn_on_ignored_db_username_claim(app)

        messages = [call.args[0] % call.args[1:]
                    for call in app.logger.warning.call_args_list]
        self.assertEqual(len(messages), len(self.expected))
        for message, provider in zip(messages, self.expected):
            self.assertIn(provider, message)
            self.assertIn('OAUTH2_DB_USERNAME_CLAIM', message)
