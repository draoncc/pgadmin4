##########################################################################
#
# pgAdmin 4 - PostgreSQL Tools
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""The 'Use pgAdmin username' setting of a shared server: which requests
may set it, and what turning it off does to the non-owners."""

import inspect
import json
import unittest
import uuid
from unittest.mock import MagicMock, patch

from flask import Flask
from flask_babel import Babel

from pgadmin.model import db, Server, ServerGroup, SharedServer, User
from pgadmin.utils.constants import LDAP, OAUTH2
from pgadmin.utils.route import BaseTestGenerator

SRV_MODULE = 'pgadmin.browser.server_groups.servers'


class TestPrepareSharingDataFlag(BaseTestGenerator):
    """The flag is dropped from a non-administrator's payload, like the
    shared username, and kept for an administrator."""

    scenarios = [
        ('Administrator keeps the flag',
         dict(admin=True, server_mode=True, expect_kept=True)),
        ('Non-administrator loses the flag',
         dict(admin=False, server_mode=True, expect_kept=False)),
        ('Desktop mode keeps the flag',
         dict(admin=False, server_mode=False, expect_kept=True)),
    ]

    def runTest(self):
        from pgadmin.browser.server_groups.servers import \
            prepare_sharing_data
        user = MagicMock()
        user.has_role.return_value = self.admin
        payload = {'shared_username_from_pgadmin': True, 'comment': 'x'}
        with patch(SRV_MODULE + '.current_user', user), \
                patch(SRV_MODULE + '.config.SERVER_MODE',
                      self.server_mode):
            data, err = prepare_sharing_data(payload)

        self.assertIsNone(err)
        self.assertEqual(data['comment'], 'x')
        self.assertEqual('shared_username_from_pgadmin' in data,
                         self.expect_kept)
        # The caller's dict is untouched.
        self.assertIn('shared_username_from_pgadmin', payload)


class TestTurningTheFlagOff(BaseTestGenerator):
    """Every non-owner copy goes back to the current shared username."""

    def setUp(self):
        self.created = []
        tag = uuid.uuid4().hex[:8]
        with self.app.app_context():
            owner = self._add(User(
                username='own-{0}@example.com'.format(tag), email=None,
                active=True, auth_source=OAUTH2,
                fs_uniquifier=uuid.uuid4().hex))
            other = self._add(User(
                username='oth-{0}@example.com'.format(tag), email=None,
                active=True, auth_source=LDAP,
                fs_uniquifier=uuid.uuid4().hex))
            group = self._add(ServerGroup(user_id=owner.id, name='G'))
            other_group = self._add(ServerGroup(user_id=other.id, name='G'))
            server = self._add(Server(
                user_id=owner.id, servergroup_id=group.id, name='shared',
                host='db.example.com', port=5432,
                maintenance_db='postgres', username='owner_db',
                save_password=0, shared=True, shared_username='shr',
                shared_username_from_pgadmin=True))
            self._add(SharedServer(
                osid=server.id, user_id=other.id,
                server_owner=owner.username,
                servergroup_id=other_group.id, name='shared',
                host='db.example.com', port=5432,
                maintenance_db='postgres', username='stale',
                save_password=0, shared=True))
            self.server_id = server.id
            self.other_id = other.id

    def tearDown(self):
        with self.app.app_context():
            for obj in reversed(self.created):
                db.session.delete(db.session.merge(obj))
            db.session.commit()

    def _add(self, obj):
        """Save a row and remember it, so tearDown can delete it."""
        db.session.add(obj)
        db.session.commit()
        self.created.append(obj)
        return obj

    def _copy_username(self):
        """Return the username stored on the non-owner's copy."""
        return SharedServer.query.filter_by(
            osid=self.server_id, user_id=self.other_id).one().username

    def runTest(self):
        from pgadmin.browser.server_groups.servers import \
            reset_shared_usernames
        with self.app.app_context():
            server = Server.query.get(self.server_id)
            server.shared_username_from_pgadmin = False
            reset_shared_usernames(server)
            db.session.commit()
            self.assertEqual(self._copy_username(), 'shr')


class TestUpdateTurnsTheFlagOff(BaseTestGenerator):
    """Updating a shared server through ServerNode.update resets the
    non-owners' copies to the Shared Username only when the update turns
    the flag off."""

    scenarios = [
        ('Clearing the flag resets the copies',
         dict(payload={'shared_username_from_pgadmin': False},
              expect_reset=True)),
        ('Leaving the flag on keeps the copies',
         dict(payload={'comment': 'edited'}, expect_reset=False)),
    ]

    def setUp(self):
        # Pure logic test with mocks: skip the server setup.
        unittest.TestCase.setUp(self)

    def runTest(self):
        from pgadmin.browser.server_groups.servers import ServerNode
        server = Server(
            id=7, user_id=1, servergroup_id=1, name='shared',
            host='db.example.com', port=5432, maintenance_db='postgres',
            username='owner_db', save_password=0, shared=True,
            shared_username='shr', shared_username_from_pgadmin=True)
        copies = [MagicMock(username='alice@example.com'),
                  MagicMock(username='bob@example.com')]
        shared_cls = MagicMock()
        shared_cls.query.filter_by.return_value = copies

        manager = MagicMock()
        manager.connection.return_value.connected.return_value = False
        driver = MagicMock()
        driver.connection_manager.return_value = manager
        owner = MagicMock(id=1)
        owner.has_role.return_value = True

        node = ServerNode.__new__(ServerNode)
        node.blueprint = MagicMock()
        node.blueprint.generate_browser_node.return_value = {}
        app = Flask(__name__)
        Babel(app)
        with app.test_request_context(
                method='PUT', data=json.dumps(self.payload),
                content_type='application/json'), \
                patch(SRV_MODULE + '.get_server', return_value=server), \
                patch(SRV_MODULE + '.current_user', owner), \
                patch(SRV_MODULE + '.config.SERVER_MODE', True), \
                patch(SRV_MODULE + '.get_driver', return_value=driver), \
                patch(SRV_MODULE + '.get_crypt_key',
                      return_value=(True, 'key')), \
                patch(SRV_MODULE + '.SharedServer', shared_cls), \
                patch(SRV_MODULE + '.db'), \
                patch(SRV_MODULE + '.server_icon_and_background'):
            # Skip the login and MFA decorators: this tests the update.
            inspect.unwrap(ServerNode.update)(node, 1, 7)

        expected = ['shr', 'shr'] if self.expect_reset else \
            ['alice@example.com', 'bob@example.com']
        self.assertEqual([c.username for c in copies], expected)
        self.assertEqual(server.shared_username_from_pgadmin,
                         not self.expect_reset)
