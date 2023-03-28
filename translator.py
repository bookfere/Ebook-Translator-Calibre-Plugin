import json

from calibre_plugins.ebook_translator.engines.google import GoogleTranslate
from calibre_plugins.ebook_translator.engines.chatgpt import ChatgptTranslate
from calibre_plugins.ebook_translator.engines.deepl import DeeplTranslate
from calibre_plugins.ebook_translator.engines.deeplpro import DeeplProTranslate


load_translations()


class TranslatorBuilder:
    engines = {
        'Google': GoogleTranslate,
        'ChatGPT': ChatgptTranslate,
        'DeepL': DeeplTranslate,
        'DeepL(Pro)': DeeplProTranslate,
    }

    def __init__(self, source_lang, target_lang, engine, api_key):
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.engine = engine or 'Google'
        self.api_key = api_key

    def build(self):
        translator_class = self.engines.get(self.engine)
        if translator_class is None:
            raise Exception(_('Translate engine not exists.'))
        translator = translator_class(
            self.engine, self.api_key, self.source_lang, self.target_lang)
        return translator
