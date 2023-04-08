import re
from types import MethodType

from calibre.utils.logging import Log
from calibre.constants import __version__
from calibre.ebooks.conversion.plumber import Plumber
from calibre_plugins.ebook_translator import EbookTranslator
from calibre_plugins.ebook_translator.config import get_config, get_configs
from calibre_plugins.ebook_translator.utils import ns, uid, trim
from calibre_plugins.ebook_translator.cache import TranslationCache
from calibre_plugins.ebook_translator.translation import Translation
from calibre_plugins.ebook_translator.translator import TranslatorBuilder


load_translations()


def get_translator(source_lang, target_lang):
    engine = get_config('translate_engine')
    api_key = get_config('api_key.%s' % engine)
    builder = TranslatorBuilder(source_lang, target_lang, engine, api_key)
    translator = builder.build()
    if get_config('proxy_enabled'):
        translator.set_proxy(get_config('proxy_setting'))
    if translator.is_chatgpt():
        prompts = get_config('chatgpt_prompt')
        translator.set_prompt(prompts.get('auto'), prompts.get('lang'))
    return translator


def get_translation(translator):
    translation = Translation(translator, get_config('translation_position'),
                              get_config('translation_color'))
    translation.set_request_attempt(get_config('request_attempt'))
    translation.set_request_interval(get_config('request_interval'))
    return translation


def extract_elements(pages):
    elements = []
    for page in pages:
        if 'html' not in page.media_type:
            continue
        p_elements = list(
            filter(filter_content, page.data.findall('.//x:p', namespaces=ns)))
        if len(p_elements) > 1:
            tags = ('h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                    'div[@class="paragraph"]')
            pattern = './/*[self::x:p%s]' % ''.join(
                [' or self::x:%s' % tag for tag in tags])
            elements.extend(page.data.xpath(pattern, namespaces=ns))
        else:
            body = page.data.find('./x:body', namespaces=ns)
            elements.extend(get_elements(body, []))
    return list(filter(filter_content, elements))


def get_elements(root, elements):
    for element in root.findall('./*'):
        element_has_content = False
        if element.text is not None and trim(element.text) != '':
            element_has_content = True
        else:
            children = element.findall('./*')
            for child in children:
                if child.tail is not None and trim(child.tail) != '':
                    element_has_content = True
                    break
        if element_has_content:
            elements.append(element)
        else:
            get_elements(element, elements)
    # Return root if all children has no content
    return elements if elements else [root]


def filter_content(element):
    content = trim(''.join(element.itertext()))
    if content == '':
        return False

    default_rules = ['^[\d\s\._-]+$']
    patterns = [re.compile(rule) for rule in default_rules]

    mode, rules = get_configs('rule_mode', 'filter_rules')
    for rule in rules:
        if mode == 'regex':
            patterns.append(re.compile(rule))
        else:
            args = [re.escape(rule)]
            if mode == 'normal':
                args.append(re.I)
            patterns.append(re.compile(*args))

    for pattern in patterns:
        if pattern.search(content):
            return False
    return True


def convert_book(input_path, output_path, source_lang, target_lang,
                 notification):
    """parameter notification is automatically added by arbitrary_n."""
    log = Log()
    translator = get_translator(source_lang, target_lang)
    translation = get_translation(translator)

    dagnosis = """==============================
| Diagnosis Information
==============================
| Calibre Version: {}
| Plugin Version: {}
| Translate Engine: {}
| Source Language: {}
| Target Language: {}
| Input Path: {}
| Output Path: {}
=============================="""
    log.info(dagnosis.format(
        __version__, EbookTranslator.__version__, translator.name, source_lang,
        target_lang, input_path, output_path))

    if get_config('cache_enabled'):
        cache = TranslationCache(uid(
            translator.name, input_path, source_lang, target_lang))
        translation.set_cache(cache)

    if get_config('log_translation'):
        translation.set_log(log)

    plumber = Plumber(
        input_path, output_path, log=log, report_progress=notification)

    _convert = plumber.output_plugin.convert

    def convert(self, oeb, output_path, input_plugin, opts, log):
        log.info('translating ebook content ... (this will take a while)')
        translation.set_progress(self.report_progress)
        translation.handle(extract_elements(oeb.manifest.items))
        _convert(oeb, output_path, input_plugin, opts, log)

    plumber.output_plugin.convert = MethodType(convert, plumber.output_plugin)
    plumber.run()
