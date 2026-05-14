"""Thin wrapper around PDF/PPTX parsers that normalizes their output."""

from dataclasses import dataclass

from app.checker.parsers import PDFParser, PPTXParser


@dataclass(frozen=True)
class ParsedPresentation:
    full_text: str
    slide_texts: list[str]
    slide_titles: list[str]
    slide_count: int

    @property
    def is_empty(self) -> bool:
        return not self.full_text.strip()


def parse_presentation(file_path: str, ext: str) -> ParsedPresentation:
    ext = ext.lower()
    if ext == '.pdf':
        return _parse_pdf(file_path)
    if ext == '.pptx':
        return _parse_pptx(file_path)
    raise ValueError(f'Unsupported file type: {ext}')


def _parse_pdf(file_path: str) -> ParsedPresentation:
    result = PDFParser.extract_with_fallback(file_path)
    pages = result.get('pages', [])
    slide_texts = [page.get('text', '') for page in pages]
    slide_titles = [(page.get('text', '') or '')[:80] for page in pages]
    return ParsedPresentation(
        full_text=result.get('text', ''),
        slide_texts=slide_texts,
        slide_titles=slide_titles,
        slide_count=len(pages),
    )


def _parse_pptx(file_path: str) -> ParsedPresentation:
    result = PPTXParser.extract_text(file_path)
    slides = result.get('slides', [])
    slide_texts: list[str] = []
    slide_titles: list[str] = []
    for slide in slides:
        title = slide.get('title') or ''
        content = slide.get('content') or []
        parts = [title, *content] if title else list(content)
        slide_texts.append(' '.join(p for p in parts if p))
        if title:
            slide_titles.append(title[:80])
        elif content:
            slide_titles.append((content[0] or '')[:80])
        else:
            slide_titles.append('')
    return ParsedPresentation(
        full_text=result.get('text', ''),
        slide_texts=slide_texts,
        slide_titles=slide_titles,
        slide_count=len(slides),
    )
