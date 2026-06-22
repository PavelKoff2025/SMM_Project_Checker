import json

from flask import current_app, jsonify, render_template, request
from flask_login import current_user, login_required

from app import db, limiter
from app.checker import checker_bp
from app.checker.llm_client import (
    DEFAULT_PROVIDER,
    PROVIDERS,
    is_provider_configured,
    list_providers,
)
from app.checker.services import ReportService
from app.models import ProjectCheck
from app.queue import enqueue_check
from app.services.file_storage import (
    FileValidationError,
    persist_upload,
    sanitize_original_filename,
    split_extension,
    validate_upload,
)


def _resolve_provider(raw: str | None) -> str:
    candidate = (raw or '').strip().lower() or DEFAULT_PROVIDER
    if candidate not in PROVIDERS:
        candidate = DEFAULT_PROVIDER
    return candidate


def _owned_or_404(check_id: int):
    check = db.session.get(ProjectCheck, check_id)
    if not check or check.user_id != current_user.id:
        return None
    return check


@checker_bp.route('/')
@login_required
def index():
    return render_template('history.html')


@checker_bp.route('/upload')
@login_required
def upload_page():
    providers = list_providers(current_app.config)
    return render_template(
        'upload.html', providers=providers, default_provider=DEFAULT_PROVIDER
    )


@checker_bp.route('/api/providers', methods=['GET'])
@login_required
def providers():
    return jsonify({
        'ok': True,
        'default': DEFAULT_PROVIDER,
        'providers': list_providers(current_app.config),
    })


@checker_bp.route('/check/<int:check_id>/progress')
@login_required
def progress_page(check_id: int):
    if not _owned_or_404(check_id):
        return render_template('error.html', message='Проверка не найдена.'), 404
    return render_template('progress.html', check_id=check_id)


@checker_bp.route('/check/<int:check_id>/report')
@login_required
def report_page(check_id: int):
    check = _owned_or_404(check_id)
    if not check:
        return render_template('error.html', message='Проверка не найдена.'), 404
    return render_template('report.html', check_id=check_id, check=check)


@checker_bp.route('/api/check/upload', methods=['POST'])
@login_required
@limiter.limit('5/minute')
def upload_and_check():
    if 'file' not in request.files:
        return jsonify({'ok': False, 'error': 'Файл не предоставлен.'}), 400

    file = request.files['file']
    original_filename = sanitize_original_filename(file.filename or '')
    if not original_filename:
        return jsonify({'ok': False, 'error': 'Файл не выбран.'}), 400

    provider = _resolve_provider(request.form.get('provider'))
    if not is_provider_configured(provider, current_app.config):
        return jsonify({
            'ok': False,
            'error': f'Провайдер «{PROVIDERS[provider].label}» не настроен.',
        }), 400

    _, ext = split_extension(original_filename)

    try:
        validate_upload(file.stream, ext)
    except FileValidationError as exc:
        status = 413 if 'лимит' in str(exc) else 400
        return jsonify({'ok': False, 'error': str(exc)}), status

    upload_dir = current_app.config['UPLOAD_FOLDER']
    try:
        safe_filename, _ = persist_upload(file.stream, upload_dir, ext)
    except FileValidationError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400

    check = ProjectCheck(
        user_id=current_user.id,
        original_filename=original_filename,
        safe_filename=safe_filename,
        status='processing',
        llm_provider=provider,
    )
    db.session.add(check)
    db.session.commit()

    enqueue_check(check.id)

    return jsonify({
        'check_id': check.id,
        'original_filename': original_filename,
        'status': 'processing',
        'provider': provider,
    }), 201


@checker_bp.route('/api/check/<int:check_id>/status', methods=['GET'])
@login_required
def status(check_id: int):
    check = _owned_or_404(check_id)
    if not check:
        return jsonify({'ok': False, 'error': 'Проверка не найдена.'}), 404
    return jsonify({
        'ok': True,
        'check_id': check.id,
        'status': check.status,
        'provider': check.llm_provider,
    })


@checker_bp.route('/api/check/<int:check_id>/report', methods=['GET'])
@login_required
def report(check_id: int):
    check = _owned_or_404(check_id)
    if not check:
        return jsonify({'ok': False, 'error': 'Проверка не найдена.'}), 404
    if check.status == 'error':
        report_data = json.loads(check.final_report) if check.final_report else {}
        return jsonify({
            'ok': False,
            'error': report_data.get('error', 'Произошла ошибка при анализе.'),
            'status': 'error',
        }), 200
    if check.status != 'completed':
        return jsonify({
            'ok': False, 'error': 'Проверка ещё не завершена.', 'status': check.status
        }), 409

    report_data = json.loads(check.final_report) if check.final_report else {}
    return jsonify({
        'ok': True,
        'report': report_data,
        'provider': check.llm_provider,
    })


@checker_bp.route('/api/check/<int:check_id>/export', methods=['GET'])
@login_required
def export(check_id: int):
    check = _owned_or_404(check_id)
    if not check:
        return jsonify({'ok': False, 'error': 'Проверка не найдена.'}), 404
    if check.status != 'completed':
        return jsonify(
            {'ok': False, 'error': 'Проверка ещё не завершена.', 'status': check.status}
        ), 409

    report_data = json.loads(check.final_report) if check.final_report else {}
    fmt = request.args.get('format', 'txt')

    if fmt == 'md':
        return jsonify({
            'ok': True,
            'format': 'md',
            'content': ReportService.export_to_markdown(report_data),
        })
    if fmt == 'pdf':
        return jsonify({
            'ok': True,
            'format': 'pdf',
            'content': ReportService.export_to_pdf(report_data).hex(),
        })
    return jsonify({
        'ok': True,
        'format': 'txt',
        'content': ReportService.export_to_txt(report_data),
    })


@checker_bp.route('/search')
@login_required
def search_page():
    return render_template('search.html')


@checker_bp.route('/api/search', methods=['GET'])
@login_required
def search():
    q = (request.args.get('q') or '').strip()
    if not q:
        return jsonify({'ok': True, 'checks': []})

    checks = (
        ProjectCheck.query
        .filter(ProjectCheck.status == 'completed', ProjectCheck.grade.isnot(None))
        .all()
    )
    q_lower = q.lower()
    matched = [c for c in checks if q_lower in (c.original_filename or '').lower()]
    matched.sort(key=lambda c: float(c.grade or 0), reverse=True)

    return jsonify({
        'ok': True,
        'q': q,
        'checks': [
            {
                'id': c.id,
                'filename': c.original_filename,
                'grade': c.grade,
                'username': c.user.username,
                'created_at': c.created_at.isoformat() if c.created_at else None,
            }
            for c in matched
        ],
    })


@checker_bp.route('/rating')
@login_required
def rating_page():
    return render_template('rating.html')


@checker_bp.route('/api/rating', methods=['GET'])
@login_required
def rating():
    checks = (
        ProjectCheck.query
        .filter(ProjectCheck.status == 'completed', ProjectCheck.grade.isnot(None))
        .all()
    )
    checks.sort(key=lambda c: float(c.grade or 0), reverse=True)
    return jsonify({
        'ok': True,
        'checks': [
            {
                'id': c.id,
                'filename': c.original_filename,
                'grade': c.grade,
                'username': c.user.username,
                'created_at': c.created_at.isoformat() if c.created_at else None,
            }
            for c in checks
        ],
    })


@checker_bp.route('/api/check/history', methods=['GET'])
@login_required
def history():
    checks = (
        ProjectCheck.query
        .filter_by(user_id=current_user.id)
        .order_by(ProjectCheck.created_at.desc())
        .all()
    )
    return jsonify({
        'ok': True,
        'checks': [
            {
                'id': c.id,
                'filename': c.original_filename,
                'status': c.status,
                'grade': c.grade,
                'provider': c.llm_provider,
                'created_at': c.created_at.isoformat() if c.created_at else None,
            }
            for c in checks
        ],
    })
