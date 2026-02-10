"""
Test ParagraphMerge functionality
"""
import sys
import os

# Add lib directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from chunk import SmartChunk, Paragraph, BoundaryType
from paragraph_merge import ParagraphMerger, ParagraphMergeConfig


def test_paragraph_merger():
    """Test the ParagraphMerger with various scenarios."""

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

    # Test 4: Empty input
    print("\n[Test 4] Empty input")
    config4 = ParagraphMergeConfig()
    merger4 = ParagraphMerger(config4)

    chunks4 = merger4.merge([])

    print(f"Input: 0 paragraphs")
    print(f"Output: {len(chunks4)} chunks")
    assert len(chunks4) == 0
    print("✓ Test 4 passed!")

    print("\n" + "=" * 70)
    print("All ParagraphMerger tests passed! ✓")
    print("=" * 70)
    print("\nSummary of tested functionality:")
    print("  ✓ Basic paragraph merging")
    print("  ✓ Character limit enforcement")
    print("  ✓ Overflow paragraph handling (single paragraph > limit)")
    print("  ✓ Empty input handling")
    print("=" * 70)


if __name__ == '__main__':
    test_paragraph_merger()
