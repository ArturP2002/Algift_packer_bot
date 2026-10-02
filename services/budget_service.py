_PREDEFINED = {
    "1000-3000": (1000, 3000),
    "3000-5000": (3000, 5000),
    "5000-10000": (5000, 10000),
    "10000-20000": (10000, 20000),
}
# Свой бюджет — это ориентир, а не точная цена: подарок на 40 тыс. может стоить и 30 тыс.
_CUSTOM_FLOOR_RATIO = 0.7


def normalize_budget(value: str) -> int:
    if value in _PREDEFINED:
        return _PREDEFINED[value][1]
    if value.isdigit():
        return int(value)
    raise ValueError("Invalid budget value")


def budget_floor(value: str) -> int:
    """Нижняя граница цены подарка для выбранного бюджета."""
    if value in _PREDEFINED:
        return _PREDEFINED[value][0]
    return int(normalize_budget(value) * _CUSTOM_FLOOR_RATIO)
