from .google import (
    GoogleFreeTranslate, GoogleBasicTranslate, GoogleAdvancedTranslate)
from .chatgpt import ChatgptTranslate, AzureChatgptTranslate
from .deepl import DeeplTranslate, DeeplProTranslate, DeeplFreeTranslate
from .youdao import YoudaoTranslate
from .baidu import BaiduTranslate
from .edge import EdgeTranslate


builtin_engines = (
    GoogleFreeTranslate, GoogleBasicTranslate, GoogleAdvancedTranslate,
    ChatgptTranslate, AzureChatgptTranslate, DeeplTranslate, DeeplProTranslate,
    DeeplFreeTranslate, YoudaoTranslate, BaiduTranslate, EdgeTranslate)
