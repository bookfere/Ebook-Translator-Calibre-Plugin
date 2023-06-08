import os
import json
import shutil
import sqlite3
import os.path
import tempfile
from glob import glob

from .utils import uid
from .config import get_config
from .element import Extraction


class Paragraph:
    def __init__(self, id, md5, raw, original, ignored=False, attributes=None,
                 page=None, translation=None, engine_name=None,
                 target_lang=None):
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

    def get_attributes(self):
        if self.attributes:
            return json.loads(self.attributes)
        return {}


class TranslationCache:
    """We use two types of cache: one is used temporarily for communication,
    and another one is used to cache translations, which avoids the need for
    retranslation. This is controlled by the parameter `enabled`.
    """
    __version__ = '20230608'

    fresh = True
    dir_path = os.path.join(
        tempfile.gettempdir(), 'com.bookfere.Calibre.EbookTranslator')
    cache_path = os.path.join(dir_path, 'cache')
    temp_path = os.path.join(dir_path, 'temp')

    def __init__(self, identity, persistence=True):
        self.persistence = persistence
        self.file_path = self._path(
            uid(identity + self.__version__ + Extraction.__version__))
        if os.path.exists(self.file_path):
            self.fresh = False
        self.cache_only = False
        self.connection = sqlite3.connect(self.file_path)
        self.cursor = self.connection.cursor()
        self.cursor.execute(
            'CREATE TABLE IF NOT EXISTS cache('
            'id UNIQUE, md5 UNIQUE, raw, original, ignored, '
            'attributes DEFAULT NULL, page DEFAULT NULL,'
            'translation DEFAULT NULL, engine_name DEFAULT NULL, '
            'target_lang DEFAULT NULL)')

    @classmethod
    def count(cls):
        total = 0
        for cache in glob(os.path.join(cls.cache_path, '*.db')):
            total += os.path.getsize(cache)
        return '%sMB' % round(float(total) / (1000 ** 2), 2)

    @classmethod
    def clean(cls):
        shutil.rmtree(cls.dir_path, ignore_errors=True)

    @classmethod
    def get_dir(cls):
        return cls.dir_path

    def is_fresh(self):
        return self.fresh

    def is_persistence(self):
        return self.persistence

    def set_cache_only(self, cache_only):
        self.cache_only = cache_only

    def _path(self, name):
        if not os.path.exists(self.dir_path):
            os.mkdir(self.dir_path)
        cache_dir = self.cache_path
        if not self.is_persistence():
            cache_dir = self.temp_path
        if not os.path.exists(cache_dir):
            os.mkdir(cache_dir)
        return os.path.join(cache_dir, '%s.db' % name)

    def save(self, original_group):
        if self.is_fresh():
            for original_unit in original_group:
                self.add(*original_unit)

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
            # 'ON CONFLICT (md5) DO UPDATE SET original=excluded.original',
            # 'translation=excluded.translation, '
            # 'engine_name=excluded.engine_name, '
            # 'target_lang=excluded.target_lang',
            (id, md5, raw, original, ignored, attributes, page))
        self.connection.commit()

    def update(self, ids, **kwargs):
        ids = ids if isinstance(ids, list) else [ids]
        data = ', '.join(['%s=?' % column for column in kwargs])
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
        self.connection.commit()
        self.connection.close()

    def destroy(self):
        self.close()
        os.path.exists(self.file_path) and os.remove(self.file_path)

    def done(self):
        self.persistence or self.destroy()

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
    return TranslationCache(uid, get_config().get('cache_enabled'))
