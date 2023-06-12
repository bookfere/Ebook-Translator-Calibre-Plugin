from calibre.utils.config import JSONConfig

from .engines import ChatgptTranslate


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


def get_config():
    preferences = JSONConfig('plugins/ebook_translator')
    preferences.defaults = defaults
    return Configuration(preferences)


def upgrade_config():
    """Upgrade to 1.4.0"""
    config = get_config()
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
            if 'lang' in chatgpt_prompt:
                preference.update(prompt=prompts.get('lang'))
        config.delete('chatgpt_prompt')

    languages = config.get('preferred_language')
    if languages is not None:
        for engine_name, language in languages.items():
            preference = get_engine_preference(engine_name)
            preference.update(target_lang=language)
        config.delete('preferred_language')

    api_keys = config.get('api_key')
    if api_keys is not None:
        for engine_name, api_key in api_keys.items():
            preference = get_engine_preference(engine_name)
            preference.update(api_keys=[api_key])
        config.delete('api_key')

    if len(engine_preferences) > 0:
        config.update(engine_preferences=engine_preferences)
        config.commit()
