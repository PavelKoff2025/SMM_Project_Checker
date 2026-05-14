import io

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table

from app.validators.template_validator import PresentationTemplateValidator


class ReportService:

    CRITERIA_LABELS = {
        'structure': 'Структура презентации',
        'platform_design': 'Оформление площадок',
        'usp': 'УТП',
        'competitor_analysis': 'Анализ конкурентов (ER)',
        'vk_ads': 'VK Ads кампания',
    }

    @classmethod
    def generate_report(cls, llm_response: dict) -> dict:
        criteria = llm_response.get('criteria', {})
        feedback_per = llm_response.get('criteria_feedback', {}) or {}
        score = llm_response.get('score', 0)
        feedback = llm_response.get('feedback', '')
        strengths = llm_response.get('strengths', [])
        weaknesses = llm_response.get('weaknesses', [])

        return {
            'grade': round(score, 1),
            'criteria': {
                label: criteria.get(key, 0)
                for key, label in cls.CRITERIA_LABELS.items()
            },
            'criteria_feedback': {
                label: feedback_per.get(key, '')
                for key, label in cls.CRITERIA_LABELS.items()
            },
            'feedback': feedback,
            'strengths': strengths,
            'weaknesses': weaknesses,
        }

    @staticmethod
    def export_to_txt(report: dict) -> str:
        lines = []
        lines.append('=' * 60)
        lines.append('SMM PROJECT CHECKER — ОТЧЕТ')
        lines.append('=' * 60)
        lines.append(f'Общая оценка: {report["grade"]}/10\n')

        lines.append('Критерии:')
        for name, score in report['criteria'].items():
            bar = '█' * int(score) + '░' * (10 - int(score))
            lines.append(f'  {name}: {score}/10  {bar}')

        per = report.get('criteria_feedback') or {}
        if any(per.values()):
            lines.append('\nДетальный разбор по критериям:')
            for name in report['criteria'].keys():
                comment = (per.get(name) or '').strip()
                if comment:
                    lines.append(f'\n  {name}:')
                    for paragraph in comment.split('\n'):
                        lines.append(f'    {paragraph}')

        lines.append(f'\nОбщий итог:\n{report["feedback"]}\n')

        if report['strengths']:
            lines.append('Сильные стороны:')
            for s in report['strengths']:
                lines.append(f'  + {s}')

        if report['weaknesses']:
            lines.append('\nСлабые стороны:')
            for w in report['weaknesses']:
                lines.append(f'  - {w}')

        lines.append('\n' + '=' * 60)
        return '\n'.join(lines)

    @staticmethod
    def export_to_markdown(report: dict) -> str:
        lines = []
        lines.append('# SMM Project Checker — Отчет\n')
        lines.append(f'**Общая оценка:** {report["grade"]}/10\n')
        lines.append('## Критерии\n')
        lines.append('| Критерий | Оценка |')
        lines.append('|----------|-------:|')
        for name, score in report['criteria'].items():
            bar = '█' * int(score) + '░' * (10 - int(score))
            lines.append(f'| {name} | {score}/10 {bar} |')

        per = report.get('criteria_feedback') or {}
        if any(per.values()):
            lines.append('\n## Детальный разбор по критериям\n')
            for name in report['criteria'].keys():
                comment = (per.get(name) or '').strip()
                if comment:
                    lines.append(f'### {name}\n')
                    lines.append(f'{comment}\n')

        lines.append(f'\n## Общий итог\n\n{report["feedback"]}\n')

        if report['strengths']:
            lines.append('## Сильные стороны\n')
            for s in report['strengths']:
                lines.append(f'- ✅ {s}')

        if report['weaknesses']:
            lines.append('\n## Слабые стороны\n')
            for w in report['weaknesses']:
                lines.append(f'- ❌ {w}')

        lines.append('')
        return '\n'.join(lines)

    @staticmethod
    def export_to_pdf(report: dict) -> bytes:
        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf, pagesize=A4,
            leftMargin=20 * mm, rightMargin=20 * mm,
            topMargin=20 * mm, bottomMargin=20 * mm,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle', parent=styles['Title'],
            spaceAfter=12,
        )
        heading_style = ParagraphStyle(
            'CustomHeading', parent=styles['Heading2'],
            spaceBefore=12, spaceAfter=6,
        )
        body_style = ParagraphStyle(
            'CustomBody', parent=styles['Normal'],
            spaceAfter=6, leading=14,
        )

        elements = []

        elements.append(Paragraph('SMM Project Checker — Отчет', title_style))
        elements.append(Paragraph(
            f'Общая оценка: <b>{report["grade"]}/10</b>', body_style
        ))
        elements.append(Spacer(1, 6 * mm))

        elements.append(Paragraph('Критерии', heading_style))
        table_data = [['Критерий', 'Оценка']]
        for name, score in report['criteria'].items():
            table_data.append([name, f'{score}/10'])
        table = Table(table_data, colWidths=[120 * mm, 40 * mm])
        table.setStyle([
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, '#cccccc'),
            ('BACKGROUND', (0, 0), (-1, 0), '#333333'),
            ('TEXTCOLOR', (0, 0), (-1, 0), '#ffffff'),
        ])
        elements.append(table)
        elements.append(Spacer(1, 6 * mm))

        per = report.get('criteria_feedback') or {}
        if any(per.values()):
            elements.append(Paragraph('Детальный разбор по критериям', heading_style))
            for name in report['criteria'].keys():
                comment = (per.get(name) or '').strip()
                if comment:
                    elements.append(Paragraph(f'<b>{name}</b>', body_style))
                    for paragraph in comment.split('\n'):
                        elements.append(Paragraph(paragraph, body_style))
                    elements.append(Spacer(1, 2 * mm))

        elements.append(Paragraph('Общий итог', heading_style))
        for line in report['feedback'].split('\n'):
            elements.append(Paragraph(line, body_style))

        if report['strengths']:
            elements.append(Spacer(1, 4 * mm))
            elements.append(Paragraph('Сильные стороны', heading_style))
            for s in report['strengths']:
                elements.append(Paragraph(f'✓ {s}', body_style))

        if report['weaknesses']:
            elements.append(Spacer(1, 4 * mm))
            elements.append(Paragraph('Слабые стороны', heading_style))
            for w in report['weaknesses']:
                elements.append(Paragraph(f'✗ {w}', body_style))

        doc.build(elements)
        buf.seek(0)
        return buf.read()

    @staticmethod
    def generate_teacher_letter(
        filename: str,
        grade: float,
        feedback: str,
        criteria_feedback: dict | None = None,
    ) -> str:
        passed = grade >= 4.0
        result = 'Зачет' if passed else 'Незачет'
        lines = []
        lines.append(f'Добрый день! Проверил ваш выпускной проект "{filename}".')
        lines.append('')
        lines.append('Мои основные мысли и замечания ниже:')
        lines.append('')
        lines.append(feedback)

        if criteria_feedback and any((v or '').strip() for v in criteria_feedback.values()):
            lines.append('')
            lines.append('Детальный разбор по критериям:')
            for name, comment in criteria_feedback.items():
                comment = (comment or '').strip()
                if not comment:
                    continue
                lines.append('')
                lines.append(f'• {name}')
                lines.append(comment)

        lines.append('')
        lines.append(f'Ваша итоговая оценка по курсу "Взаимодействие с социальными медиа" — "{result}".')
        lines.append('')
        lines.append('С уважением, Павел Васильевич Кариков, преподаватель.')
        return '\n'.join(lines)

    @staticmethod
    def check_template_compliance(extracted_slides: list) -> dict:
        """
        Проверяет соответствие презентации шаблону.
        """
        validator = PresentationTemplateValidator()
        full_text = ' '.join(extracted_slides)
        result = validator.validate(full_text, extracted_slides)

        recommendations = []

        if result['compliance_percentage'] < 50:
            recommendations.append(
                "❌ КРИТИЧНО: Презентация не соответствует шаблону. "
                f"Найдено только {result['compliance_percentage']}% обязательных блоков."
            )
        elif result['compliance_percentage'] < 80:
            recommendations.append(
                f"⚠️ ПРЕДУПРЕЖДЕНИЕ: Презентация частично соответствует шаблону "
                f"({result['compliance_percentage']}%). Добавьте отсутствующие блоки."
            )
        else:
            recommendations.append(
                f"✓ Презентация соответствует шаблону ({result['compliance_percentage']}%)"
            )

        if result['missing_blocks']:
            recommendations.append(
                f"Отсутствуют блоки: {', '.join(result['missing_blocks'])}"
            )

        return {
            'compliance_percentage': result['compliance_percentage'],
            'missing_blocks': result['missing_blocks'],
            'found_blocks': result['found_blocks'],
            'total_slides': result['total_slides'],
            'recommendations': recommendations,
        }
