##########################################################################
#
# pgAdmin 4 - PostgreSQL Tools
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pgadmin.utils.route import BaseTestGenerator


class TestPanelAIAvailability(BaseTestGenerator):
    """Each new Query Tool layout gets the current server-side AI status."""

    @patch('pgadmin.tools.sqleditor.render_template', return_value='')
    @patch('pgadmin.tools.sqleditor.get_driver')
    @patch('pgadmin.tools.sqleditor.get_server')
    @patch('pgadmin.llm.utils.is_llm_enabled')
    def runTest(self, enabled, get_server, get_driver, render):
        get_driver.return_value.connection_manager.return_value = \
            MagicMock(user='test')
        get_server.return_value = SimpleNamespace(
            shared=False, bgcolor=None, name='test', username='test', role='')
        for value in (True, False):
            with self.subTest(enabled=value):
                enabled.return_value = value
                response = self.tester.post(
                    '/sqleditor/panel/1',
                    query_string={
                        'sid': 1, 'title': 'Query Tool',
                        'selectedNodeInfo': '{}',
                        'llm_enabled': str(not value).lower(),
                    })
                self.assertEqual(response.status_code, 200)
                params = json.loads(render.call_args.kwargs['params'])
                self.assertIs(params['llm_enabled'], value)
