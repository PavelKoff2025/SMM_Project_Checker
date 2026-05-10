class PresentationTemplateValidator:
    """
    Проверяет наличие 10 логических блоков в презентации.
    Не привязывается к номерам слайдов → допускает любые дополнительные слайды с визуалами.
    """

    REQUIRED_BLOCKS = {
        "title": {
            "name": "Титульный слайд",
            "keywords": ["группа", "тимлид", "участник", "дата", "проект"],
            "min_matches": 2
        },
        "goals_short": {
            "name": "Цели и задачи (кратко)",
            "keywords": ["цель smm", "ключевые задачи", "оформлены площадки", "utm", "аватар"],
            "min_matches": 2
        },
        "goals_detailed": {
            "name": "Описание проекта (развернуто)",
            "keywords": ["учебный проект", "продвижении", "рабочую smm-стратегию", "полный цикл"],
            "min_matches": 2
        },
        "platforms": {
            "name": "Оформление площадок",
            "keywords": ["вконтакте", "telegram", "дзен", "vk", "скриншот", "адаптация", "фирменный стиль"],
            "min_matches": 3
        },
        "utp_audience": {
            "name": "УТП, выгоды, ЦА, аватары",
            "keywords": ["утп", "выгоды", "целевая аудитория", "аватар", "сегмент", "боли"],
            "min_matches": 3
        },
        "competitors": {
            "name": "Анализ конкурентов",
            "keywords": ["конкурент", "er", "март 2026", "формула", "сильные", "слабые"],
            "min_matches": 3
        },
        "vk_ads_strategy": {
            "name": "Стратегия VK Ads",
            "keywords": ["vk ads", "кампания", "группы объявлений", "таргетинг", "бюджет", "перформанс"],
            "min_matches": 3
        },
        "creatives": {
            "name": "Креативы и таргетинг",
            "keywords": ["креатив", "объявление", "макет", "cta", "заголовок", "визуал"],
            "min_matches": 2
        },
        "team_results": {
            "name": "Итоги команды",
            "keywords": ["распределение задач", "получилось", "сложности", "выводы", "команда"],
            "min_matches": 2
        },
        "conclusion": {
            "name": "Заключение",
            "keywords": ["спасибо за внимание", "ссылки", "вопросы", "qr"],
            "min_matches": 2
        }
    }

    def validate(self, full_text: str, slides_text: list[str]) -> dict:
        found_blocks = []
        missing_blocks = []
        block_details = {}

        full_text_lower = full_text.lower()

        for block_key, config in self.REQUIRED_BLOCKS.items():
            matches = sum(1 for kw in config["keywords"] if kw.lower() in full_text_lower)
            is_found = matches >= config["min_matches"]

            containing_slides = []
            for i, slide in enumerate(slides_text):
                slide_lower = slide.lower()
                if any(kw.lower() in slide_lower for kw in config["keywords"]):
                    containing_slides.append(i + 1)

            block_info = {
                "name": config["name"],
                "found": is_found,
                "matches": matches,
                "slides": containing_slides
            }
            block_details[block_key] = block_info

            if is_found:
                found_blocks.append(block_info)
            else:
                missing_blocks.append(config["name"])

        compliance_pct = round((len(found_blocks) / len(self.REQUIRED_BLOCKS)) * 100, 1)

        extra_slides_note = "Дополнительные слайды с визуалами/скриншотами допускаются и не снижают оценку."

        return {
            "compliance_percentage": compliance_pct,
            "found_blocks": found_blocks,
            "missing_blocks": missing_blocks,
            "total_slides": len(slides_text),
            "details": block_details,
            "extra_slides_note": extra_slides_note,
            "is_critical": compliance_pct < 80
        }
