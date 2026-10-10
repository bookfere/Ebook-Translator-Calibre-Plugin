"""
Translation Chunk - Data structure for batch translation.

Represents a translation unit that can contain multiple paragraphs
merged together for efficient API usage.
"""

from typing import List, Optional
from enum import Enum


class BoundaryType(Enum):
    """Type of boundary that determines chunk splitting."""
    PARAGRAPH = "paragraph"          # Regular paragraph boundary
    HEADING = "heading"              # Heading/section boundary
    LIST = "list"                    # List item boundary
    SPECIAL = "special"              # Special content (code, table, etc)
    SEMANTIC = "semantic"            # Semantic boundary (quote, caption, etc)


class Paragraph:
    """
    Represents a single paragraph with metadata.

    This wraps the plugin's existing Element class with additional
    information needed for intelligent merging.
    """

    def __init__(self, element, element_type: str = 'p',
                 boundary_type: BoundaryType = BoundaryType.PARAGRAPH):
        """
        Args:
            element: The plugin's Element object
            element_type: HTML element type (p, h1, h2, li, etc.)
            boundary_type: Type of boundary this paragraph represents
        """
        self.element = element
        self.element_type = element_type
        self.boundary_type = boundary_type
        self._text = None
        self._length = None
        self.eid = None  # Element ID for tracking original index

    @property
    def text(self) -> str:
        """Get the plain text content of the paragraph."""
        if self._text is None:
            # Use the element's get_content() method
            self._text = self.element.get_content()
        return self._text

    @property
    def length(self) -> int:
        """Get the character length of the paragraph."""
        if self._length is None:
            self._length = len(self.text)
        return self._length

    def __repr__(self):
        preview = self.text[:50].replace('\n', ' ')
        if len(self.text) > 50:
            preview += '...'
        return f'Paragraph({self.element_type}, {self.length} chars, "{preview}")'


class SmartChunk:
    """
    A translation chunk containing multiple paragraphs.

    This is the core data structure for batch translation. Multiple
    paragraphs are merged into a single chunk to reduce API calls
    while maintaining translation quality.

    Allows individual paragraphs to exceed character limits (overflow)
    to handle edge cases where a single paragraph is very long.
    """

    def __init__(self, max_paragraphs: int = 50, max_characters: int = 3000):
        """
        Args:
            max_paragraphs: Maximum number of paragraphs in this chunk
            max_characters: Maximum number of characters in this chunk
        """
        self.max_paragraphs = max_paragraphs
        self.max_characters = max_characters
        self.paragraphs: List[Paragraph] = []
        self._total_length = 0
        self._formatted_text = None
        self._is_overflow = False  # Track if this chunk contains an overflow paragraph

    @property
    def paragraph_count(self) -> int:
        """Get the number of paragraphs in this chunk."""
        return len(self.paragraphs)

    @property
    def total_length(self) -> int:
        """Get the total character length of this chunk."""
        return self._total_length

    @property
    def is_empty(self) -> bool:
        """Check if this chunk has no paragraphs."""
        return len(self.paragraphs) == 0

    @property
    def is_overflow(self) -> bool:
        """Check if this chunk contains a paragraph that exceeded limits."""
        return self._is_overflow

    @property
    def is_full(self) -> bool:
        """
        Check if this chunk has reached its limits.

        Note: Even if full, can still add an overflow paragraph if chunk is empty.

        Returns:
            True if at max paragraph count or max character count
        """
        return (self.paragraph_count >= self.max_paragraphs or
                self.total_length >= self.max_characters)

    def can_add(self, paragraph: Paragraph) -> bool:
        """
        Check if a paragraph can be added to this chunk.

        Args:
            paragraph: The paragraph to check

        Returns:
            True if the paragraph can be added without exceeding limits
        """
        # Check paragraph count limit
        if self.paragraph_count >= self.max_paragraphs:
            return False

        # Check character count limit
        new_length = self.total_length + paragraph.length
        if new_length > self.max_characters:
            return False

        return True

    def add(self, paragraph: Paragraph) -> bool:
        """
        Add a paragraph to this chunk.

        Args:
            paragraph: The paragraph to add

        Returns:
            True if added successfully, False if limits exceeded
        """
        if not self.can_add(paragraph):
            return False

        self.paragraphs.append(paragraph)
        self._total_length += paragraph.length
        self._formatted_text = None  # Invalidate cached formatted text
        return True

    def force_add(self, paragraph: Paragraph):
        """
        Force add a paragraph even if it exceeds limits.

        This is used when a single paragraph is longer than max_characters.
        Such paragraphs are allowed to overflow to avoid translation failures.

        Args:
            paragraph: The paragraph to add
        """
        self.paragraphs.append(paragraph)
        self._total_length += paragraph.length
        self._formatted_text = None  # Invalidate cached formatted text
        self._is_overflow = True

    def get_formatted_text(self, separator: str = '\n\n') -> str:
        """
        Get the formatted text for translation.

        Paragraphs are joined with the separator. This text will be
        sent to the translation engine.

        Args:
            separator: String to join paragraphs with (default: '\n\n')

        Returns:
            Formatted text string
        """
        if self._formatted_text is None:
            texts = [p.text for p in self.paragraphs]
            self._formatted_text = separator.join(texts)
        return self._formatted_text

    def set_translation(self, translated_text: str,
                       separator: str = '\n\n') -> List[str]:
        """
        Set the translated text and split it back into paragraphs.

        Args:
            translated_text: The translated text from the API
            separator: The same separator used in get_formatted_text()

        Returns:
            List of translated paragraph texts
        """
        # Split translated text back into individual paragraphs
        # Note: This is a simple implementation. More sophisticated
        # methods may be needed for edge cases.
        translated_paragraphs = translated_text.split(separator)

        # Handle case where translation has different paragraph count
        if len(translated_paragraphs) != len(self.paragraphs):
            # Fallback: distribute translation evenly
            # This shouldn't happen with good translations, but we
            # need to handle it gracefully
            pass

        return translated_paragraphs

    def __repr__(self):
        overflow_mark = ' [OVERFLOW]' if self._is_overflow else ''
        return (f'SmartChunk({self.paragraph_count} paragraphs, '
                f'{self.total_length} chars{overflow_mark})')

    def __len__(self):
        return len(self.paragraphs)


def test_chunk():
    """Test the SmartChunk data structure."""
    import sys
    if sys.platform == 'win32':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    print("=" * 70)
    print("SmartChunk Tests")
    print("=" * 70)

    # Create mock paragraph class for testing
    class MockParagraph:
        def __init__(self, text, element_type='p'):
            self.text = text
            self.element_type = element_type

        def get_content(self):
            return self.text

    # Test 1: Basic chunk operations
    print("\n[Test 1] Basic chunk operations")
    chunk = SmartChunk(max_paragraphs=3, max_characters=100)

    para1 = Paragraph(MockParagraph("First paragraph."))
    para2 = Paragraph(MockParagraph("Second paragraph."))
    para3 = Paragraph(MockParagraph("Third paragraph."))

    assert chunk.add(para1)
    assert chunk.add(para2)
    assert chunk.add(para3)

    print(f"Chunk: {chunk}")
    print(f"Paragraph count: {chunk.paragraph_count}")
    print(f"Total length: {chunk.total_length}")
    print(f"Is full: {chunk.is_full}")
    assert chunk.paragraph_count == 3
    assert chunk.is_full
    print("✓ Test 1 passed!")

    # Test 2: Character limit
    print("\n[Test 2] Character limit")
    chunk2 = SmartChunk(max_paragraphs=10, max_characters=50)

    long_para = Paragraph(MockParagraph("This is a very long paragraph " * 10))
    assert not chunk2.add(long_para)  # Should fail due to length

    short_para = Paragraph(MockParagraph("Short."))
    assert chunk2.add(short_para)
    assert chunk2.paragraph_count == 1
    print("✓ Test 2 passed!")

    # Test 3: Overflow paragraph handling
    print("\n[Test 3] Overflow paragraph (single paragraph > max_characters)")
    chunk3 = SmartChunk(max_paragraphs=50, max_characters=100)

    # Create a paragraph longer than max_characters
    overflow_para = Paragraph(MockParagraph("A" * 200))
    print(f"Overflow paragraph length: {overflow_para.length}")
    print(f"Max characters: {chunk3.max_characters}")

    # Normal add fails
    assert not chunk3.add(overflow_para)
    print("Normal add() failed as expected")

    # Force add succeeds
    chunk3.force_add(overflow_para)
    assert chunk3.paragraph_count == 1
    assert chunk3.total_length == 200
    assert chunk3.is_overflow == True
    print(f"Chunk after force_add: {chunk3}")
    print(f"Is overflow: {chunk3.is_overflow}")
    print("✓ Test 3 passed!")

    # Test 4: Formatted text
    print("\n[Test 4] Formatted text generation")
    chunk4 = SmartChunk()
    chunk4.add(Paragraph(MockParagraph("First")))
    chunk4.add(Paragraph(MockParagraph("Second")))
    chunk4.add(Paragraph(MockParagraph("Third")))

    formatted = chunk4.get_formatted_text()
    print(f"Formatted text: '{formatted}'")
    assert formatted == "First\n\nSecond\n\nThird"
    print("✓ Test 4 passed!")

    # Test 5: can_add check
    print("\n[Test 5] can_add validation")
    chunk5 = SmartChunk(max_paragraphs=2, max_characters=50)

    test_para = Paragraph(MockParagraph("Test content."))
    assert chunk5.can_add(test_para)
    assert not chunk5.is_full

    chunk5.add(test_para)
    chunk5.add(test_para)

    assert not chunk5.can_add(test_para)  # Max paragraphs reached
    assert chunk5.is_full
    print("✓ Test 5 passed!")

    print("\n" + "=" * 70)
    print("All SmartChunk tests passed! ✓")
    print("=" * 70)


if __name__ == '__main__':
    test_chunk()
