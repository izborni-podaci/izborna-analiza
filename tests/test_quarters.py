from types import SimpleNamespace as S

from izbori import quarters

AREA = {"settlement": "Нови Сад",
        "features": [{"properties": {"name": n}} for n in ("Телеп", "Адице", "Лиман 1", "Грбавица", "Бистрица")],
        "points": [["Основна школа „Вељко Петровић“", "Лиман 1"], ["месна заједница Братство-Телеп", "Телеп"],
                   ["Мрвица", "Грбавица"], ["Основна школа „Јован Поповић“", "Телеп"],
                   ["Основна школа „Јован Поповић“", "Адице"], ["Гимназија „Јован Јовановић Змај“", "Грбавица"], ["ОШ „Жарко Зрењанин“", "Бистрица"],
                   ["Средња школа „Жарко Зрењанин“", "Телеп"]]}


def st(key, name, where="Нови Сад"):
    return S(key=key, name=name, where=where)


def test_stations_go_to_their_buildings_quarter():
    sts = [st("1", 'ОШ "ВЕЉКО ПЕТРОВИЋ"'), st("2", 'МЗ "АДИЦЕ" (ВЕЛИКА САЛА)'), st("3", 'МЗ "БРАТСТВО-ТЕЛЕП"'),
           st("4", 'ПУ "РАДОСНО ДЕТИЊСТВО" - ОБЈЕКАТ "МРВИЦА"'), st("5", 'ОШ "ЈОВАН ПОПОВИЋ"'),
           st("6", 'МЗ "ВЕЉКО ПЕТРОВИЋ"'), st("7", 'ОШ "ВЕЉКО ПЕТРОВИЋ"', where="Футог"),
           st("8", 'ГИМНАЗИЈА "ЈОВАН ЈОВАНОВИЋ ЗМАЈ"'), st("9", 'ОШ "ЖАРКО ЗРЕЊАНИН"'), st("10", 'МЗ "ЈУЖНИ ТЕЛЕП"')]
    got = quarters.place(sts, lambda s: s.where, AREA)
    assert got == {"1": "Лиман 1", "2": "Адице", "3": "Телеп", "4": "Грбавица", "8": "Грбавица",
                   "9": "Ново насеље", "10": "Телеп"}  # 9: the primary school, by the name people use
    # 5: a school of that name in two quarters; 6: a community hall named like a school; 7: another settlement
