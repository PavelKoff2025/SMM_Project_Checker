import json
import os

from flask import jsonify, request, current_app, render_template
from flask_login import login_required, current_user

from app import db
from app.models import ProjectCheck
from app.checker import checker_bp
from app.checker.parsers import PDFParser, PPTXParser
from app.checker.llm_client import DeepSeekClient
from app.checker.prompt_templates import (
    SLIDE_TEMPLATE,
    STRUCTURE_VALIDATION_INSTRUCTION,
    SYSTEM_PROMPT,
    TEMPLATE_COMPLIANCE_CHECK,
    USER_PROMPT_TEMPLATE,
)
from app.checker.services import ReportService


@checker_bp.route('/')
@login_required
def index():
    return render_template('history.html')


@checker_bp.route('/upload')
@login_required
def upload_page():
    return render_template('upload.html')


@checker_bp.route('/check/<int:check_id>/progress')
@login_required
def progress_page(check_id: int):
    check = db.session.get(ProjectCheck, check_id)
    if not check or check.user_id != current_user.id:
        return render_template('error.html', message='Проверка не найдена.'), 404
    return render_template('progress.html', check_id=check_id)


@checker_bp.route('/check/<int:check_id>/report')
@login_required
def report_page(check_id: int):
    check = db.session.get(ProjectCheck, check_id)
    if not check or check.user_id != current_user.id:
        return render_template('error.html', message='Проверка не найдена.'), 404
    return render_template('report.html', check_id=check_id, check=check)


ALLOWED_EXTENSIONS = {'pdf', 'pptx'}
MAX_FILE_SIZE = 32 * 1024 * 1024


def _allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[-1].lower() in ALLOWED_EXTENSIONS


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
                    s.get('title', '') or s.get('content', [''])[0][:80]
                    for s in result.get('slides', [])
                ]
            else:
                raise ValueError(f'Unsupported file type: {ext}')

            if not check.extracted_text.strip():
                raise ValueError('No text could be extracted from the file.')

            slide_info_lines = [f'Всего слайдов: {slide_count}']
            for i, title in enumerate(slide_titles, 1):
                slide_info_lines.append(f'  Слайд {i}: {title}')
            slide_info = '\n'.join(slide_info_lines)

            slide_texts = [s['text'] for s in result.get('pages', result.get('slides', []))]
            template_check = ReportService.check_template_compliance(slide_texts)
            template_check_summary = '\n'.join(template_check['recommendations'])
            if template_check['missing_blocks']:
                template_check_summary += (
                    f"\nОтсутствуют блоки: {', '.join(template_check['missing_blocks'])}"
                )

            api_key = current_app.config.get('DEEPSEEK_API_KEY') or os.environ.get('DEEPSEEK_API_KEY', '')
            if not api_key:
                raise RuntimeError('DEEPSEEK_API_KEY is not configured.')

            client = DeepSeekClient(api_key=api_key)
            system_prompt = (
                SYSTEM_PROMPT.format(
                    structure_validation=STRUCTURE_VALIDATION_INSTRUCTION.format(
                        validation_result_json=json.dumps(
                            template_check, ensure_ascii=False, indent=2
                        )
                    )
                )
                + TEMPLATE_COMPLIANCE_CHECK.format(
                    template_check_result=template_check_summary
                )
            )
            text_for_llm = USER_PROMPT_TEMPLATE.format(
                project_name=check.original_filename,
                team_members='—',
                slide_info=slide_info,
                extracted_text=check.extracted_text,
                slide_template=SLIDE_TEMPLATE,
            )

            llm_result = client.analyze_presentation(text=text_for_llm, system_prompt=system_prompt)

            check.llm_response = json.dumps(llm_result, ensure_ascii=False)
            check.grade = str(round(llm_result.get('score', 0), 1))
            report_data = ReportService.generate_report(llm_result)
            report_data['filename'] = check.original_filename
            report_data['teacher_letter'] = ReportService.generate_teacher_letter(
                check.original_filename, float(check.grade), report_data['feedback']
            )
            check.final_report = json.dumps(report_data, ensure_ascii=False)
            check.status = 'completed'

        except Exception as e:
            check.status = 'error'
            check.final_report = json.dumps({'error': 'Внутренняя ошибка сервера'}, ensure_ascii=False)
            current_app.logger.error('Check %d failed: %s', check_id, str(e), exc_info=True)

        db.session.commit()


@checker_bp.route('/api/check/<int:check_id>/status', methods=['GET'])
@login_required
def status(check_id: int):
    check = db.session.get(ProjectCheck, check_id)
    if not check or check.user_id != current_user.id:
        return jsonify({'ok': False, 'error': 'Проверка не найдена.'}), 404

    return jsonify({
        'ok': True,
        'check_id': check.id,
        'status': check.status,
    })


@checker_bp.route('/api/check/<int:check_id>/report', methods=['GET'])
@login_required
def report(check_id: int):
    check = db.session.get(ProjectCheck, check_id)
    if not check or check.user_id != current_user.id:
        return jsonify({'ok': False, 'error': 'Проверка не найдена.'}), 404

    if check.status != 'completed':
        return jsonify({'ok': False, 'error': 'Проверка ещё не завершена.', 'status': check.status}), 409

    report_data = json.loads(check.final_report) if check.final_report else {}
    return jsonify({'ok': True, 'report': report_data})


@checker_bp.route('/api/check/<int:check_id>/export', methods=['GET'])
@login_required
def export(check_id: int):
    check = db.session.get(ProjectCheck, check_id)
    if not check or check.user_id != current_user.id:
        return jsonify({'ok': False, 'error': 'Проверка не найдена.'}), 404

    if check.status != 'completed':
        return jsonify({'ok': False, 'error': 'Проверка ещё не завершена.', 'status': check.status}), 409

    report = json.loads(check.final_report) if check.final_report else {}
    fmt = request.args.get('format', 'txt')

    service = ReportService()

    if fmt == 'md':
        content = service.export_to_markdown(report)
        return jsonify({'ok': True, 'format': 'md', 'content': content})

    if fmt == 'pdf':
        pdf_bytes = service.export_to_pdf(report)
        return jsonify({
            'ok': True,
            'format': 'pdf',
            'content': pdf_bytes.hex(),
        })

    content = service.export_to_txt(report)
    return jsonify({'ok': True, 'format': 'txt', 'content': content})


@checker_bp.route('/api/check/history', methods=['GET'])
@login_required
def history():
    checks = ProjectCheck.query.filter_by(user_id=current_user.id)\
        .order_by(ProjectCheck.created_at.desc()).all()

    return jsonify({
        'ok': True,
        'checks': [
            {
                'id': c.id,
                'filename': c.original_filename,
                'status': c.status,
                'grade': c.grade,
                'created_at': c.created_at.isoformat() if c.created_at else None,

            }
            for c in checks
        ],
    })
