import json
import gc
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from flask_app import create_app, socketio
from flask_app.utils.database import database
from flask_app.utils import llm


EXPERIENCE = 'AI Agents & Prompt Engineering'
WRITE_CODE = '''existing = db.query("SELECT * FROM skills WHERE name = 'Rust'")
if existing:
    outcome = "Element already exists in the skills table."
else:
    db.insertRows('skills', ['experience_id', 'name', 'skill_level'],
        ["(SELECT experience_id FROM experiences WHERE name = 'AI Agents & Prompt Engineering')", 'Rust', 5])
    outcome = "New Rust added to the skills table."
'''


def plan(*steps):
    return repr(['handle_ai_chat_request(role=' + json.dumps(role) + ', message=' + json.dumps(message) + ')'
                 for role, message in steps])


class AgentsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old_cwd = Path.cwd()
        os.chdir(Path(__file__).resolve().parents[1])
        cls.temp = tempfile.TemporaryDirectory(prefix=".test-db-", dir=Path(__file__).parent)
        cls.db_file = str(Path(cls.temp.name) / 'resume.db')
        original_init = socketio.init_app
        # Test harness only: pinned eventlet does not support this machine's Python 3.13.
        with patch('flask_app.utils.database.DB_PATH', cls.db_file), patch.object(
                socketio, 'init_app', side_effect=lambda app: original_init(app, async_mode='threading')):
            cls.app, cls.socketio = create_app()
        cls.app.testing = True

    @classmethod
    def tearDownClass(cls):
        gc.collect()  # Release connections left by the handout query error path.
        cls.temp.cleanup()
        os.chdir(cls.old_cwd)

    def setUp(self):
        self.db = self.app.db
        self.db.query("DELETE FROM skills WHERE name IN ('Rust', 'NullableTest')")

    def test_template_and_seeded_roles(self):
        roles = self.db.getLLMRoles()
        self.assertEqual(set(roles), {'Orchestrator', 'Database Read Expert',
                                     'Database Write Expert', 'Content Expert'})
        prompt = llm.fill_template('Tester', 'testing', 'Say hi.', 'Hello?')
        for absent in ('{{', 'Context:', 'Examples:'):
            self.assertNotIn(absent, prompt)
        self.assertIn('Hello?', prompt)
        self.assertEqual(llm.DEFAULT_MODEL, 'qwen/qwen3-coder:free')

    def test_read_real_database_and_reject_write(self):
        with patch.object(llm, 'send_message', return_value="SELECT name FROM institutions"):
            result = llm.handle_ai_chat_request(self.db, 'Database Read Expert', 'Where?')
        self.assertIn('University College of Applied Sciences', result)
        self.assertIn('safely', llm.execute_read_query(self.db, 'DELETE FROM skills'))
        self.assertIn("couldn't", llm.execute_read_query(self.db, 'SELECT missing FROM skills'))

    def test_write_duplicate_reload_and_restart(self):
        self.assertEqual(llm.execute_write_action(self.db, WRITE_CODE), 'New Rust added to the skills table.')
        self.assertEqual(llm.execute_write_action(self.db, WRITE_CODE), 'Element already exists in the skills table.')
        self.assertEqual(len(self.db.query("SELECT * FROM skills WHERE name = 'Rust'")), 1)
        for _ in range(2):
            response = self.app.test_client().get('/resume')
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Rust', response.data)
        restarted = database()
        restarted.db_path = self.db_file
        restarted.createTables(purge=False)
        self.assertEqual(len(restarted.query("SELECT * FROM skills WHERE name = 'Rust'")), 1)

    def test_failed_generated_code(self):
        self.assertEqual(llm.execute_write_action(self.db, "raise ValueError('bad')"), 'Operation was unsuccessful.')

    def test_null_compatibility(self):
        code = "outcome = 'ok' if NULL is None else 'bad'"
        self.assertEqual(llm.execute_write_action(self.db, code), 'ok')


    def test_content_context_and_fallback(self):
        with patch.object(llm, 'send_message', return_value='A resume.') as model:
            self.assertEqual(llm.handle_ai_chat_request(self.db, 'Content Expert', 'What is this page?'), 'A resume.')
            prompt = model.call_args.args[1]
            self.assertIn(EXPERIENCE, prompt)
            self.assertIn('University College of Applied Sciences', prompt)
        with patch.object(llm, 'send_message', return_value='Hi') as model:
            self.assertEqual(llm.handle_ai_chat_request(self.db, None, 'Hello'), 'Hi')
            model.assert_called_once_with('Hello')

    def test_compound_socket_flow(self):
        request = 'Does he know Rust? If not, add it to ' + EXPERIENCE
        output_plan = plan(('Database Read Expert', 'Does he know Rust?'),
                           ('Database Write Expert', 'If absent, add Rust to ' + EXPERIENCE))
        outputs = [output_plan, "SELECT * FROM skills WHERE name = 'Rust'", WRITE_CODE,
                   'New Rust added to the skills table.']
        client = self.socketio.test_client(self.app)
        try:
            with patch.object(llm, 'send_message', side_effect=outputs) as model:
                client.emit('send_message', {'message': request})
                events = client.get_received()
                self.assertEqual(model.call_count, 4)
                self.assertEqual(model.call_args_list[2].args[0], 'If absent, add Rust to ' + EXPERIENCE)
                self.assertIn('New Rust added to the skills table.', model.call_args_list[3].args[1])
            self.assertEqual(events[0]['name'], 'receive_message')
            self.assertEqual(events[0]['args'][0]['response'], outputs[-1])
            self.assertIn(b'Rust', self.app.test_client().get('/resume').data)
            client.emit('send_message', {'message': '  '})
            self.assertEqual(client.get_received(), [])
        finally:
            client.disconnect()

    def test_unparseable_plan(self):
        with patch.object(llm, 'handle_ai_chat_request') as expert:
            self.assertIn("couldn't plan", llm.run_orchestrator_plan(self.db, 'test', 'not a list'))
            expert.assert_not_called()


if __name__ == '__main__':
    unittest.main()
