import os
import re
import json
import shutil
import sqlite3
import os.path
import tempfile
from datetime import datetime
from glob import glob

from calibre.utils.localization import _  # type: ignore

from .utils import size_by_unit
from .config import get_config


load_translations()  # type: ignore


class Paragraph:
    def __init__(
            self, id, md5, raw, original, ignored=False, attributes=None,
            page=None, translation=None, engine_name=None, target_lang=None):
        self.id = id
        self.md5 = md5
        self.raw = raw
        self.original = original
        self.ignored = ignored
        self.attributes = attributes
        self.page = page
        self.translation = translation
        self.engine_name = engine_name
        self.target_lang = target_lang

        self.row = -1
        self.is_cache = False
        self.error = None
        self.aligned = True

    def get_attributes(self) -> dict:
        if self.attributes:
            return json.loads(self.attributes)
        return {}

    def is_alignment(self, separator: str) -> bool:
        if self.translation is None or self.translation.strip() == '':
            return True
        pattern = re.compile(separator)
        count_original = len(pattern.split(self.original.strip()))
        count_translation = len(pattern.split(self.translation.strip()))
        return count_original == count_translation

    def do_aligment(self, separator: str) -> None:
        """Verify alignment status if the translation is misaligned."""
        # Check if translation is aligned with original
        if self.translation is None or self.is_alignment(separator):
            return
        # Auto-add line spacing to translation text
        single_saparator = separator[0]
        lines = self.translation.split(single_saparator)
        processed_lines = []
        # Add empty line after non-empty line if next line is also non-empty.
        for i, line in enumerate(lines):
            processed_lines.append(line)
            if (line.strip() and i + 1 < len(lines) and lines[i + 1].strip()):
                processed_lines.append('')
        self.translation = single_saparator.join(processed_lines)


def default_cache_path():
    path = os.path.join(
        tempfile.gettempdir(), 'com.bookfere.Calibre.EbookTranslator')
    if not os.path.exists(path):
        os.mkdir(path)
    return path


def custom_cache_path():
    config = get_config()
    path = config.get('cache_path')
    if path and os.path.exists(path):
        return path
    path = default_cache_path()
    config.save(cache_path=path)
    return path


class TranslationCache:
    fresh = True
    dir_path = custom_cache_path()
    cache_path = os.path.join(dir_path, 'cache')
    temp_path = os.path.join(dir_path, 'temp')

    def __init__(self, identity, persistence=True):
        """:persistence: We use two types of cache, one is used temporarily for
        communication, and another one is used to cache translations, which
        avoids the need for retranslation.
        """
        self.identity = identity
        self.persistence = persistence
        self.file_path = self._path(identity)
        # An interruption may occur, resulting in the cache size being less
        # than 50,000 bytes. Therefore, we need to resave it again.
        if os.path.exists(self.file_path) and self.size() > 50000:
            self.fresh = False
        self.cache_only = False
        self.connection = sqlite3.connect(
            self.file_path, check_same_thread=False)
        self.cursor = self.connection.cursor()
        self.cursor.execute(
            'CREATE TABLE IF NOT EXISTS cache('
            'id UNIQUE, md5 UNIQUE, raw, original, ignored, '
            'attributes DEFAULT NULL, page DEFAULT NULL,'
            'translation DEFAULT NULL, engine_name DEFAULT NULL, '
            'target_lang DEFAULT NULL)')
        self.cursor.execute(
            'CREATE TABLE IF NOT EXISTS info(key UNIQUE, value)')

    @classmethod
    def move(cls, dest):
        for dir_path in glob(os.path.join(cls.dir_path, '*')):
            if os.path.exists(dir_path):
                shutil.move(dir_path, dest)
        cls.dir_path = dest
        cls.cache_path = os.path.join(dest, 'cache')
        cls.temp_path = os.path.join(dest, 'temp')

    @classmethod
    def count(cls):
        total = 0
        for file_path in glob(os.path.join(cls.cache_path, '*.db')):
            total += os.path.getsize(file_path)
        return size_by_unit(total, 'MB')

    @classmethod
    def remove(cls, filename):
        file_path = os.path.join(cls.cache_path, filename)
        if os.path.exists(file_path):
            os.remove(file_path)

    @classmethod
    def clean(cls):
        for filename in os.listdir(cls.cache_path):
            cls.remove(filename)

    @classmethod
    def get_list(cls):
        names = []
        for file_path in glob(os.path.join(cls.cache_path, '*.db')):
            name = os.path.basename(file_path)
            cache = cls(os.path.splitext(name)[0])
            title = cache.get_info('title') or '[%s]' % _('Unknown')
            engine = cache.get_info('engine_name')
            lang = cache.get_info('target_lang')
            merge = int(cache.get_info('merge_length') or 0)
            size = size_by_unit(os.path.getsize(file_path), 'MB')
            time = datetime.fromtimestamp(os.path.getmtime(file_path)) \
                .strftime('%Y-%m-%d %H:%M:%S')
            names.append((title, engine, lang, merge, size, time, name))
            cache.close()
        return names

    def _path(self, name):
        if not os.path.exists(self.dir_path):
            os.mkdir(self.dir_path)
        cache_dir = self.cache_path
        if not self.is_persistence():
            cache_dir = self.temp_path
        if not os.path.exists(cache_dir):
            os.mkdir(cache_dir)
        return os.path.join(cache_dir, '%s.db' % name)

    def size(self):
        return os.path.getsize(self.file_path)

    def is_fresh(self):
        return self.fresh

    def get_identity(self):
        return self.identity

    def is_persistence(self):
        return self.persistence

    def set_cache_only(self, cache_only):
        self.cache_only = cache_only

    def set_info(self, key, value):
        self.cursor.execute(
            'INSERT INTO info VALUES (?1, ?2) '
            'ON CONFLICT (KEY) DO UPDATE SET value=excluded.value',
            (key, value))
        self.connection.commit()

    def get_info(self, key):
        resource = self.cursor.execute(
            'SELECT value FROM info WHERE key=?', (key,))
        result = resource.fetchone()
        return result[0] if result else None

    def del_info(self, key):
        self.cursor.execute(
            'DELETE FROM info WHERE key=?', (key,))
        self.connection.commit()

    def save(self, original_group):
        if self.is_fresh():
            for original_unit in original_group:
                self.add(*original_unit)
            self.connection.commit()

    def all(self):
        resource = self.cursor.execute('SELECT * FROM cache WHERE NOT ignored')
        return resource.fetchall()

    def get(self, ids):
        placeholders = ', '.join(['?'] * len(ids))
        resource = self.cursor.execute(
            'SELECT * FROM cache WHERE id IN (%s) ' % placeholders, tuple(ids))
        return resource.fetchall()

    def first(self, **kwargs):
        if kwargs:
            data = ' AND '.join(['%s=?' % column for column in kwargs])
            resource = self.cursor.execute(
                'SELECT * FROM cache WHERE %s' % data, tuple(kwargs.values()))
        else:
            resource = self.cursor.execute('SELECT * FROM cache LIMIT 1')
        return resource.fetchone()

    def add(self, id, md5, raw, original, ignored=False, attributes=None,
            page=None):
        self.cursor.execute(
            'INSERT INTO cache VALUES ('
            '?1, ?2, ?3, ?4, ?5, ?6, ?7, NULL, NULL, NULL'
            ') ON CONFLICT DO NOTHING',
            (id, md5, raw, original, ignored, attributes, page))
        # self.connection.commit()

    def update(self, ids, **kwargs):
        ids = ids if isinstance(ids, list) else [ids]
        data = ', '.join(['%s=?' % column for column in kwargs.keys()])
        placeholders = ', '.join(['?'] * len(ids))
        self.cursor.execute(
            'UPDATE cache SET %s WHERE id IN (%s)' % (data, placeholders),
            tuple(list(kwargs.values()) + ids))
        self.connection.commit()

    def ignore(self, ids):
        self.update(ids, ignored=True)

    def delete(self, ids):
        placeholders = ', '.join(['?'] * len(ids))
        self.cursor.execute(
            'DELETE FROM cache WHERE id IN (%s)' % placeholders, tuple(ids))
        self.connection.commit()

    def close(self):
        self.cursor.close()
        self.connection.commit()
        self.connection.close()

    def destroy(self):
        self.close()
        if os.path.exists(self.file_path):
            os.remove(self.file_path)

    def done(self):
        if not self.persistence:
            self.destroy()

    def paragraph(self, id=None):
        return Paragraph(*self.first(id=id))

    def get_paragraphs(self, ids):
        return [Paragraph(*item) for item in self.get(ids)]

    def all_paragraphs(self):
        paragraphs = []
        for item in self.all():
            paragraph = Paragraph(*item)
            if self.cache_only and not paragraph.translation:
                continue
            paragraphs.append(paragraph)
        return paragraphs

    def update_paragraph(self, paragraph):
        self.update(
            paragraph.id, translation=paragraph.translation,
            engine_name=paragraph.engine_name,
            target_lang=paragraph.target_lang)

    def delete_paragraphs(self, paragraphs):
        self.delete([paragraph.id for paragraph in paragraphs])

    def ignore_paragraphs(self, paragraphs):
        self.ignore([paragraph.id for paragraph in paragraphs])


def get_cache(uid):
    config = get_config()
    return TranslationCache(uid, config.get('cache_enabled') or False)
