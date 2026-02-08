import os
import os.path
import shutil
from typing import Any

from calibre.constants import config_dir  # type: ignore
from calibre.utils.config_base import plugin_dir  # type: ignore
from calibre.utils.config import JSONConfig  # type: ignore

from .. import EbookTranslator
from ..engines import (
    GoogleFreeTranslateNew, ChatgptTranslate, AzureChatgptTranslate)


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
    'log_content': True,
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


class Configuration:
    def __init__(self, config={}):
        self.preferences = config

    def get(self, key, default=None):
        """Get config value with dot flavor. e.g. get('a.b.c')"""
        if key is None:
            return default
        temp = self.preferences
        for key in key.split('.'):
            if isinstance(temp, dict) and key in temp:
                temp = temp.get(key)
                continue
            temp = defaults.get(key)
        return default if temp is None else temp

    def set(self, key, value):
        """Set config value with dot flavor. e.g. set('a.b.c', '1')"""
        temp = self.preferences
        keys = key.split('.')
        while len(keys) > 0:
            key = keys.pop(0)
            if len(keys) > 0:
                if key in temp and isinstance(temp.get(key), dict):
                    temp = temp[key]
                    continue
                temp[key] = {}
                temp = temp.get(key)
                continue
        temp[key] = value

    def update(self, *args, **kwargs):
        self.preferences.update(*args, **kwargs)

    def delete(self, key):
        if key in self.preferences:
            del self.preferences[key]
            return True
        return False

    def refresh(self):
        self.preferences.refresh()

    def commit(self):
        self.preferences.commit()

    def save(self, *args, **kwargs):
        self.update(*args, **kwargs)
        self.commit()


def get_config():
    preferences = JSONConfig('plugins/ebook_translator')
    preferences.defaults = defaults
    return Configuration(preferences)


def upgrade_config():
    config = get_config()
    version = EbookTranslator.version
    if version >= (2, 0, 0):  # type: ignore
        ver200_upgrade(config)
    if version >= (2, 0, 3):  # type: ignore
        ver203_upgrade(config)
    if version >= (2, 0, 5):  # type: ignore
        ver205_upgrade(config)
    if version >= (2, 4, 0):  # type: ignore
        ver240_upgrade()


def ver200_upgrade(config):
    """Upgrade the configuration for version 2.0.0 or earlier."""
    if config.get('engine_preferences'):
        return

    engine_preferences = {}

    def get_engine_preference(engine_name):
        if engine_name not in engine_preferences:
            engine_preferences.update({engine_name: {}})
        return engine_preferences.get(engine_name)

    chatgpt_prompt = config.get('chatgpt_prompt')
    if chatgpt_prompt is not None:
        if len(chatgpt_prompt) > 0:
            preference = get_engine_preference(ChatgptTranslate.name)
            prompts = config.get('chatgpt_prompt')
            if preference is not None and 'lang' in chatgpt_prompt:
                preference.update(prompt=prompts.get('lang'))
        config.delete('chatgpt_prompt')

    languages = config.get('preferred_language')
    if languages is not None:
        for engine_name, language in languages.items():
            preference = get_engine_preference(engine_name)
            if preference is not None:
                preference.update(target_lang=language)
        config.delete('preferred_language')

    api_keys = config.get('api_key')
    if api_keys is not None:
        for engine_name, api_key in api_keys.items():
            preference = get_engine_preference(engine_name)
            if preference is not None:
                preference.update(api_keys=[api_key])
        config.delete('api_key')

    if len(engine_preferences) > 0:
        config.update(engine_preferences=engine_preferences)
        config.commit()


def ver203_upgrade(config):
    """Upgrade the configuration for version 2.0.3 or earlier."""
    engine_config = config.get('engine_preferences')
    azure_chatgpt = engine_config.get('ChatGPT(Azure)')
    if azure_chatgpt and 'model' in azure_chatgpt:
        model = azure_chatgpt.get('model')
        if model not in AzureChatgptTranslate.models:
            del azure_chatgpt['model']

    if len(engine_config) < 1:
        engine_config.update({GoogleFreeTranslateNew.name: {}})

    old_concurrency_limit = config.get('concurrency_limit')
    old_request_attempt = config.get('request_attempt')
    old_request_interval = config.get('request_interval')
    old_request_timeout = config.get('request_timeout')

    for data in engine_config.values():
        if old_concurrency_limit is not None and old_concurrency_limit != 1:
            data.update(concurrency_limit=old_concurrency_limit)
        if old_request_attempt is not None and old_request_attempt != 3:
            data.update(request_attempt=old_request_attempt)
        if old_request_interval is not None and old_request_interval != 5:
            data.update(request_interval=old_request_interval)
        if old_request_timeout is not None and old_request_timeout != 10:
            data.update(request_timeout=old_request_timeout)

    config.delete('concurrency_limit')
    config.delete('request_attempt')
    config.delete('request_interval')
    config.delete('request_timeout')

    config.commit()


def ver205_upgrade(config):
    """Upgrade the configuration for version 2.0.5 or earlier."""
    if config.get('translate_engine') in ('GeminiPro', 'GeminiFlash'):
        config.update(translate_engine='Gemini')
    preferences = config.get('engine_preferences')
    if 'GeminiPro' in preferences.keys():
        preferences['Gemini'] = preferences.pop('GeminiPro')
    if 'GeminiFlash' in preferences.keys():
        preferences['Gemini'] = preferences.pop('GeminiFlash')
        preferences['Gemini'].update(model='gemini-1.5-flash')
    config.commit()


def ver240_upgrade():
    old_config_path = os.path.join(config_dir, EbookTranslator.author)
    new_config_path = os.path.join(plugin_dir, EbookTranslator.identifier)
    if os.path.exists(new_config_path) and os.path.exists(old_config_path):
        shutil.rmtree(old_config_path)
    if os.path.exists(old_config_path):
        os.rename(old_config_path, new_config_path)
        os.rename(
            os.path.join(new_config_path, EbookTranslator.identifier + '.ini'),
            os.path.join(new_config_path, 'settings.ini'))
