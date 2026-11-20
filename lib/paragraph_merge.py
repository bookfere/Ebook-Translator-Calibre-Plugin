"""
Paragraph Merge - Merge paragraphs for batch translation.

Implements paragraph merging to reduce API calls while handling
edge cases like overflow paragraphs.
"""

import sys
from typing import List

try:
    from .chunk import SmartChunk, Paragraph, BoundaryType
    try:
        from .format_handler import FormatHandler
    except ImportError:
        FormatHandler = None
except ImportError:
    # Fallback for direct execution
    from chunk import SmartChunk, Paragraph, BoundaryType
    try:
        from format_handler import FormatHandler
    except ImportError:
        FormatHandler = None


class ParagraphMergeConfig:
    """Configuration for paragraph merge behavior."""

    def __init__(self):
        # Limits
        self.max_paragraphs = 50
        self.max_characters = 3000

        # Separator between paragraphs in a chunk
        self.separator = '\n\n'

        # Format preservation (disabled by default)
        self.enable_format_preservation = False


class ParagraphMerger:
    """
    Merges paragraphs into translation chunks.

    Handles:
    - Respecting paragraph and character limits
    - Overflow paragraphs (single paragraph > limit)
    - Optional format preservation
    """

    def __init__(self, config: ParagraphMergeConfig = None):
        """
        Args:
            config: ParagraphMergeConfig instance (uses defaults if None)
        """
        self.config = config or ParagraphMergeConfig()
        self.format_handler = FormatHandler() if (
            self.config.enable_format_preservation and FormatHandler
        ) else None

    def merge(self, paragraphs: List[Paragraph]) -> List[SmartChunk]:
        """
        Merge paragraphs into chunks.

        Strategy:
        - Add paragraphs to current chunk while under limits
        - When limits exceeded, start new chunk
        - Handle overflow paragraphs (single paragraph > max_characters)

        Args:
            paragraphs: List of Paragraph objects to merge

        Returns:
            List of SmartChunk objects
        """
        if not paragraphs:
            return []

        chunks = []
        current_chunk = SmartChunk(
            self.config.max_paragraphs,
            self.config.max_characters
        )

        for para in paragraphs:
            # Try to add paragraph normally
            if current_chunk.add(para):
                continue

            # Can't add - need to handle the situation
            if current_chunk.is_empty:
                # Special case: single paragraph exceeds limits
                # Force add it (allow overflow)
                current_chunk.force_add(para)
                chunks.append(current_chunk)
                current_chunk = SmartChunk(
                    self.config.max_paragraphs,
                    self.config.max_characters
                )
            else:
                # Normal case: current chunk is full
                chunks.append(current_chunk)
                current_chunk = SmartChunk(
                    self.config.max_paragraphs,
                    self.config.max_characters
                )
                # Try adding to new chunk
                if not current_chunk.add(para):
                    # Still can't add (overflow paragraph)
                    current_chunk.force_add(para)
                    chunks.append(current_chunk)
                    current_chunk = SmartChunk(
                        self.config.max_paragraphs,
                        self.config.max_characters
                    )

        # Add last chunk if not empty
        if not current_chunk.is_empty:
            chunks.append(current_chunk)

        return chunks

    def merge_with_format_preservation(self, paragraphs: List[Paragraph]) -> List[SmartChunk]:
        """
        Merge paragraphs with format preservation enabled.

        This extracts format markers before merging and ensures they
        are preserved through the translation process.

        Args:
            paragraphs: List of Paragraph objects

        Returns:
            List of SmartChunk objects with format information
        """
        # First do regular merge
        chunks = self.merge(paragraphs)

        # Format preservation would be handled here
        # For now, this is a placeholder for future implementation
        if self.format_handler:
            pass  # TODO: Implement format extraction for chunks

        return chunks


def detect_paragraph_type(element) -> tuple:
    """
    Detect the type of paragraph element.

    Args:
        element: An lxml element object

    Returns:
        Tuple of (element_type: str, boundary_type: BoundaryType)
    """
    try:
        from lxml import etree
    except ImportError:
        etree = None

    if etree and hasattr(element, 'tag'):
        tag = etree.QName(element).localname
    else:
        tag = 'p'

    # For now, we don't need detailed boundary types
    # Just return paragraph type
    return tag or 'p', BoundaryType.PARAGRAPH


def test_paragraph_merger():
    """Test the ParagraphMerger with various scenarios."""
    # Import within test to avoid relative import issues
    import os
    sys.path.insert(0, os.path.dirname(__file__))

    if sys.platform == 'win32':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    from chunk import SmartChunk, Paragraph, BoundaryType

    print("=" * 70)
    print("ParagraphMerger Tests")
    print("=" * 70)

    # Create mock paragraph class
    class MockElement:
        def __init__(self, text):
            self._text = text

        def get_content(self):
            return self._text

    # Test 1: Basic merging
    print("\n[Test 1] Basic paragraph merging")
    config = ParagraphMergeConfig()
    config.max_paragraphs = 3
    config.max_characters = 200

    merger = ParagraphMerger(config)

    paragraphs = [
        Paragraph(MockElement("First paragraph.")),
        Paragraph(MockElement("Second paragraph.")),
        Paragraph(MockElement("Third paragraph.")),
        Paragraph(MockElement("Fourth paragraph.")),
    ]

    chunks = merger.merge(paragraphs)

    print(f"Input: {len(paragraphs)} paragraphs")
    print(f"Output: {len(chunks)} chunks")
    for i, chunk in enumerate(chunks):
        print(f"  Chunk {i+1}: {chunk}")

    # Should have 2 chunks (3 paras each for first chunk, 1 for second)
    assert len(chunks) == 2
    assert chunks[0].paragraph_count == 3
    assert chunks[1].paragraph_count == 1
    print("✓ Test 1 passed!")

    # Test 2: Character limit
    print("\n[Test 2] Character limit enforcement")
    config2 = ParagraphMergeConfig()
    config2.max_characters = 50

    merger2 = ParagraphMerger(config2)

    paragraphs2 = [
        Paragraph(MockElement("Short." * 3)),  # ~18 chars
        Paragraph(MockElement("Medium length paragraph here.")),  # ~32 chars
        Paragraph(MockElement("Another paragraph.")),  # ~21 chars
    ]

    chunks2 = merger2.merge(paragraphs2)

    print(f"Input: {len(paragraphs2)} paragraphs")
    print(f"Output: {len(chunks2)} chunks")
    for i, chunk in enumerate(chunks2):
        print(f"  Chunk {i+1}: {chunk}")

    # First two should fit, third should be separate
    assert len(chunks2) >= 2
    print("✓ Test 2 passed!")

    # Test 3: Overflow paragraph (single paragraph > limit)
    print("\n[Test 3] Overflow paragraph handling")
    config3 = ParagraphMergeConfig()
    config3.max_characters = 100

    merger3 = ParagraphMerger(config3)

    # Create a paragraph longer than max_characters
    long_text = "This is a very long paragraph. " * 20  # ~500 chars
    paragraphs3 = [
        Paragraph(MockElement("Short intro.")),
        Paragraph(MockElement(long_text)),
        Paragraph(MockElement("Short outro.")),
    ]

    chunks3 = merger3.merge(paragraphs3)

    print(f"Input: {len(paragraphs3)} paragraphs")
    print(f"  Paragraph 2 length: {len(long_text)} chars")
    print(f"  Max characters: {config3.max_characters}")
    print(f"Output: {len(chunks3)} chunks")
    for i, chunk in enumerate(chunks3):
        print(f"  Chunk {i+1}: {chunk}")

    # Should have 3 chunks (intro, overflow, outro)
    assert len(chunks3) == 3
    assert chunks3[1].is_overflow == True
    print("✓ Test 3 passed!")

    print("\n" + "=" * 70)
    print("All ParagraphMerger tests passed! ✓")
    print("=" * 70)


if __name__ == '__main__':
    test_paragraph_merger()
