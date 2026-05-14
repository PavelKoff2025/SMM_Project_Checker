import io
import zipfile

import pytest

from app.services.file_storage import (
    FileValidationError,
    persist_upload,
    sanitize_original_filename,
    split_extension,
    validate_upload,
)


def _build_pptx_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr('ppt/presentation.xml', '<?xml version="1.0"?><root/>')
        zf.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types/>')
    return buf.getvalue()


def test_sanitize_strips_dangerous_chars():
    assert sanitize_original_filename('<script>a.pdf') == 'scripta.pdf'


def test_split_extension_lowercases():
    assert split_extension('Project.PDF') == ('Project.PDF', '.pdf')


def test_validate_rejects_unknown_extension():
    stream = io.BytesIO(b'%PDF-1.4 hello')
    with pytest.raises(FileValidationError):
        validate_upload(stream, '.exe')


def test_validate_rejects_empty_file():
    with pytest.raises(FileValidationError):
        validate_upload(io.BytesIO(b''), '.pdf')


def test_validate_rejects_pdf_with_wrong_magic():
    with pytest.raises(FileValidationError):
        validate_upload(io.BytesIO(b'not a pdf'), '.pdf')


def test_validate_accepts_pdf():
    validate_upload(io.BytesIO(b'%PDF-1.4 content'), '.pdf')


def test_persist_rejects_non_pptx_zip(tmp_path):
    fake_zip = io.BytesIO()
    with zipfile.ZipFile(fake_zip, 'w') as zf:
        zf.writestr('hello.txt', 'no presentation here')
    fake_zip.seek(0)
    validate_upload(fake_zip, '.pptx')
    with pytest.raises(FileValidationError):
        persist_upload(fake_zip, str(tmp_path), '.pptx')


def test_persist_accepts_valid_pptx(tmp_path):
    stream = io.BytesIO(_build_pptx_bytes())
    validate_upload(stream, '.pptx')
    safe_name, path = persist_upload(stream, str(tmp_path), '.pptx')
    assert safe_name.endswith('.pptx')
    assert (tmp_path / safe_name).exists()
    assert path.endswith(safe_name)
