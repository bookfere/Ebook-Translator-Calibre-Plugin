from .base import Base
from .google import (
    GoogleFreeTranslateNew, GoogleFreeTranslateHtml, GoogleFreeTranslate,
    GoogleBasicTranslate, GoogleBasicTranslateADC, GoogleAdvancedTranslate,
    GeminiTranslate)
from .openai import ChatgptTranslate
from .anthropic import ClaudeTranslate, ClaudeBatchTranslate
from .deepl import DeeplTranslate, DeeplProTranslate, DeeplFreeTranslate
from .youdao import YoudaoTranslate
from .baidu import BaiduTranslate
from .microsoft import MicrosoftEdgeTranslate, AzureChatgptTranslate
from .deepseek import DeepseekTranslate

builtin_engines: tuple[type[Base], ...] = (
    GoogleFreeTranslateNew, GoogleFreeTranslateHtml, GoogleFreeTranslate,
    GoogleBasicTranslate, GoogleBasicTranslateADC, GoogleAdvancedTranslate,
    ChatgptTranslate, AzureChatgptTranslate, GeminiTranslate, ClaudeTranslate,
    ClaudeBatchTranslate, DeepseekTranslate, DeeplTranslate, DeeplProTranslate,
    DeeplFreeTranslate, MicrosoftEdgeTranslate, YoudaoTranslate, BaiduTranslate)
