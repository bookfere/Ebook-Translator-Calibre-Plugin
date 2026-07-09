import json
import unittest
from unittest.mock import Mock, patch, call

from ...lib.cache import Paragraph
from ...lib.exception import TranslationCanceled, TranslationFailed
from ...lib.novel import (
    Chapter, ChapterBuilder, TokenBudget, ContextManager, NovelTranslator,
    tag_paragraphs, parse_tagged_response, _extract_json_object,
    _extract_entities_fallback,
    novel_cache_id, _href_to_page_id,
    INFO_NOVEL_SUMMARIES, INFO_NOVEL_GLOSSARY, INFO_NOVEL_PROGRESS,
    INFO_NOVEL_MODE)


module_name = 'calibre_plugins.ebook_translator.lib.novel'


def make_paragraph(pid, text, page='p1', ignored=False):
    """Build a Paragraph suitable for novel-mode tests."""
    return Paragraph(
        pid, 'md5-%s' % pid, text, text, ignored=ignored, page=page)


class MockTocNode:
    """Mimic calibre.ebooks.oeb.base.TOC nodes just enough for the tests."""

    def __init__(self, title, href, children=None):
        self.title = title
        self.href = href
        self.nodes = list(children or [])


class MockManifestItem:
    def __init__(self, item_id, href):
        self.id = item_id
        self.href = href


# ---------------------------------------------------------------------------
# _href_to_page_id
# ---------------------------------------------------------------------------


class TestHrefToPageId(unittest.TestCase):
    def setUp(self):
        self.items = [
            MockManifestItem('a', 'OEBPS/ch1.xhtml'),
            MockManifestItem('b', 'OEBPS/ch2.xhtml'),
            MockManifestItem('c', 'OEBPS/ch3.xhtml'),
        ]

    def test_exact_match(self):
        self.assertEqual('a', _href_to_page_id(
            'OEBPS/ch1.xhtml', self.items))

    def test_fragment_stripped(self):
        self.assertEqual('b', _href_to_page_id(
            'OEBPS/ch2.xhtml#section-3', self.items))

    def test_basename_fallback(self):
        self.assertEqual('c', _href_to_page_id('ch3.xhtml', self.items))

    def test_empty_href(self):
        self.assertIsNone(_href_to_page_id('', self.items))
        self.assertIsNone(_href_to_page_id(None, self.items))

    def test_unknown(self):
        self.assertIsNone(_href_to_page_id('unknown.xhtml', self.items))


# ---------------------------------------------------------------------------
# ChapterBuilder
# ---------------------------------------------------------------------------


class TestChapterBuilder(unittest.TestCase):
    def setUp(self):
        # Three xhtml pages, spine order = a, b, c.
        self.pages = ['a', 'b', 'c']
        self.items = [
            MockManifestItem('a', 'OEBPS/ch1.xhtml'),
            MockManifestItem('b', 'OEBPS/ch2.xhtml'),
            MockManifestItem('c', 'OEBPS/ch3.xhtml'),
        ]
        self.paragraphs = [
            make_paragraph(0, 'Alpha paragraph one with enough text to pass the front-matter filter.',
                           page='a'),
            make_paragraph(1, 'Alpha paragraph two with enough text to pass the front-matter filter.',
                           page='a'),
            make_paragraph(2, 'Beta paragraph one with enough text to pass the front-matter filter.',
                           page='b'),
            make_paragraph(3, 'Beta paragraph two with enough text to pass the front-matter filter.',
                           page='b'),
            make_paragraph(
                4,
                'Gamma paragraph one: this single paragraph is intentionally long '
                'so that the front-matter filter (default 100 chars) does not '
                'exclude the page from chapter content.',
                page='c'),
            # Aux metadata paragraphs, should be filtered out.
            make_paragraph(5, 'Book title', page='content.opf'),
            make_paragraph(6, 'TOC title', page='toc.ncx'),
        ]

    def test_toc_level_1(self):
        toc = [
            MockTocNode('Chapter One', 'OEBPS/ch1.xhtml'),
            MockTocNode('Chapter Two', 'OEBPS/ch2.xhtml'),
            MockTocNode('Chapter Three', 'OEBPS/ch3.xhtml'),
        ]
        chapters = ChapterBuilder(
            self.pages, toc, self.items, self.paragraphs).build()
        self.assertEqual(3, len(chapters))
        self.assertEqual([1, 2, 3], [c.index for c in chapters])
        self.assertEqual(
            ['Chapter One', 'Chapter Two', 'Chapter Three'],
            [c.title for c in chapters])
        self.assertEqual(2, len(chapters[0].paragraphs))
        self.assertEqual(2, len(chapters[1].paragraphs))
        self.assertEqual(1, len(chapters[2].paragraphs))
        # Aux paragraphs must not leak into chapters.
        for c in chapters:
            for p in c.paragraphs:
                self.assertNotIn(p.page, ChapterBuilder.AUX_PAGES)

    def test_toc_level_1_only_ignores_nested(self):
        # Only the top-level nodes should define chapter boundaries; a
        # nested subnode inside "Chapter One" must not split the chapter.
        toc = [
            MockTocNode('Chapter One', 'OEBPS/ch1.xhtml', [
                MockTocNode('Section 1.1', 'OEBPS/ch2.xhtml')]),
            MockTocNode('Chapter Two', 'OEBPS/ch3.xhtml'),
        ]
        chapters = ChapterBuilder(
            self.pages, toc, self.items, self.paragraphs).build()
        self.assertEqual(2, len(chapters))
        # Chapter One should now include pages a and b.
        self.assertEqual(['a', 'b'], chapters[0].page_ids)
        self.assertEqual(['c'], chapters[1].page_ids)

    def test_fallback_to_files_when_toc_empty(self):
        chapters = ChapterBuilder(
            self.pages, [], self.items, self.paragraphs).build()
        self.assertEqual(3, len(chapters))
        # Titles derive from first paragraph text (truncated to 80 chars).
        self.assertTrue(chapters[0].title.startswith('Alpha paragraph one'),
                        chapters[0].title)
        self.assertTrue(chapters[1].title.startswith('Beta paragraph one'),
                        chapters[1].title)
        self.assertTrue(chapters[2].title.startswith('Gamma paragraph one'),
                        chapters[2].title)

    def test_fallback_when_toc_has_single_node(self):
        toc = [MockTocNode('Only', 'OEBPS/ch1.xhtml')]
        chapters = ChapterBuilder(
            self.pages, toc, self.items, self.paragraphs).build()
        # Falls back to xhtml file mode -> 3 chapters, not 1.
        self.assertEqual(3, len(chapters))

    def test_page_before_first_boundary_goes_to_chapter_1(self):
        # TOC starts at ch2 but page 'a' exists in the spine.
        toc = [
            MockTocNode('Chapter Two', 'OEBPS/ch2.xhtml'),
            MockTocNode('Chapter Three', 'OEBPS/ch3.xhtml'),
        ]
        chapters = ChapterBuilder(
            self.pages, toc, self.items, self.paragraphs).build()
        self.assertEqual(2, len(chapters))
        self.assertIn('a', chapters[0].page_ids)
        self.assertIn('b', chapters[0].page_ids)
        self.assertIn('c', chapters[1].page_ids)

    def test_toc_with_bad_href_is_skipped(self):
        toc = [
            MockTocNode('Chapter One', 'OEBPS/ch1.xhtml'),
            MockTocNode('Broken', 'does_not_exist.xhtml'),
            MockTocNode('Chapter Two', 'OEBPS/ch2.xhtml'),
        ]
        chapters = ChapterBuilder(
            self.pages, toc, self.items, self.paragraphs).build()
        # Broken href yields 2 usable boundaries, not 3.
        self.assertEqual(2, len(chapters))

    def test_aux_paragraphs_collected_separately(self):
        builder = ChapterBuilder(
            self.pages, [], self.items, self.paragraphs)
        self.assertEqual(2, len(builder.aux_paragraphs))
        pages = {p.page for p in builder.aux_paragraphs}
        self.assertEqual({'content.opf', 'toc.ncx'}, pages)

    def test_ignored_paragraphs_kept_but_not_counted(self):
        paragraphs = list(self.paragraphs)
        paragraphs[0].ignored = True  # First 'a' paragraph is ignored.
        chapters = ChapterBuilder(
            self.pages, [], self.items, paragraphs,
            front_matter_min_chars=0).build()
        # It still travels through the pipeline so DOM re-assembly can run.
        self.assertEqual(2, len(chapters[0].paragraphs))
        # But translatable count reflects the ignored flag.
        self.assertEqual(1, len(chapters[0].translatable_paragraphs()))

    def test_empty_spine(self):
        chapters = ChapterBuilder([], [], [], []).build()
        self.assertEqual([], chapters)

    def test_char_count(self):
        chapter = Chapter(1, 't', ['a'], [
            make_paragraph(0, 'hello'),
            make_paragraph(1, 'world!', ignored=True),
            make_paragraph(2, ''),
        ])
        # Only non-ignored paragraphs contribute.
        self.assertEqual(len('hello') + 0, chapter.char_count)

    # -- toc_level_2 ----------------------------------------------------------

    def _pages_and_items_for_anthology(self):
        """Return spine/items for a minimal 2-book anthology.

        Structure mirrors a real anthology EPUB:
          spine: cover_b1, ch1_b1, ch2_b1, cover_b2, ch1_b2
          TOC level-1: Book1 -> cover_b1, Book2 -> cover_b2
          TOC level-2: Ch1 -> ch1_b1, Ch2 -> ch2_b1, Ch1b2 -> ch1_b2
        """
        pages = ['cover_b1', 'ch1_b1', 'ch2_b1', 'cover_b2', 'ch1_b2']
        items = [
            MockManifestItem('cover_b1', 'book1/cover.xhtml'),
            MockManifestItem('ch1_b1', 'book1/chapter1.xhtml'),
            MockManifestItem('ch2_b1', 'book1/chapter2.xhtml'),
            MockManifestItem('cover_b2', 'book2/cover.xhtml'),
            MockManifestItem('ch1_b2', 'book2/chapter1.xhtml'),
        ]
        return pages, items

    def test_toc_level2_splits_anthology_into_narrative_chapters(self):
        pages, items = self._pages_and_items_for_anthology()
        # Level-1 TOC nodes each have level-2 children.
        toc = [
            MockTocNode('Book One', 'book1/cover.xhtml', [
                MockTocNode('Chapter One', 'book1/chapter1.xhtml'),
                MockTocNode('Chapter Two', 'book1/chapter2.xhtml'),
            ]),
            MockTocNode('Book Two', 'book2/cover.xhtml', [
                MockTocNode('Chapter One', 'book2/chapter1.xhtml'),
            ]),
        ]
        paragraphs = [
            make_paragraph(0, 'x' * 200, page='ch1_b1'),
            make_paragraph(1, 'x' * 200, page='ch2_b1'),
            make_paragraph(2, 'x' * 200, page='ch1_b2'),
            # Cover pages: short text (< 100 chars)
            make_paragraph(3, 'Book One', page='cover_b1'),
            make_paragraph(4, 'Book Two', page='cover_b2'),
        ]
        builder = ChapterBuilder(
            pages, toc, items, paragraphs, source='toc_level_2',
            front_matter_min_chars=0)  # disable front-matter filter here
        chapters = builder.build()
        # 3 level-2 chapters: Ch1/B1, Ch2/B1, Ch1/B2
        self.assertEqual(3, len(chapters))
        self.assertEqual('Chapter One', chapters[0].title)
        self.assertEqual('Chapter Two', chapters[1].title)
        self.assertEqual('Chapter One', chapters[2].title)

    def test_toc_level2_fallback_to_level1_when_no_children(self):
        """If level-2 has fewer than 2 entries, fall back to level-1."""
        pages, items = self._pages_and_items_for_anthology()
        toc = [
            MockTocNode('Book One', 'book1/cover.xhtml'),  # no children
            MockTocNode('Book Two', 'book2/cover.xhtml'),  # no children
        ]
        paragraphs = [make_paragraph(i, 'text', page=p)
                      for i, p in enumerate(pages)]
        builder = ChapterBuilder(
            pages, toc, items, paragraphs, source='toc_level_2',
            front_matter_min_chars=0)
        chapters = builder.build()
        # Falls back to level-1 -> 2 chapters
        self.assertEqual(2, len(chapters))
        self.assertEqual('Book One', chapters[0].title)

    # -- front-matter filter --------------------------------------------------

    def test_front_matter_filter_excludes_short_pages(self):
        """Pages with very little text are excluded from chapter content."""
        pages = ['cover', 'ch1', 'ch2']
        items = [
            MockManifestItem('cover', 'cover.xhtml'),
            MockManifestItem('ch1', 'chapter1.xhtml'),
            MockManifestItem('ch2', 'chapter2.xhtml'),
        ]
        toc = [
            MockTocNode('Ch1', 'chapter1.xhtml'),
            MockTocNode('Ch2', 'chapter2.xhtml'),
        ]
        paragraphs = [
            # Cover page: 8 chars only (below threshold 100)
            make_paragraph(0, 'THE BOOK', page='cover'),
            # Narrative pages: plenty of text
            make_paragraph(1, 'x' * 200, page='ch1'),
            make_paragraph(2, 'x' * 150, page='ch2'),
        ]
        builder = ChapterBuilder(
            pages, toc, items, paragraphs, source='toc_level_1',
            front_matter_min_chars=100)
        chapters = builder.build()
        self.assertEqual(2, len(chapters))
        # The cover page paragraph must not appear in any chapter.
        for ch in chapters:
            for p in ch.paragraphs:
                self.assertNotEqual('cover', p.page,
                    'Cover page paragraph leaked into chapter content')

    def test_front_matter_filter_zero_disables(self):
        """Setting front_matter_min_chars=0 disables the filter entirely."""
        pages = ['cover', 'ch1']
        items = [
            MockManifestItem('cover', 'cover.xhtml'),
            MockManifestItem('ch1', 'chapter1.xhtml'),
        ]
        toc = [MockTocNode('Ch1', 'chapter1.xhtml'),
               MockTocNode('Cover', 'cover.xhtml')]
        paragraphs = [
            make_paragraph(0, 'THE BOOK', page='cover'),  # short
            make_paragraph(1, 'x' * 200, page='ch1'),
        ]
        builder = ChapterBuilder(
            pages, toc, items, paragraphs, source='toc_level_1',
            front_matter_min_chars=0)
        chapters = builder.build()
        # With filter disabled, cover paragraph must appear in chapter 2
        all_pages = {p.page for ch in chapters for p in ch.paragraphs}
        self.assertIn('cover', all_pages)

    def test_front_matter_long_pages_not_excluded(self):
        """Pages with enough text are kept even with the filter enabled."""
        pages = ['ch1', 'ch2']
        items = [
            MockManifestItem('ch1', 'chapter1.xhtml'),
            MockManifestItem('ch2', 'chapter2.xhtml'),
        ]
        toc = [MockTocNode('Ch1', 'chapter1.xhtml'),
               MockTocNode('Ch2', 'chapter2.xhtml')]
        paragraphs = [
            make_paragraph(0, 'x' * 200, page='ch1'),  # 200 chars > 100
            make_paragraph(1, 'x' * 150, page='ch2'),
        ]
        builder = ChapterBuilder(
            pages, toc, items, paragraphs, source='toc_level_1',
            front_matter_min_chars=100)
        chapters = builder.build()
        all_pages = {p.page for ch in chapters for p in ch.paragraphs}
        self.assertIn('ch1', all_pages)
        self.assertIn('ch2', all_pages)


# ---------------------------------------------------------------------------
# TokenBudget
# ---------------------------------------------------------------------------


class TestTokenBudget(unittest.TestCase):
    def test_estimate_latin(self):
        budget = TokenBudget()
        # ~4 chars/token on latin text.
        self.assertGreater(budget.estimate('hello world!'), 0)
        self.assertLess(budget.estimate('hello world!'), 10)

    def test_estimate_cjk(self):
        budget = TokenBudget()
        # 4 CJK characters -> ~2 tokens with ratio_cjk=2.
        cjk_text = '你好世界'
        self.assertGreaterEqual(budget.estimate(cjk_text), 2)

    def test_estimate_empty(self):
        self.assertEqual(0, TokenBudget().estimate(''))
        self.assertEqual(0, TokenBudget().estimate(None))

    def test_budget_minimum(self):
        # Very small budgets are clamped to at least 100.
        budget = TokenBudget(budget=10)
        self.assertEqual(100, budget.budget)

    def test_chunk_single_fit(self):
        paragraphs = [
            make_paragraph(0, 'short one'),
            make_paragraph(1, 'short two'),
            make_paragraph(2, 'short three'),
        ]
        budget = TokenBudget(budget=8000)
        chunks = budget.chunk(paragraphs, reserved=0)
        self.assertEqual(1, len(chunks))
        self.assertEqual(3, len(chunks[0]))

    def test_chunk_splits_when_needed(self):
        # A tiny budget will force multiple chunks.
        paragraphs = [
            make_paragraph(0, 'x' * 400),
            make_paragraph(1, 'y' * 400),
            make_paragraph(2, 'z' * 400),
        ]
        # 400 chars / 4 ~= 100 tokens per paragraph.
        budget = TokenBudget(budget=200)
        chunks = budget.chunk(paragraphs, reserved=0)
        self.assertGreater(len(chunks), 1)
        # Total paragraphs preserved.
        total = sum(len(c) for c in chunks)
        self.assertEqual(3, total)

    def test_chunk_never_splits_paragraph(self):
        paragraphs = [make_paragraph(0, 'x' * 100000)]  # ~25k tokens
        budget = TokenBudget(budget=200)
        chunks = budget.chunk(paragraphs, reserved=0)
        self.assertEqual(1, len(chunks))
        self.assertEqual(1, len(chunks[0]))

    def test_chunk_reserves_headroom(self):
        paragraphs = [make_paragraph(i, 'x' * 400) for i in range(10)]
        # 8000 budget, reserved 7500 -> only 500 tokens available.
        # Each paragraph ~100 tokens -> at most ~5 per chunk.
        budget = TokenBudget(budget=8000)
        chunks = budget.chunk(paragraphs, reserved=7500)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 5)

    def test_chunk_carries_ignored_paragraphs(self):
        paragraphs = [
            make_paragraph(0, 'text 1'),
            make_paragraph(1, '', ignored=True),
            make_paragraph(2, 'text 2'),
        ]
        chunks = TokenBudget(budget=8000).chunk(paragraphs, reserved=0)
        self.assertEqual(1, len(chunks))
        # All paragraphs (including ignored) are still present.
        self.assertEqual(3, len(chunks[0]))

    # -- dual-cap chunking ------------------------------------------------

    def test_chunk_capped_by_max_paragraphs(self):
        # 100 very short paragraphs, small token weight but many tags.
        # Cap tokens is generous (8000) so the paragraph cap should fire.
        paragraphs = [make_paragraph(i, 'short') for i in range(100)]
        budget = TokenBudget(budget=8000, max_paragraphs=30)
        chunks = budget.chunk(paragraphs, reserved=0)
        # 100 / 30 = ceil(3.33) => 4 chunks.
        self.assertEqual(4, len(chunks))
        for c in chunks:
            # Each chunk must not exceed the paragraph cap.
            self.assertLessEqual(len(c), 30)

    def test_chunk_capped_by_tokens(self):
        # Few very large paragraphs: token cap should fire first.
        paragraphs = [make_paragraph(i, 'x' * 3000) for i in range(5)]
        # Very small token budget forces splitting on tokens.
        budget = TokenBudget(budget=200, max_paragraphs=60)
        chunks = budget.chunk(paragraphs, reserved=0)
        # Oversized paragraphs become singleton chunks -> 5 chunks.
        self.assertGreater(len(chunks), 1)
        # No chunk should hold more than one paragraph in this case.
        for c in chunks:
            self.assertEqual(1, len(c))

    def test_chunk_max_paragraphs_zero_disables_cap(self):
        # Many short paragraphs, generous token budget, cap=0 -> single chunk.
        paragraphs = [make_paragraph(i, 'short') for i in range(200)]
        budget = TokenBudget(budget=100000, max_paragraphs=0)
        chunks = budget.chunk(paragraphs, reserved=0)
        self.assertEqual(1, len(chunks))
        self.assertEqual(200, len(chunks[0]))

    def test_chunk_default_max_paragraphs(self):
        # Default is 80: with structured JSON output the model reliably
        # follows alignment markers at this count, making it the appropriate
        # default for capable engines (ChatGPT, Gemini, Ollama 0.31+).
        budget = TokenBudget(budget=8000)
        self.assertEqual(80, budget.max_paragraphs)

    def test_chunk_with_stats_reports_reason(self):
        # 70 short paragraphs, generous token budget, cap=60.
        # First chunk closed by paragraphs, second by end of stream.
        paragraphs = [make_paragraph(i, 'short') for i in range(70)]
        budget = TokenBudget(budget=100000, max_paragraphs=60)
        stats = budget.chunk_with_stats(paragraphs, reserved=0)
        self.assertEqual(2, len(stats))
        # (chunk, tokens, reason)
        self.assertEqual(TokenBudget.REASON_PARAGRAPHS, stats[0][2])
        self.assertEqual(TokenBudget.REASON_END, stats[-1][2])
        # First chunk has exactly 60 paragraphs (the cap).
        self.assertEqual(60, len(stats[0][0]))

    def test_chunk_with_stats_token_reason(self):
        # Trigger token-based closure with small budget.
        paragraphs = [make_paragraph(i, 'x' * 400) for i in range(10)]
        # 400 chars / 4 ~= 100 tokens per paragraph.
        budget = TokenBudget(budget=250, max_paragraphs=60)
        stats = budget.chunk_with_stats(paragraphs, reserved=0)
        # At least the first split should be token-driven.
        reasons = [s[2] for s in stats[:-1]]
        self.assertIn(TokenBudget.REASON_TOKENS, reasons)

    def test_chunk_ignored_do_not_count_toward_paragraph_cap(self):
        # 5 translatable + 55 ignored + 5 translatable = 10 translatable
        # but 65 total. With max_paragraphs=60 the cap should NOT fire
        # because ignored paragraphs do not consume the budget.
        paragraphs = []
        for i in range(5):
            paragraphs.append(make_paragraph(i, 'text'))
        for i in range(5, 60):
            paragraphs.append(make_paragraph(i, '', ignored=True))
        for i in range(60, 65):
            paragraphs.append(make_paragraph(i, 'text'))
        budget = TokenBudget(budget=100000, max_paragraphs=60)
        chunks = budget.chunk(paragraphs, reserved=0)
        # All 65 paragraphs (including ignored) fit in a single chunk.
        self.assertEqual(1, len(chunks))
        self.assertEqual(65, len(chunks[0]))


# ---------------------------------------------------------------------------
# ContextManager
# ---------------------------------------------------------------------------


class TestContextManager(unittest.TestCase):
    def setUp(self):
        self.cache = Mock()
        self.cache.get_info.return_value = None

    def test_load_empty(self):
        ctx = ContextManager(self.cache).load()
        self.assertEqual([], ctx.get_summaries())
        self.assertEqual({}, ctx.get_glossary())
        self.assertEqual(0, ctx.get_progress())
        # load() also marks the cache as novel-mode.
        self.cache.set_info.assert_any_call(INFO_NOVEL_MODE, '1')

    def test_load_existing(self):
        summaries = [{'chapter': 1, 'title': 'a', 'summary': 'ok'}]
        glossary = {'Frodo': {
            'translation': 'Frodo', 'type': 'character', 'notes': 'hobbit'}}
        self.cache.get_info.side_effect = lambda key: {
            INFO_NOVEL_SUMMARIES: json.dumps(summaries),
            INFO_NOVEL_GLOSSARY: json.dumps(glossary),
            INFO_NOVEL_PROGRESS: '1',
        }.get(key)
        ctx = ContextManager(self.cache).load()
        self.assertEqual(summaries, ctx.get_summaries())
        self.assertEqual(glossary, ctx.get_glossary())
        self.assertEqual(1, ctx.get_progress())

    def test_load_handles_corrupted_json(self):
        self.cache.get_info.side_effect = lambda key: {
            INFO_NOVEL_SUMMARIES: 'not json',
            INFO_NOVEL_GLOSSARY: '[not a dict]',
            INFO_NOVEL_PROGRESS: 'garbage',
        }.get(key)
        ctx = ContextManager(self.cache).load()
        self.assertEqual([], ctx.get_summaries())
        self.assertEqual({}, ctx.get_glossary())
        self.assertEqual(0, ctx.get_progress())

    def test_append_chapter(self):
        ctx = ContextManager(self.cache).load()
        ctx.append_chapter(1, 'The Ring', 'Frodo gets the ring.', [
            {'source': 'Frodo', 'translation': 'Frodo',
             'type': 'character', 'notes': 'hobbit'},
            {'source': 'The Shire', 'translation': 'La Contea',
             'type': 'place'},
        ])
        summaries = ctx.get_summaries()
        self.assertEqual(1, len(summaries))
        self.assertEqual('Frodo gets the ring.', summaries[0]['summary'])
        glossary = ctx.get_glossary()
        self.assertIn('Frodo', glossary)
        self.assertEqual('La Contea', glossary['The Shire']['translation'])
        self.assertEqual(1, ctx.get_progress())
        # Persistence: three set_info calls (summaries, glossary, progress).
        keys = [c.args[0] for c in self.cache.set_info.call_args_list]
        self.assertIn(INFO_NOVEL_SUMMARIES, keys)
        self.assertIn(INFO_NOVEL_GLOSSARY, keys)
        self.assertIn(INFO_NOVEL_PROGRESS, keys)

    def test_append_chapter_ignores_malformed_entities(self):
        ctx = ContextManager(self.cache).load()
        ctx.append_chapter(1, 't', 's', [
            {'source': 'Ok', 'translation': 'Ok'},
            {'source': '', 'translation': 'nope'},      # empty source
            {'source': 'X', 'translation': ''},         # empty translation
            'not a dict',
            {'source': 'Y'},                             # missing translation
        ])
        self.assertEqual(['Ok'], list(ctx.get_glossary().keys()))

    def test_glossary_cap_fifo(self):
        ctx = ContextManager(self.cache, glossary_max_entries=3).load()
        ctx.append_chapter(1, 't', 's', [
            {'source': 'A', 'translation': 'A'},
            {'source': 'B', 'translation': 'B'},
            {'source': 'C', 'translation': 'C'},
        ])
        self.assertEqual(3, len(ctx.get_glossary()))
        ctx.append_chapter(2, 't', 's', [
            {'source': 'D', 'translation': 'D'},
        ])
        keys = list(ctx.get_glossary().keys())
        self.assertEqual(3, len(keys))
        self.assertNotIn('A', keys)  # Oldest dropped.
        self.assertIn('D', keys)

    def test_progress_never_decreases(self):
        ctx = ContextManager(self.cache).load()
        ctx.append_chapter(3, 't', 's')
        self.assertEqual(3, ctx.get_progress())
        ctx.append_chapter(2, 't', 's')  # Retro-append should not lower.
        self.assertEqual(3, ctx.get_progress())

    def test_context_text_basic(self):
        ctx = ContextManager(self.cache).load()
        ctx.append_chapter(1, 'Prologue', 'Something happens.', [
            {'source': 'Bilbo', 'translation': 'Bilbo',
             'type': 'character'},
        ])
        text = ctx.context_text(budget_tokens=2000)
        self.assertIn('Prologue', text)
        self.assertIn('Something happens.', text)
        self.assertIn('Bilbo', text)

    def test_context_text_truncation(self):
        ctx = ContextManager(self.cache).load()
        # Fill with many long summaries; small budget forces trimming.
        for i in range(10):
            ctx.append_chapter(
                i + 1, 'T%d' % i, 'x' * 500,
                [{'source': 'K%d' % i, 'translation': 'V%d' % i}])
        # Budget of 100 tokens ~= 400 chars.
        text = ctx.context_text(budget_tokens=100)
        # It should never be empty and always contain the header labels.
        self.assertTrue(text)

    def test_replace_glossary(self):
        ctx = ContextManager(self.cache).load()
        ctx.append_chapter(1, 't', 's', [
            {'source': 'A', 'translation': 'A'},
        ])
        ctx.replace_glossary({
            'B': {'translation': 'B', 'type': 'character'},
            'Bad': {'translation': ''},  # dropped: missing translation
            'Weird': 'not a dict',        # dropped: wrong type
        })
        self.assertEqual({'B'}, set(ctx.get_glossary().keys()))

    def test_reset(self):
        ctx = ContextManager(self.cache).load()
        ctx.append_chapter(2, 't', 's', [
            {'source': 'A', 'translation': 'A'}])
        ctx.reset()
        self.assertEqual([], ctx.get_summaries())
        self.assertEqual({}, ctx.get_glossary())
        self.assertEqual(0, ctx.get_progress())


# ---------------------------------------------------------------------------
# tag_paragraphs / parse_tagged_response
# ---------------------------------------------------------------------------


class TestTagging(unittest.TestCase):
    def test_tag_paragraphs_basic(self):
        paragraphs = [
            make_paragraph(0, 'First.'),
            make_paragraph(1, 'Second.'),
            make_paragraph(2, 'Third.'),
        ]
        tagged, indices = tag_paragraphs(paragraphs)
        self.assertEqual([1, 2, 3], indices)
        self.assertIn('[1]\nFirst.', tagged)
        self.assertIn('[2]\nSecond.', tagged)
        self.assertIn('[3]\nThird.', tagged)

    def test_tag_paragraphs_skips_ignored(self):
        paragraphs = [
            make_paragraph(0, 'A'),
            make_paragraph(1, 'B', ignored=True),
            make_paragraph(2, 'C'),
        ]
        tagged, indices = tag_paragraphs(paragraphs)
        # Indices count the *paragraphs list* position, not translated count.
        self.assertEqual([1, 3], indices)
        self.assertIn('[1]\nA', tagged)
        self.assertIn('[3]\nC', tagged)
        self.assertNotIn('[2]', tagged)

    def test_parse_tagged_response(self):
        response = (
            "Sure, here is the translation:\n"
            "[1]\nPrimo.\n\n"
            "[2]\nSecondo.\n\n"
            "[3]\nTerzo.\n\nEnd of translation.")
        parsed = parse_tagged_response(response, [1, 2, 3])
        self.assertEqual({1: 'Primo.', 2: 'Secondo.', 3: 'Terzo.'}, parsed)

    def test_parse_tagged_response_multiline(self):
        response = (
            "[1]\nLine one.\nLine two.\n\n"
            "[2]\nAlone.")
        parsed = parse_tagged_response(response, [1, 2])
        self.assertEqual(2, len(parsed))
        self.assertIn('Line one.', parsed[1])
        self.assertIn('Line two.', parsed[1])
        self.assertEqual('Alone.', parsed[2])

    def test_parse_tagged_response_missing(self):
        response = "[1]\nOnly one."
        parsed = parse_tagged_response(response, [1, 2, 3])
        self.assertEqual({1: 'Only one.'}, parsed)

    def test_parse_tagged_response_ignores_hallucinated_tags(self):
        response = "[1]\nReal.\n\n[5]\nHallucinated."
        parsed = parse_tagged_response(response, [1, 2])
        # Marker 5 was not expected; ignored.
        self.assertEqual({1: 'Real.'}, parsed)

    def test_parse_tagged_response_empty(self):
        self.assertEqual({}, parse_tagged_response('', [1]))
        self.assertEqual({}, parse_tagged_response(None, [1]))

    def test_parse_tagged_response_extra_whitespace(self):
        response = (
            "\n\n  [1]  \nPrimo paragrafo.\n\n\n"
            "  [2]\nSecondo.\n")
        parsed = parse_tagged_response(response, [1, 2])
        self.assertEqual('Primo paragrafo.', parsed[1])
        self.assertEqual('Secondo.', parsed[2])

    def test_parse_tagged_response_duplicate_marker_last_wins(self):
        response = "[1]\nFirst try.\n\n[1]\nBetter version."
        parsed = parse_tagged_response(response, [1])
        self.assertEqual('Better version.', parsed[1])


# ---------------------------------------------------------------------------
# _extract_json_object
# ---------------------------------------------------------------------------


class TestExtractJson(unittest.TestCase):
    def test_clean_json(self):
        self.assertEqual(
            {'a': 1}, _extract_json_object('{"a": 1}'))

    def test_with_prose_prefix(self):
        self.assertEqual(
            {'entities': []},
            _extract_json_object('Here is the JSON:\n{"entities": []}'))

    def test_with_code_fence(self):
        self.assertEqual(
            {'x': 'y'},
            _extract_json_object('```json\n{"x": "y"}\n```'))

    def test_ignores_braces_in_strings(self):
        self.assertEqual(
            {'text': 'this { is not } a brace'},
            _extract_json_object('{"text": "this { is not } a brace"}'))

    def test_returns_none_when_invalid(self):
        self.assertIsNone(_extract_json_object('no json here'))
        self.assertIsNone(_extract_json_object(''))
        self.assertIsNone(_extract_json_object(None))
        self.assertIsNone(_extract_json_object('{"broken":'))


class TestExtractEntitiesFallback(unittest.TestCase):
    def test_arrow_syntax(self):
        text = (
            'Here are some entities:\n'
            '"Aslan" -> "Aslan" (character): the lion king\n'
            '"Narnia" -> "Narnia" (place)\n'
            'End of list.')
        entities = _extract_entities_fallback(text)
        sources = [e['source'] for e in entities]
        self.assertIn('Aslan', sources)
        self.assertIn('Narnia', sources)

    def test_double_arrow_syntax(self):
        text = 'Aslan => Aslan (character) - the lion'
        entities = _extract_entities_fallback(text)
        self.assertTrue(
            any(e['source'] == 'Aslan' for e in entities))

    def test_unicode_arrow(self):
        text = '"Frodo" → "Frodo" (character): the hobbit'
        entities = _extract_entities_fallback(text)
        self.assertTrue(
            any(e['source'] == 'Frodo' for e in entities))

    def test_skips_prose_lines(self):
        text = (
            'This sentence has many words but is not an entity mapping.\n'
            'Here are the entities I extracted from the chapter:')
        entities = _extract_entities_fallback(text)
        # No entity mapping in prose (no ``->`` separator).
        self.assertEqual([], entities)

    def test_empty_returns_empty(self):
        self.assertEqual([], _extract_entities_fallback(''))
        self.assertEqual([], _extract_entities_fallback(None))

    def test_dedup_by_source(self):
        text = (
            '"Aslan" -> "Aslan" (character): king\n'
            '"Aslan" -> "Aslan" (character): duplicate line')
        entities = _extract_entities_fallback(text)
        self.assertEqual(
            1, sum(1 for e in entities if e['source'] == 'Aslan'))


# ---------------------------------------------------------------------------
# novel_cache_id
# ---------------------------------------------------------------------------


class TestNovelCacheId(unittest.TestCase):
    def test_deterministic(self):
        a = novel_cache_id('/b.epub', 'ChatGPT', 'Italian', '')
        b = novel_cache_id('/b.epub', 'ChatGPT', 'Italian', '')
        self.assertEqual(a, b)

    def test_differs_from_classic(self):
        from ...lib.utils import uid
        classic = uid('/b.epub' + 'ChatGPT' + 'Italian' + '1800' + '')
        novel = novel_cache_id('/b.epub', 'ChatGPT', 'Italian', '')
        self.assertNotEqual(classic, novel)

    def test_encoding_included(self):
        a = novel_cache_id('/b.epub', 'ChatGPT', 'Italian', '')
        b = novel_cache_id('/b.epub', 'ChatGPT', 'Italian', 'gbk')
        self.assertNotEqual(a, b)


# ---------------------------------------------------------------------------
# NovelTranslator
# ---------------------------------------------------------------------------


def _echo_markers(text, suffix=' (IT)'):
    """Test helper: echo back the [N] markers found in ``text``, appending
    ``suffix`` to each paragraph body. Simulates a well-behaved LLM that
    respects the numbered-marker translation format.
    """
    import re
    result = []
    for m in re.finditer(
            r'^\s*\[(\d+)\]\s*\n(.*?)(?=\n\s*\[\d+\]|\Z)',
            text, re.MULTILINE | re.DOTALL):
        result.append('[%s]\n%s%s' % (
            m.group(1), m.group(2).strip(), suffix))
    return '\n\n'.join(result)


def _is_translation_call(prompt):
    """The novel translator uses distinct system prompts for the three
    call kinds:

      * Translation: "You are a professional literary translator..."
      * Summary:     "You are a helpful assistant that produces concise
                     summaries."
      * Glossary:    "You are a helpful assistant. Answer with strict
                     JSON only."

    We detect the translation call by the presence of "translator" in the
    prompt (unique to that path); the two "helpful assistant" prompts are
    used for the two auxiliary calls.
    """
    return 'translator' in (prompt or '').lower()


def _is_glossary_call(prompt):
    return 'json' in (prompt or '').lower()


def _is_summary_call(prompt):
    return ('helpful assistant' in (prompt or '').lower()
            and 'json' not in (prompt or '').lower())


class FakeEngine:
    """Minimal engine stub compatible with NovelTranslator expectations."""

    name = 'FakeEngine'
    request_attempt = 2
    source_lang = 'English'
    target_lang = 'Italian'

    def __init__(self, translate_side_effect=None):
        self.prompt = 'original prompt'
        self.translate_calls = []
        self._translate_side_effect = translate_side_effect

    def override_prompt(self, prompt):
        self._stash = self.prompt
        self.prompt = prompt

    def restore_prompt(self):
        if hasattr(self, '_stash'):
            self.prompt = self._stash

    def get_target_lang(self):
        return self.target_lang

    def translate(self, text):
        self.translate_calls.append({
            'prompt': self.prompt, 'text': text})
        if self._translate_side_effect is not None:
            value = self._translate_side_effect(text, self.prompt)
            if isinstance(value, Exception):
                raise value
            return value
        return text


class TestNovelTranslator(unittest.TestCase):
    def setUp(self):
        self.cache = Mock()
        self.cache.get_info.return_value = None
        self.ctx = ContextManager(self.cache).load()
        # Reset mock so we can inspect only calls made during the test proper.
        self.cache.reset_mock()

        self.paragraphs = [
            make_paragraph(0, 'Alpha 1', page='a'),
            make_paragraph(1, 'Alpha 2', page='a'),
            make_paragraph(2, 'Beta 1', page='b'),
        ]
        self.chapters = [
            Chapter(1, 'Chapter One', ['a'], self.paragraphs[:2]),
            Chapter(2, 'Chapter Two', ['b'], self.paragraphs[2:]),
        ]

    def _make_translator(self, engine, config=None):
        # Disable the short-chapter guard by default so tests can use tiny
        # synthetic paragraphs without their summary/glossary calls being
        # short-circuited by ``novel_min_chars_for_context``.
        base_config = {'novel_min_chars_for_context': 0}
        if config:
            base_config.update(config)
        translator = NovelTranslator(
            engine, self.chapters, self.ctx, self.cache,
            config=base_config)
        translator.set_logging(Mock())
        translator.set_progress(Mock())
        return translator

    def test_run_translates_all_chapters(self):
        def side_effect(text, prompt):
            if _is_translation_call(prompt):
                return _echo_markers(text)
            if _is_glossary_call(prompt):
                return '{"entities": []}'
            # Summary path.
            return 'Summary text.'
        engine = FakeEngine(translate_side_effect=side_effect)
        translator = self._make_translator(engine)
        count = translator.run()
        self.assertEqual(2, count)
        # Both chapters were persisted.
        self.assertEqual(2, self.ctx.get_progress())
        # All non-ignored paragraphs got translated.
        for p in self.paragraphs:
            self.assertIsNotNone(p.translation)
            self.assertIn('(IT)', p.translation)
            self.assertEqual('FakeEngine', p.engine_name)
            self.assertEqual('Italian', p.target_lang)

    def test_run_resumes_from_progress(self):
        # Simulate a previous run that completed chapter 1.
        self.ctx.progress = 1
        collected = []

        def side_effect(text, prompt):
            collected.append(text[:20])
            if _is_translation_call(prompt):
                return _echo_markers(text)
            return '{"entities": []}'
        engine = FakeEngine(translate_side_effect=side_effect)
        translator = self._make_translator(engine)
        count = translator.run()
        self.assertEqual(1, count)
        # Only chapter 2 paragraph should be translated in this run.
        self.assertIsNone(self.paragraphs[0].translation)
        self.assertIsNone(self.paragraphs[1].translation)
        self.assertIsNotNone(self.paragraphs[2].translation)

    def test_cancel_stops_run(self):
        engine = FakeEngine()
        translator = self._make_translator(engine)
        translator.set_cancel_request(lambda: True)
        with self.assertRaises(TranslationCanceled):
            translator.run()

    def test_missing_tags_are_logged(self):
        # Engine that returns only marker 1 -> alignment retries kick in
        # but still miss marker 2.
        def side_effect(text, prompt):
            if _is_translation_call(prompt):
                return '[1]\nOnly first.'
            return '{"entities": []}'
        engine = FakeEngine(translate_side_effect=side_effect)
        translator = self._make_translator(engine)
        log = Mock()
        translator.set_logging(log)
        translator.run()
        # The paragraph that was translated is stored, the missing one is
        # left as None but progress still advances (soft failure).
        self.assertEqual('Only first.', self.paragraphs[0].translation)
        # Missing-marker warning was logged at some point.
        warning_seen = any(
            'missing' in (c.args[0] if c.args else '').lower()
            for c in log.call_args_list)
        self.assertTrue(warning_seen)

    def test_summary_and_glossary_persisted(self):
        def side_effect(text, prompt):
            if _is_translation_call(prompt):
                return _echo_markers(text)
            if _is_glossary_call(prompt):
                return ('Here is JSON: {"entities": ['
                        '{"source": "Alpha", "translation": "Alfa", '
                        '"type": "character"}]}')
            # Summary path.
            return 'This chapter introduces Alpha.'
        engine = FakeEngine(translate_side_effect=side_effect)
        translator = self._make_translator(engine)
        translator.run()
        summaries = self.ctx.get_summaries()
        self.assertEqual(2, len(summaries))
        self.assertIn('Alpha', summaries[0]['summary'])
        glossary = self.ctx.get_glossary()
        self.assertIn('Alpha', glossary)
        self.assertEqual('Alfa', glossary['Alpha']['translation'])

    def test_no_translatable_content_skips_chapter(self):
        # Chapter 1 contains only an ignored paragraph.
        self.chapters[0] = Chapter(1, 'Empty', ['a'], [
            make_paragraph(0, '', page='a', ignored=True)])

        def side_effect(text, prompt):
            if _is_translation_call(prompt):
                return _echo_markers(text)
            return '{"entities": []}'
        engine = FakeEngine(translate_side_effect=side_effect)
        translator = self._make_translator(engine)
        translator.run()
        # Progress still advances past chapter 1.
        self.assertEqual(2, self.ctx.get_progress())

    def test_short_chapters_skip_context_calls(self):
        # With the default guard, tiny chapters ("Alpha 1", "Alpha 2", ...)
        # must be translated but must NOT trigger summary / glossary calls.
        tracker = {'summary': 0, 'glossary': 0}

        def side_effect(text, prompt):
            if _is_translation_call(prompt):
                return _echo_markers(text)
            if _is_glossary_call(prompt):
                tracker['glossary'] += 1
                return '{"entities": []}'
            # Assume any other call is the summary request.
            tracker['summary'] += 1
            return 'Summary text.'

        engine = FakeEngine(translate_side_effect=side_effect)
        # Explicit threshold well above the tiny sample paragraphs.
        translator = self._make_translator(
            engine, config={'novel_min_chars_for_context': 500})
        translator.run()
        # Both chapters are shorter than 500 chars once translated: no
        # summary / glossary calls should be made.
        self.assertEqual(0, tracker['summary'])
        self.assertEqual(0, tracker['glossary'])
        # But paragraphs must still be translated.
        for p in self.paragraphs:
            self.assertIsNotNone(p.translation)

    def test_glossary_fallback_from_line_based(self):
        # LLM returns a non-JSON list; the fallback parser should
        # recover some entries.
        long_text = ' '.join(['Alpha'] * 200)  # push chapter over threshold
        self.paragraphs = [
            make_paragraph(0, long_text, page='a'),
            make_paragraph(1, long_text, page='b'),
        ]
        self.chapters = [
            Chapter(1, 'Chapter One', ['a'], self.paragraphs[:1]),
            Chapter(2, 'Chapter Two', ['b'], self.paragraphs[1:]),
        ]

        def side_effect(text, prompt):
            if _is_translation_call(prompt):
                return _echo_markers(text)
            if _is_glossary_call(prompt):
                # Return plain prose, not JSON.
                return (
                    'Here are the entities I found:\n'
                    '"Alpha" -> "Alfa" (character): main figure\n'
                    '"Beta" -> "Beta" (place)\n'
                    'Nothing else notable.')
            return 'Summary text.'

        engine = FakeEngine(translate_side_effect=side_effect)
        translator = self._make_translator(engine)
        translator.run()
        glossary = self.ctx.get_glossary()
        # At least one entity should have been recovered via the fallback.
        self.assertGreater(len(glossary), 0)

    def test_head_and_tail_short_text_unchanged(self):
        # Short text under the budget is returned verbatim.
        engine = FakeEngine()
        translator = self._make_translator(engine)
        text = 'This is short.'
        self.assertEqual(text, translator._head_and_tail(text, 100))

    def test_head_and_tail_long_text_truncated(self):
        engine = FakeEngine()
        translator = self._make_translator(engine)
        text = 'HEAD_START' + ('x' * 5000) + 'TAIL_END'
        clipped = translator._head_and_tail(text, 500)
        self.assertLess(len(clipped), len(text))
        self.assertEqual(len(clipped), 500)
        self.assertIn('HEAD_START', clipped)
        self.assertNotIn('TAIL_END', clipped)
        self.assertNotIn('middle omitted', clipped)

    def test_head_and_tail_zero_disables(self):
        # max_chars <= 0 disables truncation.
        engine = FakeEngine()
        translator = self._make_translator(engine)
        text = 'x' * 100000
        self.assertEqual(text, translator._head_and_tail(text, 0))

    def test_translation_failure_after_retries(self):
        engine = FakeEngine(
            translate_side_effect=lambda t, p: Exception('boom'))
        translator = self._make_translator(engine)
        with patch(f'{module_name}.time'):
            with self.assertRaises(TranslationFailed):
                translator.run()

    # -- overlap chunking -------------------------------------------------

    def test_overlap_default_is_three(self):
        # Default from configuration is 3 sliding paragraphs.
        engine = FakeEngine()
        translator = self._make_translator(engine, config={})
        # _make_translator forces novel_min_chars_for_context=0 but not
        # the overlap; it should fall back to the runtime default.
        self.assertEqual(3, translator.overlap_paragraphs)

    def test_overlap_can_be_disabled(self):
        engine = FakeEngine()
        translator = self._make_translator(
            engine, config={'novel_overlap_paragraphs': 0})
        self.assertEqual(0, translator.overlap_paragraphs)

    def test_overlap_negative_clamped_to_zero(self):
        engine = FakeEngine()
        translator = self._make_translator(
            engine, config={'novel_overlap_paragraphs': -5})
        self.assertEqual(0, translator.overlap_paragraphs)

    def test_overlap_passed_to_next_chunk(self):
        """When overlap > 0, the second chunk must receive as context the
        translations produced by the first chunk."""
        # Build a chapter with enough paragraphs to force 2 chunks
        # (max_paragraphs=3 forces 3+3 = 2 chunks).
        paras = [make_paragraph(i, 'para %d' % i, page='a')
                 for i in range(6)]
        self.chapters = [Chapter(1, 'Ch', ['a'], paras)]
        self.paragraphs = paras

        seen_users = []

        def side_effect(text, prompt):
            if _is_translation_call(prompt):
                seen_users.append(text)
                return _echo_markers(text)
            if _is_glossary_call(prompt):
                return '{"entities": []}'
            return 'Summary.'

        engine = FakeEngine(translate_side_effect=side_effect)
        translator = self._make_translator(
            engine, config={
                'novel_overlap_paragraphs': 2,
                'novel_max_paragraphs_per_chunk': 3,
            })
        translator.run()

        # We expect at least 2 translation calls (2 chunks).
        translation_calls = [t for t in seen_users
                             if 'Translate each numbered' in t]
        self.assertGreaterEqual(len(translation_calls), 2)
        # First chunk: no overlap block.
        first = translation_calls[0]
        self.assertNotIn('already translated', first)
        # Second chunk: overlap block present with previous translations.
        second = translation_calls[1]
        self.assertIn('already translated', second)
        # The overlap must contain the translated form of at least one
        # paragraph from the first chunk (which was echoed with '(IT)').
        self.assertIn('(IT)', second.split(
            'Translate each numbered')[0])

    def test_overlap_disabled_no_context_block(self):
        """With overlap=0 no chunk should carry a context block, even the
        second one."""
        paras = [make_paragraph(i, 'para %d' % i, page='a')
                 for i in range(6)]
        self.chapters = [Chapter(1, 'Ch', ['a'], paras)]
        self.paragraphs = paras

        seen_users = []

        def side_effect(text, prompt):
            if _is_translation_call(prompt):
                seen_users.append(text)
                return _echo_markers(text)
            if _is_glossary_call(prompt):
                return '{"entities": []}'
            return 'Summary.'

        engine = FakeEngine(translate_side_effect=side_effect)
        translator = self._make_translator(
            engine, config={
                'novel_overlap_paragraphs': 0,
                'novel_max_paragraphs_per_chunk': 3,
            })
        translator.run()

        for t in seen_users:
            self.assertNotIn('already translated', t)

    def test_overlap_larger_than_previous_chunk_is_truncated(self):
        """If overlap window is larger than the number of translations
        available from the previous chunk, we simply use what we have."""
        paras = [make_paragraph(i, 'para %d' % i, page='a')
                 for i in range(4)]
        self.chapters = [Chapter(1, 'Ch', ['a'], paras)]
        self.paragraphs = paras

        seen_users = []

        def side_effect(text, prompt):
            if _is_translation_call(prompt):
                seen_users.append(text)
                return _echo_markers(text)
            if _is_glossary_call(prompt):
                return '{"entities": []}'
            return 'Summary.'

        engine = FakeEngine(translate_side_effect=side_effect)
        # Ask for 10 paragraphs of overlap but each chunk only has 2.
        translator = self._make_translator(
            engine, config={
                'novel_overlap_paragraphs': 10,
                'novel_max_paragraphs_per_chunk': 2,
            })
        translator.run()

        # The run must complete without error, and the second chunk must
        # still include a context block (with just 2 paragraphs, not 10).
        translation_calls = [t for t in seen_users
                             if 'Translate each numbered' in t]
        self.assertGreaterEqual(len(translation_calls), 2)
        # Every paragraph must have been translated.
        for p in paras:
            self.assertIsNotNone(p.translation)
            self.assertIn('(IT)', p.translation)

    @patch(f'{module_name}.time')
    def test_retry_sleeps_between_attempts(self, mock_time):
        engine = FakeEngine(
            translate_side_effect=lambda t, p: Exception('nope'))
        translator = self._make_translator(engine)
        # request_attempt=2 -> two attempts, one sleep in between.
        with self.assertRaises(TranslationFailed):
            translator._translate_with_retry('sys', 'user', attempts=2)
        mock_time.sleep.assert_called()


# ---------------------------------------------------------------------------
# Structured output (JSON) path
# ---------------------------------------------------------------------------


class StructuredEngine(FakeEngine):
    """FakeEngine that pretends to support structured JSON output.

    Overrides ``translate`` so it *invokes* ``get_body`` (or the swapped
    ``get_body_for_structured``) exactly once per call, giving tests a
    reliable hook to assert which path was chosen.
    """
    structured_output_mode = 'schema'

    def __init__(self, translate_side_effect=None):
        super().__init__(translate_side_effect=translate_side_effect)
        self.body_calls = []
        self.structured_body_calls = []

    def get_body(self, text):
        self.body_calls.append(text)
        return '{"messages": ["marker-path"]}'

    def get_body_for_structured(self, text, schema=None):
        self.structured_body_calls.append({
            'text': text, 'schema': schema})
        return '{"structured": true, "text": "..."}'

    def translate(self, text):
        # Force the routing hook to actually run: build the body via
        # whatever get_body is currently swapped in on the instance,
        # then let the parent class dispatch the response.
        self.get_body(text)
        return super().translate(text)


class UnstructuredEngine(FakeEngine):
    """FakeEngine that does NOT advertise structured output support."""
    structured_output_mode = None


def _echo_markers_as_json(text, suffix=' (IT)'):
    """Test helper: parse the JSON payload embedded in ``text`` (produced
    by ``_build_structured_payload``) and echo it back with translated
    fields, simulating a well-behaved server returning JSON.
    """
    import json as _json
    import re
    # The payload is embedded after "Input:\n" in the user text.
    m = re.search(r'Input:\s*\n(\{.*\})\s*\Z', text, re.DOTALL)
    if not m:
        return '{"paragraphs": []}'
    try:
        obj = _json.loads(m.group(1))
    except ValueError:
        return '{"paragraphs": []}'
    out = {'paragraphs': []}
    for p in obj.get('paragraphs', []):
        out['paragraphs'].append({
            'n': p['n'],
            'translation': (p.get('source') or '').strip() + suffix,
        })
    return _json.dumps(out, ensure_ascii=False)


class TestStructuredOutputCapability(unittest.TestCase):
    """Detection of engine structured-output capability + user setting."""

    def _make_translator(self, engine, config=None):
        cache = Mock()
        cache.get_info.return_value = None
        ctx = ContextManager(cache).load()
        cache.reset_mock()
        translator = NovelTranslator(
            engine, [], ctx, cache, config=config or {})
        translator.set_logging(Mock())
        translator.set_progress(Mock())
        return translator

    def test_structured_setting_default_is_auto(self):
        translator = self._make_translator(StructuredEngine())
        self.assertEqual('auto', translator.structured_output_setting)

    def test_structured_setting_normalises_invalid_value(self):
        translator = self._make_translator(
            StructuredEngine(),
            config={'novel_structured_output': 'nonsense'})
        self.assertEqual('auto', translator.structured_output_setting)

    def test_engine_supports_structured_detection_true(self):
        translator = self._make_translator(StructuredEngine())
        self.assertTrue(translator._engine_supports_structured())

    def test_engine_supports_structured_detection_false(self):
        translator = self._make_translator(UnstructuredEngine())
        self.assertFalse(translator._engine_supports_structured())

    def test_structured_active_auto_capable_engine(self):
        translator = self._make_translator(StructuredEngine())
        self.assertTrue(translator._structured_active())

    def test_structured_active_auto_uncapable_engine(self):
        translator = self._make_translator(UnstructuredEngine())
        self.assertFalse(translator._structured_active())

    def test_structured_active_off_overrides_capability(self):
        translator = self._make_translator(
            StructuredEngine(),
            config={'novel_structured_output': 'off'})
        self.assertFalse(translator._structured_active())

    def test_structured_active_force_overrides_missing_capability(self):
        translator = self._make_translator(
            UnstructuredEngine(),
            config={'novel_structured_output': 'force'})
        self.assertTrue(translator._structured_active())

    def test_structured_choice_logged_once(self):
        # The verbose one-shot log should fire exactly once per instance.
        engine = StructuredEngine()
        translator = self._make_translator(engine)
        log = Mock()
        translator.set_logging(log)
        translator._structured_active()
        translator._structured_active()
        translator._structured_active()
        format_logs = [
            c for c in log.call_args_list
            if 'Output format' in (c.args[0] if c.args else '')]
        self.assertEqual(1, len(format_logs))
        self.assertIn('structured JSON', format_logs[0].args[0])

    def test_structured_choice_logs_reason_when_disabled(self):
        translator = self._make_translator(
            StructuredEngine(),
            config={'novel_structured_output': 'off'})
        log = Mock()
        translator.set_logging(log)
        translator._structured_active()
        format_logs = [
            c for c in log.call_args_list
            if 'Output format' in (c.args[0] if c.args else '')]
        self.assertEqual(1, len(format_logs))
        message = format_logs[0].args[0]
        self.assertIn('text markers', message)
        self.assertIn('disabled by user setting', message)


class TestStructuredOutputParser(unittest.TestCase):
    """Robustness of _parse_structured_response."""

    def _make_translator(self):
        cache = Mock()
        cache.get_info.return_value = None
        ctx = ContextManager(cache).load()
        cache.reset_mock()
        translator = NovelTranslator(
            StructuredEngine(), [], ctx, cache, config={})
        translator.set_logging(Mock())
        translator.set_progress(Mock())
        return translator

    def test_parse_basic(self):
        translator = self._make_translator()
        response = ('{"paragraphs": ['
                    '{"n": 1, "translation": "Primo."},'
                    '{"n": 2, "translation": "Secondo."}]}')
        parsed = translator._parse_structured_response(response, [1, 2])
        self.assertEqual({1: 'Primo.', 2: 'Secondo.'}, parsed)

    def test_parse_ignores_extra_fields(self):
        translator = self._make_translator()
        response = ('{"paragraphs": ['
                    '{"n": 1, "translation": "Primo.", '
                    '"source": "orig", "extra": "junk"}]}')
        parsed = translator._parse_structured_response(response, [1])
        self.assertEqual({1: 'Primo.'}, parsed)

    def test_parse_filters_unexpected_indices(self):
        translator = self._make_translator()
        response = ('{"paragraphs": ['
                    '{"n": 1, "translation": "Real."},'
                    '{"n": 99, "translation": "Hallucinated."}]}')
        parsed = translator._parse_structured_response(response, [1, 2])
        self.assertEqual({1: 'Real.'}, parsed)

    def test_parse_missing_paragraphs(self):
        translator = self._make_translator()
        response = '{"paragraphs": [{"n": 1, "translation": "Only one."}]}'
        parsed = translator._parse_structured_response(response, [1, 2, 3])
        self.assertEqual({1: 'Only one.'}, parsed)

    def test_parse_json_with_prose_prefix(self):
        translator = self._make_translator()
        response = ('Here is your JSON: {"paragraphs": ['
                    '{"n": 1, "translation": "T"}]} thanks!')
        parsed = translator._parse_structured_response(response, [1])
        self.assertEqual({1: 'T'}, parsed)

    def test_parse_json_with_markdown_fence(self):
        translator = self._make_translator()
        response = ('```json\n{"paragraphs": ['
                    '{"n": 1, "translation": "T"}]}\n```')
        parsed = translator._parse_structured_response(response, [1])
        self.assertEqual({1: 'T'}, parsed)

    def test_parse_n_as_string(self):
        # Some models emit "n": "1" instead of "n": 1.
        translator = self._make_translator()
        response = '{"paragraphs": [{"n": "1", "translation": "Uno"}]}'
        parsed = translator._parse_structured_response(response, [1])
        self.assertEqual({1: 'Uno'}, parsed)

    def test_parse_malformed_json_returns_empty(self):
        translator = self._make_translator()
        parsed = translator._parse_structured_response(
            'this is not json', [1])
        self.assertEqual({}, parsed)

    def test_parse_missing_paragraphs_field_returns_empty(self):
        translator = self._make_translator()
        parsed = translator._parse_structured_response(
            '{"other": "field"}', [1])
        self.assertEqual({}, parsed)

    def test_parse_empty_translation_skipped(self):
        translator = self._make_translator()
        response = ('{"paragraphs": ['
                    '{"n": 1, "translation": ""},'
                    '{"n": 2, "translation": "OK"}]}')
        parsed = translator._parse_structured_response(response, [1, 2])
        # Empty translation is dropped; the alignment retry will fill it.
        self.assertEqual({2: 'OK'}, parsed)

    def test_parse_preserves_inline_placeholders(self):
        # {id_00001} placeholders must survive the JSON round-trip.
        translator = self._make_translator()
        response = ('{"paragraphs": [{"n": 1, '
                    '"translation": "Testo con {id_00001} preservato."}]}')
        parsed = translator._parse_structured_response(response, [1])
        self.assertIn('{id_00001}', parsed[1])


class TestStructuredDispatcher(unittest.TestCase):
    """The dispatcher routes to the structured path when active."""

    def _make_pair(self, engine_cls, config=None):
        cache = Mock()
        cache.get_info.return_value = None
        ctx = ContextManager(cache).load()
        cache.reset_mock()
        base_config = {'novel_min_chars_for_context': 0}
        if config:
            base_config.update(config)
        paragraphs = [
            make_paragraph(0, 'First paragraph.', page='a'),
            make_paragraph(1, 'Second paragraph.', page='a'),
        ]
        chapter = Chapter(1, 'C1', ['a'], paragraphs)

        def side_effect(text, prompt):
            if _is_translation_call(prompt):
                # Both marker path and structured path arrive here.
                # Return the appropriate format based on the request body.
                if '"structured"' in text or 'JSON' in text.upper() \
                        or 'Input:' in text:
                    return _echo_markers_as_json(text)
                return _echo_markers(text)
            if _is_glossary_call(prompt):
                return '{"entities": []}'
            return 'Summary.'

        engine = engine_cls(translate_side_effect=side_effect)
        translator = NovelTranslator(
            engine, [chapter], ctx, cache, config=base_config)
        translator.set_logging(Mock())
        translator.set_progress(Mock())
        return translator, engine, paragraphs

    def test_dispatcher_calls_structured_path_when_engine_supports(self):
        translator, engine, paragraphs = self._make_pair(StructuredEngine)
        translator.run()
        # get_body_for_structured must have been called at least once.
        self.assertGreater(len(engine.structured_body_calls), 0)
        # All paragraphs must be translated.
        for p in paragraphs:
            self.assertIsNotNone(p.translation)
            self.assertIn('(IT)', p.translation)

    def test_dispatcher_uses_markers_when_engine_not_capable(self):
        translator, engine, paragraphs = self._make_pair(UnstructuredEngine)
        translator.run()
        # UnstructuredEngine does not override get_body_for_structured;
        # it inherits FakeEngine (which doesn't track structured calls).
        for p in paragraphs:
            self.assertIsNotNone(p.translation)
            self.assertIn('(IT)', p.translation)

    def test_dispatcher_respects_off_setting(self):
        translator, engine, paragraphs = self._make_pair(
            StructuredEngine,
            config={'novel_structured_output': 'off'})
        translator.run()
        # Engine supports structured but user forced it off: no structured
        # calls should have been made.
        self.assertEqual(0, len(engine.structured_body_calls))

    def test_dispatcher_respects_force_setting(self):
        # UnstructuredEngine doesn't declare capability, but 'force'
        # asks the pipeline to try structured anyway. Since
        # UnstructuredEngine's get_body_for_structured falls back to
        # get_body (via GenAI default), the call still succeeds.
        translator, engine, paragraphs = self._make_pair(
            UnstructuredEngine,
            config={'novel_structured_output': 'force'})
        # Sanity: the structured path is chosen.
        self.assertTrue(translator._structured_active())


class TestStructuredEnginePayloads(unittest.TestCase):
    """Verify each engine builds the correct provider-specific body.

    These tests exercise the real engine classes and therefore need the
    ``calibre_plugins.ebook_translator`` package to be importable. They
    are skipped in isolated dev environments (where only ``lib/novel.py``
    is loaded standalone) but run normally under ``calibre-debug``.
    """

    @classmethod
    def _can_import_engines(cls):
        try:
            import calibre_plugins.ebook_translator.engines.openai  # noqa
            import calibre_plugins.ebook_translator.engines.google  # noqa
            return True
        except ImportError:
            return False

    def setUp(self):
        if not self._can_import_engines():
            self.skipTest(
                'engines module not importable in isolated environment')

    def test_openai_response_format_json_schema(self):
        # Import lazily to avoid loading engine chain at module scope.
        from calibre_plugins.ebook_translator.engines.openai import (
            ChatgptTranslate)
        engine = ChatgptTranslate.__new__(ChatgptTranslate)
        engine.model = 'gpt-x'
        engine.prompt = 'You translate.'
        engine.stream = True  # must still be disabled in structured mode
        engine.samplings = ['temperature']
        engine.sampling = 'temperature'
        engine.temperature = 0.5
        engine.top_p = 1.0
        engine.source_lang = 'English'
        engine.target_lang = 'Italian'
        # Minimal method stubs needed by get_body_for_structured.
        engine.get_prompt = lambda: 'You translate.'

        schema = {'type': 'object', 'properties': {'x': {'type': 'string'}}}
        body_str = engine.get_body_for_structured('hello', schema=schema)
        import json as _json
        body = _json.loads(body_str)
        self.assertEqual('json_schema', body['response_format']['type'])
        self.assertEqual(
            'novel_translation',
            body['response_format']['json_schema']['name'])
        self.assertEqual(
            schema, body['response_format']['json_schema']['schema'])
        self.assertTrue(
            body['response_format']['json_schema'].get('strict'))
        # Streaming is disabled for structured requests.
        self.assertNotIn('stream', body)

    def test_openai_response_format_json_object_when_no_schema(self):
        from calibre_plugins.ebook_translator.engines.openai import (
            ChatgptTranslate)
        engine = ChatgptTranslate.__new__(ChatgptTranslate)
        engine.model = 'gpt-x'
        engine.prompt = 'You translate.'
        engine.stream = False
        engine.samplings = ['temperature']
        engine.sampling = 'temperature'
        engine.temperature = 0.5
        engine.top_p = 1.0
        engine.source_lang = 'English'
        engine.target_lang = 'Italian'
        engine.get_prompt = lambda: 'You translate.'

        body_str = engine.get_body_for_structured('hi', schema=None)
        import json as _json
        body = _json.loads(body_str)
        self.assertEqual('json_object', body['response_format']['type'])

    def test_gemini_response_mime_and_schema(self):
        from calibre_plugins.ebook_translator.engines.google import (
            GeminiTranslate)
        engine = GeminiTranslate.__new__(GeminiTranslate)
        engine.model = 'gemini-x'
        engine.stream = False
        engine.temperature = 0.5
        engine.top_p = 1.0
        engine.top_k = 40
        engine.source_lang = 'English'
        engine.target_lang = 'Italian'
        # Minimal method stubs used by GeminiTranslate.get_body().
        engine._prompt = lambda text: 'Translate: ' + text

        schema = {'type': 'object', 'properties': {'x': {'type': 'string'}}}
        body_str = engine.get_body_for_structured('hi', schema=schema)
        import json as _json
        body = _json.loads(body_str)
        self.assertEqual(
            'application/json',
            body['generationConfig']['responseMimeType'])
        self.assertEqual(
            schema, body['generationConfig']['responseSchema'])


if __name__ == '__main__':
    unittest.main()
