from calibre_plugins.ebook_translator.engines.google import GoogleTranslate
from calibre_plugins.ebook_translator.engines.chatgpt import ChatgptTranslate
from calibre_plugins.ebook_translator.engines.deepl import DeeplTranslate
from calibre_plugins.ebook_translator.engines.deeplpro import DeeplProTranslate
from calibre_plugins.ebook_translator.engines.youdao import YoudaoTranslate
from calibre_plugins.ebook_translator.engines.baidu import BaiduTranslate


load_translations()


class TranslatorBuilder:
    engines = (
        GoogleTranslate,
        ChatgptTranslate,
        DeeplTranslate,
        DeeplProTranslate,
        YoudaoTranslate,
        BaiduTranslate,
    )

    def __init__(self, source_lang, target_lang, engine, api_key):
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.api_key = api_key

        self.engine = self.get_engine_class(engine)

    @classmethod
    def get_engine_class(cls, name):
        for engine in cls.engines:
            if engine.name == name:
                return engine
        raise Exception(_('Translate engine not exists.'))

    def build(self):
        return self.engine(self.api_key, self.source_lang, self.target_lang)
