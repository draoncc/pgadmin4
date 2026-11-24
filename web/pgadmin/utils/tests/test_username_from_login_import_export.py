##########################################################################
#
# pgAdmin 4 - PostgreSQL Tools
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL License
#
##########################################################################

"""servers.json carries "Username from login" as UsernameFromLogin. A
server that sets it needs no Username or SharedUsername, it is refused
with the password method, and an export loads back in unchanged."""

import io
import json
from contextlib import redirect_stdout
from unittest.mock import patch

import config

from pgadmin.utils.route import BaseTestGenerator
from pgadmin.utils.tests.test_passexec_import_export import \
    _ImportExportMixin, GROUP

ENTRA_SHARED = {
    'Name': 'Azure PostgreSQL',
    'Host': 'example.postgres.database.azure.com',
    'Port': 5432,
    'MaintenanceDB': 'postgres',
    'Shared': True,
    'AuthMethod': 'entra',
    'UsernameFromLogin': True,
    'ConnectionParameters': {'sslmode': 'verify-full'},
}


class _UsernameFromLoginMixin(_ImportExportMixin):

    def _write(self, servers):
        """Write servers, given in full, to the servers.json file."""
        with open(self.path, 'w') as f:
            json.dump({'Servers': {
                s['Name']: dict({'Group': GROUP}, **s)
                for s in servers}}, f)

    def _load_file(self):
        from pgadmin.utils import load_database_servers
        out = io.StringIO()
        with redirect_stdout(out):
            ok, _ = load_database_servers(
                self.path, None, self.user, from_setup=True)
        self.assertTrue(ok, out.getvalue())


class TestUsernameFromLoginImport(_UsernameFromLoginMixin,
                                  BaseTestGenerator):
    """A server with UsernameFromLogin loads without a username."""

    def runTest(self):
        self._write([
            ENTRA_SHARED,
            {'Name': 'private', 'Host': 'db.example.com', 'Port': 5432,
             'MaintenanceDB': 'postgres', 'AuthMethod': 'oauth_direct',
             'UsernameFromLogin': True},
            {'Name': 'group-role', 'Host': 'db.example.com', 'Port': 5432,
             'MaintenanceDB': 'postgres', 'AuthMethod': 'oauth_exchange',
             'UsernameFromLogin': True, 'Username': 'group-role'},
            {'Name': 'off', 'Host': 'db.example.com', 'Port': 5432,
             'MaintenanceDB': 'postgres', 'AuthMethod': 'oauth_direct',
             'Username': 'test_user'},
        ])

        self._load_file()

        shared = self._loaded('Azure PostgreSQL')
        self.assertTrue(shared.shared)
        self.assertTrue(shared.username_from_login)
        self.assertIsNone(shared.username)
        self.assertIsNone(shared.shared_username)
        private = self._loaded('private')
        self.assertTrue(private.username_from_login)
        self.assertIsNone(private.username)
        self.assertEqual(self._loaded('group-role').username, 'group-role')
        self.assertFalse(self._loaded('off').username_from_login)


class TestUsernameFromLoginImportRefused(_UsernameFromLoginMixin,
                                         BaseTestGenerator):
    """A file that cannot work is refused as a whole, naming the
    server."""

    scenarios = [
        ('With the password method', dict(
            bad={'AuthMethod': 'password', 'UsernameFromLogin': True},
            expect='Username from login')),
        ('Without a method', dict(
            bad={'UsernameFromLogin': True},
            expect='Username from login')),
        ('Not a boolean', dict(
            bad={'AuthMethod': 'oauth_direct', 'UsernameFromLogin': 'yes'},
            expect='UsernameFromLogin')),
        ('Off and without a username', dict(
            bad={'AuthMethod': 'oauth_direct', 'UsernameFromLogin': False},
            expect='Username')),
        ('Outside server mode', dict(
            bad={'AuthMethod': 'oauth_direct', 'UsernameFromLogin': True},
            server_mode=False, expect='server mode')),
    ]
    server_mode = True

    def runTest(self):
        from pgadmin.model import Server, ServerGroup
        from pgadmin.utils import load_database_servers

        base = {'Host': 'db.example.com', 'Port': 5432,
                'MaintenanceDB': 'postgres'}
        self._write([dict(base, Name='good', Username='test_user'),
                     dict(base, Name='bad', **self.bad)])

        # The setup.py path prints the error and exits.
        out = io.StringIO()
        with redirect_stdout(out), self.assertRaises(SystemExit), \
                patch.object(config, 'SERVER_MODE', self.server_mode):
            load_database_servers(
                self.path, None, self.user, from_setup=True)

        self.assertIn(self.expect, out.getvalue())
        self.assertIn("'bad'", out.getvalue())
        group = ServerGroup.query.filter_by(
            user_id=self.user.id, name=GROUP).first()
        self.assertTrue(group is None or Server.query.filter_by(
            servergroup_id=group.id).count() == 0)


class TestUsernameFromLoginExport(_UsernameFromLoginMixin,
                                  BaseTestGenerator):
    """The export writes UsernameFromLogin when it is on and leaves out
    the empty usernames, so that it loads back in unchanged."""

    def runTest(self):
        self._write([ENTRA_SHARED])
        self._load_file()
        self._add_server('off', auth_method='oauth_direct',
                         username_from_login=False)

        dumped = self._dump()
        exported = dumped['Azure PostgreSQL']

        self.assertEqual({k: exported.get(k) for k in ENTRA_SHARED},
                         ENTRA_SHARED)
        self.assertNotIn('Username', exported)
        self.assertNotIn('SharedUsername', exported)
        self.assertNotIn('UsernameFromLogin', dumped['off'])

        self._cleanup()
        self._write([exported])
        self._load_file()
        self.assertEqual(self._dump()['Azure PostgreSQL'], exported)


class TestUsernameFromLoginRoundTrip(_UsernameFromLoginMixin,
                                     BaseTestGenerator):
    """Servers exported and imported again are unchanged, for the owner
    and for a non-owner who follows the owner's method and "Username from
    login" (both NULL on their shared server)."""

    SERVERS = [
        ENTRA_SHARED,
        {'Name': 'shared-password', 'Host': 'db.example.com', 'Port': 5432,
         'MaintenanceDB': 'postgres', 'Shared': True,
         'AuthMethod': 'password', 'Username': 'owner',
         'SharedUsername': 'shared-user'},
        {'Name': 'shared-token', 'Host': 'db.example.com', 'Port': 5432,
         'MaintenanceDB': 'postgres', 'Shared': True,
         'AuthMethod': 'oauth_direct', 'Username': 'owner',
         'SharedUsername': 'group-role', 'UsernameFromLogin': True},
        {'Name': 'private', 'Host': 'db.example.com', 'Port': 5432,
         'MaintenanceDB': 'postgres', 'AuthMethod': 'oauth_exchange',
         'UsernameFromLogin': True},
        {'Name': 'shared-owner-username', 'Host': 'db.example.com',
         'Port': 5432, 'MaintenanceDB': 'postgres', 'Shared': True,
         'AuthMethod': 'entra', 'Username': 'owner@example.test',
         'UsernameFromLogin': True,
         'ConnectionParameters': {'sslmode': 'verify-full'}},
    ]

    def _views(self):
        """What the owner and a following non-owner connect with."""
        from pgadmin.browser.server_groups.servers import ServerModule
        from pgadmin.model import SharedServer
        views = {}
        for spec in self.SERVERS:
            owner = self._loaded(spec['Name'])
            view = [owner.auth_method, bool(owner.username_from_login),
                    owner.username]
            if owner.shared:
                following = SharedServer(
                    osid=owner.id, user_id=owner.user_id + 1000,
                    auth_method=None, username_from_login=None,
                    username=None, connection_params={})
                merged = ServerModule.get_shared_server_properties(
                    owner, following)
                view += [merged.auth_method, merged.username_from_login,
                         merged.username]
            views[spec['Name']] = view
        return views

    def runTest(self):
        self._write(self.SERVERS)
        self._load_file()
        exported = self._dump()
        before = self._views()

        self._cleanup()
        self._write(exported.values())
        self._load_file()

        self.assertEqual(self._dump(), exported)
        self.assertEqual(self._views(), before)
        self.assertEqual(before['Azure PostgreSQL'],
                         ['entra', True, None, 'entra', True, None])
        self.assertEqual(before['shared-password'],
                         ['password', False, 'owner',
                          'password', False, 'shared-user'])
        # The owner's own username is not a shared username: a non-owner
        # still takes theirs from the login.
        self.assertEqual(before['shared-owner-username'],
                         ['entra', True, 'owner@example.test',
                          'entra', True, None])
