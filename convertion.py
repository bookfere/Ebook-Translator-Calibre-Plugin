import re
from types import MethodType

from calibre.constants import __version__
from calibre.ebooks.conversion.plumber import Plumber
from calibre_plugins.ebook_translator import EbookTranslator
from calibre_plugins.ebook_translator.config import get_config
from calibre_plugins.ebook_translator.utils import (
    ns, log, uid, trim, sorted_mixed_keys)
from calibre_plugins.ebook_translator.cache import TranslationCache
from calibre_plugins.ebook_translator.element import get_string, get_name
from calibre_plugins.ebook_translator.translator import get_translator
from calibre_plugins.ebook_translator.translation import get_translation


load_translations()


def get_sorted_pages(pages):
    return sorted(
        [page for page in pages if 'html' in page.media_type],
        key=lambda page: sorted_mixed_keys(page.href))


def extract_elements(pages):
    elements = []
    for page in get_sorted_pages(pages):
        body = page.data.find('./x:body', namespaces=ns)
        elements.extend(get_elements(body, []))
    return list(filter(filter_content, elements))


def get_elements(root, elements=[]):
    ignore_tags = ['pre', 'code']
    for element in root.findall('./*'):
        if get_name(element) in ignore_tags:
            continue
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
    # Return root if all children have no content
    return elements if elements else [root]


def filter_content(element):
    content = trim(''.join(element.itertext()))
    if content == '':
        return False

    default_rules = [r'^[\d\s\._-]+$']
    patterns = [re.compile(rule) for rule in default_rules]

    mode, rules = get_config('rule_mode'), get_config('filter_rules')
    for rule in rules:
        if mode == 'regex':
            patterns.append(re.compile(rule))
        else:
            args = [re.escape(rule)]
            if mode == 'normal':
                args.append(re.I)
            patterns.append(re.compile(*args))
    if get_config('filter_scope') == 'html':
        content = get_string(element, True)
    for pattern in patterns:
        if pattern.search(content):
            return False
    return True


def convert_book(input_path, output_path, source_lang, target_lang,
                 notification):
    """parameter notification is automatically added by arbitrary_n."""
    translator = get_translator()
    translator.set_source_lang(source_lang)
    translator.set_target_lang(target_lang)
    translation = get_translation(translator)

    if get_config('cache_enabled'):
        cache = TranslationCache(uid(
            translator.name, input_path, source_lang, target_lang))
        translation.set_cache(cache)

    if get_config('log_translation'):
        translation.set_log(log)

    diagnosis_info = """==============================
| Diagnosis Information
==============================
| Calibre Version: {}
| Plugin Version: {}
| Translate Engine: {}
| Source Language: {}
| Target Language: {}
| Input Path: {}
| Output Path: {}"""
    diagnosis_info = diagnosis_info.format(
        __version__, EbookTranslator.__version__, translator.name,
        source_lang, target_lang, input_path, output_path)

    plumber = Plumber(
        input_path, output_path, log=log, report_progress=notification)

    _convert = plumber.output_plugin.convert

    def convert(self, oeb, output_path, input_plugin, opts, log):
        log.info('translating ebook content ... (this will take a while)')
        log.info(diagnosis_info)
        translation.set_progress(self.report_progress)
        translation.handle(extract_elements(oeb.manifest.items))
        _convert(oeb, output_path, input_plugin, opts, log)

    plumber.output_plugin.convert = MethodType(convert, plumber.output_plugin)
    plumber.run()
