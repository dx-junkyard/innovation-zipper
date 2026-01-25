"""
Wikipedia XML Dump Parser

Parses Wikipedia dump files (e.g., jawiki-20260101-pages-articles.xml.bz2)
using streaming to handle large files efficiently.
"""

import bz2
import re
import xml.etree.ElementTree as ET
from typing import Iterator, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

# MediaWiki XML namespace
MEDIAWIKI_NS = "{http://www.mediawiki.org/xml/export-0.11/}"

# Common patterns for Wikipedia markup cleanup
WIKI_MARKUP_PATTERNS = [
    (re.compile(r'\[\[Category:[^\]]+\]\]', re.IGNORECASE), ''),  # Category links
    (re.compile(r'\[\[ファイル:[^\]]+\]\]', re.IGNORECASE), ''),  # File links (Japanese)
    (re.compile(r'\[\[File:[^\]]+\]\]', re.IGNORECASE), ''),  # File links (English)
    (re.compile(r'\[\[画像:[^\]]+\]\]', re.IGNORECASE), ''),  # Image links (Japanese)
    (re.compile(r'\[\[Image:[^\]]+\]\]', re.IGNORECASE), ''),  # Image links (English)
    (re.compile(r'\{\{[^}]+\}\}'), ''),  # Templates
    (re.compile(r'\{\|[^}]+\|\}', re.DOTALL), ''),  # Tables
    (re.compile(r'<ref[^>]*>.*?</ref>', re.DOTALL), ''),  # References
    (re.compile(r'<ref[^/>]*/>', re.DOTALL), ''),  # Self-closing refs
    (re.compile(r'<!--.*?-->', re.DOTALL), ''),  # HTML comments
    (re.compile(r"'''?([^']+)'''?"), r'\1'),  # Bold/italic
    (re.compile(r'\[\[([^|\]]+)\|([^\]]+)\]\]'), r'\2'),  # Piped links [[link|text]]
    (re.compile(r'\[\[([^\]]+)\]\]'), r'\1'),  # Simple links [[link]]
    (re.compile(r'\[https?://[^\s\]]+\s*([^\]]*)\]'), r'\1'),  # External links
    (re.compile(r'<[^>]+>'), ''),  # HTML tags
    (re.compile(r'={2,}([^=]+)={2,}'), r'\1'),  # Section headers
    (re.compile(r'\n{3,}'), '\n\n'),  # Multiple newlines
    (re.compile(r'^\s*\*+\s*', re.MULTILINE), ''),  # List markers
    (re.compile(r'^\s*#+\s*', re.MULTILINE), ''),  # Numbered list markers
]

# Patterns to detect non-article pages
NON_ARTICLE_PREFIXES = [
    'Wikipedia:',
    'ウィキペディア:',
    'Template:',
    'テンプレート:',
    'Category:',
    'カテゴリ:',
    'Help:',
    'ヘルプ:',
    'Portal:',
    'ポータル:',
    'MediaWiki:',
    'メディアウィキ:',
    'Module:',
    'モジュール:',
    'Draft:',
    '利用者:',
    'User:',
    'ファイル:',
    'File:',
    'プロジェクト:',
    'Project:',
]

# Redirect patterns
REDIRECT_PATTERNS = [
    re.compile(r'^#REDIRECT', re.IGNORECASE),
    re.compile(r'^#転送', re.IGNORECASE),
]


def is_redirect(text: str) -> bool:
    """Check if text is a redirect page."""
    if not text:
        return False
    text_start = text[:50].strip()
    return any(pattern.match(text_start) for pattern in REDIRECT_PATTERNS)


def is_article_page(title: str) -> bool:
    """Check if the page title indicates a main article (not meta page)."""
    if not title:
        return False
    return not any(title.startswith(prefix) for prefix in NON_ARTICLE_PREFIXES)


def clean_wikitext(text: str) -> str:
    """
    Clean Wikipedia markup from text.
    Converts wikitext to plain text for indexing.
    """
    if not text:
        return ""

    result = text

    for pattern, replacement in WIKI_MARKUP_PATTERNS:
        result = pattern.sub(replacement, result)

    # Final cleanup
    result = result.strip()

    # Remove excessive whitespace
    result = re.sub(r' {2,}', ' ', result)

    return result


def extract_first_paragraph(text: str, max_length: int = 500) -> str:
    """
    Extract the first meaningful paragraph from cleaned text.
    Used for creating summaries.
    """
    if not text:
        return ""

    # Split by double newline (paragraph boundary)
    paragraphs = text.split('\n\n')

    for para in paragraphs:
        para = para.strip()
        # Skip short paragraphs (likely headers or artifacts)
        if len(para) > 50:
            if len(para) > max_length:
                # Truncate at sentence boundary if possible
                sentences = para[:max_length].split('。')
                if len(sentences) > 1:
                    return '。'.join(sentences[:-1]) + '。'
                return para[:max_length] + '...'
            return para

    return text[:max_length] if text else ""


def parse_wikipedia_dump(
    file_path: str,
    min_content_length: int = 100,
    max_articles: Optional[int] = None,
    skip_redirects: bool = True,
    clean_markup: bool = True
) -> Iterator[Dict[str, Any]]:
    """
    Parse a Wikipedia dump file and yield article data.

    Args:
        file_path: Path to the .xml.bz2 dump file
        min_content_length: Minimum cleaned content length to include
        max_articles: Maximum number of articles to parse (None for all)
        skip_redirects: Skip redirect pages
        clean_markup: Clean wiki markup from content

    Yields:
        Dict with keys: id, title, content, url, summary
    """
    article_count = 0
    skipped_count = 0

    logger.info(f"Starting to parse Wikipedia dump: {file_path}")

    # Open bz2 file
    if file_path.endswith('.bz2'):
        file_handle = bz2.open(file_path, 'rt', encoding='utf-8')
    else:
        file_handle = open(file_path, 'r', encoding='utf-8')

    try:
        # Use iterparse for memory-efficient parsing
        context = ET.iterparse(file_handle, events=('end',))

        for event, elem in context:
            # Look for page elements
            tag_name = elem.tag.replace(MEDIAWIKI_NS, '')

            if tag_name == 'page':
                try:
                    # Extract page data
                    title_elem = elem.find(f'{MEDIAWIKI_NS}title')
                    id_elem = elem.find(f'{MEDIAWIKI_NS}id')
                    revision_elem = elem.find(f'{MEDIAWIKI_NS}revision')

                    if title_elem is None or revision_elem is None:
                        elem.clear()
                        continue

                    title = title_elem.text or ""
                    page_id = id_elem.text if id_elem is not None else ""

                    # Skip non-article pages
                    if not is_article_page(title):
                        skipped_count += 1
                        elem.clear()
                        continue

                    text_elem = revision_elem.find(f'{MEDIAWIKI_NS}text')
                    raw_content = text_elem.text if text_elem is not None else ""

                    # Skip redirects
                    if skip_redirects and is_redirect(raw_content):
                        skipped_count += 1
                        elem.clear()
                        continue

                    # Clean content
                    if clean_markup:
                        content = clean_wikitext(raw_content)
                    else:
                        content = raw_content

                    # Skip if content is too short
                    if len(content) < min_content_length:
                        skipped_count += 1
                        elem.clear()
                        continue

                    # Generate URL
                    url = f"https://ja.wikipedia.org/wiki/{title.replace(' ', '_')}"

                    # Extract summary
                    summary = extract_first_paragraph(content)

                    article_count += 1

                    if article_count % 10000 == 0:
                        logger.info(f"Parsed {article_count} articles, skipped {skipped_count}")

                    yield {
                        "id": page_id,
                        "title": title,
                        "content": content,
                        "url": url,
                        "summary": summary,
                        "metadata": {
                            "source": "wikipedia",
                            "lang": "ja",
                            "raw_length": len(raw_content),
                            "clean_length": len(content)
                        }
                    }

                    if max_articles and article_count >= max_articles:
                        logger.info(f"Reached max_articles limit: {max_articles}")
                        break

                except Exception as e:
                    logger.warning(f"Error parsing page: {e}")

                # Clear element to free memory
                elem.clear()

    finally:
        file_handle.close()

    logger.info(f"Finished parsing. Total articles: {article_count}, Skipped: {skipped_count}")


def batch_articles(
    articles: Iterator[Dict[str, Any]],
    batch_size: int = 100
) -> Iterator[list]:
    """
    Batch articles into groups for efficient API calls.

    Args:
        articles: Iterator of article dicts
        batch_size: Number of articles per batch

    Yields:
        List of article dicts
    """
    batch = []

    for article in articles:
        batch.append(article)

        if len(batch) >= batch_size:
            yield batch
            batch = []

    # Yield remaining articles
    if batch:
        yield batch


class WikipediaImportStats:
    """Track import statistics."""

    def __init__(self):
        self.total_parsed = 0
        self.total_imported = 0
        self.total_errors = 0
        self.total_skipped = 0
        self.current_batch = 0
        self.errors = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_parsed": self.total_parsed,
            "total_imported": self.total_imported,
            "total_errors": self.total_errors,
            "total_skipped": self.total_skipped,
            "current_batch": self.current_batch,
            "recent_errors": self.errors[-10:]  # Last 10 errors
        }

    def add_error(self, error: str):
        self.errors.append(error)
        self.total_errors += 1
        # Keep only last 100 errors in memory
        if len(self.errors) > 100:
            self.errors = self.errors[-100:]
