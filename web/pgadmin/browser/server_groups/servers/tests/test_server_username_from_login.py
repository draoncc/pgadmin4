##########################################################################
#
# pgAdmin 4 - PostgreSQL Tools
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""The "Username from login" setting through the servers API: what an
owner and a non-owner can store, and what they see."""

import json
import unittest

import config
from pgadmin.utils.route import BaseTestGenerator
from regression.python_test_utils import test_utils as utils
from .test_shared_server_auth_method import NonOwnerApiMixin, \
    create_shared_server, owner_server


class OwnerUsernameFromLoginTestCase(BaseTestGenerator):
    """An owner creates and updates a server with the setting."""

    scenarios = [
        ('Stored with a token method and no username', dict(
            create={'auth_method': 'oauth_direct',
                    'username_from_login': True, 'username': ''},
            expected_create=200, expected=True, expected_username=None)),
        ('Off by default', dict(
            create={'auth_method': 'oauth_direct'},
            expected_create=200, expected=False,
            expected_username='database-user')),
        ('Refused with password', dict(
            create={'auth_method': 'password',
                    'username_from_login': True},
            expected_create=400)),
        ('Refused without a method', dict(
            create={'username_from_login': True},
            expected_create=400)),
        ('Turned on with a token method in the same update', dict(
            create={'auth_method': 'password'}, expected_create=200,
            update={'auth_method': 'oauth_exchange',
                    'username_from_login': True},
            expected_update=200, expected=True,
            expected_username='database-user')),
        ('Refused when turned on for a password server', dict(
            create={'auth_method': 'password'}, expected_create=200,
            update={'username_from_login': True},
            expected_update=400, expected=False,
            expected_username='database-user')),
        ('Refused when the method changes to password', dict(
            create={'auth_method': 'oauth_direct',
                    'username_from_login': True},
            expected_create=200,
            update={'auth_method': 'password'},
            expected_update=400, expected=True,
            expected_username='database-user')),
        ('Turned off with the change to password', dict(
            create={'auth_method': 'oauth_direct',
                    'username_from_login': True},
            expected_create=200,
            update={'auth_method': 'password',
                    'username_from_login': False},
            expected_update=200, expected=False,
            expected_username='database-user')),
    ]
    update = None

    def setUp(self):
        # The server is saved without connecting to it, so no PostgreSQL
        # server is needed.
        unittest.TestCase.setUp(self)
        self.server_id = None
        self.url = '/browser/server/obj/{0}/'.format(utils.SERVER_GROUP)

    def runTest(self):
        payload = {
            'name': 'username-from-login-probe',
            'host': 'database.example.test',
            'port': 5432,
            'db': 'postgres',
            'username': 'database-user',
            'role': None,
            'connect_now': False,
            'connection_params': [],
        }
        payload.update(self.create)
        response = self.tester.post(
            self.url, data=json.dumps(payload), content_type='html/json')
        self.assertEqual(response.status_code, self.expected_create,
                         response.data)
        if self.expected_create != 200:
            self.assertIn('Username from login',
                          json.loads(response.data)['errormsg'])
            return
        self.server_id = json.loads(
            response.data.decode('utf-8'))['node']['_id']

        if self.update is not None:
            response = self.tester.put(
                self.url + str(self.server_id),
                data=json.dumps(dict(self.update, id=self.server_id)),
                content_type='html/json')
            self.assertEqual(response.status_code, self.expected_update,
                             response.data)
            if self.expected_update != 200:
                self.assertIn('Username from login',
                              json.loads(response.data)['errormsg'])

        response = self.tester.get(self.url + str(self.server_id))
        self.assertEqual(response.status_code, 200, response.data)
        properties = json.loads(response.data.decode('utf-8'))
        self.assertIs(properties['username_from_login'], self.expected)
        self.assertEqual(properties['username'], self.expected_username)

    def tearDown(self):
        if self.server_id is not None:
            utils.delete_server_with_api(self.tester, self.server_id)


class NonOwnerUsernameFromLoginTestCase(NonOwnerApiMixin, BaseTestGenerator):
    """A non-owner follows the owner's setting until they choose their
    own value, which then sticks."""

    scenarios = [
        ('Follows the owner, with the shared username winning', dict(
            owner_server={'auth_method': 'oauth_exchange',
                          'username_from_login': True},
            update=None, expected=True, expected_username='shared-user',
            owner_changes={'username_from_login': False},
            expected_after=False)),
        ('Follows the owner, with no shared username', dict(
            owner_server={'auth_method': 'oauth_direct',
                          'username_from_login': True,
                          'shared_username': ''},
            update=None, expected=True, expected_username=None,
            owner_changes={'username_from_login': False},
            expected_after=False)),
        ('Follows the owner turning it on', dict(
            owner_server={'auth_method': 'oauth_direct',
                          'shared_username': ''},
            update=None, expected=False, expected_username=None,
            owner_changes={'username_from_login': True},
            expected_after=True)),
        ('Turns it off with a username of their own, which sticks', dict(
            owner_server={'auth_method': 'oauth_direct',
                          'username_from_login': True},
            update={'username_from_login': False,
                    'username': 'group-role'},
            expected=False, expected_username='group-role',
            owner_changes={'username_from_login': True},
            expected_after=False)),
        ('Turns it on with a token method the owner did not choose', dict(
            owner_server={'auth_method': 'password'},
            update={'auth_method': 'oauth_direct',
                    'username_from_login': True, 'username': ''},
            expected=True, expected_username=None,
            owner_changes={'username_from_login': False},
            expected_after=True)),
        ('Is ignored when they choose password', dict(
            owner_server={'auth_method': 'oauth_direct',
                          'username_from_login': True},
            update={'auth_method': 'password'},
            expected=False, expected_username='shared-user',
            owner_changes=None, expected_after=False)),
        ('Is refused when they turn it on with password', dict(
            owner_server={'auth_method': 'oauth_direct'},
            update={'auth_method': 'password',
                    'username_from_login': True},
            expected_status=400,
            expected=False, expected_username='shared-user',
            owner_changes=None, expected_after=False)),
    ]
    expected_status = 200

    def runTest(self):
        if self.update is not None:
            response = self.put(self.update)
            self.assertEqual(response.status_code, self.expected_status,
                             response.data)
        properties = self.properties()
        self.assertIs(properties['username_from_login'], self.expected)
        self.assertEqual(properties['username'], self.expected_username)
        if self.owner_changes:
            self.owner_update(**self.owner_changes)
        self.assertIs(self.properties()['username_from_login'],
                      self.expected_after)


class NewNonOwnerUsernameTestCase(BaseTestGenerator):
    """While a non-owner follows the owner's "Username from login", their
    shared server stores no username of its own."""

    scenarios = [
        ('Owner with Username from login', dict(
            owner_value=True, stored_username=None)),
        ('Owner without Username from login', dict(
            owner_value=None, stored_username='database-user')),
    ]

    def setUp(self):
        unittest.TestCase.setUp(self)

    def runTest(self):
        owner = owner_server('entra', username_from_login=self.owner_value)
        shared = create_shared_server(self, owner)
        self.assertIsNone(shared.username_from_login)
        self.assertEqual(shared.username, self.stored_username)
