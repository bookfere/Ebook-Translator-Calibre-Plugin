from calibre.utils.config import JSONConfig


preferences = JSONConfig('plugins/ebook_translator')


def init_config(items):
    if not preferences:
        save_config(items)


def save_config(items):
    for key, value in items:
        set_config(key, value)


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
