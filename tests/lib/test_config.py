import unittest
from typing import Any
from unittest.mock import call, Mock

from ...lib.config import (
    Configuration, get_config, ver200_upgrade, ver203_upgrade,
    migrate_opencode_config)


class TestFunction(unittest.TestCase):
    def setUp(self):
        self.config = get_config()

    def test_default(self):
        defaults: dict[str, Any] = {
            'preferred_mode': None,
            'to_library': True,
            'output_path': None,
            'translate_engine': None,
            'engine_preferences': {},
            'proxy_enabled': False,
            'proxy_type': 'http',
            'proxy_setting': {},
            'cache_enabled': True,
            'cache_path': None,
            'log_translation': True,
            'show_notification': True,
            'translation_position': None,
            'column_gap': {
                '_type': 'percentage',
                'percentage': 10,
                'space_count': 6,
            },
            'original_color': None,
            'translation_color': None,
            'priority_rules': [],
            'rule_mode': 'normal',
            'filter_scope': 'text',
            'filter_rules': [],
            'ignore_rules': [],
            'reserve_rules': [],
            'custom_engines': {},
            'glossary_enabled': False,
            'glossary_path': None,
            'merge_enabled': False,
            'merge_length': 1800,
            'ebook_metadata': {},
            'search_paths': [],
        }

        self.assertEqual(defaults, self.config.preferences.defaults)

    def test_ver200_upgrade(self):
        data = {
            'other_config': 'anything',
            'chatgpt_prompt': {
                'auto': 'Test auto prompt',
                'lang': 'Test lang prompt'
            },
            'preferred_language': {
                'ChatGPT': 'English',
                'Google': 'Chinese',
            },
            'api_key': {
                'ChatGPT': '12345',
                'Google': '67890',
            },
        }

        config = Mock()
        config.get.side_effect = lambda key: data.get(key)
        config.delete.side_effect = lambda key: data.pop(key)
        config.update.side_effect = lambda **kwargs: data.update(**kwargs)

        ver200_upgrade(config)
        self.assertEqual(data, {
            'other_config': 'anything',
            'engine_preferences': {
                'ChatGPT': {
                    'prompt': 'Test lang prompt',
                    'target_lang': 'English',
                    'api_keys': ['12345'],
                },
                'Google': {
                    'target_lang': 'Chinese',
                    'api_keys': ['67890']
                },
            },
        })

        data = {'chatgpt_prompt': {}}

        ver200_upgrade(config)
        self.assertEqual(data, {})

        config.commit.assert_called()

    def test_ver203_upgrade(self):
        data = {
            'engine_preferences': {
                'ChatGPT(Azure)': {
                    'model': 'xxx'
                }
            },
            'concurrency_limit': 2,
            'request_attempt': 0,
            'request_interval': 1,
            'request_timeout': None,
        }

        self.assertIn('model', data['engine_preferences']['ChatGPT(Azure)'])

        config = Mock()
        config.get.side_effect = lambda key: data.get(key)
        config.delete.side_effect = lambda key: key in data and data.pop(key)

        ver203_upgrade(config)
        engine = data['engine_preferences']['ChatGPT(Azure)']
        self.assertNotIn('model', engine)
        self.assertEqual(2, engine['concurrency_limit'])
        self.assertEqual(0, engine['request_attempt'])
        self.assertEqual(1, engine['request_interval'])
        self.assertNotIn('request_timeout', engine)
        self.assertNotIn('concurrency_limit', data)
        self.assertNotIn('request_attempt', data)
        self.assertNotIn('request_interval', data)
        self.assertNotIn('request_timeout', data)

        config.commit.assert_called()


class TestMigrateOpenCodeConfig(unittest.TestCase):
    def make_config(self, data):
        config = Mock()
        config.get.side_effect = lambda key: data.get(key)
        config.update.side_effect = lambda **kwargs: data.update(**kwargs)
        return config

    def test_migrate_from_chatgpt_opencode_endpoint(self):
        data = {
            'engine_preferences': {
                'ChatGPT': {
                    'api_keys': ['a', 'b'],
                    'endpoint': (
                        'https://opencode.ai/zen/go/v1/chat/completions'),
                    'model': 'gpt-5.6-luna',
                    'prompt': 'test prompt',
                    'stream': False,
                },
            },
        }

        config = self.make_config(data)
        migrate_opencode_config(config)
        self.assertIn('OpenCode Go', data['engine_preferences'])
        self.assertIn('ChatGPT', data['engine_preferences'])
        self.assertEqual(
            data['engine_preferences']['OpenCode Go'],
            data['engine_preferences']['ChatGPT'])
        config.commit.assert_called()

    def test_no_migration_when_opencode_preferences_exist(self):
        data = {
            'engine_preferences': {
                'OpenCode Go': {'api_keys': ['a']},
                'ChatGPT': {
                    'endpoint': (
                        'https://opencode.ai/zen/go/v1/chat/completions'),
                },
            },
        }

        config = self.make_config(data)
        migrate_opencode_config(config)
        self.assertEqual(
            data['engine_preferences']['OpenCode Go'], {'api_keys': ['a']})
        config.commit.assert_not_called()

    def test_migrate_zen_endpoint_to_zen_engine(self):
        data = {
            'engine_preferences': {
                'ChatGPT': {
                    'api_keys': ['a', 'b'],
                    'endpoint': (
                        'https://opencode.ai/zen/v1/chat/completions'),
                    'model': 'deepseek-v4-flash',
                },
            },
        }

        config = self.make_config(data)
        migrate_opencode_config(config)
        self.assertIn('OpenCode Zen', data['engine_preferences'])
        self.assertEqual(
            data['engine_preferences']['OpenCode Zen'],
            data['engine_preferences']['ChatGPT'])
        self.assertNotIn('OpenCode Go', data['engine_preferences'])
        config.commit.assert_called()

    def test_no_migration_when_zen_preferences_exist(self):
        data = {
            'engine_preferences': {
                'OpenCode Zen': {'api_keys': ['a']},
                'ChatGPT': {
                    'endpoint': (
                        'https://opencode.ai/zen/v1/chat/completions'),
                },
            },
        }

        config = self.make_config(data)
        migrate_opencode_config(config)
        self.assertEqual(
            data['engine_preferences']['OpenCode Zen'], {'api_keys': ['a']})
        config.commit.assert_not_called()

    def test_no_migration_without_opencode_endpoint(self):
        data = {
            'engine_preferences': {
                'ChatGPT': {
                    'endpoint': 'https://api.openai.com/v1/chat/completions',
                    'model': 'gpt-4o',
                },
            },
        }

        config = self.make_config(data)
        migrate_opencode_config(config)
        self.assertNotIn('OpenCode Go', data['engine_preferences'])
        config.commit.assert_not_called()

    def test_no_migration_without_chatgpt_preferences(self):
        data = {'engine_preferences': {}}

        config = self.make_config(data)
        migrate_opencode_config(config)
        self.assertEqual(data['engine_preferences'], {})
        config.commit.assert_not_called()


class TestConfig(unittest.TestCase):
    def setUp(self):
        self.config = Configuration()

    def test_get(self):
        self.config.preferences = {'a': 1, 'b': {'b1': {'b2': 2}}}

        self.assertEqual(None, self.config.get(None))
        self.assertEqual(1, self.config.get(None, 1))
        self.assertEqual(None, self.config.get('a.fake'))
        self.assertEqual(1, self.config.get('a.fake', 1))
        self.assertEqual({'b2': 2}, self.config.get('b.b1'))
        self.assertEqual(2, self.config.get('b.b1.b2'))
        self.assertIsNone(self.config.get('translation_position'))

    def test_set(self):
        self.config.preferences = {
            'a': 1,
            'b': {
                'b1': 2,
                'b2': True,
                'b3': False,
            }
        }

        self.config.set('a.a1', 1)
        self.assertEqual(1, self.config.preferences['a']['a1'])

        self.config.set('b', 2)
        self.assertEqual(2, self.config.preferences['b'])

        self.config.set('c', 3)
        self.assertEqual(3, self.config.preferences['c'])

        self.config.set('d.d1.d11.d111', 4)
        self.assertEqual(4, self.config.preferences['d']['d1']['d11']['d111'])

        self.assertEqual(self.config.preferences, {
            'a': {
                'a1': 1
            },
            'b': 2,
            'c': 3,
            'd': {
                'd1': {
                    'd11': {
                        'd111': 4
                    }
                }
            }
        })

    def test_update(self):
        self.config.preferences = Mock()
        self.config.update(a=6, b=4)
        self.config.preferences.update.assert_called_with(a=6, b=4)

    def test_delete(self):
        self.config.preferences = {'a': 1, 'b': 2}
        self.assertTrue(self.config.delete('a'))
        self.assertFalse(self.config.delete('c'))
        self.assertEqual({'b': 2}, self.config.preferences)

    def test_commit(self):
        self.config.preferences = Mock()
        self.config.commit()
        self.config.preferences.commit.assert_called_once()

    def test_save(self):
        self.config.preferences = Mock()
        self.config.save(b=2)
        self.assertEqual(
            self.config.preferences.mock_calls,
            [call.update(b=2), call.commit()])
