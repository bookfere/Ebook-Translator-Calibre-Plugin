import json

from calibre_plugins.ebook_translator.config import (
    set_config, get_config, default_config)
from calibre_plugins.ebook_translator.engines import builtin_engines
from calibre_plugins.ebook_translator.engines.custom import CustomTranslate


def get_engine_class(engine_name):
    engines = {engine.name: engine for engine in builtin_engines}
    engine_class = engines.get(engine_name) or CustomTranslate
    if engine_class.is_custom():
        engine_data = get_config('custom_engines.%s' % engine_name)
        if engine_data is not None:
            engine_data = json.loads(engine_data)
            engine_class.set_engine_data(engine_data)
            engine_class.set_lang_codes(engine_data.get('languages'))
        else:
            default_engine = default_config.get('translate_engine')
            set_config('translate_engine', default_engine)
            return get_engine_class(default_engine)
    else:
        engine_class.set_lang_codes(json.loads(get_resources(
            'engines/codes/%s' % engine_class.support_lang)))
    return engine_class


def get_translator():
    engine_name = get_config('translate_engine')
    engine_class = get_engine_class(engine_name)
    translator = engine_class()
    api_key = get_config('api_key.%s' % engine_name)
    api_key and translator.set_api_key(api_key)
    if get_config('proxy_enabled'):
        translator.set_proxy(get_config('proxy_setting'))
    if translator.is_chatgpt():
        translator.set_prompt(**get_config('chatgpt_prompt'))
        get_config('merge_enabled') and translator.set_keep_mark()
    return translator
