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
            make_paragraph(0, 'Alpha 1', page='a'),
            make_paragraph(1, 'Alpha 2', page='a'),
            make_paragraph(2, 'Beta 1', page='b'),
            make_paragraph(3, 'Beta 2', page='b'),
            make_paragraph(4, 'Gamma 1', page='c'),
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
        # Titles derive from first paragraph text.
        self.assertEqual('Alpha 1', chapters[0].title)
        self.assertEqual('Beta 1', chapters[1].title)
        self.assertEqual('Gamma 1', chapters[2].title)

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
            self.pages, [], self.items, paragraphs).build()
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

    def test_chunk_default_max_paragraphs_is_60(self):
        # Backward-compatible default. New default is 60.
        budget = TokenBudget(budget=8000)
        self.assertEqual(60, budget.max_paragraphs)

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
        self.assertIn('<P1>First.</P1>', tagged)
        self.assertIn('<P2>Second.</P2>', tagged)
        self.assertIn('<P3>Third.</P3>', tagged)

    def test_tag_paragraphs_skips_ignored(self):
        paragraphs = [
            make_paragraph(0, 'A'),
            make_paragraph(1, 'B', ignored=True),
            make_paragraph(2, 'C'),
        ]
        tagged, indices = tag_paragraphs(paragraphs)
        # Indices count the *paragraphs list* position, not translated count.
        self.assertEqual([1, 3], indices)
        self.assertIn('<P1>A</P1>', tagged)
        self.assertIn('<P3>C</P3>', tagged)
        self.assertNotIn('<P2>', tagged)

    def test_parse_tagged_response(self):
        response = (
            "Sure, here is the translation:\n"
            "<P1>Primo.</P1>\n"
            "<P2>Secondo.</P2>\n"
            "<P3>Terzo.</P3>\nEnd of translation.")
        parsed = parse_tagged_response(response, [1, 2, 3])
        self.assertEqual({1: 'Primo.', 2: 'Secondo.', 3: 'Terzo.'}, parsed)

    def test_parse_tagged_response_multiline(self):
        response = (
            "<P1>Line one.\nLine two.</P1>\n"
            "<P2>Alone.</P2>")
        parsed = parse_tagged_response(response, [1, 2])
        self.assertEqual(2, len(parsed))
        self.assertIn('Line one.', parsed[1])
        self.assertIn('Line two.', parsed[1])

    def test_parse_tagged_response_missing(self):
        response = "<P1>Only one.</P1>"
        parsed = parse_tagged_response(response, [1, 2, 3])
        self.assertEqual({1: 'Only one.'}, parsed)

    def test_parse_tagged_response_ignores_hallucinated_tags(self):
        response = "<P1>Real.</P1><P5>Hallucinated.</P5>"
        parsed = parse_tagged_response(response, [1, 2])
        # Tag 5 was not expected; ignored.
        self.assertEqual({1: 'Real.'}, parsed)

    def test_parse_tagged_response_empty(self):
        self.assertEqual({}, parse_tagged_response('', [1]))
        self.assertEqual({}, parse_tagged_response(None, [1]))


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
            # Translation call: response contains the same tags.
            if '<P1>' in text or '<P2>' in text or '<P3>' in text:
                # Echo back all tags found in the user text.
                import re
                result = []
                for m in re.finditer(r'<P(\d+)>(.*?)</P\1>',
                                     text, re.DOTALL):
                    result.append('<P%s>%s (IT)</P%s>' % (
                        m.group(1), m.group(2), m.group(1)))
                return '\n'.join(result)
            # Summary and glossary calls: return trivial values.
            if 'Summarize' in prompt or 'summar' in prompt.lower():
                return 'Summary text.'
            if 'JSON' in prompt or 'entities' in prompt.lower():
                return '{"entities": []}'
            # Fallback (used e.g. by summary user-side prompt).
            if 'summary' in text.lower():
                return 'Summary text.'
            return '{"entities": []}'
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
            if '<P' in text:
                import re
                return '\n'.join(
                    '<P%s>%s (IT)</P%s>' % (m.group(1), m.group(2),
                                             m.group(1))
                    for m in re.finditer(r'<P(\d+)>(.*?)</P\1>',
                                         text, re.DOTALL))
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
        # Engine that returns only tag 1 -> alignment retries kick in but
        # still miss tag 2.
        def side_effect(text, prompt):
            if '<P' in text:
                return '<P1>Only first.</P1>'
            return '{"entities": []}'
        engine = FakeEngine(translate_side_effect=side_effect)
        translator = self._make_translator(engine)
        log = Mock()
        translator.set_logging(log)
        translator.run()
        # The paragraph that was translated is stored, the missing one is
        # left as None but progress still advances (soft failure).
        self.assertEqual('Only first.', self.paragraphs[0].translation)
        # Missing-tag warning was logged at some point.
        warning_seen = any(
            'missing' in (c.args[0] if c.args else '').lower()
            for c in log.call_args_list)
        self.assertTrue(warning_seen)

    def test_summary_and_glossary_persisted(self):
        def side_effect(text, prompt):
            if '<P' in text and 'JSON' not in prompt \
                    and 'entities' not in prompt.lower():
                import re
                return '\n'.join(
                    '<P%s>%s (IT)</P%s>' % (m.group(1), m.group(2),
                                             m.group(1))
                    for m in re.finditer(r'<P(\d+)>(.*?)</P\1>',
                                         text, re.DOTALL))
            if 'JSON' in prompt or 'entities' in prompt.lower():
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
            if '<P' in text:
                import re
                return '\n'.join(
                    '<P%s>%s (IT)</P%s>' % (m.group(1), m.group(2),
                                             m.group(1))
                    for m in re.finditer(r'<P(\d+)>(.*?)</P\1>',
                                         text, re.DOTALL))
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
            if '<P' in text and 'JSON' not in prompt \
                    and 'entities' not in prompt.lower():
                import re
                return '\n'.join(
                    '<P%s>%s (IT)</P%s>' % (m.group(1), m.group(2),
                                             m.group(1))
                    for m in re.finditer(r'<P(\d+)>(.*?)</P\1>',
                                         text, re.DOTALL))
            if 'JSON' in prompt or 'entities' in prompt.lower():
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
            if '<P' in text and 'JSON' not in prompt \
                    and 'entities' not in prompt.lower():
                import re
                return '\n'.join(
                    '<P%s>%s (IT)</P%s>' % (m.group(1), m.group(2),
                                             m.group(1))
                    for m in re.finditer(r'<P(\d+)>(.*?)</P\1>',
                                         text, re.DOTALL))
            if 'JSON' in prompt or 'entities' in prompt.lower():
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

    def test_translation_failure_after_retries(self):
        engine = FakeEngine(
            translate_side_effect=lambda t, p: Exception('boom'))
        translator = self._make_translator(engine)
        with patch(f'{module_name}.time'):
            with self.assertRaises(TranslationFailed):
                translator.run()

    @patch(f'{module_name}.time')
    def test_retry_sleeps_between_attempts(self, mock_time):
        engine = FakeEngine(
            translate_side_effect=lambda t, p: Exception('nope'))
        translator = self._make_translator(engine)
        # request_attempt=2 -> two attempts, one sleep in between.
        with self.assertRaises(TranslationFailed):
            translator._translate_with_retry('sys', 'user', attempts=2)
        mock_time.sleep.assert_called()


if __name__ == '__main__':
    unittest.main()
