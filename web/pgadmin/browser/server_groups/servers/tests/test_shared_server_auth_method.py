##########################################################################
#
# pgAdmin 4 - PostgreSQL Tools
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""A non-owner of a shared server follows the owner's server
authentication method until they choose one of their own, which then
sticks."""

import json
import sqlite3
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import config
from pgadmin.browser.server_groups import servers as servers_module
from pgadmin.utils.route import BaseTestGenerator
from regression.python_test_utils import test_utils as utils
from regression.python_test_utils.test_utils import \
    create_user_wise_test_client
from regression.test_setup import config_data


METHODS = ('password', 'oauth_direct', 'oauth_exchange', 'entra')

test_user_details = None
if config.SERVER_MODE:
    test_user_details = \
        config_data['pgAdmin4_test_non_admin_credentials']


def owner_server(auth_method, **kwargs):
    """The owner's shared server, as a detached model object."""
    values = dict(
        id=1,
        user_id=1,
        name='OAuth shared server',
        host='database.example.test',
        port=5432,
        maintenance_db='postgres',
        shared=True,
        shared_username='database-user',
        auth_method=auth_method,
        connection_params={
            'oauth_client_id': 'postgres-cluster',
            'oauth_issuer': 'https://identity.example.test',
            'sslmode': 'verify-full',
        },
    )
    values.update(kwargs)
    return servers_module.Server(**values)


def create_shared_server(test, owner):
    """The non-owner's shared server, as it is created the first time
    they open the owner's server."""
    with patch.object(servers_module, 'db') as database, \
            patch.object(servers_module, 'User') as user_model, \
            patch.object(servers_module, 'current_user',
                         SimpleNamespace(id=2)):
        user_model.query.filter_by.return_value.first.return_value = (
            SimpleNamespace(username='server-owner')
        )

        servers_module.ServerModule.create_shared_server(owner, 1)

        database.session.add.assert_called_once()
        database.session.commit.assert_called_once_with()
        shared = database.session.add.call_args.args[0]

    test.assertIsInstance(shared, servers_module.SharedServer)
    test.assertEqual(shared.user_id, 2)
    test.assertEqual(shared.osid, owner.id)
    return shared


class SharedServerAuthMethodTest(BaseTestGenerator):
    scenarios = [
        ('New non-owner follows the owner on ' + method, {
            'operation': 'create',
            'owner_method': method,
            'user_method': None,
            'expected': method,
        })
        for method in METHODS
    ] + [
        ('Non-owner follows the owner changing to ' + method, {
            'operation': 'owner_changes',
            'owner_method': 'password',
            'changed_method': method,
            'user_method': None,
            'expected': method,
        })
        for method in METHODS
    ] + [
        ('Owner {0}, non-owner chose {1}'.format(owner_method, user_method), {
            'operation': 'merge',
            'owner_method': owner_method,
            'user_method': user_method,
            'expected': user_method,
        })
        for owner_method, user_method in (
            # An existing row that stores password keeps it.
            ('entra', 'password'),
            ('oauth_direct', 'password'),
            ('oauth_exchange', 'password'),
            ('password', 'oauth_direct'),
            ('password', 'entra'),
            ('oauth_direct', 'oauth_exchange'),
            ('entra', 'oauth_direct'),
        )
    ]

    def setUp(self):
        # Bypass the PostgreSQL connection setup.
        # Use real, detached model objects and mock only persistence.
        unittest.TestCase.setUp(self)

    def runTest(self):
        owner = owner_server(self.owner_method)
        owner_params = owner.connection_params
        owner_snapshot = dict(owner_params)

        if self.operation in ('create', 'owner_changes'):
            shared = create_shared_server(self, owner)
        else:
            shared = servers_module.SharedServer(
                osid=owner.id,
                user_id=2,
                auth_method=self.user_method,
                connection_params={},
            )
        if self.operation == 'owner_changes':
            owner.auth_method = self.changed_method

        result = servers_module.ServerModule.get_shared_server_properties(
            owner, shared,
        )

        self.assertEqual(result.auth_method, self.expected)
        # Following the owner stores nothing of the non-owner's own.
        self.assertEqual(shared.auth_method, self.user_method)

        # The OAuth parameters are ordinary connection parameters and are
        # still shared with the non-owner.
        self.assertEqual(result.connection_params, owner_snapshot)
        self.assertIsNot(result.connection_params, owner_params)
        self.assertEqual(owner_params, owner_snapshot)


class NonOwnerApiMixin:
    """The servers API as seen by a non-owner of a shared server, in
    server mode.

    The tester's server is handed to another pgAdmin user, so that the
    tester is a non-owner of it."""

    owner_server = {}

    def setUp(self):
        self.server_id = None
        if not config.SERVER_MODE:
            self.skipTest('Shared servers need a server-mode run.')
        self.url = '/browser/server/obj/{0}/'.format(utils.SERVER_GROUP)
        payload = {
            'name': 'shared-probe',
            'host': 'database.example.test',
            'port': 5432,
            'db': 'postgres',
            'username': 'owner',
            'role': None,
            'connect_now': False,
            'shared': True,
            'shared_username': 'shared-user',
            'connection_params': [],
        }
        payload.update(self.owner_server)
        response = self.tester.post(
            self.url, data=json.dumps(payload), content_type='html/json')
        self.assertEqual(response.status_code, 200, response.data)
        self.server_id = json.loads(
            response.data.decode('utf-8'))['node']['_id']
        self._sql('SELECT user_id FROM server WHERE id=?')
        self.tester_id = self.rows[0][0]
        owner_id = utils.create_user({
            'login_username': 'shared-owner@example.test',
            'login_password': 'not-used'})
        self._sql('UPDATE server SET user_id=? WHERE id=?', owner_id)

    def _sql(self, statement, *args):
        conn = sqlite3.connect(config.TEST_SQLITE_PATH)
        try:
            self.rows = conn.execute(
                statement, args + (self.server_id,)).fetchall()
            conn.commit()
        finally:
            conn.close()

    def owner_update(self, **columns):
        """Change the owner's server, as the owner would."""
        for column, value in columns.items():
            self._sql('UPDATE server SET {0}=? WHERE id=?'.format(column),
                      value)

    def put(self, data):
        return self.tester.put(
            self.url + str(self.server_id),
            data=json.dumps(dict(data, id=self.server_id)),
            content_type='html/json')

    def properties(self):
        response = self.tester.get(self.url + str(self.server_id))
        self.assertEqual(response.status_code, 200, response.data)
        return json.loads(response.data.decode('utf-8'))

    def tearDown(self):
        if self.server_id is None:
            return
        self._sql('DELETE FROM sharedserver WHERE osid=?')
        self._sql('UPDATE server SET user_id=? WHERE id=?', self.tester_id)
        utils.delete_server_with_api(self.tester, self.server_id)


class SharedServerAuthMethodApiTest(NonOwnerApiMixin, BaseTestGenerator):
    """A non-owner follows the owner's method through the servers API
    until they choose their own."""

    owner_server = {'auth_method': 'oauth_direct'}

    scenarios = [
        ('Non-owner sees the owner method', dict(
            update=None, expected_status=200,
            expected_method='oauth_direct', owner_changes_to='oauth_exchange',
            expected_after='oauth_exchange')),
        ('Non-owner chooses their own method, which sticks', dict(
            update={'auth_method': 'password'}, expected_status=200,
            expected_method='password', owner_changes_to='oauth_exchange',
            expected_after='password')),
        ('Kerberos is refused with the followed token method', dict(
            update={'kerberos_conn': True}, expected_status=400,
            expected_method='oauth_direct', owner_changes_to=None,
            expected_after='oauth_direct')),
    ]

    def runTest(self):
        if self.update is not None:
            response = self.put(self.update)
            self.assertEqual(response.status_code, self.expected_status,
                             response.data)
        self.assertEqual(self.properties()['auth_method'],
                         self.expected_method)
        if self.owner_changes_to:
            self.owner_update(auth_method=self.owner_changes_to)
        self.assertEqual(self.properties()['auth_method'],
                         self.expected_after)
