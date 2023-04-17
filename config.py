from calibre.utils.config import JSONConfig


preferences = JSONConfig('plugins/ebook_translator')

default_config = {
    'to_library': True,
    'output_path': None,
    'translate_engine': 'Google',
    'chatgpt_prompt': {},
    'api_key': {},
    'proxy_enabled': False,
    'proxy_setting': [],
    'request_attempt': 3,
    'request_interval': 5,
    'cache_enabled': True,
    'log_translation': True,
    'translation_position': 'after',
    'translation_color': None,
    'rule_mode': 'normal',
    'filter_rules': [],
    'custom_engines': {},
}


def init_config():
    if not preferences:
        save_config(default_config)
    for key, value in default_config.items():
        if key not in preferences:
            set_config(key, value)
    return {k: get_config(k, v) for k, v in default_config.items()}


def save_config(config):
    for key, value in config.items():
        set_config(key, value)


def get_configs(*keys):
    return [get_config(key) for key in keys]


def get_config(key, default=None):
    temp = preferences.copy()
    for key in key.split('.'):
        if isinstance(temp, dict) and key in temp:
            temp = temp[key]
            continue
        temp = None

    return temp if temp is not None else default


def set_config(key, value):
    temp = preferences
    keys = key.split('.')
    while len(keys) > 0:
        key = keys.pop(0)
        if len(keys) > 0:
            if key in temp and isinstance(temp[key], dict):
                temp = temp[key]
                continue
            temp[key] = {}
            temp = temp[key]
            continue
    temp[key] = value
