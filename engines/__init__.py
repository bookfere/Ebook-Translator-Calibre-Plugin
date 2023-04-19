from calibre_plugins.ebook_translator.engines.google import GoogleTranslate
from calibre_plugins.ebook_translator.engines.chatgpt import ChatgptTranslate
from calibre_plugins.ebook_translator.engines.deepl import (
    DeeplTranslate, DeeplProTranslate)
from calibre_plugins.ebook_translator.engines.youdao import YoudaoTranslate
from calibre_plugins.ebook_translator.engines.baidu import BaiduTranslate


builtin_engines = (
    GoogleTranslate, ChatgptTranslate, DeeplTranslate, DeeplProTranslate,
    YoudaoTranslate, BaiduTranslate)
