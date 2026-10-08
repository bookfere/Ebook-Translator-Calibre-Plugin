"""Novel Mode: chapter-aware sequential translation pipeline for LLMs.

This module implements a dedicated translation pipeline optimized for narrative
long-form content (novels). Unlike the default paragraph-by-paragraph parallel
pipeline (see ``lib/translation.py``), the novel pipeline:

  * groups paragraphs by chapter, using the ebook Table of Contents when
    available (fallback: one XHTML file per chapter);
  * translates chapters sequentially, one after the other, without concurrency;
  * chunks each chapter to fit an LLM token budget (default ~8k) without ever
    splitting a paragraph in half;
  * maintains a running summary of previously translated chapters, injected
    into each translation prompt so the model preserves narrative continuity;
  * maintains a dynamic glossary of characters, places and other named
    entities extracted after each chapter, kept consistent across the book;
  * persists progress, summaries and glossary in the existing SQLite cache
    (via the ``info`` key/value table -- no schema change) so an interrupted
    translation can be resumed from the last completed chapter.

The public entry points are:

    ChapterBuilder(oeb, paragraphs, config).build() -> list[Chapter]
    TokenBudget(budget).chunk(paragraphs, reserved) -> list[list[Paragraph]]
    ContextManager(cache).load() / append_chapter() / context_text()
    NovelTranslator(translator, chapters, context_manager, cache, config).run()

This module has no direct dependency on Qt so it is fully unit-testable.
"""

import re
import json
import time

from calibre.utils.localization import _  # type: ignore

from .utils import log, sep, uid, dummy
from .exception import TranslationCanceled, TranslationFailed


load_translations()  # type: ignore


# ---------------------------------------------------------------------------
# Chapter model
# ---------------------------------------------------------------------------


class Chapter:
    """A logical chapter of the book.

    A chapter groups one or more page_ids together with the list of already
    extracted Paragraphs that belong to those pages. The ``index`` is 1-based
    and matches the order of the chapter inside the book (spine order).
    """

    def __init__(self, index, title, page_ids, paragraphs):
        self.index = index
        self.title = title or ''
        self.page_ids = list(page_ids)
        self.paragraphs = list(paragraphs)

    @property
    def char_count(self):
        return sum(len(p.original or '') for p in self.paragraphs
                   if not p.ignored)

    def translatable_paragraphs(self):
        return [p for p in self.paragraphs if not p.ignored]

    def __repr__(self):
        return ('Chapter(index=%s, title=%r, page_ids=%s, paragraphs=%d)'
                % (self.index, self.title, self.page_ids,
                   len(self.paragraphs)))


# ---------------------------------------------------------------------------
# Chapter builder
# ---------------------------------------------------------------------------


def _href_to_page_id(href, manifest_items):
    """Map an href (as found in TOC nodes) to a manifest item id.

    TOC hrefs often contain a fragment (``chap1.xhtml#section-2``) which must
    be stripped before comparing with the manifest item href.
    """
    if not href:
        return None
    clean = href.split('#', 1)[0]
    # Try exact match first.
    for item in manifest_items:
        if getattr(item, 'href', None) == clean:
            return item.id
    # Fallback: match by basename (some TOCs use relative paths).
    base = clean.rsplit('/', 1)[-1]
    for item in manifest_items:
        item_href = getattr(item, 'href', '') or ''
        if item_href.rsplit('/', 1)[-1] == base:
            return item.id
    return None


class ChapterBuilder:
    """Build ``Chapter`` objects from an OEB book and a flat paragraph list.

    Strategy:

    1. Determine the ordered list of "page ids" (the spine order used by the
       existing extraction pipeline: ``manifest.items`` filtered to xhtml
       and sorted by ``sorted_mixed_keys``).
    2. Determine chapter boundaries. Preference order:
         a. Top-level TOC nodes (level 1 only) if the TOC has 2+ nodes.
         b. Otherwise fall back to "one xhtml file == one chapter".
    3. Group paragraphs by (or between) those boundaries. Any paragraphs
       whose ``page`` id does not belong to any chapter range are attached
       to the closest previous chapter (typically front matter appended to
       chapter 1) so nothing is silently dropped.

    Only paragraphs coming from XHTML pages are considered as chapter
    content. Metadata and TOC paragraphs (page_id ``content.opf`` / ``toc.ncx``)
    are collected separately in ``self.aux_paragraphs`` so callers can decide
    what to do with them -- typically translated via the classic pipeline,
    keeping the novel pipeline focused on narrative content.
    """

    AUX_PAGES = {'content.opf', 'toc.ncx'}

    def __init__(self, ordered_page_ids, toc_nodes, manifest_items,
                 paragraphs, source='toc_level_1',
                 front_matter_min_chars=100):
        """
        :ordered_page_ids: list of page ids in spine order (xhtml only).
        :toc_nodes: list of TOC root nodes (each has ``.title`` and
            ``.href`` and ``.nodes``). May be an empty list.
        :manifest_items: iterable of manifest items exposing ``.id`` and
            ``.href``. Used to resolve TOC hrefs to page ids.
        :paragraphs: list of Paragraph rows extracted from the cache.
        :source: 'toc_level_1' | 'toc_level_2' | 'xhtml_file'.
        :front_matter_min_chars: XHTML pages whose total non-ignored text
            is shorter than this threshold are considered front/back matter
            (Cover, Titlepage, decorative pages) and their paragraphs are
            silently dropped from chapter content. Set to 0 to disable.
        """
        self.ordered_page_ids = list(ordered_page_ids)
        self.toc_nodes = list(toc_nodes or [])
        self.manifest_items = list(manifest_items or [])
        self.paragraphs = list(paragraphs)
        self.source = source
        self.front_matter_min_chars = max(0, int(front_matter_min_chars))
        self.aux_paragraphs = [
            p for p in self.paragraphs if p.page in self.AUX_PAGES]

        # Pre-compute per-page character counts (non-ignored paragraphs only)
        # used by the front-matter filter.
        self._page_char_count = {}
        for p in self.paragraphs:
            if p.page in self.AUX_PAGES or p.ignored:
                continue
            self._page_char_count[p.page] = (
                self._page_char_count.get(p.page, 0)
                + len(p.original or ''))

    def _is_front_matter(self, page_id):
        """Return True if ``page_id`` looks like a decorative / front-matter
        page that should be excluded from chapter content.

        Detection strategy:

        1. If ``front_matter_min_chars`` is 0, the filter is disabled.
        2. Pages with fewer non-ignored characters than the threshold are
           treated as front matter (e.g. a Titlepage that only carries
           ``"THE MAGICIAN'S NEPHEW"`` as a single heading paragraph, or a
           Cover page with nothing but an image).

        This handles the common EPUB pattern where each book inside a
        multi-book anthology has its own Cover.xhtml / Titlepage.xhtml that
        contains only a large-caps styled heading.  Sending those headings
        to the LLM as isolated paragraphs produces hallucinations because
        the model has no narrative context around them.
        """
        if self.front_matter_min_chars <= 0:
            return False
        return self._page_char_count.get(page_id, 0) < self.front_matter_min_chars

    # -- boundary discovery ------------------------------------------------

    def _boundaries_from_toc(self):
        """Return an ordered list of (page_id, title) marking chapter starts.

        Only top-level TOC nodes are considered. Nodes whose href cannot be
        resolved to a manifest item are silently skipped.
        """
        result = []
        seen = set()
        for node in self.toc_nodes:
            href = getattr(node, 'href', None)
            title = getattr(node, 'title', None) or ''
            page_id = _href_to_page_id(href, self.manifest_items)
            if page_id is None or page_id in seen:
                continue
            if page_id not in self.ordered_page_ids:
                continue
            seen.add(page_id)
            result.append((page_id, title.strip()))
        # Sort boundaries by spine order.
        order = {pid: i for i, pid in enumerate(self.ordered_page_ids)}
        result.sort(key=lambda t: order[t[0]])
        return result

    def _boundaries_from_toc_level2(self):
        """Return boundaries from the *second* level of the TOC hierarchy.

        Many multi-book anthologies have a two-level TOC:

          Level 1: Cover.xhtml   (entire book)
            Level 2: Chapter One  -> Chapter_1.xhtml
            Level 2: Chapter Two  -> Chapter_2.xhtml
            ...

        Using level-2 nodes as chapter boundaries maps each narrative chapter
        to its own translation unit, giving the LLM the chapter title in the
        prompt header and preventing front-matter pages (Cover, Titlepage,
        Contents) from polluting the first chunk.

        If the TOC has no level-2 children or fewer than 2 usable entries,
        falls back to level-1 boundaries.
        """
        result = []
        seen = set()
        for top_node in self.toc_nodes:
            children = getattr(top_node, 'nodes', []) or []
            for child in children:
                href = getattr(child, 'href', None)
                title = getattr(child, 'title', None) or ''
                page_id = _href_to_page_id(href, self.manifest_items)
                if page_id is None or page_id in seen:
                    continue
                if page_id not in self.ordered_page_ids:
                    continue
                seen.add(page_id)
                result.append((page_id, title.strip()))
        if len(result) < 2:
            # Not enough level-2 entries -- fall back to level-1.
            return self._boundaries_from_toc()
        order = {pid: i for i, pid in enumerate(self.ordered_page_ids)}
        result.sort(key=lambda t: order[t[0]])
        return result

    def _boundaries_from_files(self):
        """One xhtml file == one chapter. Titles are best-effort:

        we use the first paragraph text from the page (truncated) if a page
        has content, else 'Chapter N'.
        """
        result = []
        by_page = {}
        for p in self.paragraphs:
            if p.page in self.AUX_PAGES:
                continue
            by_page.setdefault(p.page, []).append(p)
        for i, pid in enumerate(self.ordered_page_ids, start=1):
            title = _('Chapter {}').format(i)
            content_ps = [p for p in by_page.get(pid, []) if not p.ignored]
            if content_ps:
                first = (content_ps[0].original or '').strip()
                if first:
                    title = first[:80]
            result.append((pid, title))
        return result

    def _resolve_boundaries(self):
        boundaries = []
        if self.source == 'toc_level_1':
            boundaries = self._boundaries_from_toc()
            if len(boundaries) < 2:
                boundaries = self._boundaries_from_files()
        elif self.source == 'toc_level_2':
            boundaries = self._boundaries_from_toc_level2()
            if len(boundaries) < 2:
                boundaries = self._boundaries_from_files()
        else:
            boundaries = self._boundaries_from_files()
        if not boundaries and self.ordered_page_ids:
            # Extreme fallback: single chapter with everything.
            boundaries = [(self.ordered_page_ids[0], _('Chapter 1'))]
        return boundaries

    # -- assembly ----------------------------------------------------------

    def build(self):
        boundaries = self._resolve_boundaries()
        if not boundaries:
            return []

        # Determine the (start_page_id -> [page_ids...]) mapping.
        order = {pid: i for i, pid in enumerate(self.ordered_page_ids)}
        boundary_positions = [(order[bid], bid, title)
                              for bid, title in boundaries]
        boundary_positions.sort(key=lambda t: t[0])

        # Build page_id -> chapter_index (1-based) mapping.
        page_to_chapter = {}
        chapter_page_ids = {i: [] for i in range(1, len(boundary_positions) + 1)}
        chapter_titles = {}
        for chap_i, (_pos, bid, title) in enumerate(
                boundary_positions, start=1):
            chapter_titles[chap_i] = (
                title or _('Chapter {}').format(chap_i))

        for idx, pid in enumerate(self.ordered_page_ids):
            # Find which chapter this page belongs to: the greatest chapter
            # start whose position <= idx.
            chap_i = 0
            for c_i, (pos, _bid, _t) in enumerate(
                    boundary_positions, start=1):
                if pos <= idx:
                    chap_i = c_i
                else:
                    break
            # If a page precedes the first boundary, attach it to chapter 1.
            if chap_i == 0:
                chap_i = 1
            page_to_chapter[pid] = chap_i
            chapter_page_ids[chap_i].append(pid)

        # Group paragraphs by chapter, applying the front-matter filter.
        # Pages identified as front matter (very short text, e.g. Cover,
        # Titlepage) are silently excluded from chapter content.  Their
        # paragraphs are still in the cache and will be translated by the
        # auxiliary pipeline (metadata/TOC titles), but they will not be
        # sent to the LLM as part of the chapter narrative payload.
        chapter_paragraphs = {i: [] for i in chapter_titles}
        skipped_pages = set()
        for p in self.paragraphs:
            if p.page in self.AUX_PAGES:
                continue
            chap_i = page_to_chapter.get(p.page)
            if chap_i is None:
                continue
            if self._is_front_matter(p.page):
                skipped_pages.add(p.page)
                continue
            chapter_paragraphs[chap_i].append(p)

        chapters = []
        for i in sorted(chapter_titles):
            ch = Chapter(
                index=i,
                title=chapter_titles[i],
                page_ids=chapter_page_ids[i],
                paragraphs=chapter_paragraphs[i],
            )
            chapters.append(ch)
        return chapters


# ---------------------------------------------------------------------------
# Token budget / chunking
# ---------------------------------------------------------------------------


_CJK_RE = re.compile(
    r'[\u3000-\u303f\u3040-\u309f\u30a0-\u30ff\u3400-\u4dbf'
    r'\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff]')


class TokenBudget:
    """Cheap token estimation and dual-cap chunking, char-based.

    We deliberately avoid heavy dependencies (tiktoken and friends): they are
    accurate for GPT/Claude but wrong for Gemma/Mistral/others and would add
    a >1MB payload for marginal gain. We use a simple heuristic:

      * Latin/Cyrillic/etc: ~4 chars per token.
      * CJK: ~2 chars per token (each ideograph is often one token).

    Chunking is driven by **two independent caps**, both enforced
    simultaneously: whichever is reached first closes the current chunk.

      * ``budget``: maximum estimated tokens per chunk. Prevents overflowing
        the model's context window.
      * ``max_paragraphs``: maximum non-ignored paragraphs per chunk.
        Prevents the LLM from being overwhelmed by too many ``<Pn>...</Pn>``
        alignment markers when paragraphs are short (dialogue, TOC lists,
        one-line stanzas). Empirically, medium-sized local models start
        losing tags reliably above ~60-80 tags per chunk. Set to 0 to
        disable this cap and fall back to token-only chunking.

    Paragraphs that alone exceed the per-chunk budget are still emitted as
    a single-paragraph chunk (with a warning) rather than being split
    mid-sentence.
    """

    # Reasons why a chunk was closed. Exposed via ``chunk_with_stats``.
    REASON_TOKENS = 'tokens'
    REASON_PARAGRAPHS = 'paragraphs'
    REASON_OVERSIZED = 'oversized'
    REASON_END = 'end'

    def __init__(self, budget=12000, max_paragraphs=80,
                 ratio_latin=4.0, ratio_cjk=2.0, cjk_threshold=0.30):
        if budget < 100:
            budget = 100
        self.budget = int(budget)
        # 0 (or negative) disables the paragraph cap.
        self.max_paragraphs = max(0, int(max_paragraphs or 0))
        self.ratio_latin = float(ratio_latin)
        self.ratio_cjk = float(ratio_cjk)
        self.cjk_threshold = float(cjk_threshold)

    def estimate(self, text):
        if not text:
            return 0
        total = len(text)
        cjk = len(_CJK_RE.findall(text))
        # If more than threshold of the text is CJK, use CJK ratio for the
        # whole string (which slightly overestimates -- desirable, we want
        # a safety margin).
        if total > 0 and (cjk / total) >= self.cjk_threshold:
            return max(1, int(total / self.ratio_cjk))
        # Mixed: apply CJK ratio to CJK chars and Latin ratio to the rest.
        latin = total - cjk
        return max(1, int(cjk / self.ratio_cjk + latin / self.ratio_latin))

    def chunk(self, paragraphs, reserved=0):
        """Split ``paragraphs`` into contiguous chunks respecting both the
        token budget and the paragraph cap.

        :reserved: number of tokens to leave available for the system prompt,
            the running summary, the glossary and the model reply. The
            effective per-chunk budget is ``self.budget - reserved`` with a
            minimum of 200 tokens.

        Returns a list of paragraph-lists. Use ``chunk_with_stats`` to also
        obtain the per-chunk token estimate and the reason why each chunk
        was closed (useful for tuning / logging).
        """
        return [c for c, _tok, _reason
                in self.chunk_with_stats(paragraphs, reserved)]

    def chunk_with_stats(self, paragraphs, reserved=0):
        """Same as :meth:`chunk` but returns list of tuples
        ``(chunk, tokens_estimate, reason)`` where ``reason`` is one of
        ``TokenBudget.REASON_*``. The reason indicates which limit closed
        the chunk (or ``REASON_END`` for the tail chunk).
        """
        available = max(200, self.budget - int(reserved))
        chunks = []
        current = []
        current_tokens = 0
        current_translatable = 0  # non-ignored paragraph count

        for p in paragraphs:
            if getattr(p, 'ignored', False):
                # Ignored paragraphs still travel through the pipeline (they
                # must be re-injected into the DOM) but they consume no
                # tokens for translation and do not count toward the
                # paragraph cap.
                current.append(p)
                continue

            text = p.original or ''
            tokens = self.estimate(text)

            # Oversized single paragraph: emit alone (do not split mid-
            # sentence). If ``current`` is non-empty flush it first so
            # ordering is preserved.
            if tokens >= available:
                if current:
                    # Determine closing reason for the flushed chunk.
                    reason = self.REASON_TOKENS
                    if (self.max_paragraphs
                            and current_translatable >= self.max_paragraphs):
                        reason = self.REASON_PARAGRAPHS
                    chunks.append((current, current_tokens, reason))
                    current = []
                    current_tokens = 0
                    current_translatable = 0
                log.warn(
                    'Novel mode: paragraph estimated at %d tokens exceeds '
                    'per-chunk budget %d; sending as-is.'
                    % (tokens, available))
                chunks.append(([p], tokens, self.REASON_OVERSIZED))
                continue

            would_exceed_tokens = current_tokens + tokens > available
            would_exceed_paragraphs = (
                self.max_paragraphs
                and current_translatable >= self.max_paragraphs)

            if (would_exceed_tokens or would_exceed_paragraphs) and current:
                # Which cap fired first? If both, tokens takes precedence
                # (the harder limit for the model).
                if would_exceed_tokens:
                    reason = self.REASON_TOKENS
                else:
                    reason = self.REASON_PARAGRAPHS
                chunks.append((current, current_tokens, reason))
                current = [p]
                current_tokens = tokens
                current_translatable = 1
                continue

            current.append(p)
            current_tokens += tokens
            current_translatable += 1

        if current:
            chunks.append((current, current_tokens, self.REASON_END))
        return chunks


# ---------------------------------------------------------------------------
# Context / summary / glossary manager
# ---------------------------------------------------------------------------


# Cache info keys (single source of truth).
INFO_NOVEL_MODE = 'novel_mode'
INFO_NOVEL_SUMMARIES = 'novel_summaries'
INFO_NOVEL_GLOSSARY = 'novel_glossary'
INFO_NOVEL_PROGRESS = 'novel_progress'
INFO_NOVEL_CHAPTERS = 'novel_chapters_meta'


class ContextManager:
    """Persist and expose the running context for a novel translation.

    Two pieces of context are maintained:

      * ``summaries``: an ordered list of dicts
        ``{"chapter": int, "title": str, "summary": str}``, one per chapter
        that has already been translated.
      * ``glossary``: a dict mapping the original name (source language) to
        a dict ``{"translation": str, "type": str, "notes": str}``. The type
        is a free-form label (character/place/object/other/...); the notes
        are optional.

    Both are serialized as JSON in the SQLite ``info`` key/value table of the
    translation cache. No schema change is required.
    """

    def __init__(self, cache, glossary_max_entries=200,
                 summaries_keep_last=None):
        """
        :cache: a ``TranslationCache`` instance.
        :glossary_max_entries: hard cap. When new entries would exceed it,
            oldest entries are dropped (FIFO). Set to 0 for no limit.
        :summaries_keep_last: if not None, only the last N summaries are
            included in ``context_text``. Older ones still remain persisted
            in case the user wants to see them in the UI.
        """
        self.cache = cache
        self.glossary_max_entries = int(glossary_max_entries or 0)
        self.summaries_keep_last = summaries_keep_last
        self.summaries = []
        self.glossary = {}
        self.progress = 0

    # -- persistence -------------------------------------------------------

    def load(self):
        raw = self.cache.get_info(INFO_NOVEL_SUMMARIES)
        try:
            self.summaries = json.loads(raw) if raw else []
            if not isinstance(self.summaries, list):
                self.summaries = []
        except (ValueError, TypeError):
            self.summaries = []

        raw = self.cache.get_info(INFO_NOVEL_GLOSSARY)
        try:
            self.glossary = json.loads(raw) if raw else {}
            if not isinstance(self.glossary, dict):
                self.glossary = {}
        except (ValueError, TypeError):
            self.glossary = {}

        raw = self.cache.get_info(INFO_NOVEL_PROGRESS)
        try:
            self.progress = int(raw) if raw else 0
        except (ValueError, TypeError):
            self.progress = 0

        self.cache.set_info(INFO_NOVEL_MODE, '1')
        return self

    def _persist(self):
        self.cache.set_info(
            INFO_NOVEL_SUMMARIES, json.dumps(
                self.summaries, ensure_ascii=False))
        self.cache.set_info(
            INFO_NOVEL_GLOSSARY, json.dumps(
                self.glossary, ensure_ascii=False))
        self.cache.set_info(INFO_NOVEL_PROGRESS, str(self.progress))

    # -- getters -----------------------------------------------------------

    def get_progress(self):
        return self.progress

    def get_summaries(self):
        return list(self.summaries)

    def get_glossary(self):
        return dict(self.glossary)

    # -- mutation ----------------------------------------------------------

    def append_chapter(self, chapter_index, title, summary,
                       glossary_updates=None):
        """Record that ``chapter_index`` was completed.

        :summary: the summary text (already in the target language).
        :glossary_updates: iterable of dicts with at least ``source`` and
            ``translation`` keys; ``type`` and ``notes`` are optional.
            Duplicates (by ``source``) update the existing entry.
        """
        summary = (summary or '').strip()
        if summary or title:
            self.summaries.append({
                'chapter': int(chapter_index),
                'title': title or '',
                'summary': summary,
            })
        if glossary_updates:
            self._merge_glossary(glossary_updates)
        # Progress advances only forward.
        if chapter_index > self.progress:
            self.progress = int(chapter_index)
        self._persist()

    def _merge_glossary(self, updates):
        for item in updates:
            if not isinstance(item, dict):
                continue
            source = (item.get('source') or '').strip()
            translation = (item.get('translation') or '').strip()
            if not source or not translation:
                continue
            entry = self.glossary.get(source, {})
            entry['translation'] = translation
            if item.get('type'):
                entry['type'] = str(item['type']).strip()
            if item.get('notes'):
                entry['notes'] = str(item['notes']).strip()
            self.glossary[source] = entry
        # Enforce cap (FIFO on insertion order preserved by dict).
        if self.glossary_max_entries and \
                len(self.glossary) > self.glossary_max_entries:
            overflow = len(self.glossary) - self.glossary_max_entries
            for key in list(self.glossary.keys())[:overflow]:
                del self.glossary[key]

    def replace_glossary(self, new_glossary):
        """Wholesale replacement (used by the UI editor)."""
        self.glossary = {
            k: v for k, v in new_glossary.items()
            if isinstance(v, dict) and v.get('translation')}
        self._persist()

    def reset(self):
        self.summaries = []
        self.glossary = {}
        self.progress = 0
        self._persist()

    # -- context composition ----------------------------------------------

    def _format_summaries(self, summaries):
        if not summaries:
            return _('(none)')
        lines = []
        for s in summaries:
            title = s.get('title') or ''
            head = _('Chapter {n}').format(n=s.get('chapter', '?'))
            if title:
                head = '%s - %s' % (head, title)
            body = (s.get('summary') or '').strip()
            if body:
                lines.append('- %s: %s' % (head, body))
            else:
                lines.append('- %s' % head)
        return '\n'.join(lines)

    def _format_glossary(self, glossary):
        if not glossary:
            return _('(empty)')
        lines = []
        for source, entry in glossary.items():
            translation = entry.get('translation', '')
            gtype = entry.get('type', '')
            notes = entry.get('notes', '')
            extras = []
            if gtype:
                extras.append(gtype)
            if notes:
                extras.append(notes)
            suffix = ' (%s)' % ', '.join(extras) if extras else ''
            lines.append('- %s -> %s%s' % (source, translation, suffix))
        return '\n'.join(lines)

    def context_text(self, budget_tokens=1500, ratio=4.0):
        """Return a formatted string containing the recent summaries and the
        full glossary, truncated to fit ``budget_tokens`` (approximate).

        Priority when trimming (from most to least important, i.e. dropped
        last): glossary > most recent summaries > older summaries.
        """
        max_chars = max(200, int(budget_tokens * ratio))

        summaries = self.summaries
        if self.summaries_keep_last is not None:
            summaries = summaries[-int(self.summaries_keep_last):]

        glossary_text = self._format_glossary(self.glossary)
        summaries_text = self._format_summaries(summaries)

        combined = (
            _('Story so far (previous chapters summary):') + '\n'
            + summaries_text + '\n\n'
            + _('Glossary (use these exact translations):') + '\n'
            + glossary_text)

        if len(combined) <= max_chars:
            return combined

        # Progressively drop oldest summaries.
        while len(summaries) > 1:
            summaries = summaries[1:]
            summaries_text = self._format_summaries(summaries)
            combined = (
                _('Story so far (previous chapters summary):') + '\n'
                + summaries_text + '\n\n'
                + _('Glossary (use these exact translations):') + '\n'
                + glossary_text)
            if len(combined) <= max_chars:
                return combined

        # Still too big: truncate glossary lines.
        glossary_lines = glossary_text.split('\n')
        while glossary_lines and len(combined) > max_chars:
            glossary_lines.pop()
            glossary_text = '\n'.join(glossary_lines) or _('(truncated)')
            combined = (
                _('Story so far (previous chapters summary):') + '\n'
                + summaries_text + '\n\n'
                + _('Glossary (use these exact translations):') + '\n'
                + glossary_text)
        return combined


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------


DEFAULT_NOVEL_TRANSLATION_PROMPT = (
    'You are a professional literary translator working on a novel. '
    'Translate from <slang> to <tlang>. Preserve the author\'s narrative '
    'voice, tone, register and pacing. Do NOT summarize, shorten, expand, '
    'or explain anything. Do NOT answer questions in the text.\n\n'
    '{context}')


# Format instructions live in the USER message, not in the system prompt.
# Local models (Gemma, Mistral, LLaMA) tend to "forget" formatting rules
# placed in a long system prompt but respect them when they are the last
# thing they read before the actual task.
DEFAULT_NOVEL_FORMAT_INSTRUCTIONS = (
    'Translate each numbered paragraph below. Rules:\n'
    '1) Keep the exact marker "[N]" on its own line before each translated '
    'paragraph, in the same order and with the same numbers as the source.\n'
    '2) Do NOT drop, add, split, merge or renumber paragraphs.\n'
    '3) Do NOT translate the markers themselves.\n'
    '4) Preserve verbatim any inline placeholder like {id_XXXXX} '
    '(they represent images, line breaks and similar).\n'
    '5) Reply with the numbered paragraphs only. No preamble, no '
    'explanation, no closing remarks.\n\n'
    'Source paragraphs:\n\n{text}')


DEFAULT_NOVEL_SUMMARY_PROMPT = (
    'Summarize the following chapter of a novel in <tlang>. '
    'Write 150 to 350 words. Focus on: plot events, character '
    'introductions and developments, key locations, and any information '
    'that will be useful to translate the following chapters consistently '
    '(e.g. relationships between characters, unresolved threads). '
    'Do not include any preamble or metacommentary; return the summary '
    'text only.\n\n'
    'Chapter {chapter_num}: "{chapter_title}"\n\n'
    '{text}')


DEFAULT_NOVEL_GLOSSARY_PROMPT = (
    'You extract named entities from a translated novel chapter. '
    'List NEW entities not already in the existing list: characters, '
    'places, unique objects, organizations.\n\n'
    'Reply with ONLY a JSON object. No preamble, no explanation, no '
    'markdown fences. Follow this exact schema:\n\n'
    '{{"entities": [\n'
    '  {{"source": "Aslan", "translation": "Aslan", "type": "character", '
    '"notes": "the lion"}},\n'
    '  {{"source": "Narnia", "translation": "Narnia", "type": "place", '
    '"notes": ""}}\n'
    ']}}\n\n'
    'If no new entities, reply exactly: {{"entities": []}}\n\n'
    'Existing (skip these): {existing_keys}\n\n'
    'Source:\n{source_text}\n\n'
    'Translation:\n{translated_text}')


# ---------------------------------------------------------------------------
# Paragraph tagging / alignment
# ---------------------------------------------------------------------------


# Paragraph markers
# -----------------
#
# We use bracketed numeric markers ``[N]`` on their own line before each
# paragraph rather than XML-style ``<Pn>...</Pn>`` tags. Empirically, local
# LLMs (Gemma, Mistral, LLaMA-based) follow this format much more reliably:
# XML tags require nested balancing which the models tend to skip when the
# context is long, while numeric markers are the natural way these models
# already structure numbered lists in their training data.
#
# Format sent to the LLM:
#     [1]
#     First paragraph text.
#
#     [2]
#     Second paragraph text.
#
# Expected response:
#     [1]
#     Primo paragrafo tradotto.
#
#     [2]
#     Secondo paragrafo tradotto.

# Matches a marker line ``[N]`` capturing everything up to the next marker
# or end of string.  MULTILINE + DOTALL so ``.`` spans newlines inside a
# paragraph, and ``^\s*\[N\]`` anchors on a line by itself.
_MARKER_RE = re.compile(
    r'^[ \t]*\[(\d+)\][ \t]*\n(.*?)(?=\n[ \t]*\[\d+\][ \t]*\n|\Z)',
    re.MULTILINE | re.DOTALL)


def tag_paragraphs(paragraphs):
    """Return the ``[N]\\ntext`` block that will be sent to the LLM plus
    the list of indices used (in order).

    Ignored paragraphs are skipped (they carry no translatable content).
    """
    parts = []
    indices = []
    for i, p in enumerate(paragraphs, start=1):
        if getattr(p, 'ignored', False):
            continue
        text = (p.original or '').strip()
        parts.append('[%d]\n%s' % (i, text))
        indices.append(i)
    # Blank line between paragraphs helps the LLM keep them separated and
    # makes the parser boundary regex simpler / more robust.
    return '\n\n'.join(parts), indices


def parse_tagged_response(response, expected_indices):
    """Parse an LLM response containing ``[N]`` numeric markers.

    Returns a dict ``{index: translation}``. Missing indices are absent
    from the dict; callers can then decide how to handle the mismatch.

    The parser is tolerant of the common LLM habits:
      * leading/trailing prose (e.g. "Here is the translation:")
      * extra whitespace between markers
      * duplicate markers (last one wins)
      * hallucinated marker numbers (filtered by ``expected_indices``)
    """
    if not response:
        return {}
    found = {}
    for m in _MARKER_RE.finditer(response):
        try:
            idx = int(m.group(1))
        except (ValueError, TypeError):
            continue
        body = m.group(2)
        # Trim trailing prose after the last marker: if the body ends
        # with a blank line followed by additional text, that text is
        # commentary (e.g. "End of translation.") and must be dropped.
        # A blank line is ``\n\n`` with optional whitespace.
        blank_break = re.search(r'\n[ \t]*\n', body)
        if blank_break:
            # Everything after the blank line is discarded UNLESS it
            # itself contains a marker — but that case is already
            # handled by the outer finditer, so this cut is safe.
            body = body[:blank_break.start()]
        # Latest occurrence wins if duplicated.
        found[idx] = body.strip()
    # Filter to only expected indices to avoid pollution from
    # hallucinated tags.
    return {i: found[i] for i in expected_indices if i in found}


# ---------------------------------------------------------------------------
# Novel translator (sequential orchestrator)
# ---------------------------------------------------------------------------


def _extract_json_object(text):
    """Best-effort extraction of the first top-level JSON object in ``text``.

    LLMs (especially small ones) sometimes wrap JSON output in prose or a
    Markdown code fence. We scan for the first ``{`` and take the balanced
    substring up to its matching ``}``.
    """
    if not text:
        return None
    # Strip common markdown fences first (```json ... ```).
    fence_stripped = re.sub(
        r'^```(?:json)?\s*\n?|\n?```\s*$', '', text.strip(), flags=re.M)
    for candidate_text in (fence_stripped, text):
        start = candidate_text.find('{')
        if start < 0:
            continue
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(candidate_text)):
            ch = candidate_text[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == '\\':
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    candidate = candidate_text[start:i + 1]
                    try:
                        return json.loads(candidate)
                    except ValueError:
                        break  # try next candidate_text
    return None


# Fallback pattern for line-based entity extraction when JSON parsing fails.
# The separator between source and translation is restricted to arrow-like
# symbols (``->``, ``=>``, ``→``) which are unambiguous entity mappings;
# colon and pipe alone would match prose lines like "Here are the
# entities: ...".
_ENTITY_LINE_PATTERNS = [
    re.compile(
        # source: run of non-quote, non-arrow-marker chars.
        r'["\']?(?P<source>[^"\'\n\->=→|(]{1,80}?)["\']?\s*'
        # separator: any arrow form.
        r'(?:->|→|=>)\s*'
        # translation: run stopping before optional (type) or notes.
        r'["\']?(?P<translation>[^"\'\n(]{1,120}?)["\']?\s*'
        # optional (type)
        r'(?:\((?P<type>[^)\n]+)\))?\s*'
        # optional notes prefixed by : or - or |
        r'(?:[:\-\|]\s*(?P<notes>[^\n]{1,200}))?',
        re.MULTILINE),
]


def _extract_entities_fallback(text):
    """Extract entities using line-based regex when JSON parsing fails.

    Returns a list of dicts compatible with ``_extract_glossary_updates``.
    Only returns entries that look plausible (both source and translation
    non-empty, source shorter than 80 chars).
    """
    if not text:
        return []
    # Try to find lines that look like key/value entity mappings. We are
    # deliberately conservative: prefer no entries over noisy ones.
    entities = []
    seen_sources = set()
    for pattern in _ENTITY_LINE_PATTERNS:
        for m in pattern.finditer(text):
            source = (m.group('source') or '').strip(' "\',.;')
            translation = (m.group('translation') or '').strip(' "\',.;')
            # Filter obvious noise: skip lines that don't look like entities.
            if not source or not translation:
                continue
            if source == translation and len(source) < 3:
                continue
            if len(source) > 80 or len(translation) > 120:
                continue
            # Skip lines that are clearly prose (contain verbs / long text).
            if source.count(' ') > 5:
                continue
            if source.lower() in seen_sources:
                continue
            seen_sources.add(source.lower())
            entities.append({
                'source': source,
                'translation': translation,
                'type': (m.group('type') or '').strip() or 'other',
                'notes': (m.group('notes') or '').strip(' "\',.;'),
            })
    return entities


class NovelTranslator:
    """Sequential chapter-by-chapter translator with running context.

    Design constraints (contrasted with ``lib.translation.Translation``):

      * strictly sequential: chapter N+1 depends on the summary of chapter N.
      * per-chunk retry with alignment-aware re-request.
      * writes each translated paragraph into the cache as soon as it is
        available, so an interruption leaves a partial-but-consistent state.
      * bumps ``ContextManager.progress`` only when a full chapter is done.

    The translator engine is expected to expose the same interface as
    ``engines.base.Base.translate(text)`` and, if it is a ``GenAI`` subclass,
    the helper ``override_prompt(prompt)`` -- but we fall back gracefully
    if the helper is not available by assigning to ``translator.prompt``
    directly.
    """

    def __init__(self, translator, chapters, context_manager, cache,
                 config=None):
        self.translator = translator
        self.chapters = list(chapters)
        self.ctx = context_manager
        self.cache = cache
        self.config = dict(config or {})

        # Callbacks (all optional; safe defaults).
        self.progress = dummy       # (fraction: float, message: str)
        self.log = dummy            # (message: str, is_error: bool=False)
        self.chapter_started = dummy   # (chapter: Chapter)
        self.chapter_done = dummy      # (chapter: Chapter, summary: str,
                                       #  glossary_delta: list[dict])
        self.cancel_request = lambda: False

        # Runtime state.
        self.abort_count = 0
        self.total_chapters = 0
        self.completed_chapters = 0
        # One-shot log flag: set to True after the first _structured_active
        # call logs the chosen output format. Reset per instance.
        self._structured_choice_logged = False

    # -- setters (mirroring lib.translation.Translation) -------------------

    def set_progress(self, cb):
        self.progress = cb or dummy

    def set_logging(self, cb):
        self.log = cb or dummy

    def set_chapter_started(self, cb):
        self.chapter_started = cb or dummy

    def set_chapter_done(self, cb):
        self.chapter_done = cb or dummy

    def set_cancel_request(self, cb):
        self.cancel_request = cb or (lambda: False)

    # -- configuration accessors ------------------------------------------

    def _cfg(self, key, default):
        return self.config.get(key, default) if self.config else default

    @property
    def chunk_tokens(self):
        return int(self._cfg('novel_chunk_tokens', 12000))

    @property
    def max_paragraphs_per_chunk(self):
        """Maximum number of translatable paragraphs per chunk.

        Prevents the LLM from being overwhelmed by too many ``[N]``
        alignment markers when paragraphs are short (dialogue, TOC lists,
        one-line stanzas). The chunk is closed as soon as either the token
        budget or this paragraph cap is reached -- whichever comes first.
        Set to 0 to disable the cap and use only the token budget.
        """
        return int(self._cfg('novel_max_paragraphs_per_chunk', 80))

    @property
    def overlap_paragraphs(self):
        """Number of already-translated paragraphs from the previous chunk
        to replay as narrative context for the next chunk.

        Analogous to the sliding-window overlap used in RAG chunking, but
        here the overlap serves a different purpose: it preserves
        dialogue threads, pronoun referents and stylistic continuity
        across chunk boundaries. The overlap is:

          * shown to the LLM as *already-translated* text so it needs no
            further translation (avoids re-cost + preserves consistency);
          * not re-aligned into the DOM (the ``paragraph.translation``
            for those items was already written by the previous chunk);
          * subtracted from the per-chunk token budget so the total
            request size stays within the model window.

        Set to 0 to disable overlap entirely.
        """
        return max(0, int(self._cfg('novel_overlap_paragraphs', 3)))

    @property
    def structured_output_setting(self):
        """User preference for the structured (JSON) output path.

        Values:
          ``'auto'``  -- use structured output when the current engine
                         advertises support via ``structured_output_mode``.
                         Otherwise fall back to text markers ``[N]``.
                         This is the default and the safest choice.
          ``'off'``   -- always use text markers, even if the engine
                         supports structured output. Useful for debugging
                         or when a specific model produces low-quality
                         translations in JSON mode.
          ``'force'`` -- use structured output regardless of what the
                         engine advertises. Useful for OpenAI-compatible
                         custom endpoints (Ollama exotics, LM Studio,
                         vLLM, ...) that accept ``response_format`` but
                         do not declare the capability in the plugin.
        """
        value = self._cfg('novel_structured_output', 'auto')
        if value not in ('auto', 'off', 'force'):
            value = 'auto'
        return value

    def _engine_supports_structured(self):
        """Return True if the current translator declares native support
        for structured output (JSON mode or JSON schema)."""
        return getattr(
            self.translator, 'structured_output_mode', None) in (
                'json', 'schema')

    def _structured_active(self):
        """Combine the user setting and the engine capability to decide
        whether the current chunk should be translated via the structured
        path or the marker path.

        Emits a one-shot log line the first time it is called so the
        user sees which path is active without needing to inspect chunk
        payloads. The choice is stable per translation session (the
        engine and the config do not change mid-run).
        """
        setting = self.structured_output_setting
        supports = self._engine_supports_structured()

        if setting == 'off':
            active = False
        elif setting == 'force':
            active = True
        else:  # 'auto'
            active = supports

        # Verbose one-shot log: informs the user which output format the
        # LLM will be asked to produce.
        if not getattr(self, '_structured_choice_logged', False):
            self._structured_choice_logged = True
            engine_name = getattr(
                self.translator, 'name', self.translator.__class__.__name__)
            capability_desc = getattr(
                self.translator, 'structured_output_mode', None) or 'none'
            if active:
                self.log(_(
                    'Output format: structured JSON '
                    '(engine={eng}, capability={cap}, setting={s}). '
                    'Chunks can safely hold more paragraphs than with '
                    'text markers.').format(
                        eng=engine_name, cap=capability_desc, s=setting))
            else:
                if setting == 'off':
                    reason = _('disabled by user setting')
                elif not supports:
                    reason = _('engine does not advertise support')
                else:
                    reason = _('unknown')
                self.log(_(
                    'Output format: text markers [N] '
                    '(engine={eng}, capability={cap}, setting={s}, '
                    'reason={reason}).').format(
                        eng=engine_name, cap=capability_desc,
                        s=setting, reason=reason))
        return active

    @property
    def context_tokens(self):
        return int(self._cfg('novel_context_tokens', 1500))

    @property
    def summary_tokens(self):
        return int(self._cfg('novel_summary_tokens', 400))

    @property
    def min_chars_for_context(self):
        """Minimum translated-chapter length below which summary+glossary
        LLM calls are skipped. Guards against wasting time on front/back
        matter (Copyright, Table of Contents, About the Author, ...).
        """
        return int(self._cfg('novel_min_chars_for_context', 300))

    @property
    def translation_prompt(self):
        value = self._cfg('novel_translation_prompt', None)
        return value or DEFAULT_NOVEL_TRANSLATION_PROMPT

    @property
    def summary_prompt(self):
        value = self._cfg('novel_summary_prompt', None)
        return value or DEFAULT_NOVEL_SUMMARY_PROMPT

    @property
    def glossary_prompt(self):
        value = self._cfg('novel_glossary_prompt', None)
        return value or DEFAULT_NOVEL_GLOSSARY_PROMPT

    # -- engine plumbing ---------------------------------------------------

    def _apply_prompt(self, prompt_text):
        """Swap the engine's system prompt for the duration of one request.

        Uses ``override_prompt`` if defined by the engine (GenAI helper),
        else falls back to assigning to ``.prompt`` directly.
        """
        if hasattr(self.translator, 'override_prompt'):
            self.translator.override_prompt(prompt_text)
        else:
            self.translator.prompt = prompt_text

    def _restore_prompt(self):
        if hasattr(self.translator, 'restore_prompt'):
            self.translator.restore_prompt()

    def _fill_placeholders(self, template, extra=None):
        source_lang = getattr(self.translator, 'source_lang', '') or ''
        target_lang = getattr(self.translator, 'target_lang', '') or ''
        replacements = {
            '<slang>': source_lang or 'source language',
            '<tlang>': target_lang or 'target language',
        }
        if extra:
            replacements.update(extra)
        for k, v in replacements.items():
            template = template.replace(k, v)
        return template

    def _run_translation_call(self, user_text):
        """Invoke ``translator.translate`` handling both plain-string and
        generator (streaming) return values.
        """
        result = self.translator.translate(user_text)
        # Streaming: collect the generator.
        if hasattr(result, '__iter__') and not isinstance(result, str):
            try:
                result = ''.join(chunk for chunk in result)
            except TypeError:
                # Not actually a generator (e.g. bytes), let the engine
                # deal with it.
                pass
        return result or ''

    def _translate_with_retry(self, system_prompt, user_text, attempts=None):
        """Send ``system_prompt`` + ``user_text`` to the LLM with retries.

        Retries here are for total failures of the request (network,
        parsing, ...). Alignment-level retries are handled separately by
        ``_translate_chunk``.
        """
        attempts = attempts or getattr(
            self.translator, 'request_attempt', 3) or 3
        last_error = None
        for attempt in range(1, attempts + 1):
            if self.cancel_request():
                raise TranslationCanceled(_('Translation canceled.'))
            try:
                self._apply_prompt(system_prompt)
                return self._run_translation_call(user_text)
            except Exception as e:
                last_error = e
                self.log(
                    _('Novel mode request failed (attempt {}/{}): {}').format(
                        attempt, attempts, e), True)
                time.sleep(min(30, 5 * attempt))
            finally:
                self._restore_prompt()
        raise TranslationFailed(
            _('Novel mode: giving up after {} attempts. Last error: {}')
            .format(attempts, last_error))

    # -- chunk-level translation with alignment retry ---------------------

    def _translate_chunk(self, chunk_paragraphs, context_text,
                         chapter_num, chapter_title, chunk_num, total_chunks,
                         overlap_translations=None):
        """Dispatcher: choose between structured (JSON) and text-marker
        translation paths depending on engine capability and user config.

        The two paths implement the same contract:

            (chunk_paragraphs, ...) -> {chunk_local_index: translation}

        The dispatcher swaps them transparently; the caller
        (:meth:`_translate_chapter`) does not need to know which one was
        used. A one-shot log line at the very first invocation records
        the chosen path so the user can verify what is happening.
        """
        if self._structured_active():
            return self._translate_chunk_structured(
                chunk_paragraphs, context_text,
                chapter_num, chapter_title, chunk_num, total_chunks,
                overlap_translations=overlap_translations)
        return self._translate_chunk_markers(
            chunk_paragraphs, context_text,
            chapter_num, chapter_title, chunk_num, total_chunks,
            overlap_translations=overlap_translations)

    def _translate_chunk_markers(self, chunk_paragraphs, context_text,
                                 chapter_num, chapter_title, chunk_num,
                                 total_chunks, overlap_translations=None):
        """Translate one chunk of paragraphs, returning a dict
        ``{paragraph_index: translation}`` covering all non-ignored
        paragraphs. If the LLM misses some indices, up to 2 alignment
        retries are attempted before giving up (missing translations end
        up as ``None`` and the caller may re-run with a smaller chunk).

        :overlap_translations: optional list of already-translated
            paragraph texts from the immediately preceding chunk. When
            provided, they are shown to the LLM as narrative context
            (do NOT retranslate) so it can preserve pronouns, dialogue
            threads and stylistic continuity across chunk boundaries.
        """
        tagged, indices = tag_paragraphs(chunk_paragraphs)
        if not indices:
            return {}

        # System prompt: role + languages + narrative context (summary +
        # glossary). Static per-chapter -- no formatting rules here.
        system_prompt = self._fill_placeholders(
            self.translation_prompt, extra={'{context}': context_text})

        # Build the user message. Order matters: header, then optional
        # overlap block (already translated -- for reading only), then
        # format instructions + the tagged source paragraphs.
        header = _('Chapter {n}: "{title}" (chunk {c}/{t})').format(
            n=chapter_num, title=chapter_title,
            c=chunk_num, t=total_chunks)

        overlap_block = ''
        if overlap_translations:
            joined = '\n\n'.join(
                t.strip() for t in overlap_translations if t and t.strip())
            if joined:
                overlap_block = (
                    '\n\n'
                    + _('--- Context from previous paragraphs '
                        '(already translated -- do NOT modify or '
                        'retranslate this section) ---')
                    + '\n' + joined + '\n'
                    + _('--- End of context ---'))

        format_body = self._fill_placeholders(
            DEFAULT_NOVEL_FORMAT_INSTRUCTIONS, extra={'{text}': tagged})
        user_text = '%s%s\n\n%s' % (header, overlap_block, format_body)

        response = self._translate_with_retry(system_prompt, user_text)
        parsed = parse_tagged_response(response, indices)
        missing = [i for i in indices if i not in parsed]

        # Alignment retries: only ask for the missing paragraphs so the LLM
        # doesn't waste tokens re-translating the ones we already have.
        # The retry request omits the overlap block: the model has already
        # seen the surrounding context in the initial call, and repeating
        # it would just eat into the retry budget.
        for retry in range(2):
            if not missing:
                break
            self.log(
                _('Alignment retry {}: {} missing markers.').format(
                    retry + 1, len(missing)))
            fixup_paras = [chunk_paragraphs[i - 1] for i in missing]
            # Re-tag using the original indices so downstream logic stays
            # consistent.
            fixup_tagged = self._retag(fixup_paras, missing)
            fixup_body = self._fill_placeholders(
                _('The previous response was incomplete. Translate only '
                  'the numbered paragraphs below, keeping the exact same '
                  '[N] markers with the same numbers, in the same order. '
                  'Reply with the numbered paragraphs only.\n\n'
                  'Source paragraphs:\n\n{text}'),
                extra={'{text}': fixup_tagged})
            user_text = fixup_body
            response = self._translate_with_retry(system_prompt, user_text)
            fixup_parsed = parse_tagged_response(response, missing)
            parsed.update(fixup_parsed)
            missing = [i for i in indices if i not in parsed]

        if missing:
            self.log(
                _('Warning: {} paragraph(s) missing after retries: {}').format(
                    len(missing), missing), True)
        return parsed

    def _retag(self, paragraphs, indices):
        """Like ``tag_paragraphs`` but forces the marker numbers to be
        exactly ``indices`` (skipping ignored paragraphs). Uses the same
        ``[N]\\ntext`` format as :func:`tag_paragraphs`.
        """
        assert len(paragraphs) == len(indices)
        parts = []
        for p, idx in zip(paragraphs, indices):
            if getattr(p, 'ignored', False):
                continue
            text = (p.original or '').strip()
            parts.append('[%d]\n%s' % (idx, text))
        return '\n\n'.join(parts)

    # -- structured (JSON) output path -------------------------------------

    #: JSON Schema describing the response shape for the structured path.
    #: Kept as a class attribute so it can be reused as a stable reference
    #: across chunks (the value is constant per translation session).
    _STRUCTURED_RESPONSE_SCHEMA = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'paragraphs': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'additionalProperties': False,
                    'properties': {
                        'n': {'type': 'integer'},
                        'translation': {'type': 'string'},
                    },
                    'required': ['n', 'translation'],
                },
            },
        },
        'required': ['paragraphs'],
    }

    def _build_structured_payload(self, chunk_paragraphs, indices):
        """Return the JSON payload with source paragraphs to translate.

        The response must mirror this shape but with ``translation``
        replacing (or accompanying) the ``source`` field.
        """
        return {
            'paragraphs': [
                {
                    'n': i,
                    'source': (chunk_paragraphs[i - 1].original or '').strip(),
                }
                for i in indices
            ],
        }

    def _parse_structured_response(self, response, expected_indices):
        """Parse a JSON response and return ``{index: translation}``.

        Robust to the common LLM sloppiness:
          * responses wrapped in prose or Markdown fences (delegated to
            :func:`_extract_json_object`);
          * extra fields inside each paragraph object;
          * ``n`` values as strings instead of integers;
          * missing paragraphs (caller handles via alignment retry);
          * hallucinated indices not in ``expected_indices``.
        """
        if not response:
            return {}
        obj = _extract_json_object(response)
        if not obj or not isinstance(obj.get('paragraphs'), list):
            return {}
        expected = set(expected_indices)
        result = {}
        for item in obj['paragraphs']:
            if not isinstance(item, dict):
                continue
            raw_n = item.get('n')
            try:
                n = int(raw_n)
            except (TypeError, ValueError):
                continue
            if n not in expected:
                continue
            translation = (item.get('translation') or '').strip()
            if translation:
                result[n] = translation
        return result

    def _translate_with_retry_structured(self, system_prompt, user_text,
                                         schema=None, attempts=None):
        """Same retry loop as :meth:`_translate_with_retry` but the
        request body is built via ``engine.get_body_for_structured`` so
        the server enforces the JSON response.

        The structured body includes ``stream: true`` so that long
        responses (80+ translated paragraphs) are delivered token by
        token without triggering the client-side request timeout.
        Because the engine's ``_parse_stream`` returns a generator, we
        must reassemble all chunks into a single string here before the
        caller tries to parse the JSON.

        Additionally, the engine's ``request_timeout`` is temporarily
        raised to at least 300 seconds as a safety net: with streaming
        the timeout only governs the connection and the first byte, so
        300 s is never reached in practice, but it protects against edge
        cases where the server is slow to start streaming.

        TCP keepalive is also enabled for the duration of the structured
        call (``request_keepalive = True``). This prevents intermediate
        NAT devices / stateful firewalls (typical home routers, corporate
        proxies) from dropping the connection during the time the LLM
        spends generating the first token. Without keepalive we observed
        Ollama's ``srv stop: cancel task`` at exactly the router NAT
        session timeout (~30s).

        Implementation swaps ``get_body`` temporarily rather than
        threading a "structured" flag through :meth:`_translate_with_retry`;
        this keeps the retry / backoff / cancel logic in one place.
        """
        from types import GeneratorType

        translator = self.translator
        original_get_body = translator.get_body
        original_timeout = getattr(translator, 'request_timeout', None)
        original_keepalive = getattr(translator, 'request_keepalive', False)
        # Raise timeout defensively; with streaming this only covers the
        # time until the first token arrives, not the total generation.
        min_structured_timeout = 300.0
        if original_timeout is not None \
                and original_timeout < min_structured_timeout:
            translator.request_timeout = min_structured_timeout
        # Enable TCP keepalive on the underlying socket. The structured
        # path may spend tens of seconds waiting for the first streamed
        # token from the LLM; without keepalive, intermediate NAT devices
        # (routers, corporate firewalls) silently drop the connection
        # after ~30s of idle, causing the Ollama-side "cancel task" we
        # observed in the logs.
        translator.request_keepalive = True

        def structured_get_body(text):
            return translator.get_body_for_structured(text, schema)

        translator.get_body = structured_get_body
        try:
            result = self._translate_with_retry(
                system_prompt, user_text, attempts=attempts)
        finally:
            translator.get_body = original_get_body
            if original_timeout is not None:
                translator.request_timeout = original_timeout
            translator.request_keepalive = original_keepalive

        # If the engine returned a streaming generator (because stream:true
        # is set in the body), collect all chunks now so the JSON parser
        # receives the complete response string.
        if isinstance(result, GeneratorType):
            result = ''.join(chunk for chunk in result)

        return result or ''

    def _translate_chunk_structured(self, chunk_paragraphs, context_text,
                                    chapter_num, chapter_title, chunk_num,
                                    total_chunks, overlap_translations=None):
        """Translate one chunk via the engine's native JSON output.

        Contract identical to :meth:`_translate_chunk_markers` -- returns
        ``{chunk_local_index: translation}`` covering all non-ignored
        paragraphs. Alignment retries call the *marker* path as a safety
        net so we always converge on some usable output even when the
        JSON server rejects our schema.
        """
        indices = [
            i for i, p in enumerate(chunk_paragraphs, start=1)
            if not getattr(p, 'ignored', False)
        ]
        if not indices:
            return {}

        # System prompt: role + languages + narrative context (summary +
        # glossary). Same as the marker path.
        system_prompt = self._fill_placeholders(
            self.translation_prompt, extra={'{context}': context_text})

        # User message: header + optional overlap block + JSON schema
        # instructions + serialized payload.
        header = _('Chapter {n}: "{title}" (chunk {c}/{t})').format(
            n=chapter_num, title=chapter_title,
            c=chunk_num, t=total_chunks)

        overlap_block = ''
        if overlap_translations:
            joined = '\n\n'.join(
                t.strip() for t in overlap_translations if t and t.strip())
            if joined:
                overlap_block = (
                    '\n\n'
                    + _('--- Context from previous paragraphs '
                        '(already translated -- do NOT modify or '
                        'retranslate this section) ---')
                    + '\n' + joined + '\n'
                    + _('--- End of context ---'))

        payload = self._build_structured_payload(chunk_paragraphs, indices)
        payload_json = json.dumps(payload, ensure_ascii=False, indent=2)

        instructions = _(
            'You will receive a JSON object with a list of numbered '
            'source paragraphs. Reply with a JSON object of the same '
            'shape, where each paragraph carries a "translation" field '
            'containing your translation of "source". Preserve the "n" '
            'field verbatim. Preserve any inline placeholder like '
            '{id_XXXXX}. Do not add, drop, or renumber paragraphs. '
            'Return ONLY the JSON object, no preamble.')

        user_text = (
            '%s%s\n\n%s\n\nInput:\n%s'
            % (header, overlap_block, instructions, payload_json))

        response = self._translate_with_retry_structured(
            system_prompt, user_text,
            schema=self._STRUCTURED_RESPONSE_SCHEMA)
        parsed = self._parse_structured_response(response, indices)
        missing = [i for i in indices if i not in parsed]

        # Alignment retries (structured): ask only for the missing
        # paragraphs, still in JSON form. If two retries still fail, fall
        # back to the marker path for the remaining ones (belt and
        # suspenders).
        for retry in range(2):
            if not missing:
                break
            self.log(
                _('Structured retry {}: {} missing entries.').format(
                    retry + 1, len(missing)))
            fixup_indices = list(missing)
            fixup_payload = self._build_structured_payload(
                chunk_paragraphs, fixup_indices)
            fixup_json = json.dumps(
                fixup_payload, ensure_ascii=False, indent=2)
            fixup_body = (
                _('The previous JSON response was incomplete. Reply '
                  'with a JSON object translating ONLY the paragraphs '
                  'below. Same shape as before: "paragraphs" array of '
                  '{"n": int, "translation": string}. Return JSON only.')
                + '\n\nInput:\n' + fixup_json)
            response = self._translate_with_retry_structured(
                system_prompt, fixup_body,
                schema=self._STRUCTURED_RESPONSE_SCHEMA)
            fixup_parsed = self._parse_structured_response(
                response, fixup_indices)
            parsed.update(fixup_parsed)
            missing = [i for i in indices if i not in parsed]

        if missing:
            # Last-resort fallback: try the marker path for the leftover
            # paragraphs. This handles the corner case where the server
            # refuses the JSON schema on a specific input (rare).
            self.log(
                _('Structured path could not resolve {} paragraph(s); '
                  'falling back to text markers for those.').format(
                      len(missing)))
            fallback_paras = [
                chunk_paragraphs[i - 1] for i in missing]
            fallback_result = self._translate_chunk_markers(
                fallback_paras, context_text,
                chapter_num, chapter_title, chunk_num, total_chunks,
                overlap_translations=overlap_translations)
            # Map back to the original chunk-local indices.
            for local_i, i in enumerate(missing, start=1):
                if local_i in fallback_result:
                    parsed[i] = fallback_result[local_i]
            missing = [i for i in indices if i not in parsed]

        if missing:
            self.log(
                _('Warning: {} paragraph(s) missing after all retries: {}')
                .format(len(missing), missing), True)
        return parsed

    # -- summary / glossary extraction -------------------------------------

    def _build_translated_chapter_text(self, paragraphs, translations):
        parts = []
        for i, p in enumerate(paragraphs, start=1):
            if getattr(p, 'ignored', False):
                continue
            t = translations.get(i)
            if t:
                parts.append(t)
        return '\n\n'.join(parts)

    def _build_source_chapter_text(self, paragraphs):
        parts = []
        for p in paragraphs:
            if getattr(p, 'ignored', False):
                continue
            text = (p.original or '').strip()
            if text:
                parts.append(text)
        return '\n\n'.join(parts)

    def _head_and_tail(self, text, max_chars):
        """Truncate ``text`` to at most ``max_chars``, keeping only the head.

        Used for summary/glossary prompts. We deliberately take ONLY the
        beginning of the translated chapter text because:

          * The opening paragraphs reliably introduce the characters, setting
            and plot thread for that chapter -- exactly what a useful summary
            needs.

        If the text already fits within ``max_chars`` it is returned verbatim.
        If ``max_chars`` <= 0, truncation is disabled.
        """
        if max_chars <= 0 or len(text) <= max_chars:
            return text
        return text[:max_chars]

    def _summary_input_budget_chars(self):
        """Max characters to feed the summary/glossary LLM calls.

        Rule of thumb: keep the input under ~4x the token budget reserved
        for these auxiliary calls, so the model has room for its own
        response. Hardcoded to a sensible default; the ``novel_summary_
        input_max_chars`` config key can override.
        """
        default = 12000  # ~3000 words in Latin text
        return int(self._cfg('novel_summary_input_max_chars', default))

    def _generate_summary(self, chapter, translated_text):
        if not translated_text.strip():
            return ''
        max_chars = self._summary_input_budget_chars()
        clipped = self._head_and_tail(translated_text, max_chars)
        if len(clipped) < len(translated_text):
            self.log(_(
                'Summary input truncated: {} -> {} chars.').format(
                    len(translated_text), len(clipped)))
        system_prompt = self._fill_placeholders(
            _('You are a helpful assistant that produces concise summaries.'))
        user_prompt = self._fill_placeholders(
            self.summary_prompt.format(
                chapter_num=chapter.index,
                chapter_title=chapter.title,
                text=clipped))
        try:
            response = self._translate_with_retry(
                system_prompt, user_prompt, attempts=2)
        except TranslationFailed as e:
            self.log(_('Summary generation failed: {}').format(e), True)
            return ''
        return response.strip()

    def _extract_glossary_updates(self, chapter, source_text, translated_text):
        if not source_text.strip() or not translated_text.strip():
            return []
        max_chars = self._summary_input_budget_chars()
        src_clipped = self._head_and_tail(source_text, max_chars)
        tgt_clipped = self._head_and_tail(translated_text, max_chars)
        existing_keys = ', '.join(sorted(self.ctx.get_glossary().keys())) \
            or _('(none)')
        system_prompt = self._fill_placeholders(
            _('You are a helpful assistant. Answer with strict JSON only.'))
        user_prompt = self._fill_placeholders(
            self.glossary_prompt.format(
                existing_keys=existing_keys,
                source_text=src_clipped,
                translated_text=tgt_clipped))
        try:
            response = self._translate_with_retry(
                system_prompt, user_prompt, attempts=2)
        except TranslationFailed as e:
            self.log(
                _('Glossary extraction failed: {}').format(e), True)
            return []

        entities = []
        # Path 1: JSON parsing (preferred).
        obj = _extract_json_object(response)
        if obj and isinstance(obj.get('entities'), list):
            for item in obj['entities']:
                if not isinstance(item, dict):
                    continue
                src = (item.get('source') or '').strip()
                tgt = (item.get('translation') or '').strip()
                if not src or not tgt:
                    continue
                entities.append({
                    'source': src,
                    'translation': tgt,
                    'type': (item.get('type') or '').strip() or 'other',
                    'notes': (item.get('notes') or '').strip(),
                })

        # Path 2: line-based regex fallback if JSON gave us nothing.
        if not entities:
            fallback = _extract_entities_fallback(response)
            if fallback:
                self.log(
                    _('Glossary extraction: JSON not usable, recovered '
                      '{} entries via fallback parser.').format(
                          len(fallback)))
                entities = fallback
            else:
                self.log(
                    _('Glossary extraction: could not parse JSON, '
                      'skipping.'), True)

        # Filter out entities already present (LLMs often repeat despite
        # being told not to).
        existing = set(self.ctx.get_glossary().keys())
        filtered = [e for e in entities if e['source'] not in existing]
        if filtered:
            self.log(_('Glossary: +{} new entries (chapter {}).').format(
                len(filtered), chapter.index))
        return filtered

    # -- persistence -------------------------------------------------------

    def _store_chapter(self, chapter, translations):
        """Write chapter translations back to cache paragraphs."""
        engine_name = getattr(self.translator, 'name', None)
        target_lang = None
        if hasattr(self.translator, 'get_target_lang'):
            try:
                target_lang = self.translator.get_target_lang()
            except Exception:
                target_lang = None
        target_lang = target_lang or getattr(
            self.translator, 'target_lang', None)

        for i, paragraph in enumerate(chapter.paragraphs, start=1):
            if paragraph.ignored:
                continue
            translation = translations.get(i)
            if translation is None:
                continue
            paragraph.translation = translation
            paragraph.engine_name = engine_name
            paragraph.target_lang = target_lang
            paragraph.is_cache = False
            self.cache.update_paragraph(paragraph)

    # -- main loop ---------------------------------------------------------

    def run(self):
        """Execute the pipeline. Returns the number of chapters translated."""
        self.total_chapters = len(self.chapters)
        self.completed_chapters = 0
        if self.total_chapters == 0:
            self.log(_('Novel mode: no chapters to translate.'))
            return 0

        start = self.ctx.get_progress()
        if start >= self.total_chapters:
            self.log(
                _('Novel mode: nothing to do (progress={}, chapters={}).')
                .format(start, self.total_chapters))
            return 0

        self.log(sep())
        self.log(_('Novel mode: starting.'))
        self.log(_('Total chapters: {}').format(self.total_chapters))
        self.log(_('Resuming from chapter: {}').format(start + 1))
        self.log(sep('┈'))

        start_ts = time.time()
        for chapter in self.chapters[start:]:
            if self.cancel_request():
                raise TranslationCanceled(_('Translation canceled.'))
            self._translate_chapter(chapter)
            self.completed_chapters += 1

        elapsed = round((time.time() - start_ts) / 60, 2)
        self.log(sep())
        self.log(_('Novel mode: completed {} chapter(s) in {} minutes.')
                 .format(self.completed_chapters, elapsed))
        self.progress(1.0, _('Novel mode: completed.'))
        return self.completed_chapters

    def _translate_chapter(self, chapter):
        self.chapter_started(chapter)
        self.log(sep())
        self.log(_('Chapter {}/{}: {}').format(
            chapter.index, self.total_chapters, chapter.title))

        total_chars = sum(
            len(p.original or '')
            for p in chapter.paragraphs if not p.ignored)
        self.log(_(
            '  Structure: {} page(s), {} paragraphs, {} chars. '
            'page_ids: {}').format(
                len(chapter.page_ids),
                len(chapter.paragraphs),
                total_chars,
                chapter.page_ids[:5])
            + (' ...' if len(chapter.page_ids) > 5 else ''))

        translatable = chapter.translatable_paragraphs()
        if not translatable:
            self.log(_('Chapter {} has no translatable content, skipping.')
                     .format(chapter.index))
            self.ctx.append_chapter(chapter.index, chapter.title, '', [])
            self.chapter_done(chapter, '', [])
            self._report_progress()
            return

        # Chunk with dual-cap (token budget + paragraph count).
        budget = TokenBudget(
            budget=self.chunk_tokens,
            max_paragraphs=self.max_paragraphs_per_chunk,
        )
        overlap_reserved = self.overlap_paragraphs * 80
        chunks_with_stats = budget.chunk_with_stats(
            translatable,
            reserved=(
                self.context_tokens + self.summary_tokens + overlap_reserved))
        chunks = [c for c, _tok, _reason in chunks_with_stats]
        total_chunks = len(chunks)
        cap_paragraphs_display = (
            str(self.max_paragraphs_per_chunk)
            if self.max_paragraphs_per_chunk else _('unlimited'))
        overlap_display = (
            str(self.overlap_paragraphs)
            if self.overlap_paragraphs else _('disabled'))
        self.log(_(
            'Split into {} chunk(s). Caps: {} tokens / {} paragraphs. '
            'Overlap: {} paragraphs.')
            .format(
                total_chunks, self.chunk_tokens, cap_paragraphs_display,
                overlap_display))
        # Per-chunk diagnostic (helps tune the caps against a real book).
        # ``reason`` is one of TokenBudget.REASON_* and tells which limit
        # closed the chunk.
        for i, (chunk_paras, tok_est, reason) in enumerate(
                chunks_with_stats, start=1):
            visible = sum(
                1 for p in chunk_paras if not getattr(p, 'ignored', False))
            self.log(_(
                '  Chunk {}/{}: {} paragraphs, ~{} tokens '
                '(closed by: {}).').format(
                    i, total_chunks, visible, tok_est, reason))

        context_text = self.ctx.context_text(
            budget_tokens=self.context_tokens)

        # Translate each chunk.
        translations = {}
        # We need to map each translatable paragraph's chunk-local index to
        # its position inside the *chapter*. Simplest: enumerate the chapter
        # paragraphs (skipping ignored) and remember, for each chunk, which
        # chapter-index each of its paragraphs corresponds to.
        chapter_local_index = {}
        counter = 0
        for i, p in enumerate(chapter.paragraphs, start=1):
            if p.ignored:
                continue
            counter += 1
            chapter_local_index[counter] = i  # translatable_seq -> chapter_seq

        # Sliding overlap: after each chunk we capture up to
        # ``self.overlap_paragraphs`` of its just-produced translations
        # and pass them to the next chunk as reading context. The first
        # chunk of a chapter starts with an empty overlap.
        overlap_translations = []

        seq = 0
        for c_idx, chunk in enumerate(chunks, start=1):
            if self.cancel_request():
                raise TranslationCanceled(_('Translation canceled.'))
            # Local (per-chunk) indices are what the LLM sees; we later
            # rewrite them back into chapter-level indices.
            chunk_result = self._translate_chunk(
                chunk, context_text, chapter.index, chapter.title,
                c_idx, total_chunks,
                overlap_translations=overlap_translations or None)

            # Track the translations produced by THIS chunk so we can
            # build the overlap for the NEXT one. We record them in the
            # order the LLM saw them (chunk-local order), not in chapter
            # order, so that a "recent context" window is preserved.
            new_translations_in_chunk = []
            for local_i in range(1, len(chunk) + 1):
                p = chunk[local_i - 1]
                if p.ignored:
                    continue
                seq += 1
                translation = chunk_result.get(local_i)
                if translation is not None:
                    translations[chapter_local_index[seq]] = translation
                    new_translations_in_chunk.append(translation)
            # Persist translations as they arrive.
            self._store_chapter(chapter, translations)

            # Prepare overlap for the next chunk (last N translated
            # paragraphs of THIS chunk). If this chunk produced fewer
            # translations than the overlap window, the window naturally
            # shrinks to what is available.
            if self.overlap_paragraphs > 0 and new_translations_in_chunk:
                overlap_translations = new_translations_in_chunk[
                    -self.overlap_paragraphs:]
            else:
                overlap_translations = []

        # Summary + glossary.
        source_text = self._build_source_chapter_text(chapter.paragraphs)
        translated_text = self._build_translated_chapter_text(
            chapter.paragraphs, translations)

        # Skip context extraction on trivially short chapters
        # (Copyright, TOC, About the Author, ...). They are still
        # translated normally at the paragraph level; only the two
        # extra LLM calls (summary + glossary) are avoided.
        translated_len = len(translated_text.strip())
        summary = ''
        glossary_delta = []
        threshold = self.min_chars_for_context
        if translated_len < threshold:
            self.log(_(
                'Chapter {}: {} chars translated, below threshold {}. '
                'Skipping summary + glossary extraction.').format(
                    chapter.index, translated_len, threshold))
        else:
            summary = self._generate_summary(chapter, translated_text)
            if summary:
                preview = summary.strip().replace('\n', ' ')
                if len(preview) > 160:
                    preview = preview[:157] + '...'
                self.log(_('Summary (chapter {}): {}').format(
                    chapter.index, preview))
            else:
                self.log(_(
                    'Summary (chapter {}): empty response.').format(
                        chapter.index), True)
            glossary_delta = self._extract_glossary_updates(
                chapter, source_text, translated_text)

        # Persist context (marks chapter as done, bumps progress).
        self.ctx.append_chapter(
            chapter.index, chapter.title, summary, glossary_delta)
        self.chapter_done(chapter, summary, glossary_delta)
        self._report_progress()

    def _report_progress(self):
        done = self.ctx.get_progress()
        total = self.total_chapters or 1
        fraction = min(1.0, done / float(total))
        self.progress(
            fraction,
            _('Novel mode: chapter {}/{} done.').format(done, total))


# ---------------------------------------------------------------------------
# Helper: cache-id namespacing for novel mode
# ---------------------------------------------------------------------------


def novel_cache_id(input_path, engine_name, target_lang, encoding=''):
    """Compute a cache id specific to novel mode.

    The classic cache id (see ``lib/conversion.py:convert_item``) mixes in
    ``merge_length``. Novel mode has no merge length, so we substitute the
    tag ``novel_v1`` to keep the two caches strictly separated. That way,
    switching modes on the same book does not clobber the other mode's
    stored translations.
    """
    return uid(
        input_path + engine_name + target_lang + 'novel_v1'
        + (encoding or ''))
