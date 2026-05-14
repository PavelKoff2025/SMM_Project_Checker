"""Orchestrates a single presentation check from start to finish.

The service owns parsing, template validation, LLM call, report generation
and database state transitions. Routes should remain thin.
"""

import json
import logging
import os

from flask import Flask

from app import db
from app.checker.llm_client import DEFAULT_PROVIDER, LLMConfigError, create_client
from app.checker.prompt_templates import (
    SLIDE_TEMPLATE,
    STRUCTURE_VALIDATION_INSTRUCTION,
    SYSTEM_PROMPT,
    TEMPLATE_COMPLIANCE_CHECK,
    USER_PROMPT_TEMPLATE,
)
from app.checker.services import ReportService
from app.models import ProjectCheck
from app.services.file_storage import delete_silently
from app.services.presentation_service import (
    ParsedPresentation,
    parse_presentation,
)

logger = logging.getLogger(__name__)


def _build_system_prompt(template_check: dict, template_check_summary: str) -> str:
    structure_block = STRUCTURE_VALIDATION_INSTRUCTION.format(
        validation_result_json=json.dumps(template_check, ensure_ascii=False, indent=2)
    )
    compliance_block = TEMPLATE_COMPLIANCE_CHECK.format(
        template_check_result=template_check_summary
    )
    return SYSTEM_PROMPT.format(structure_validation=structure_block) + compliance_block


def _build_user_prompt(
    original_filename: str,
    parsed: ParsedPresentation,
) -> str:
    slide_info_lines = [f'Всего слайдов: {parsed.slide_count}']
    for i, title in enumerate(parsed.slide_titles, 1):
        slide_info_lines.append(f'  Слайд {i}: {title}')
    slide_info = '\n'.join(slide_info_lines)
    return USER_PROMPT_TEMPLATE.format(
        project_name=original_filename,
        team_members='—',
        slide_info=slide_info,
        extracted_text=parsed.full_text,
        slide_template=SLIDE_TEMPLATE,
    )


def _summarize_template_check(template_check: dict) -> str:
    summary = '\n'.join(template_check.get('recommendations', []))
    missing = template_check.get('missing_blocks') or []
    if missing:
        summary += f"\nОтсутствуют блоки: {', '.join(missing)}"
    return summary


def run_check(app: Flask, check_id: int) -> None:
    """Run a check inside an app context; safe to call from a worker thread."""
    with app.app_context():
        check = db.session.get(ProjectCheck, check_id)
        if not check:
            return

        upload_dir = app.config['UPLOAD_FOLDER']
        file_path = os.path.join(upload_dir, check.safe_filename)
        _, ext = os.path.splitext(check.safe_filename)

        try:
            parsed = parse_presentation(file_path, ext)
            if parsed.is_empty:
                raise ValueError('No text could be extracted from the file.')

            check.extracted_text = parsed.full_text

            template_check = ReportService.check_template_compliance(parsed.slide_texts)
            template_check_summary = _summarize_template_check(template_check)

            provider = check.llm_provider or DEFAULT_PROVIDER
            try:
                client = create_client(provider, app.config)
            except LLMConfigError as exc:
                raise RuntimeError(str(exc)) from exc

            logger.info(
                'Check %d: using %s (%s) for analysis',
                check_id, client.__class__.__name__, client.model,
            )

            system_prompt = _build_system_prompt(template_check, template_check_summary)
            user_prompt = _build_user_prompt(check.original_filename, parsed)
            llm_result = client.analyze_presentation(
                text=user_prompt, system_prompt=system_prompt
            )

            check.llm_response = json.dumps(llm_result, ensure_ascii=False)
            check.grade = str(round(llm_result.get('score', 0), 1))

            report_data = ReportService.generate_report(llm_result)
            report_data['filename'] = check.original_filename
            report_data['template_compliance'] = template_check
            report_data['teacher_letter'] = ReportService.generate_teacher_letter(
                check.original_filename,
                float(check.grade),
                report_data['feedback'],
                report_data.get('criteria_feedback'),
            )
            check.final_report = json.dumps(report_data, ensure_ascii=False)
            check.status = 'completed'

            delete_silently(file_path)

        except Exception:
            check.status = 'error'
            check.final_report = json.dumps(
                {'error': 'Внутренняя ошибка сервера'}, ensure_ascii=False
            )
            logger.exception('Check %d failed', check_id)

        db.session.commit()
