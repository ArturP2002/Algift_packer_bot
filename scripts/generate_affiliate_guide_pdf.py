#!/usr/bin/env python3
"""Generate anonymized PDF onboarding guide for affiliate catalog setup."""

from __future__ import annotations

from pathlib import Path

from fpdf import FPDF


FONT_REG = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
FONT_UNI = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
OUT = Path(__file__).resolve().parents[1] / "docs" / "Instrukciya_podklyuchenie_partnerskih_katalogov.pdf"


class GuidePDF(FPDF):
    def header(self) -> None:
        if self.page_no() == 1:
            return
        self.set_font("Body", "", 9)
        self.set_text_color(110, 110, 110)
        self.cell(0, 8, "Инструкция: подключение партнёрских каталогов товаров", align="L")
        self.ln(4)
        self.set_draw_color(220, 220, 220)
        self.line(18, self.get_y(), self.w - 18, self.get_y())
        self.ln(8)

    def footer(self) -> None:
        self.set_y(-16)
        self.set_font("Body", "", 9)
        self.set_text_color(140, 140, 140)
        self.cell(0, 8, f"{self.page_no()}", align="C")


def add_title(pdf: GuidePDF, text: str) -> None:
    pdf.set_font("Heading", "B", 18)
    pdf.set_text_color(20, 20, 20)
    pdf.multi_cell(0, 9, text)
    pdf.ln(4)


def add_h2(pdf: GuidePDF, text: str) -> None:
    pdf.ln(3)
    pdf.set_font("Heading", "B", 13)
    pdf.set_text_color(25, 25, 25)
    pdf.multi_cell(0, 7, text)
    pdf.ln(2)


def add_h3(pdf: GuidePDF, text: str) -> None:
    pdf.ln(1)
    pdf.set_font("Heading", "B", 11)
    pdf.set_text_color(40, 40, 40)
    pdf.multi_cell(0, 6, text)
    pdf.ln(1)


def add_body(pdf: GuidePDF, text: str) -> None:
    pdf.set_font("Body", "", 10.5)
    pdf.set_text_color(35, 35, 35)
    pdf.multi_cell(0, 5.8, text)
    pdf.ln(1.5)


def add_bullet(pdf: GuidePDF, text: str) -> None:
    pdf.set_font("Body", "", 10.5)
    pdf.set_text_color(35, 35, 35)
    x = pdf.get_x()
    pdf.cell(6, 5.8, "•")
    pdf.multi_cell(0, 5.8, text)
    pdf.set_x(x)
    pdf.ln(0.5)


def add_step(pdf: GuidePDF, num: int, text: str) -> None:
    pdf.set_font("Body", "", 10.5)
    pdf.set_text_color(35, 35, 35)
    pdf.multi_cell(0, 5.8, f"{num}. {text}")
    pdf.ln(0.8)


def add_code(pdf: GuidePDF, text: str) -> None:
    pdf.set_fill_color(245, 246, 248)
    pdf.set_text_color(30, 30, 30)
    pdf.set_font("Body", "", 9)
    pdf.set_x(18)
    pdf.multi_cell(pdf.w - 36, 5.2, text, fill=True)
    pdf.ln(2)


def add_callout(pdf: GuidePDF, title: str, text: str) -> None:
    pdf.set_fill_color(248, 250, 252)
    pdf.set_draw_color(200, 210, 220)
    y0 = pdf.get_y()
    pdf.set_xy(18, y0)
    pdf.set_font("Heading", "B", 10.5)
    pdf.set_text_color(25, 45, 70)
    pdf.multi_cell(pdf.w - 36, 6, title, fill=True)
    pdf.set_x(18)
    pdf.set_font("Body", "", 10)
    pdf.set_text_color(40, 40, 40)
    pdf.multi_cell(pdf.w - 36, 5.5, text, fill=True)
    pdf.ln(3)


def build() -> Path:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pdf = GuidePDF(format="A4", unit="mm")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(18, 18, 18)

    # Prefer Unicode font for Cyrillic; fall back to Arial family.
    if Path(FONT_UNI).exists():
        pdf.add_font("Body", "", FONT_UNI)
        pdf.add_font("Body", "B", FONT_UNI)
        pdf.add_font("Heading", "", FONT_UNI)
        pdf.add_font("Heading", "B", FONT_UNI)
    else:
        pdf.add_font("Body", "", FONT_REG)
        pdf.add_font("Body", "B", FONT_BOLD)
        pdf.add_font("Heading", "", FONT_REG)
        pdf.add_font("Heading", "B", FONT_BOLD)

    pdf.add_page()

    # Cover
    pdf.ln(18)
    pdf.set_font("Heading", "B", 22)
    pdf.set_text_color(15, 15, 15)
    pdf.multi_cell(0, 10, "Подключение партнёрских каталогов товаров")
    pdf.ln(6)
    pdf.set_font("Body", "", 10.5)
    pdf.set_text_color(60, 60, 60)
    pdf.multi_cell(
        0,
        6,
        "Документ описывает, зачем подключать партнёрские каталоги маркетплейсов "
        "и как получить доступы в сервисах Takprodam и Admitad для Telegram-бота "
        "подбора подарков с актуальными ссылками и ценами.",
    )

    # Intro
    add_h2(pdf, "1. Зачем это нужно")
    add_body(
        pdf,
        "Бот подбора подарков должен не только предлагать идеи, но и вести пользователя "
        "к конкретному товару: с реальной карточкой, ценой и рабочей ссылкой. "
        "Если отдавать только поисковые страницы маркетплейсов, пользователь видит "
        "общий поиск, а не выбранный подарок. Это снижает доверие и конверсию.",
    )
    add_bullet(pdf, "Точные ссылки на карточки товаров, а не на страницу поиска.")
    add_bullet(pdf, "Актуальные цены и наличие в рамках обновления каталога.")
    add_bullet(pdf, "Возможность зарабатывать комиссию с покупок по партнёрским ссылкам.")
    add_bullet(pdf, "Легальный канал данных без покупки разовых «дампов» и без серых схем.")

    add_h2(pdf, "2. Почему сейчас это лучший вариант")
    add_body(
        pdf,
        "У Wildberries, Ozon и Яндекс Маркета есть официальные API, но они предназначены "
        "для продавцов: через них видны только собственные товары кабинета. "
        "Публичного официального API «всего каталога маркетплейса» для стороннего сервиса нет.",
    )
    add_callout(
        pdf,
        "Практический вывод",
        "Оптимальная схема на сегодня: партнёрские платформы (Takprodam + Admitad) → "
        "своя база товаров → регулярное обновление → выдача в боте прямых партнёрских ссылок. "
        "Это сочетает легальность, актуальность данных, понятную экономику и скорость запуска.",
    )

    add_h2(pdf, "3. Что потребуется получить")
    add_body(pdf, "Для запуска нужны доступы двух типов.")
    add_h3(pdf, "Takprodam (основной источник WB / Ozon)")
    add_bullet(pdf, "API-токен паблишера")
    add_bullet(pdf, "ID площадки (source_id)")
    add_h3(pdf, "Admitad (дополнительные магазины и deeplink)")
    add_bullet(pdf, "client_id и client_secret")
    add_bullet(pdf, "ID площадки (website_id)")
    add_bullet(pdf, "ID партнёрских программ с товарными фидами (по желанию)")
    add_body(
        pdf,
        "Оба сервиса для паблишера бесплатны: платы за доступ к API и каталогу нет. "
        "Доход формируется из комиссии за целевые действия (клик / заказ).",
    )

    pdf.add_page()
    add_title(pdf, "Часть A. Takprodam")
    add_body(
        pdf,
        "Takprodam — платформа Admitad для продвижения товаров маркетплейсов "
        "(Wildberries, Ozon и др.). Это основной источник карточек для бота.",
    )

    add_h2(pdf, "A1. Регистрация и площадка")
    add_step(pdf, 1, "Откройте сайт Takprodam и войдите через Mitgo ID (при отсутствии — зарегистрируйтесь).")
    add_step(
        pdf,
        2,
        "Убедитесь, что аккаунт оформлен как самозанятый, ИП или юридическое лицо "
        "(требование платформы для работы и выплат).",
    )
    add_step(pdf, 3, "Перейдите в раздел «Площадки» → «Добавить площадку».")
    add_step(
        pdf,
        4,
        "Заполните данные: название, тип площадки (Telegram-бот / мессенджер), "
        "URL бота (например, https://t.me/your_bot), тип контента (рекомендуется до 3 тем; "
        "для gift-бота уместны «Обзор покупок» / e-commerce).",
    )
    add_step(
        pdf,
        5,
        "Подтвердите площадку кодом из интерфейса (вставьте код в описание бота/канала, "
        "как требует система).",
    )
    add_step(
        pdf,
        6,
        "Дождитесь модерации (обычно до 48 часов). Нужен статус «Подтверждена» / approved. "
        "Только после этого корректно работают партнёрские ссылки.",
    )

    add_h2(pdf, "A2. Получение API-токена")
    add_step(pdf, 1, "Откройте Профиль → Общие настройки профиля → «Генерация API токена».")
    add_step(pdf, 2, "Нажмите «Сгенерировать» и сразу скопируйте токен.")
    add_step(
        pdf,
        3,
        "Сохраните токен в безопасном месте. После закрытия окна повторно целиком его, "
        "как правило, не показывают.",
    )
    add_body(pdf, "Передайте разработчику значение:")
    add_code(pdf, "TAKPRODAM_API_TOKEN=<ваш_токен>")

    add_h2(pdf, "A3. Получение ID площадки (source_id)")
    add_body(pdf, "Вариант 1 — через API (рекомендуется):")
    add_code(
        pdf,
        'curl -H "Authorization: Bearer <ТОКЕН>" \\\n'
        '  -H "Accept: application/json" \\\n'
        '  "https://api.takprodam.ru/v2/publisher/source/"',
    )
    add_body(
        pdf,
        "В ответе найдите нужную площадку и скопируйте поле id. "
        "Используйте только площадку со статусом approved.",
    )
    add_body(pdf, "Вариант 2 — в личном кабинете: ID площадки в карточке площадки или в URL.")
    add_body(pdf, "Передайте разработчику:")
    add_code(pdf, "TAKPRODAM_SOURCE_ID=<id_площадки>\nTAKPRODAM_SUBID=giftbot")

    add_h2(pdf, "A4. Полезные ссылки Takprodam")
    add_bullet(pdf, "Старт для паблишера: support.admitad.ru (статья «Как паблишеру начать работу с Такпродам»)")
    add_bullet(pdf, "API: https://takprodam.ru/api-publisher/")
    add_bullet(pdf, "Методы API: support.admitad.ru → «API для паблишера»")

    pdf.add_page()
    add_title(pdf, "Часть B. Admitad")
    add_body(
        pdf,
        "Admitad нужен как дополнительный канал: товарные фиды отдельных магазинов "
        "и генерация deeplink. Для MVP достаточно Takprodam; Admitad расширяет покрытие.",
    )

    add_h2(pdf, "B1. Регистрация и площадка")
    add_step(pdf, 1, "Зарегистрируйтесь как паблишер на Admitad (можно тем же Mitgo ID).")
    add_step(pdf, 2, "В кабинете веб-мастера добавьте площадку и дождитесь модерации.")
    add_step(
        pdf,
        3,
        "Подключитесь к нужным партнёрским программам (магазины с товарными фидами).",
    )

    add_h2(pdf, "B2. Получение client_id и client_secret")
    add_step(pdf, 1, "Откройте Настройки → «API и приложения».")
    add_step(pdf, 2, "Нажмите «Показать учетные данные».")
    add_step(pdf, 3, "Скопируйте client_id и client_secret.")
    add_callout(
        pdf,
        "Важно по безопасности",
        "Учётные данные API дают доступ к аккаунту. Не передавайте их третьим лицам "
        "и не публикуйте в открытых репозиториях. При утечке сбросьте ключ в настройках.",
    )
    add_body(pdf, "Передайте разработчику:")
    add_code(
        pdf,
        "ADMITAD_CLIENT_ID=<client_id>\n"
        "ADMITAD_CLIENT_SECRET=<client_secret>\n"
        "ADMITAD_SCOPE=public_data websites advcampaigns deeplink_generator",
    )

    add_h2(pdf, "B3. Получение website_id")
    add_step(pdf, 1, "Настройки → Площадки — найдите ID площадки в списке/карточке.")
    add_body(pdf, "Или через API после получения access_token:")
    add_code(
        pdf,
        'curl -u "CLIENT_ID:CLIENT_SECRET" \\\n'
        '  -X POST "https://api.admitad.com/token/" \\\n'
        '  -d "grant_type=client_credentials&client_id=CLIENT_ID'
        '&scope=public_data websites advcampaigns deeplink_generator"\n\n'
        'curl -H "Authorization: Bearer ACCESS_TOKEN" \\\n'
        '  "https://api.admitad.com/websites/"',
    )
    add_body(pdf, "Передайте разработчику:")
    add_code(pdf, "ADMITAD_WEBSITE_ID=<id_площадки>\nADMITAD_SUBID=giftbot")

    add_h2(pdf, "B4. ID кампаний для товарных фидов (опционально)")
    add_body(
        pdf,
        "Если нужно подтягивать фиды конкретных магазинов, соберите ID подключённых программ "
        "и передайте списком через запятую.",
    )
    add_code(
        pdf,
        'curl -H "Authorization: Bearer ACCESS_TOKEN" \\\n'
        '  "https://api.admitad.com/advcampaigns/website/WEBSITE_ID/"',
    )
    add_code(pdf, "ADMITAD_CAMPAIGN_IDS=11111,22222")
    add_body(
        pdf,
        "Без ADMITAD_CAMPAIGN_IDS синхронизация фидов Admitad пропускается. "
        "Основной каталог бота при этом продолжает работать на Takprodam.",
    )

    pdf.add_page()
    add_title(pdf, "Чек-лист передачи данных")
    add_body(pdf, "Минимум для запуска с товарами маркетплейсов:")
    add_code(
        pdf,
        "TAKPRODAM_API_TOKEN=\n"
        "TAKPRODAM_SOURCE_ID=\n"
        "TAKPRODAM_SUBID=giftbot",
    )
    add_body(pdf, "Дополнительно (расширение покрытия):")
    add_code(
        pdf,
        "ADMITAD_CLIENT_ID=\n"
        "ADMITAD_CLIENT_SECRET=\n"
        "ADMITAD_WEBSITE_ID=\n"
        "ADMITAD_CAMPAIGN_IDS=\n"
        "ADMITAD_SUBID=giftbot\n"
        "ADMITAD_SCOPE=public_data websites advcampaigns deeplink_generator",
    )

    add_h2(pdf, "Частые вопросы")
    add_h3(pdf, "Нужно ли платить за Takprodam / Admitad?")
    add_body(
        pdf,
        "Нет. Для паблишера регистрация, кабинет и API бесплатны. "
        "Вы получаете комиссию с действий пользователей по партнёрским ссылкам.",
    )
    add_h3(pdf, "Можно ли стартовать только с Takprodam?")
    add_body(
        pdf,
        "Да. Это рекомендуемый минимум: каталог WB/Ozon уже закрывает основной сценарий gift-бота.",
    )
    add_h3(pdf, "Почему нельзя просто купить готовый датасет?")
    add_body(
        pdf,
        "Разовый файл быстро устаревает. Партнёрский каталог обновляется и сразу даёт "
        "рабочие партнёрские ссылки с учётом правил рекламы.",
    )
    add_h3(pdf, "Что делать, если площадку отклонили?")
    add_body(
        pdf,
        "Исправьте данные по замечаниям модерации и отправьте повторно. "
        "Для Telegram-бота обычно критичны корректный URL, описание и подтверждение кодом.",
    )

    add_h2(pdf, "Итог")
    add_body(
        pdf,
        "Подключение Takprodam (и при необходимости Admitad) — практичный способ дать боту "
        "реальные товары со ссылками и ценами без серых обходов и без дорогих устаревающих дампов. "
        "После передачи доступов по чек-листу разработка подключает каталог и включает выдачу "
        "прямых ссылок в ответах бота.",
    )

    pdf.output(str(OUT))
    return OUT


if __name__ == "__main__":
    path = build()
    print(path)
