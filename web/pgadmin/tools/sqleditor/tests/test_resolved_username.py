##########################################################################
#
# pgAdmin 4 - PostgreSQL Tools
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""The Query Tool uses the server's resolved database username, which
"Username from login" can take from the pgAdmin login, rather than the
username stored on the server."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pgadmin.utils.ajax import make_json_response
from pgadmin.utils.route import BaseTestGenerator

LOGIN_USER = 'ada@example.test'


def _server():
    # A "Username from login" server stores no username.
    return SimpleNamespace(
        id=1, shared=False, user_id=1, servergroup_id=1, bgcolor=None,
        name='login-username', username=None, role=None,
        auth_method='entra')


def _driver():
    manager = MagicMock()
    manager.user = LOGIN_USER
    manager.role = None
    manager.connection.return_value.connected.return_value = False
    driver = MagicMock()
    driver.connection_manager.return_value = manager
    return driver


class TestPanelTitleUser(BaseTestGenerator):
    """The Query Tool title shows the resolved username."""

    def runTest(self):
        with patch('pgadmin.tools.sqleditor.render_template',
                   return_value='') as render, \
                patch('pgadmin.tools.sqleditor.get_server',
                      return_value=_server()), \
                patch('pgadmin.tools.sqleditor.get_driver',
                      return_value=_driver()):
            response = self.tester.post(
                '/sqleditor/panel/1',
                query_string={'sid': 1, 'title': 'Query Tool',
                              'selectedNodeInfo': '{}'})
        self.assertEqual(response.status_code, 200)
        params = json.loads(render.call_args.kwargs['params'])
        self.assertEqual(params['user'], LOGIN_USER)


class TestConnectServerResolvedUser(BaseTestGenerator):
    """A Query Tool connection made as the resolved username is the
    server's own user, so the server itself is connected."""

    scenarios = [
        ('The resolved username connects the server',
         dict(user=LOGIN_USER, expect_connect=True)),
        ('Another user skips the server connect',
         dict(user='someone-else', expect_connect=False)),
    ]

    def runTest(self):
        view = MagicMock()
        view.connect.side_effect = lambda *args, **kwargs: \
            make_json_response(success=1, info='connected', data={})
        with patch('pgadmin.tools.sqleditor.get_server',
                   return_value=_server()), \
                patch('pgadmin.tools.sqleditor.get_driver',
                      return_value=_driver()), \
                patch('pgadmin.tools.sqleditor.SchemaDiffRegistry.'
                      'get_node_view', return_value=view):
            response = self.tester.post(
                '/sqleditor/connect_server/1',
                data={'user': self.user, 'role': ''})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(view.connect.called, self.expect_connect)
