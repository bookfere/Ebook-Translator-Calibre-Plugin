from typing import List


class ContextManager:
    """Manages context paragraphs for translation to improve quality.
    
    Based on techniques from:
    - https://github.com/hydropix/TranslateBooksWithLLMs
    - https://github.com/yihong0618/bilingual_book_maker
    """

    def __init__(self, paragraph_limit: int = 3, max_tokens: int = 2000, position: str = 'before'):
        """Initialize context manager.

        Args:
            paragraph_limit: Maximum number of context paragraphs to keep
            max_tokens: Maximum tokens for context (approximately chars/4)
            position: Direction of context ('before' or 'after')
        """
        self.paragraph_limit = paragraph_limit
        self.max_tokens = max_tokens
        self.position = position
        self.paragraphs = {}

    def load_paragraphs(self, paragraphs):
        """Load all paragraphs to allow direct lookup by row index for concurrent translation."""
        self.paragraphs = {int(p.id): p for p in paragraphs}
        # print(f"DEBUG: ContextManager loaded {len(self.paragraphs)} paragraphs. Keys: {list(self.paragraphs.keys())[:10]}...")

    def get_context_items(self, current_row: int) -> List[dict]:
        """Fetch the previous or next valid context paragraphs based on the current row and stored position."""
        if current_row < 0 or not self.paragraphs:
            return []

        items = []
        total_chars = 0
        
        # Determine search range based on stored position
        if self.position == 'before':
            rows = range(current_row - 1, current_row - 1 - self.paragraph_limit, -1)
        else:
            rows = range(current_row + 1, current_row + 1 + self.paragraph_limit)
            
        for row in rows:
            if row < 0 or row >= len(self.paragraphs):
                # Using len(self.paragraphs) as a proxy, but better to check if row exists
                if row not in self.paragraphs:
                    continue
            
            p = self.paragraphs.get(row)
            if not p:
                continue
                
            original = p.original.strip()
            # If the translation is not done yet (e.g., due to concurrency), it might be empty.
            translation = p.translation.strip() if hasattr(p, 'translation') and p.translation else ''
            
            if not original:
                continue
                
            if total_chars + len(original) + len(translation) > self.max_tokens * 4:
                break
                
            if self.position == 'before':
                items.insert(0, {'original': original, 'translation': translation})
            else:
                items.append({'original': original, 'translation': translation})
            total_chars += len(original) + len(translation)
            
        return items

    def get_context_block(self, current_row: int) -> str:
        """Get the formatted context block for reference."""
        items = self.get_context_items(current_row)
        if not items:
            return ''

        context_parts = []
        for item in items:
            original = item['original']
            translation = item['translation']
            
            if translation:
                context_parts.append(f"Original: {original}\nTranslation: {translation}")
            else:
                context_parts.append(f"Original: {original}")

        context_text = "\n---\n".join(context_parts)
        
        direction = 'PREVIOUS' if self.position == 'before' else 'NEXT'
        header = f"### {direction} CONTEXT (for reference only):"
        parsing_note = (
            "IMPORTANT: This context is for reference ONLY. DO NOT include, "
            "reference, or summarize any part of this context in your output. "
            "Lines starting with 'Original:' or 'Translation:' contain literal "
            "content from other parts of the book. Your task is to translate "
            "ONLY the specific text provided after this block. "
            "This context rule ends at '### END OF CONTEXT'."
        )
        footer = "### END OF CONTEXT"
        
        return f"{header}\n{parsing_note}\n\n{context_text}\n\n{footer}"

    def get_chat_messages(self, current_row: int) -> List[dict]:
        """Get context as a list of chat messages for LLM APIs."""
        items = self.get_context_items(current_row)
        if not items:
            return []
            
        messages = []
        for item in items:
            original = item['original']
            translation = item['translation']
            
            # For Chat APIs, having pairs is strongly recommended.
            # We use a clear prefix to indicate these are for context/reference.
            messages.append({'role': 'user', 'content': f"[Context] Original:\n{original}"})
            if translation:
                messages.append({'role': 'assistant', 'content': translation})
                
        return messages

    # Deprecated/Unused methods left for API compatibility
    def add_paragraph(self, original: str, translation: str = ''):
        pass

    def clear(self):
        self.paragraphs.clear()
        self.current_row = -1

    def update_translation(self, original: str, translation: str):
        pass

    def get_summary_context(self) -> str:
        return self.get_context()
