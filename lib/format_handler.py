"""
Format Handler - Preserves HTML formatting through translation.

This module handles extraction and restoration of HTML formatting marks
(italics, bold, underlines, etc.) to ensure no formatting is lost during
translation, solving the issue where formatted words are dropped (e.g.,
"NOT" in <i class="calibre4">NOT</i>).
"""

import re
from typing import Dict, List, Tuple

try:
    from lxml import etree
    HAS_LXML = True
except ImportError:
    HAS_LXML = False
    # For testing without lxml
    etree = None


class FormatSpan:
    """Represents a formatted span of text."""

    def __init__(self, tag: str, attributes: Dict[str, str], text: str):
        self.tag = tag
        self.attributes = attributes
        self.text = text

    def __repr__(self):
        attrs = ' '.join(f'{k}="{v}"' for k, v in self.attributes.items())
        return f'<{self.tag} {attrs}>{self.text}</{self.tag}>'


class FormatHandler:
    """
    Handles format extraction and restoration for translation.

    The core idea is to replace HTML formatting tags with placeholder markers
    before translation, then restore them after translation.

    Example:
        Original: He would <i class="calibre4">NOT</i> want this
        Extract:  He would {ITALIC_0}NOT{/ITALIC_0} want this
        Translate: 他一定 {ITALIC_0}不{ITALIC_0} 想要这个
        Restore:  他一定 <i class="calibre4">不</i> 想要这个
    """

    # Inline formatting elements that should be preserved
    INLINE_FORMAT_TAGS = {
        'i', 'em',               # Italics
        'b', 'strong',           # Bold
        'u', 'ins',              # Underline
        's', 'del', 'strike',    # Strikethrough
        'mark',                  # Highlight
        'small', 'sub', 'sup',   # Size/position
        'code', 'kbd', 'samp',   # Code/technical
        'cite', 'q', 'abbr',     # Semantic inline
        'span',                  # Generic inline (with class/style)
        'a',                     # Links
    }

    # Calibre-specific CSS classes to preserve
    CALIBRE_CLASSES = {
        'calibre1', 'calibre2', 'calibre3', 'calibre4', 'calibre5',
        'calibre6', 'calibre7', 'calibre8', 'calibre9', 'calibre10',
        'italic', 'bold', 'underline',
    }

    def __init__(self):
        self.marker_index = 0
        self.format_map: Dict[str, str] = {}

    def reset(self):
        """Reset the handler state for a new translation."""
        self.marker_index = 0
        self.format_map.clear()

    def _create_marker(self, tag: str) -> str:
        """Create opening and closing markers for a format tag."""
        marker_name = f'FORMAT_{self.marker_index}'
        self.marker_index += 1
        return f'{{{marker_name}}}', f'{{/{marker_name}}}', marker_name

    def _should_preserve_element(self, element: etree._Element) -> bool:
        """
        Determine if an element should be preserved.

        Preserves elements that are:
        1. Inline formatting tags (i, b, em, strong, etc.)
        2. Have class attributes matching Calibre formatting classes
        3. Have style attributes (inline CSS)
        """
        tag = etree.QName(element).localname

        # Check if it's an inline format tag
        if tag in self.INLINE_FORMAT_TAGS:
            return True

        # Check for Calibre formatting classes
        classes = element.get('class', '')
        if classes:
            class_list = classes.split()
            if any(cls in self.CALIBRE_CLASSES for cls in class_list):
                return True

        # Check for style attribute (inline CSS)
        if element.get('style'):
            return True

        return False

    def _element_to_html(self, element: etree._Element) -> str:
        """Convert an element back to HTML string with attributes."""
        tag = etree.QName(element).localname

        # Build attributes string
        attrs = []
        for name, value in element.items():
            attrs.append(f'{name}="{value}"')

        attrs_str = ' ' + ' '.join(attrs) if attrs else ''
        return f'<{tag}{attrs_str}>'

    def extract_with_markers(self, html: str) -> Tuple[str, Dict[str, str]]:
        """
        Extract text and insert format markers.

        Args:
            html: HTML string possibly containing formatting

        Returns:
            Tuple of (text_with_markers, format_map)

        Example:
            >>> handler = FormatHandler()
            >>> text, map = handler.extract_with_markers(
            ...     'He would <i class="calibre4">NOT</i> want this')
            >>> print(text)
            'He would {FORMAT_0}NOT{/FORMAT_0} want this'
            >>> print(map)
            {'{FORMAT_0}': '<i class="calibre4">', '{/FORMAT_0}': '</i>'}
        """
        self.reset()

        try:
            root = etree.fromstring(f'<root>{html}</root>')
        except Exception:
            # If parsing fails, return original HTML
            return html, {}

        text_parts = []
        self._process_node(root, text_parts)

        # Join text parts and clean up
        result = ''.join(text_parts)
        result = result.strip()

        return result, self.format_map

    def _process_node(self, node: etree._Element, text_parts: List[str]):
        """
        Recursively process an XML node and its children.

        This is the core algorithm that walks the element tree and replaces
        formatting tags with markers.
        """
        # Process text content before any children
        if node.text:
            text_parts.append(node.text)

        # Process child elements
        for child in node:
            if self._should_preserve_element(child):
                # This is a formatting element - replace with markers
                self._handle_format_element(child, text_parts)
            elif len(child) == 0 and not child.text:
                # Empty element, skip
                continue
            else:
                # Regular element - recurse
                self._process_node(child, text_parts)

            # Process tail text (text after the closing tag)
            if child.tail:
                text_parts.append(child.tail)

    def _handle_format_element(self, element: etree._Element, text_parts: List[str]):
        """
        Handle a formatting element by replacing it with markers.

        The markers are inserted in the format: {FORMAT_0}text{/FORMAT_0}
        """
        # Create markers
        open_marker, close_marker, marker_name = self._create_marker(
            etree.QName(element).localname)

        # Store the HTML tag in the format map
        open_html = self._element_to_html(element)
        close_tag = etree.QName(element).localname
        close_html = f'</{close_tag}>'

        self.format_map[open_marker] = open_html
        self.format_map[close_marker] = close_html

        # Add opening marker
        text_parts.append(open_marker)

        # Process children recursively (formatting can be nested)
        for child in element:
            if self._should_preserve_element(child):
                self._handle_format_element(child, text_parts)
            else:
                self._process_node(child, text_parts)

            if child.tail:
                text_parts.append(child.tail)

        # Add closing marker
        text_parts.append(close_marker)

    def restore_from_markers(self, text: str, format_map: Dict[str, str]) -> str:
        """
        Restore HTML formatting from markers.

        Args:
            text: Translated text with format markers
            format_map: Mapping of markers to HTML tags

        Returns:
            HTML string with restored formatting

        Example:
            >>> handler = FormatHandler()
            >>> map = {'{FORMAT_0}': '<i class="calibre4">',
            ...        '{/FORMAT_0}': '</i>'}
            >>> result = handler.restore_from_markers(
            ...     '他一定 {FORMAT_0}不{FORMAT_0} 想要这个', map)
            >>> print(result)
            '他一定 <i class="calibre4">不</i> 想要这个'
        """
        result = text

        # Restore markers in reverse order (highest index first)
        # This ensures nested formats are handled correctly
        markers = sorted(
            [(k, v) for k, v in format_map.items()],
            key=lambda x: x[0],
            reverse=True
        )

        for marker, html_tag in markers:
            result = result.replace(marker, html_tag)

        return result


def test_format_handler():
    """Test the FormatHandler with various formatting scenarios."""
    handler = FormatHandler()

    print("=" * 60)
    print("Format Handler Tests")
    print("=" * 60)

    # Test 1: Simple italic
    print("\n[Test 1] Simple italic with Calibre class")
    html = 'He would <i class="calibre4">NOT</i> want this'
    text, format_map = handler.extract_with_markers(html)
    print(f"Original:  {html}")
    print(f"Extracted: {text}")
    print(f"Format map: {format_map}")

    translated = '他一定 {FORMAT_0}不{/FORMAT_0} 想要这个'
    restored = handler.restore_from_markers(translated, format_map)
    print(f"Translated: {translated}")
    print(f"Restored:   {restored}")
    assert '<i class="calibre4">不</i>' in restored
    print("✓ Test 1 passed!")

    # Test 2: Bold with different class
    print("\n[Test 2] Bold with custom class")
    html = 'This is <span class="bold">important</span> text'
    text, format_map = handler.extract_with_markers(html)
    print(f"Original:  {html}")
    print(f"Extracted: {text}")

    translated = '这是 {FORMAT_0}重要{/FORMAT_0} 的文本'
    restored = handler.restore_from_markers(translated, format_map)
    print(f"Translated: {translated}")
    print(f"Restored:   {restored}")
    assert 'class="bold"' in restored
    print("✓ Test 2 passed!")

    # Test 3: Multiple formats
    print("\n[Test 3] Multiple formatting in one sentence")
    html = '<i>Italic</i> and <b>bold</b> text'
    text, format_map = handler.extract_with_markers(html)
    print(f"Original:  {html}")
    print(f"Extracted: {text}")
    print(f"Format map: {format_map}")

    translated = '{FORMAT_0}斜体{/FORMAT_0} 和 {FORMAT_1}粗体{/FORMAT_1} 文本'
    restored = handler.restore_from_markers(translated, format_map)
    print(f"Translated: {translated}")
    print(f"Restored:   {restored}")
    assert '<i>斜体</i>' in restored
    assert '<b>粗体</b>' in restored
    print("✓ Test 3 passed!")

    # Test 4: Nested formatting
    print("\n[Test 4] Nested formatting")
    html = '<b>Bold with <i>italic inside</i> and more</b>'
    text, format_map = handler.extract_with_markers(html)
    print(f"Original:  {html}")
    print(f"Extracted: {text}")
    print(f"Format map: {format_map}")

    # Note: Nested format markers in translation
    translated = '{FORMAT_0}粗体带 {FORMAT_1}内部斜体{/FORMAT_1} 还有更多{/FORMAT_0}'
    restored = handler.restore_from_markers(translated, format_map)
    print(f"Translated: {translated}")
    print(f"Restored:   {restored}")
    print("✓ Test 4 passed!")

    # Test 5: Style attribute
    print("\n[Test 5] Inline style attribute")
    html = 'Text with <span style="color: red">colored</span> words'
    text, format_map = handler.extract_with_markers(html)
    print(f"Original:  {html}")
    print(f"Extracted: {text}")

    translated = '带 {FORMAT_0}彩色{/FORMAT_0} 单词的文本'
    restored = handler.restore_from_markers(translated, format_map)
    print(f"Translated: {translated}")
    print(f"Restored:   {restored}")
    assert 'style="color: red"' in restored
    print("✓ Test 5 passed!")

    print("\n" + "=" * 60)
    print("All tests passed! ✓")
    print("=" * 60)


if __name__ == '__main__':
    test_format_handler()
