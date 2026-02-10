# ParagraphMerge Testing Guide

## Quick Start

1. **Restart Calibre** to reload the plugin
2. Open Settings (右键点击插件图标 -> Setting)
3. Go to "General" tab
4. Find "Merge to Translate (Beta)" section

## Enable ParagraphMerge Mode

In the "Merge to Translate" section:

1. ☑ **Check "Enable"**
2. **Mode**: Select "Paragraph Merge" (not "Legacy (Length)")
3. **Character limit**: Set to 3000 (default)
4. **Max paragraphs**: Set to 50 (default)
5. ☑ **Check "Enable Format Preservation"** (optional, for preserving italics/bold)

Click "Save" button at the bottom.

## Test Translation

### Method 1: Advanced Mode (Recommended)

1. Select an EPUB book in Calibre library
2. Click the plugin icon
3. Select "Advanced Mode"
4. Choose translation engine (e.g., Google Free, ChatGPT, etc.)
5. Set source and target languages
6. Click "Translate"
7. Watch the console/log for merge behavior

### Method 2: Batch Mode

1. Select one or multiple EPUB books
2. Click plugin icon -> "Batch Mode"
3. Configure settings
4. Click "Translate"

## Expected Behavior

### With ParagraphMerge Enabled:
- Multiple paragraphs are merged into single API requests
- Reduces API calls by ~50-60%
- Character limit is respected (default: 3000)
- Max paragraph limit is respected (default: 50)

### With Format Preservation Enabled:
- HTML formatting is preserved through translation
- Example: `<i class="calibre4">NOT</i>` → translated with italics intact
- Uses placeholder markers: `{FORMAT_0}text{/FORMAT_0}`

### Configuration Options:
| Setting | Default | Description |
|---------|---------|-------------|
| Character limit | 1800 | Max characters per translation |
| Max paragraphs | 50 | Max paragraphs per chunk |
| Format preservation | Off | Preserve HTML formatting |

## Verify Functionality

Check the translation log in Calibre:
```
Debug: Using ParagraphMerge mode
Debug: Merged 10 paragraphs into 3 chunks
Debug: Chunk 1: 3 paragraphs, 1234 characters
Debug: Chunk 2: 4 paragraphs, 2156 characters
Debug: Chunk 3: 3 paragraphs, 987 characters
```

## Troubleshooting

### No UI Changes Visible:
- Restart Calibre completely
- Check that files are copied to: `C:\Users\alan\AppData\Roaming\calibre\plugins\ebook-translator\`

### ParagraphMerge Not Activating:
- Ensure merge_enabled is True in settings
- Ensure merge_mode is set to 'paragraph' (not 'length')
- Check Calibre debug log for errors

### Format Preservation Not Working:
- Ensure "Enable Format Preservation" checkbox is checked
- Format preservation only works with ParagraphMerge mode
- Check for error messages in log

### Translation Fails:
- Try reducing "Character limit" (e.g., to 1000)
- Try reducing "Max paragraphs" (e.g., to 10)
- Check engine API key and settings
- Try with "Legacy (Length)" mode first to verify basic functionality

## Advanced Testing

### Manual Configuration (Without UI)

Edit: `C:\Users\alan\AppData\Roaming\calibre\plugins\ebook-translator\settings.ini`

Add under `[Preferences]`:
```ini
merge_enabled = true
merge_mode = paragraph
merge_length = 3000
merge_max_paragraphs = 50
merge_format_preservation = false
```

### Run Unit Tests

```bash
cd E:\Projects\eBookTranslator\Ebook-Translator-Calibre-Plugin
python tests/test_paragraph_merge.py
```

Expected output:
```
==================================================================
ParagraphMerger Tests
==================================================================

[Test 1] Basic paragraph merging
✓ Test 1 passed!

[Test 2] Character limit enforcement
✓ Test 2 passed!

[Test 3] Overflow paragraph handling
✓ Test 3 passed!
```

## Performance Comparison

| Mode | 10 Paragraphs | API Calls | Reduction |
|------|--------------|-----------|-----------|
| No Merge | ~180 chars each | 10 | - |
| Legacy | Simple accumulation | ~3-4 | 60-70% |
| ParagraphMerge | Intelligent | ~2-3 | 70-80% |

## Next Steps

After successful testing:
1. Try with different books (various paragraph lengths)
2. Test with format preservation on real formatted content
3. Adjust character/paragraph limits for optimal performance
4. Report any issues or improvements needed
