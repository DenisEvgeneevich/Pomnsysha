from __future__ import annotations
from datetime import datetime, time as dtime, timedelta
import re
from typing import Optional, Dict, Any

import dateparser

try:
    import spacy
    _SPACY_AVAILABLE = True
    _SPACY_NLP = None
except Exception:
    spacy = None
    _SPACY_AVAILABLE = False
    _SPACY_NLP = None

DEFAULT_CATEGORIES = ["Работа", "Учеба", "Личное", "Здоровье", "Покупки", "Встречи"]

def _detect_category(text: str) -> str:
    t = text.lower()
    mapping = {
        "работ": "Работа",
        "собеседован": "Работа",
        "учеб": "Учеба",
        "школ": "Учеба",
        "унив": "Учеба",
        "мед": "Здоровье",
        "врач": "Здоровье",
        "здоров": "Здоровье",
        "куп": "Покупки",
        "магазин": "Покупки",
        "встреч": "Встречи",
        "встрет": "Встречи",
        "семья": "Личное",
        "мама": "Личное",
        "папа": "Личное",
        "документ": "Личное",
    }

    for k, v in mapping.items():
        if k in t:
            return v
    return "Личное"

def _detect_priority(text: str) -> str:
    t = text.lower()
    high_words = ["срочно", "важно", "критично", "очень надо", "!!!"]
    low_words = ["не срочно", "когда будет время", "может быть"]
    for w in high_words:
        if w in t:
            return "high"
    for w in low_words:
        if w in t:
            return "low"
    return "medium"

def _extract_time(text: str) -> Optional[dtime]:

    m = re.search(r"(\d{1,2})[:\.](\d{2})", text)
    if m:
        h = int(m.group(1))
        mi = int(m.group(2))
        if 0 <= h < 24 and 0 <= mi < 60:
            return dtime(hour=h, minute=mi)
    return None

def _clean_description(text: str) -> str:

    s = text.strip()

    s = re.sub(r"\b(в|во|на|к|о|по)\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _make_title(description: str, max_words: int = 6) -> str:
    words = description.split()
    title_words = words[:max_words]
    if not title_words:
        return "Без названия"
    title = " ".join(title_words)
    return title.capitalize()

def local_parse(text: str) -> Optional[Dict[str, Any]]:
    
    if not text or not text.strip():
        return None

    raw = text.strip()

    extracted_time = _extract_time(raw)

    settings = {
        'PREFER_DATES_FROM': 'future',
        'RELATIVE_BASE': datetime.now()
    }

    parsed = dateparser.parse(raw, languages=['ru'], settings=settings)

    parsed_date = None
    if parsed:
        parsed_date = parsed.date()

    if not parsed_date:
        t = raw.lower()
        if 'сегодня' in t:
            parsed_date = datetime.now().date()
        elif 'завтра' in t:
            parsed_date = (datetime.now() + timedelta(days=1)).date()
        elif 'послезавтра' in t:
            parsed_date = (datetime.now() + timedelta(days=2)).date()
        else:

            m = re.search(r'через\s+(\d+)\s+дн', t)
            if m:
                parsed_date = (datetime.now() + timedelta(days=int(m.group(1)))).date()
            else:
                parsed_date = None

    if not parsed_date:
        parsed_date = datetime.now().date()

    today = datetime.now().date()
    if parsed_date < today:
        parsed_date = today

    description = _clean_description(raw)
    title = _make_title(description)
    category = _detect_category(raw)
    priority = _detect_priority(raw)

    activity_title = None
    activity_category = None
    try:
        want_match = re.search(r"\b(хочу|хотел бы|хотела бы|надо|нужно|пойду|схожу)\s+([а-яё-]+)", raw, re.I)
        if want_match:
            verb = want_match.group(2).lower()

            verb = re.sub(r"[^а-яё]+$", "", verb)

            verb_norm_map = {
                'плав': 'Плавание',
                'плы': 'Плавание',
                'бег': 'Бег',
                'тренир': 'Тренировка',
                'спорт': 'Спорт',
                'куп': 'Покупки',
            }
            activity_title = None
            for k, v in verb_norm_map.items():
                if k in verb:
                    activity_title = v
                    break
            if not activity_title:

                if verb.endswith('ть'):
                    stem = verb[:-1]
                    candidate = stem + 'ие'
                elif verb.endswith('ться'):
                    stem = verb[:-4]
                    candidate = stem + 'ие'
                else:
                    candidate = verb
                activity_title = candidate.capitalize()

            cat_map = {
                'плав': 'Здоровье',
                'бег': 'Здоровье',
                'тренир': 'Здоровье',
                'спорт': 'Здоровье',
                'куп': 'Покупки',
            }
            for k, v in cat_map.items():
                if k in activity_title.lower():
                    activity_category = v
                    break
    except Exception:
        activity_title = None
        activity_category = None

    try:
        if _SPACY_AVAILABLE:
            try:
                if _SPACY_NLP is None:

                    try:
                        _SPACY_NLP = spacy.load("ru_core_news_sm")
                    except Exception:

                        try:
                            _SPACY_NLP = spacy.load("ru_core_news_md")
                        except Exception:
                            _SPACY_NLP = None

                if _SPACY_NLP:
                    doc = _SPACY_NLP(raw)

                    verb_lemmas = [tok.lemma_ for tok in doc if tok.pos_ in ("VERB", "INF")]

                    noun_lemmas = [tok.lemma_ for tok in doc if tok.pos_ == "NOUN"]

                    chosen = None
                    if verb_lemmas:
                        chosen = verb_lemmas[0]
                    elif noun_lemmas:
                        chosen = noun_lemmas[0]

                    if chosen:

                        act = chosen

                        if act.endswith("ть"):
                            stem = act[:-1]
                            activity_title = (stem + "ие").lower()
                        else:
                            activity_title = act.lower()

                        normalization = {
                            'плавание': 'Плавание',
                            'плавать': 'Плавание',
                            'плыть': 'Плавание',
                            'бег': 'Бег',
                            'бегать': 'Бег',
                            'тренировка': 'Тренировка',
                            'спорт': 'Спорт',
                        }
                        normalized = normalization.get(activity_title, None)
                        if normalized:
                            activity_title = normalized
                        else:

                            activity_title = activity_title.capitalize()

                        cat_map = {
                            'плав': 'Здоровье',
                            'бег': 'Здоровье',
                            'тренир': 'Здоровье',
                            'спорт': 'Здоровье',
                            'йог': 'Здоровье',
                            'куп': 'Покупки',
                            'встр': 'Встречи',
                            'работ': 'Работа',
                            'учеб': 'Учеба',
                        }
                        for k, v in cat_map.items():
                            if k in activity_title.lower():
                                activity_category = v
                                break
            except Exception:
                activity_title = None
                activity_category = None
    except Exception:
        activity_title = None
        activity_category = None

    if activity_title:
        title = activity_title
        if activity_category:
            category = activity_category

    return {
        'date': parsed_date,
        'time': extracted_time,
        'description': description,
        'title': title,
        'category': category,
        'priority': priority
    }

if __name__ == '__main__':
    examples = [
        'совещание с командой завтра в 11:00',
        'купить цветы маме на др 12 марта',
        'срочно! доделать презентацию к пятнице',
        'паспорт сделать в конце месяца',
        'зубной в четверг запись',
    ]
    for e in examples:
        print(e, '->', local_parse(e))
