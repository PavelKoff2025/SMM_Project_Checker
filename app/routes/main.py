import json
import os
import re
import threading
import uuid

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

from app import db, limiter
from app.checker.llm_client import DeepSeekClient
from app.checker.parsers import PDFParser, PPTXParser
from app.checker.prompt_templates import (
    SLIDE_TEMPLATE,
    STRUCTURE_VALIDATION_INSTRUCTION,
    SYSTEM_PROMPT,
    TEMPLATE_COMPLIANCE_CHECK,
    USER_PROMPT_TEMPLATE,
)
from app.checker.services import ReportService
from app.models import ProjectCheck

bp = Blueprint('main', __name__, url_prefix='/api')

MAX_FILE_SIZE = 32 * 1024 * 1024
ALLOWED_EXTENSIONS = {'.pdf', '.pptx'}

MAGIC_BYTES = {
    '.pdf': b'%PDF',
    '.pptx': b'PK\x03\x04',
}


def safe_filename_cyrillic(filename: str) -> str:
    name, ext = os.path.splitext(filename)
    clean_name = re.sub(r'[^\w\-\.\u0400-\u04FF]', '_', name)
    return f"{clean_name}{ext.lower()}"


def validate_file_content(file_path: str, ext: str) -> None:
    magic = MAGIC_BYTES.get(ext)
    if not magic:
        return
    with open(file_path, 'rb') as f:
        header = f.read(len(magic))
    if not header.startswith(magic):
        os.remove(file_path)
        raise ValueError(f'Файл не является валидным {ext.upper()}')


def _process_check(app, check_id: int):
    with app.app_context():
        check = db.session.get(ProjectCheck, check_id)
        if not check:
            return

        try:
            upload_dir = current_app.config['UPLOAD_FOLDER']
            _name_uuid, ext = os.path.splitext(check.safe_filename)
            ext = ext.lower()
            file_path = os.path.join(upload_dir, check.safe_filename)

            if ext == '.pdf':
                result = PDFParser.extract_with_fallback(file_path)
                check.extracted_text = result['text']
                slide_count = len(result.get('pages', []))
                slide_titles = [
                    p.get('text', '')[:80] for p in result.get('pages', [])
                ]
            elif ext == '.pptx':
                result = PPTXParser.extract_text(file_path)
                check.extracted_text = result['text']
                slide_count = len(result.get('slides', []))
                slide_titles = [
                    s.get('title') or (s.get('content') or [''])[0][:80]
                    for s in result.get('slides', [])
                ]
            else:
                raise ValueError(f'Unsupported file type: {ext}')

            if not check.extracted_text.strip():
                raise ValueError('No text could be extracted from the file.')

            raw_slides = result.get('pages', result.get('slides', []))
            slide_texts = []
            for s in raw_slides:
                if 'text' in s:
                    slide_texts.append(s['text'])
                else:
                    parts = []
                    if s.get('title'):
                        parts.append(s['title'])
                    parts.extend(s.get('content', []))
                    slide_texts.append(' '.join(parts))
            template_check = ReportService.check_template_compliance(slide_texts)
            template_check_summary = '\n'.join(template_check['recommendations'])
            if template_check['missing_blocks']:
                template_check_summary += (
                    f"\nОтсутствуют блоки: "
                    f"{', '.join(template_check['missing_blocks'])}"
                )

            slide_info_lines = [f'Всего слайдов: {slide_count}']
            for i, title in enumerate(slide_titles, 1):
                slide_info_lines.append(f'  Слайд {i}: {title}')
            slide_info = '\n'.join(slide_info_lines)

            api_key = current_app.config.get('DEEPSEEK_API_KEY') or os.environ.get(
                'DEEPSEEK_API_KEY', ''
            )
            if not api_key:
                raise RuntimeError('DEEPSEEK_API_KEY is not configured.')

            client = DeepSeekClient(api_key=api_key)
            system_prompt = SYSTEM_PROMPT.format(
                structure_validation=STRUCTURE_VALIDATION_INSTRUCTION.format(
                    validation_result_json=json.dumps(
                        template_check, ensure_ascii=False, indent=2
                    )
                )
            ) + TEMPLATE_COMPLIANCE_CHECK.format(
                template_check_result=template_check_summary
            )
            text_for_llm = USER_PROMPT_TEMPLATE.format(
                project_name=check.original_filename,
                team_members='—',
                slide_info=slide_info,
                extracted_text=check.extracted_text,
                slide_template=SLIDE_TEMPLATE,
            )

            llm_result = client.analyze_presentation(
                text=text_for_llm, system_prompt=system_prompt
            )

            check.llm_response = json.dumps(llm_result, ensure_ascii=False)
            check.grade = str(round(llm_result.get('score', 0), 1))
            report_data = ReportService.generate_report(llm_result)
            report_data['filename'] = check.original_filename
            report_data['template_compliance'] = template_check
            report_data['teacher_letter'] = ReportService.generate_teacher_letter(
                check.original_filename, float(check.grade), report_data['feedback']
            )
            check.final_report = json.dumps(report_data, ensure_ascii=False)
            check.status = 'completed'

            try:
                os.remove(file_path)
            except OSError:
                pass

        except Exception as e:
            check.status = 'error'
            check.final_report = json.dumps({'error': 'Внутренняя ошибка сервера'}, ensure_ascii=False)
            current_app.logger.error('Check %d failed: %s', check_id, str(e), exc_info=True)

        db.session.commit()


@bp.route('/check/upload', methods=['POST'])
@login_required
@limiter.limit('5/minute')
def upload_and_check():
    if 'file' not in request.files:
        return jsonify({'ok': False, 'error': 'Файл не предоставлен.'}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({'ok': False, 'error': 'Файл не выбран.'}), 400

    original_filename = re.sub(r'[<>&"\']', '', file.filename)
    _name, ext = os.path.splitext(original_filename)
    ext = ext.lower()

    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({
            'ok': False,
            'error': f'Недопустимый формат. Разрешены: {", ".join(ALLOWED_EXTENSIONS)}',
        }), 400

    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)

    if size > MAX_FILE_SIZE:
        return jsonify({'ok': False, 'error': 'Файл превышает лимит 32 МБ.'}), 413

    upload_dir = current_app.config['UPLOAD_FOLDER']
    os.makedirs(upload_dir, exist_ok=True)

    safe_filename = f'{uuid.uuid4()}{ext}'
    file_path = os.path.join(upload_dir, safe_filename)
    file.save(file_path)
    validate_file_content(file_path, ext)

    if ext == '.pdf':
        result = PDFParser.extract_with_fallback(file_path)
        slide_texts = [p['text'] for p in result.get('pages', [])]
    elif ext == '.pptx':
        result = PPTXParser.extract_text(file_path)
        slide_texts = []
        for s in result.get('slides', []):
            parts = []
            if s.get('title'):
                parts.append(s['title'])
            parts.extend(s.get('content', []))
            slide_texts.append(' '.join(parts))
    else:
        return jsonify({'ok': False, 'error': 'Неподдерживаемый тип файла.'}), 400

    template_check = ReportService.check_template_compliance(slide_texts)

    check = ProjectCheck(
        user_id=current_user.id,
        original_filename=original_filename,
        safe_filename=safe_filename,
        status='processing',
    )
    db.session.add(check)
    db.session.commit()

    app = current_app._get_current_object()
    thread = threading.Thread(
        target=_process_check, args=(app, check.id), daemon=True
    )
    thread.start()

    return jsonify({
        'check_id': check.id,
        'original_filename': original_filename,
        'template_compliance': template_check,
        'status': 'processing',
    }), 201
