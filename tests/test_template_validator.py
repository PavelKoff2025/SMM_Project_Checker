from app.validators.template_validator import PresentationTemplateValidator


def test_validator_full_compliance():
    validator = PresentationTemplateValidator()
    slides = [
        'Название проекта: Тест. Группа М-202. Тимлид: Иванов. Дата защиты: май 2026.',
        'Цель SMM-стратегии. Ключевые задачи: оформлены площадки, УТП, аватар.',
        'Учебный проект по продвижении. Рабочую SMM-стратегию. Полный цикл.',
        'ВКонтакте, Telegram, Дзен. Скриншот. Фирменный стиль.',
        'УТП: уникальное предложение. Выгоды. Целевая аудитория. Аватар. Сегмент. Боли.',
        'Анализ конкурентов. ER за март 2026. Формула. Сильные и слабые стороны.',
        'VK Ads: кампания, группы объявлений, таргетинг, бюджет, перформанс.',
        'Креатив с CTA. Объявление. Макет. Заголовок. Визуал.',
        'Распределение задач. Получилось. Сложности. Выводы. Команда.',
        'Спасибо за внимание. Ссылки. Вопросы. QR.',
    ]
    result = validator.validate(' '.join(slides), slides)
    assert result['compliance_percentage'] == 100.0
    assert result['is_critical'] is False
    assert result['missing_blocks'] == []


def test_validator_missing_blocks():
    validator = PresentationTemplateValidator()
    slides = ['Просто какой-то текст без структуры']
    result = validator.validate(' '.join(slides), slides)
    assert result['compliance_percentage'] < 80.0
    assert result['is_critical'] is True
    assert len(result['missing_blocks']) > 0
