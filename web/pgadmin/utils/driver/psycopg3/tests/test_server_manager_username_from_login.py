##########################################################################
#
# pgAdmin 4 - PostgreSQL Tools
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""The database username of a server with "Username from login", as the
server manager works it out when connecting.

Only the outer boundaries are faked: the OAuth2 login in the session, the
token the identity provider issues and the psycopg connection. The
username is the one the connection is opened with, and the one the server
manager hands to the query tool and to background utilities."""

import base64
import json
import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from flask import Flask, session
from flask_babel import Babel
from psycopg.conninfo import conninfo_to_dict

import config
import pgadmin.utils.driver.psycopg3.connection as connection_module
from pgadmin.model import Server
from pgadmin.utils import pg_oauth2
from pgadmin.utils.driver.psycopg3 import Driver
from pgadmin.utils.driver.psycopg3.server_manager import ServerManager
from pgadmin.utils.driver.psycopg3.tests.test_connection_oauth import \
    TestOAuthConnection
from pgadmin.utils.route import BaseTestGenerator

PROVIDER = 'idp'
OBO = {'OAUTH2_ENTRA_OBO_ENABLED': True}
UPN = 'ada@example.test'
GUEST = 'guest_example.test#EXT#@tenant.example.test'


def _jwt(claims):
    """An unsigned JWT access token carrying claims."""
    def part(value):
        return base64.urlsafe_b64encode(
            json.dumps(value).encode()).decode().rstrip('=')
    return '{0}.{1}.'.format(part({'alg': 'none'}), part(claims))


class ServerManagerUsernameFromLoginTest(BaseTestGenerator):

    scenarios = [
        ('Entra takes the upn claim', dict(
            auth_method='entra', provider_config=OBO,
            claims={'upn': UPN, 'preferred_username': 'ada',
                    'email': 'ada@mail.example.test'},
            expected=UPN)),
        ('Entra falls back to preferred_username for a guest', dict(
            auth_method='entra', provider_config=OBO,
            claims={'preferred_username': GUEST,
                    'email': 'guest@example.test'},
            expected=GUEST)),
        ('Entra never takes the email claim', dict(
            auth_method='entra', provider_config=OBO,
            claims={'email': 'ada@mail.example.test'},
            error=['upn', 'preferred_username', 'username'],
            not_in_error=['email'])),
        ('Entra ignores OAUTH2_DB_USERNAME_CLAIM', dict(
            auth_method='entra',
            provider_config=dict(OBO, OAUTH2_DB_USERNAME_CLAIM='db_role'),
            claims={'upn': UPN, 'db_role': 'role'},
            expected=UPN)),
        ('OAuth direct takes upn first', dict(
            auth_method='oauth_direct', provider_config={},
            claims={'upn': UPN, 'preferred_username': 'ada',
                    'email': 'ada@mail.example.test'},
            expected=UPN)),
        ('OAuth direct then takes preferred_username', dict(
            auth_method='oauth_direct', provider_config={},
            claims={'preferred_username': 'ada',
                    'email': 'ada@mail.example.test'},
            expected='ada')),
        ('OAuth exchange then takes email', dict(
            auth_method='oauth_exchange', provider_config={},
            claims={'email': 'ada@mail.example.test', 'sub': '1234'},
            expected='ada@mail.example.test')),
        ('OAUTH2_DB_USERNAME_CLAIM chooses the claim', dict(
            auth_method='oauth_direct',
            provider_config={'OAUTH2_DB_USERNAME_CLAIM': 'db_role'},
            claims={'upn': UPN, 'db_role': 'analyst'},
            expected='analyst')),
        ('A missing OAUTH2_DB_USERNAME_CLAIM is named', dict(
            auth_method='oauth_exchange',
            provider_config={'OAUTH2_DB_USERNAME_CLAIM': 'db_role'},
            claims={'upn': UPN},
            error=['db_role', 'username'], not_in_error=['upn'])),
        ('No claim at all names the default order', dict(
            auth_method='oauth_direct', provider_config={},
            claims={'sub': '1234'},
            error=['upn', 'preferred_username', 'email', 'username'])),
        ('The access token claims are never used', dict(
            auth_method='oauth_direct', provider_config={},
            claims=None, access_token_claims={'upn': UPN},
            error=['upn', 'username'])),
        ('A login through another auth source has no claims', dict(
            auth_method='oauth_direct', provider_config={},
            claims={'upn': UPN}, oauth2_login=False,
            error=['upn', 'username'])),
        ('Entra without On-Behalf-Of gives the availability error', dict(
            auth_method='entra', provider_config={},
            claims={'upn': UPN},
            error=['OAUTH2_ENTRA_OBO_ENABLED'])),
        ('Entra after a login through another auth source', dict(
            auth_method='entra', provider_config=OBO,
            claims={'upn': UPN}, oauth2_login=False,
            error=['OAUTH2_ENTRA_OBO_ENABLED'])),
        ('A username set explicitly wins', dict(
            auth_method='entra', provider_config=OBO,
            claims={'upn': UPN}, username='entra-group',
            expected='entra-group')),
        ('An explicit username needs no claim', dict(
            auth_method='oauth_direct', provider_config={},
            claims={}, username='database-user',
            expected='database-user')),
        ('Off, no username comes from the login', dict(
            auth_method='oauth_direct', provider_config={},
            claims={'upn': UPN}, username_from_login=False,
            expected=None)),
        ('Ignored for password', dict(
            auth_method='password', provider_config={},
            claims={'upn': UPN}, expected=None)),
    ]

    username = None
    username_from_login = True
    oauth2_login = True
    access_token_claims = {}
    expected = None
    error = None
    not_in_error = ()

    def setUp(self):
        # These tests fake the database connection.
        unittest.TestCase.setUp(self)
        self.app = Flask(__name__)
        self.app.config.update(SECRET_KEY='unit-test', TESTING=True,
                               SERVER_MODE=True)
        Babel(self.app)

    def _server(self):
        return Server(
            id=7, user_id=1, servergroup_id=1, name='login-username',
            host='database.example.test', port=5432,
            maintenance_db='postgres', username=self.username,
            shared=False, kerberos_conn=False,
            auth_method=self.auth_method,
            username_from_login=self.username_from_login,
            connection_params={'sslmode': 'verify-full'},
        )

    def _login(self):
        if not self.oauth2_login:
            return
        session['oauth2_provider'] = PROVIDER
        token = {'access_token': _jwt(self.access_token_claims),
                 'token_type': 'Bearer'}
        if self.claims is not None:
            token['userinfo'] = dict(self.claims)
        session['oauth2_token'] = token

    def runTest(self):
        server = self._server()
        source = MagicMock()
        source.oauth2_config = {PROVIDER: self.provider_config}
        seen = {}

        def connect(conninfo, **kwargs):
            seen['conninfo'] = conninfo_to_dict(conninfo)
            pg = TestOAuthConnection._make_psycopg_connection()
            pg.info.backend_pid = 23456
            return pg

        with self.app.test_request_context('/'), ExitStack() as stack:
            stack.enter_context(patch.object(config, 'SERVER_MODE', True))
            stack.enter_context(patch(
                'pgadmin.authenticate.get_auth_sources',
                return_value=source))
            # The identity provider issues the database token.
            stack.enter_context(patch.object(
                pg_oauth2, 'get_entra_obo_token', return_value='obo'))
            stack.enter_context(patch.object(
                pg_oauth2, 'get_postgres_oauth_token',
                return_value='oauth'))
            stack.enter_context(patch.object(pg_oauth2,
                                             'install_oauth_hook'))
            TestOAuthConnection._apply_common_patches(stack)
            stack.enter_context(patch.object(
                connection_module.psycopg.Connection, 'connect',
                side_effect=connect))
            self._login()

            manager = ServerManager(server)
            connection = TestOAuthConnection._make_connection(manager)
            connection._decrypt_password = MagicMock(
                return_value=(True, '', None))
            status, message = connection.connect()
            utility_user = manager.user
            stale = Driver._manager_is_stale(manager, server)

        # The resolved username is never saved.
        self.assertEqual(server.username, self.username)

        if self.error:
            self.assertFalse(status)
            self.assertNotIn('conninfo', seen)
            for text in self.error:
                self.assertIn(text, message)
            for text in self.not_in_error:
                self.assertNotIn(text, message)
            self.assertIsNone(utility_user)
            return

        self.assertTrue(status, message)
        self.assertEqual(seen['conninfo'].get('user'), self.expected)
        # The query tool and background utilities connect as the same role.
        self.assertEqual(utility_user, self.expected)
        # A username from the login does not make the manager look like
        # it belongs to another server, which would drop its connections.
        self.assertFalse(stale)
