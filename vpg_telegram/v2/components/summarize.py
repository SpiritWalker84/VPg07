"""Краткое резюме загруженного файла через чат-модель (OpenAI-совместимый API)."""

from __future__ import annotations

from openai import OpenAI


def one_sentence_summary_ru(
    *,
    api_key: str,
    base_url: str,
    chat_model: str,
    filename: str,
    content_excerpt: str,
) -> str:
    """Одно предложение на русском по отрывку текста после Docling."""
    client = OpenAI(api_key=api_key, base_url=base_url)
    user_msg = (
        f"Имя файла: {filename}\n\n"
        f"Фрагмент текста документа:\n{content_excerpt.strip()}\n\n"
        "Сформулируй ровно одно короткое предложение на русском: о чём этот документ."
    )
    completion = client.chat.completions.create(
        model=chat_model,
        messages=[
            {
                "role": "system",
                "content": "Отвечай кратко. Только одно предложение без вступлений.",
            },
            {"role": "user", "content": user_msg},
        ],
        max_completion_tokens=120,
        temperature=0.3,
    )
    text = (completion.choices[0].message.content or "").strip()
    return text or "Краткое резюме сформировать не удалось."
