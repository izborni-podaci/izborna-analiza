from types import SimpleNamespace as S

from izbori import quarters

AREA = {"settlement": "Нови Сад",
        "features": [{"properties": {"name": n}} for n in ("Телеп", "Адице", "Лиман 1", "Грбавица", "Бистрица")],
        "points": [["Основна школа „Вељко Петровић“", "Лиман 1"], ["месна заједница Братство-Телеп", "Телеп"],
                   ["Мрвица", "Грбавица"], ["Основна школа „Јован Поповић“", "Телеп"],
                   ["Основна школа „Јован Поповић“", "Адице"], ["Гимназија „Јован Јовановић Змај“", "Грбавица"], ["ОШ „Жарко Зрењанин“", "Бистрица"],
                   ["Средња школа „Жарко Зрењанин“", "Телеп"], ["Градска управа за инспекцијске послове", "Адице"],
                   ["Сајлово", "Телеп"]]}


def st(key, name, where="Нови Сад"):
    return S(key=key, name=name, where=where)


def test_stations_go_to_their_buildings_quarter():
    sts = [st("1", 'ОШ "ВЕЉКО ПЕТРОВИЋ"'), st("2", 'МЗ "АДИЦЕ" (ВЕЛИКА САЛА)'), st("3", 'МЗ "БРАТСТВО-ТЕЛЕП"'),
           st("4", 'ПУ "РАДОСНО ДЕТИЊСТВО" - ОБЈЕКАТ "МРВИЦА"'), st("5", 'ОШ "ЈОВАН ПОПОВИЋ"'),
           st("6", 'МЗ "ВЕЉКО ПЕТРОВИЋ"'), st("7", 'ОШ "ВЕЉКО ПЕТРОВИЋ"', where="Футог"),
           st("8", 'ГИМНАЗИЈА "ЈОВАН ЈОВАНОВИЋ ЗМАЈ"'), st("9", 'ОШ "ЖАРКО ЗРЕЊАНИН"'), st("10", 'МЗ "ЈУЖНИ ТЕЛЕП"'),
           st("11", "ГРАДСКА УПРАВА ЗА ИНСПЕКЦИЈСКЕ ПОСЛОВЕ ГРАДА НОВОГ САДА"), st("12", 'МЗ "САЈЛОВО"'),
           st("13", "КЛУБ ПЕНЗИОНЕРА")]
    got = quarters.place(sts, lambda s: s.where, AREA)
    assert got == {"1": "Лиман 1", "2": "Адице", "3": "Телеп", "4": "Грбавица", "8": "Грбавица",
                   "9": "Ново насеље", "10": "Телеп", "11": "Адице", "12": "Телеп"}  # 9: by the name people use
    # 11: the building's whole name inside the station's; 12: a neighbourhood inside a quarter; 13: nothing distinct
    # 5: a school of that name in two quarters; 6: a community hall named like a school; 7: another settlement


def test_names():
    assert quarters.names(AREA) == ("Општина Нови Сад", "Град Нови Сад")
