"""
bot/ai.py
إعادة صياغة المقالات عربيًا وتقييمها باستخدام OpenAI API (أو أي واجهة متوافقة معها).
"""

import json
import re

from openai import OpenAI

from bot.config import OPENAI_API_KEY, OPENAI_API_BASE, OPENAI_MODEL

_SYSTEM_PROMPT = """أنت محرر أخبار عربي محترف يعمل ضمن نظام أتمتة نشر.
مهمتك عند استلام مقال (عنوان + ملخص + مصدر):
1. افهم المقال جيدًا.
2. قرر هل يستحق النشر لجمهور عربي عام مهتم بالتقنية والأخبار (publish: true/false).
3. اختر تصنيفًا واحدًا فقط من هذه القائمة بالضبط:
   technology, news, sports, gaming, ai, android, apple, crypto
4. اكتب عنوانًا عربيًا جذابًا ومحايدًا (title_ar) لا يتجاوز 15 كلمة.
5. اكتب ملخصًا عربيًا واضحًا من 2 إلى 5 فقرات قصيرة (summary_ar).
6. لا تختلق أي معلومة غير موجودة في النص الأصلي.
7. حافظ على الأرقام والأسماء المهمة كما وردت.
8. لا تنسخ النص الأصلي حرفيًا، بل أعد صياغته بأسلوبك.
9. أعطِ تقييمًا من 0 إلى 100 (score) لجودة وأهمية الخبر لجمهور عربي.

أعد الإجابة بصيغة JSON فقط بدون أي نص إضافي وبدون Markdown، بهذا الشكل بالضبط:
{"publish": true, "category": "technology", "title_ar": "...", "summary_ar": "...", "score": 82}
"""


class AIError(Exception):
    pass


def _get_client() -> OpenAI:
    if not OPENAI_API_KEY:
        raise AIError("OPENAI_API_KEY غير مضبوط في متغيرات البيئة.")
    return OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_API_BASE)


def process_article(title: str, description: str, source_name: str, category_hint: str = ""):
    """
    يرسل المقال إلى الذكاء الاصطناعي ويعيد قاموسًا:
    {publish, category, title_ar, summary_ar, score}
    يرفع AIError عند فشل الاتصال أو تعذّر تحليل الرد.
    """
    client = _get_client()

    user_content = (
        f"المصدر: {source_name}\n"
        f"التصنيف المقترح (إن وجد): {category_hint}\n"
        f"العنوان الأصلي: {title}\n"
        f"الملخص/المحتوى الأصلي: {description}\n"
    )

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.4,
        )
    except Exception as e:
        raise AIError(f"فشل الاتصال بواجهة الذكاء الاصطناعي: {e}")

    raw = response.choices[0].message.content or ""
    data = _safe_json_parse(raw)

    if data is None:
        raise AIError("تعذّر تحليل رد الذكاء الاصطناعي كـ JSON.")

    result = {
        "publish": bool(data.get("publish", False)),
        "category": str(data.get("category", category_hint or "news")).strip().lower(),
        "title_ar": str(data.get("title_ar", "")).strip(),
        "summary_ar": str(data.get("summary_ar", "")).strip(),
        "score": _safe_int(data.get("score", 0)),
    }

    if not result["title_ar"] or not result["summary_ar"]:
        raise AIError("رد الذكاء الاصطناعي لا يحتوي عنوانًا أو ملخصًا صالحًا.")

    return result


def _safe_json_parse(raw: str):
    raw = raw.strip()
    # إزالة أسوار Markdown إن وجدت (```json ... ```)
    raw = re.sub(r"^```(json)?", "", raw.strip(), flags=re.IGNORECASE).strip()
    raw = re.sub(r"```$", "", raw.strip()).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
        return None


def _safe_int(value) -> int:
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        n = 0
    return max(0, min(100, n))
