import unittest
from unittest.mock import patch, MagicMock

from ..config import Configuration, get_config, upgrade_config


class TestFunction(unittest.TestCase):
    def setUp(self):
        self.config = get_config()

    def test_default(self):
        defaults = {
            'preferred_mode': None,
            'to_library': True,
            'output_path': None,
            'translate_engine': None,
            'engine_preferences': {},
            'proxy_enabled': False,
            'proxy_setting': [],
            'concurrency_limit': 1,
            'request_attempt': 3,
            'request_interval': 5,
            'request_timeout': 10,
            'cache_enabled': True,
            'log_translation': True,
            'translation_position': 'after',
            'translation_color': None,
            'rule_mode': 'normal',
            'filter_scope': 'text',
            'filter_rules': [],
            'element_rules': [],
            'custom_engines': {},
            'glossary_enabled': False,
            'glossary_path': None,
            'merge_enabled': False,
            'merge_length': 2000,
            'ebook_metadata': {},
        }

        self.assertEqual(defaults, self.config.preferences.defaults)

    @patch('calibre_plugins.ebook_translator.config.get_config')
    def test_upgrade(self, mock_get_config):
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

        config = MagicMock()
        config.get.side_effect = lambda key: data.get(key)
        config.delete.side_effect = lambda key: data.pop(key)
        config.update.side_effect = lambda **kwargs: data.update(**kwargs)

        mock_get_config.return_value = config

        upgrade_config()

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

        # data = {'chatgpt_prompt': {}}
        # config.upgrade()
        # self.assertEqual(data, {})

        config.commit.assert_called()


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
        self.assertEqual('after', self.config.get('translation_position'))

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
        self.config.preferences = {'a': 1}
        self.config.update(a=6, b=4)
        self.assertEqual({'a': 6, 'b': 4}, self.config.preferences)
        self.config.update({'c': 0})
        self.assertEqual({'a': 6, 'b': 4, 'c': 0}, self.config.preferences)

    def test_delete(self):
        self.config.preferences = {'a': 1, 'b': 2}
        self.assertTrue(self.config.delete('a'))
        self.assertFalse(self.config.delete('c'))
        self.assertEqual({'b': 2}, self.config.preferences)

    def test_commit(self):
        self.config.preferences = MagicMock()
        self.config.commit()
        self.config.preferences.commit.assert_called_once()
