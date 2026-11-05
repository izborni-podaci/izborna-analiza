"""Text in three locales: 'cyr' (Serbian Cyrillic, the source), 'lat' (Serbian Latin, converted
automatically) and 'en'. Numbers and times are formatted per locale; times are shown in Belgrade time."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from izbori.translit import latin

LOCALES = ["lat", "cyr", "en"]
LANG_ATTR = {"lat": "sr-Latn", "cyr": "sr-Cyrl", "en": "en"}
PREFIX = {"lat": "", "cyr": "cyr/", "en": "en/"}
BELGRADE = ZoneInfo("Europe/Belgrade")

# Text between these marks is left alone when a Cyrillic page is converted to Latin.
KEEP_OPEN, KEEP_CLOSE = "", ""


def keep(text: str) -> str:
    return f"{KEEP_OPEN}{text}{KEEP_CLOSE}"


def latin_page(html: str) -> str:
    out, rest = [], html
    while True:
        i = rest.find(KEEP_OPEN)
        if i < 0:
            out.append(latin(rest))
            break
        j = rest.find(KEEP_CLOSE, i)
        out.append(latin(rest[:i]))
        out.append(rest[i + 1:j])
        rest = rest[j + 1:]
    return "".join(out)


def strip_keep(html: str) -> str:
    return html.replace(KEEP_OPEN, "").replace(KEEP_CLOSE, "")


S: dict[str, tuple[str, str]] = {
    # site
    "site_name": ("Изборни подаци", "Election data"),
    "tagline": ("Архива резултата које објављује Републичка изборна комисија и провере сваког бирачког места",
                "An archive of the results Serbia's electoral commission publishes, with checks on every polling station"),
    "nav_overview": ("Преглед", "Overview"),
    "nav_check": ("За проверу", "To check"),
    "nav_municipalities": ("Општине", "Municipalities"),
    "nav_changes": ("Измене", "Changes"),
    "nav_guide": ("Водич за контролоре и посматраче", "Guide for controllers and observers"),
    "nav_guide_short": ("Водич", "Guide"),
    "nav_explore": ("Истражи", "Explore"),
    "nav_repeat_short": ("Историја", "History"),
    "nav_about": ("О пројекту", "About"),
    "footer_data": ("Подаци: Републичка изборна комисија (РИК). Ознаке воде до записника које је објавио РИК.",
                    "Data: Republic Electoral Commission (RIK). Every flag links to the minutes RIK published."),
    "footer_code": ("Изворни код, архива и методологија", "Source code, archive and method"),
    "footer_feed": ("Атом фид", "Atom feed"),
    "principle": ("Ознака је питање, не закључак: нешто је необично и вреди погледати записник.",
                  "A flag is a question, not a verdict: something is unusual and the minutes are worth a look."),
    # kinds
    "kind_presidential": ("Председнички избори", "Presidential election"),
    "kind_parliamentary": ("Парламентарни избори", "Parliamentary election"),
    "kind_local": ("Локални избори", "Local election"),
    "kind_provincial": ("Покрајински избори", "Provincial election"),
    "kind_unknown": ("Избори", "Election"),
    # overview
    "rounds_heading": ("Избори у архиви", "Elections in the archive"),
    "no_rounds": ("Архива је још празна.", "The archive is empty so far."),
    "counting": ("Бројање у току", "Counting in progress"),
    "complete": ("Сва бирачка места обрађена", "All polling stations counted"),
    "last_change": ("Последња измена", "Last change"),
    # round
    "counted_of": ("Обрађено бирачких места: {counted} од {total}", "Polling stations counted: {counted} of {total}"),
    "rik_time": ("Време у РИК-овој датотеци", "Time in RIK's file"),
    "fetched": ("Преузето", "Fetched"),
    "snapshots": ("Сачуваних верзија", "Versions archived"),
    "rik_source": ("Резултати на сајту РИК-а", "Results on RIK's website"),
    "registered": ("Уписани бирачи", "Registered voters"),
    "voted": ("Гласали", "Voted"),
    "turnout": ("Излазност", "Turnout"),
    "ballots": ("Листића у кутији", "Ballots in the box"),
    "valid": ("Важећи листићи", "Valid ballots"),
    "invalid": ("Неважећи листићи", "Invalid ballots"),
    "no": ("Бр.", "No."),
    "list": ("Изборна листа", "Electoral list"),
    "candidate": ("Кандидат", "Candidate"),
    "votes": ("Гласова", "Votes"),
    "of_voted": ("% гласалих", "% of voters"),
    "of_valid": ("% важећих", "% of valid"),
    "seats": ("Мандата", "Seats"),
    "results_heading": ("Резултати", "Results"),
    "seats_heading": ("Расподела мандата", "Seats"),
    "status": ("Статус", "Status"),
    "over_threshold": ("Прешла цензус", "Over the threshold"),
    "minority": ("Мањинска листа", "Minority list"),
    "under_threshold": ("Испод цензуса", "Under the threshold"),
    "threshold_line": ("Цензус: {n} гласова, 3% од броја гласалих.", "Threshold: {n} votes, 3% of voters who voted."),
    "minority_rule": ("Листе националних мањина испод цензуса учествују у расподели са гласовима увећаним за 35%.",
                      "National minority lists below the threshold take part with their votes multiplied by 1.35."),
    "majority_line": ("Већина: {n}", "Majority: {n}"),
    "two_thirds_line": ("Две трећине: {n}", "Two-thirds: {n}"),
    "margins_heading": ("Гласови који мењају мандат", "Votes that change a seat"),
    "margins_note": ("Колико гласова листи треба за мандат више и колико може да изгуби а да задржи све мандате, ако се гласови осталих не промене.",
                     "How many votes each list needs for one more seat, and how many it could lose and keep every seat, with everyone else's votes unchanged."),
    "gain": ("За мандат више", "For one more seat"),
    "keep": ("Може да изгуби", "Can lose"),
    "pres_rule": ("Бира се кандидат који добије више од половине гласова бирача који су гласали. Неважећи листићи се рачунају у гласале.",
                  "The winner needs more than half of the votes of everyone who voted. Invalid ballots count among those who voted."),
    "pres_majority": ("{name} има више од половине гласова гласалих.", "{name} has more than half of the votes of those who voted."),
    "pres_short": ("Водећем кандидату недостаје {n} гласова до више од половине гласалих ({needed}).",
                   "The leader is {n} votes short of more than half of those who voted ({needed})."),
    "pres_runoff": ("Ако остане овако, следи други круг између: {a} и {b}.", "If this holds, a runoff follows between {a} and {b}."),
    "pres_runoff_round": ("Други круг: бира се кандидат са више гласова.", "Runoff: the candidate with more votes wins."),
    "majority_mark": ("50% гласалих", "50% of voters"),
    "check_heading": ("За проверу", "To check"),
    "on_this_page": ("На овој страни", "On this page"),
    "nav_repeat": ("Историја места", "Station history"),
    "nav_main": ("Главни мени", "Main menu"),
    "nav_elections": ("Избори", "Elections"),
    "menu_label": ("Језик, писмо и тема", "Language, script and theme"),
    "search_label": ("Претрага", "Search"),
    "home_title": ("Проверите има ли неправилности на вашем бирачком месту", "Check for irregularities at your polling station"),
    "home_lede": ("Резултате које објављује Републичка изборна комисија проверавамо за свако бирачко место: да ли се бројеви слажу, да ли има више потписа него листића, да ли су излазност или број неважећих листића необични. Где нешто одступа, место добија ознаку и линк на записник. Исте провере важе за све учеснике избора.", "We check the results Serbia's Republic Electoral Commission (RIK) publishes for every polling station: do the numbers add up, are there more signatures than ballots, are turnout or invalid ballots unusual. Where something is off, the station gets a flag and a link to its minutes. The same checks apply to everyone on the ballot."),
    "search_field": ("Општина или бирачко место", "Municipality or polling station"),
    "search_placeholder": ("нпр. Нови Сад или Земун 25", "e.g. Novi Sad or Zemun 25"),
    "search_button": ("Тражи", "Search"),
    "search_or": ("Или погледајте", "Or see"),
    "search_or_link": ("све изборе у архиви", "all elections in the archive"),
    "search_none": ("Ништа није нађено. Пробајте назив општине.", "Nothing found. Try the municipality's name."),
    "search_flagged": ("избори: {n} · са ознаком: {k}", "elections: {n} · flagged: {k}"),
    "search_clean": ("избори: {n} · без ознаке", "elections: {n} · never flagged"),
    "search_mun_sub": ("општина · избори: {n}", "municipality · elections: {n}"),
    "search_former": ("раније БМ {n}", "formerly No. {n}"),
    "intents_heading": ("Шта можете овде", "What you can do here"),
    "intent1_kicker": ("Последњи избори · {title}", "Latest election · {title}"),
    "intent1_title": ("Шта је необично", "What looks unusual"),
    "intent1_body": ("{n} од {total} бирачких места има бар једну ознаку.", "{n} of {total} polling stations have at least one flag."),
    "intent1_cta": ("Листа за проверу", "The list to check"),
    "intent2_kicker": ("Сви избори у архиви", "All elections in the archive"),
    "intent2_title": ("Необично више пута", "Unusual more than once"),
    "intent2_body": ("Иста бирачка места на којима су бројеви били необични на двоје или више избора, а не само једном. Таквих је {n}.", "The same polling stations whose numbers were unusual in two or more elections, not just once. There are {n}."),
    "intent3_kicker": ("За контролоре и посматраче", "For controllers and observers"),
    "intent3_title": ("Пре изборног дана", "Before election day"),
    "intent3_body": ("Права и рокови на бирачком месту, од примопредаје материјала до записника, и шта забележити.", "Rights and deadlines at the polling station, from the handover of materials to the minutes, and what to write down."),
    "intent3_cta": ("Водич за контролоре и посматраче", "Guide for controllers and observers"),
    "intent4_title": ("Ко је имао контролоре", "Who had controllers"),
    "intent4_body": ("На колико бирачких места свака листа има члана у проширеном саставу, према решењима изборних комисија.", "At how many polling stations each list has a member in the extended composition, according to the electoral commissions' decisions."),
    "intent4_cta": ("Контролори по листама", "Controllers by list"),
    "intent5_kicker": ("Ваша општина", "Your municipality"),
    "intent5_title": ("Општина кроз све изборе", "A municipality across elections"),
    "intent5_body": ("Резултати, излазност и бирачка места кроз изборе, и документи изборне комисије.", "Results, turnout and polling stations across elections, and the electoral commission's documents."),
    "intent5_cta": ("Све општине", "All municipalities"),
    "intent6_kicker": ("За новинаре и програмере", "For journalists and developers"),
    "intent6_title": ("Подаци и обавештења", "Data and alerts"),
    "intent6_body": ("Атом фид за нове ознаке, подаци у JSON-у и цела архива на GitHub-у.", "Atom feeds for new flags, the data as JSON and the whole archive on GitHub."),
    "intent6_cta": ("Како до података", "How to get the data"),
    # the archive in numbers and the next election beside the search
    "stats_rounds": ("Избора у архиви: {n}", "Elections in the archive: {n}"),
    "stats_places": ("бирачких места кроз изборе: {n}", "polling stations across elections: {n}"),
    "stats_docs": ("докумената са сајта РИК-а: {n}", "documents on RIK's site, linked: {n}"),
    "next_kicker": ("Следећи избори", "Next election"),
    "next_and": (" и ", " and "),
    "next_in": ("за {n} {unit}", "in {n} {unit}"),
    "next_day_one": ("дан", "day"),
    "next_day_many": ("дана", "days"),
    "next_today": ("данас", "today"),
    "next_tomorrow": ("сутра", "tomorrow"),
    "next_by": ("до {d}", "by {d}"),
    "next_by_midnight": ("до {d} у 24:00", "by {d}, midnight"),
    "next_from": ("од {d} у 0:00", "from {d}, 0:00"),
    "dl_boards_proposed": ("предлог чланова бирачких одбора", "nominations for the polling boards"),
    "dl_boards_appointed": ("решења о именовању бирачких одбора", "polling boards appointed"),
    "dl_observers_domestic": ("пријава домаћих посматрача", "domestic observers register"),
    "dl_handover": ("примопредаја материјала бирачким одборима", "materials handed to the polling boards"),
    "dl_silence": ("изборна тишина", "campaign silence"),
    "next_guide": ("Рокови и правила у водичу", "Deadlines and rules in the guide"),
    "next_authority": ("Рачунато уназад од дана гласања; меродаван је роковник изборне комисије.", "Counted back from voting day; the electoral commission's calendar is the authority."),
    # the list of municipalities
    "mun_index_lede": ("Свака општина и градска општина кроз изборе у архиви: резултати, излазност и бирачка места, и документи њене изборне комисије.", "Every municipality and city district across the elections in the archive: results, turnout and polling stations, and its electoral commission's documents."),
    "mun_index_name": ("Општина", "Municipality"),
    "mun_index_last": ("Где није наведено друго, бројеви и документи су са последњих избора ({title}).", "Unless another election is named, the numbers and documents are from the latest election ({title})."),
    "mun_index_elections": ("Избори", "Elections"),
    "mun_index_stations": ("Бирачка места на последњим изборима", "Polling stations at the latest election"),
    "mun_index_commission": ("Документи изборне комисије", "Electoral commission's documents"),
    "filter_group_all": ("Све у овој групи", "All in this group"),
    # the Explore page; its script gets every ex_, m_, view_, level_ and preset_ string
    "ex_lede": ("Сложите своју анализу: изаберите изборе, меру и приказ, или почните од готове. Све се рачуна у вашем прегледачу из истих бројева које сајт приказује. Свака анализа има свој линк, а подаци се преузимају као CSV.", "Put together your own analysis: pick an election, a measure and a view, or start from a ready-made one. Everything is computed in your browser from the same numbers the site shows. Every analysis has its own link, and the data downloads as CSV."),
    "ex_presets": ("Готове анализе", "Ready-made analyses"),
    "preset_fingerprint": ("Отисак избора: излазност и удео", "Election fingerprint: turnout and share"),
    "preset_turnout_map": ("Излазност по општинама", "Turnout by municipality"),
    "preset_invalid_map": ("Неважећи листићи по општинама", "Invalid ballots by municipality"),
    "preset_turnout_change": ("Промена излазности на истом месту", "Change in turnout at the same station"),
    "preset_register_change": ("Промена броја уписаних по општинама", "Change in registered voters by municipality"),
    "preset_matrix": ("Излазност кроз изборе", "Turnout across elections"),
    "preset_ctrl_map": ("Где је листа имала контролоре", "Where a list had controllers"),
    "preset_high": ("Места са излазношћу од 90% навише", "Stations with turnout of 90% or more"),
    "ex_round": ("Избори", "Election"),
    "ex_round2": ("Упореди са", "Compare with"),
    "ex_none": ("— без поређења —", "— none —"),
    "ex_view": ("Приказ", "View"),
    "view_map": ("Мапа општина", "Map of municipalities"),
    "view_density": ("Две мере", "Two measures"),
    "view_compare": ("Двоје избора", "Two elections"),
    "view_hist": ("Расподела", "Distribution"),
    "view_table": ("Табела", "Table"),
    "view_matrix": ("Општине кроз изборе", "Municipalities across elections"),
    "ex_level": ("Ниво", "Level"),
    "level_s": ("Бирачка места", "Polling stations"),
    "level_m": ("Општине", "Municipalities"),
    "ex_x": ("Мера", "Measure"),
    "ex_y": ("Друга мера", "Second measure"),
    "ex_list": ("Листа", "List"),
    "ex_pick_list": ("— изаберите листу —", "— choose a list —"),
    "ex_mun": ("Општина", "Municipality"),
    "ex_all": ("Све", "All"),
    "ex_kind": ("Бирачка места", "Polling stations"),
    "ex_kind_d": ("у земљи", "in the country"),
    "ex_kind_a": ("у иностранству", "abroad"),
    "ex_kind_p": ("у заводима", "in prisons"),
    "ex_kind_all": ("сва", "all"),
    "ex_min": ("Најмање уписаних", "At least registered"),
    "ex_flags": ("Ознаке", "Flags"),
    "ex_flags_any": ("са бар једном", "with at least one"),
    "ex_flags_none": ("без ознаке", "with none"),
    "ex_ctrl": ("Контролор листе", "Controller of a list"),
    "ex_ctrl_yes": ("има", "has one"),
    "ex_ctrl_no": ("нема", "has none"),
    "ex_obs": ("Записник о посматрачима", "Observers' record"),
    "ex_yes": ("постоји", "exists"),
    "ex_no": ("не постоји", "doesn't exist"),
    "ex_from": ("Мера од", "Measure from"),
    "ex_to": ("Мера до", "Measure to"),
    "ex_filters": ("Која места", "Which stations"),
    "m_turnout": ("Излазност", "Turnout"),
    "m_invalid": ("Неважећи листићи", "Invalid ballots"),
    "m_share": ("Удео листе", "List's share"),
    "m_top": ("Највећи удео једне листе", "Largest share of any list"),
    "m_reg": ("Уписани бирачи", "Registered voters"),
    "m_voted": ("Гласали", "Voted"),
    "m_gap": ("Потписи мање листића у кутији", "Signatures minus ballots in the box"),
    "m_flagged": ("Има ознаку", "Flagged"),
    "m_ctrl": ("Листа имала контролора", "List had a controller"),
    "m_obs": ("Записник о посматрачима", "Observers' record"),
    "ex_change": ("Промена", "Change"),
    "ex_median_change": ("медијана промене: {v}", "median change: {v}"),
    "ex_biggest": ("Највеће промене", "The largest changes"),
    "ex_pp": ("п. п.", "pp"),
    "ex_true": ("да", "yes"),
    "ex_false": ("не", "no"),
    "ex_nodata": ("нема података", "no data"),
    "ex_source": ("Подаци: Републичка изборна комисија (РИК)", "Data: Republic Electoral Commission (RIK)"),
    "ex_msg_list": ("Изаберите листу. Сајт сам не бира ниједну листу.", "Choose a list. The site doesn't pick a list by itself."),
    "ex_msg_round2": ("Изаберите друге изборе за поређење.", "Choose a second election to compare with."),
    "ex_msg_loading": ("Учитава се…", "Loading…"),
    "ex_msg_nodata": ("Нема бирачких места за овај избор.", "No polling stations match this choice."),
    "ex_msg_error": ("Подаци нису могли да се учитају.", "The data couldn't be loaded."),
    "ex_msg_obs": ("За ове изборе записници о посматрачима још нису прочитани.", "The observers' records of this election haven't been read yet."),
    "ex_msg_ctrl": ("За ове изборе решења о бирачким одборима још нису прочитана.", "The decisions on the polling boards of this election haven't been read yet."),
    "ex_msg_matrix": ("Удео листе и контролори нису исти кроз изборе, јер се листе мењају: изаберите другу меру.", "A list's share and controllers don't carry across elections, as the lists change: choose another measure."),
    "ex_n_s": ("Бирачких места: {n}", "Polling stations: {n}"),
    "ex_n_m": ("Општина: {n}", "Municipalities: {n}"),
    "ex_median": ("медијана: {v}", "median: {v}"),
    "ex_matched": ("спојено са другим изборима: {n}", "matched with the other election: {n}"),
    "ex_r": ("корелација: {v}", "correlation: {v}"),
    "ex_count": ("број бирачких места", "number of stations"),
    "ex_cell": ("{x}, {y}: бирачких места {n}", "{x}, {y}: {n} polling stations"),
    "ex_cell_pick": ("Кликните на поље да видите та бирачка места.", "Click a cell to see those polling stations."),
    "ex_bar_pick": ("Кликните на стубац да видите та бирачка места.", "Click a bar to see those polling stations."),
    "ex_dot_pick": ("Кликните на тачку да видите њена бирачка места.", "Click a point to see its polling stations."),
    "ex_map_pick": ("Кликните на општину на мапи да видите њена бирачка места.", "Click a municipality on the map to see its polling stations."),
    "ex_copy_link": ("Копирај линк", "Copy link"),
    "ex_copied": ("Линк је копиран.", "Link copied."),
    "ex_csv": ("Преузми CSV", "Download CSV"),
    "ex_svg": ("Преузми слику", "Download image"),
    "ex_show_all": ("Прикажи све", "Show all"),
    "ex_top": ("Првих {n}; CSV садржи све.", "The first {n}; the CSV has them all."),
    "ex_col_name": ("Назив", "Name"),
    "ex_col_mun": ("Општина", "Municipality"),
    "ex_col_no": ("Бр.", "No."),
    "ex_col_n": ("Места", "Stations"),
    "ex_col_code": ("Шифра општине", "Municipality code"),
    "ex_col_link": ("Линк", "Link"),
    "ex_no_geo": ("Мапа још нема границе општина.", "The map has no municipal boundaries yet."),
    "ex_not_on_map": ("Нису на мапи, али су у табели и CSV-у: {names}.", "Not on the map, but in the table and the CSV: {names}."),
    "ex_map_sums": ("Мапа сабира бирачка места по општинама.", "The map adds polling stations up by municipality."),
    "ex_attribution": ("Границе општина: © сарадници OpenStreetMap-а, ODbL.", "Municipal boundaries: © OpenStreetMap contributors, ODbL."),
    "ex_diagonal": ("исто као на ранијим изборима", "same as in the earlier election"),
    "ex_noscript": ("За ову страну потребан је JavaScript: анализе се рачунају у прегледачу. Исти подаци су у JSON-у (види О пројекту).", "This page needs JavaScript: the analyses are computed in the browser. The same data is available as JSON (see About)."),
    "ex_notes": ("Како да читате", "How to read this"),
    "ex_note_same": ("Исте мере важе за сваку листу, а ниједна листа није унапред изабрана. Највећи удео једне листе је, за свако место, удео листе која је на њему добила највише гласова, која год да је.", "The same measures apply to every list, and no list is chosen in advance. The largest share of any list is, for each station, the share of whichever list got most votes there."),
    "ex_note_question": ("Графикон показује бројеве, не закључке: необична вредност може имати обичан узрок, на пример мало бирачко место, мањинску средину, завод или иностранство. Проверите записник на страни бирачког места.", "A chart shows numbers, not conclusions: an unusual value can have an ordinary cause, such as a small station, a minority community, a prison or a station abroad. Check the minutes on the station's page."),
    "ex_note_fingerprint": ("Отисак избора: свако поље је број бирачких места са том излазношћу и тим уделом. Код већине избора места чине једну мрљу; гомилање у горњем десном углу (готово сви гласали, готово сви за једну листу) вреди проверити у записницима.", "Election fingerprint: each cell counts the polling stations with that turnout and that share. In most elections the stations form one blob; a cluster in the top right corner (nearly everyone voted, nearly all for one list) is worth checking in the minutes."),
    "ex_note_places": ("Бирачка места се између избора спајају као на странама кроз изборе: по адреси, називу и броју. Општине се спајају по шифри. Поређење иде од ранијих ка каснијим изборима.", "Polling stations are matched across elections as on the pages across elections: by address, name and number. Municipalities by their code. A comparison runs from the earlier election to the later one."),
    "ex_note_change": ("Промена удела и излазности је у процентним поенима (п. п.), а промена бројева у процентима.", "A change in a share or turnout is in percentage points (pp); a change in a count is in per cent."),
    "ex_note_ctrl": ("Контролор: листа је именовала члана или заменика проширеног састава, према решењима изборних комисија; места без прочитаног решења се не рачунају. Именовање не значи да је контролор био присутан.", "Controller: the list appointed a member or deputy of the extended composition, by the electoral commissions' decisions; stations whose decision wasn't read are left out. An appointment doesn't mean the controller was there."),
    "ex_note_map": ("Мапа: општине са Косова и Метохије још нису на мапи (граничне линије по РИК-овој подели тек треба додати), али су у табелама и CSV-у.", "Map: the municipalities of Kosovo and Metohija aren't on the map yet (their boundaries in RIK's division are still to be added), but they are in the tables and the CSV."),
    "read_heading": ("Како да читате ознаке", "How to read the flags"),
    "read_note": ("Три ствари које вреди знати пре прве листе.", "Three things worth knowing before the first list."),
    "read1_title": ("Ознака је питање, не закључак", "A flag is a question, not a verdict"),
    "read1_body": ("Значи да су бројеви необични и да вреди погледати записник. Не значи да је било преваре.", "It means the numbers are unusual and the minutes are worth a look. It does not mean there was fraud."),
    "read2_title": ("Свака провера има свој симбол", "Every check has its own symbol"),
    "read2_link": ("Сви симболи и шта значе", "All symbols and what they mean"),
    "read3_title": ("Проверите у записнику", "Check the minutes"),
    "read3_body": ("Уз свако место је линк на записник који је објавио РИК и шта у њему треба погледати.", "Every station links to the minutes RIK published and says what to look for in them."),
    "trust_source": ("Извор: Републичка изборна комисија", "Source: Republic Electoral Commission"),
    "trust_same": ("Исте провере за све учеснике", "The same checks for everyone"),
    "trust_code": ("Отворен код", "Open source"),
    "trust_private": ("Без колачића и аналитике", "No cookies, no analytics"),
    "elections_lede": ("Сви избори које пратимо. Отворите изборе за резултате, листу за проверу и општине.", "Every election we follow. Open one for its results, the list to check and the municipalities."),
    "repeat_example_heading": ("Како се чита: један пример", "How to read it: one example"),
    "repeat_example_note": ("Свака колона у табели испод је једни избори, а у ћелији су ознаке са тих избора. Ово место има ознаку на {k} од {n} избора на којима је гласало.", "Each column in the table below is one election, and a cell holds the flags from that election. This station was flagged in {k} of the {n} elections it took part in."),
    "crumbs_label": ("Путоказ", "Breadcrumb"),
    "crumbs_home": ("Почетна", "Home"),
    "station_history": ("Кроз све изборе", "Across all elections"),
    "place_lede": ("Један ред за сваке изборе на којима је место гласало, од најновијих. Избори у првој колони воде до овог места у табели општине на тим изборима.",
                   "One row for every election the station took part in, newest first. The election in the first column leads to this station in the municipality's table for that election."),
    "place_former": ("Раније: БМ {numbers}", "Formerly: No. {numbers}"),
    "place_last": ("Последњи пут: {title}", "Last seen: {title}"),
    "place_rule": ("Исто место пратимо кроз изборе по адреси, затим по називу, па по броју. Број и назив у сваком реду су они са тих избора. Када се адреса или назив јасно разликују, то је друго место, и кад је број исти.",
                   "We follow the same place through the elections by address, then by name, then by number. Each row shows the number and name from that election. When the address or name clearly differs, it is another place, even with the same number."),
    "joined_address": ("исто место по адреси", "same place by address"),
    "joined_name": ("исто место по називу", "same place by name"),
    "joined_manual": ("исто место по ручној исправци", "same place by a manual correction"),
    "joined_number": ("исто место по броју", "same place by number"),
    "top_three": ("Прва три", "Top three"),
    "mun_across_link": ("Ова општина кроз све изборе", "This municipality across all elections"),
    "mun_across_lede": ("Један ред за сваке изборе на којима је општина гласала, од најновијих. Избори у првој колони воде до општине на тим изборима, а број за проверу до списка тих места.",
                        "One row for every election the municipality took part in, newest first. The election in the first column leads to the municipality in that election, and the number to check to the list of those stations."),
    "mun_places_heading": ("Бирачка места кроз изборе", "Polling stations across elections"),
    "col_elections": ("Избори", "Elections"),
    "col_flagged": ("Са ознаком", "Flagged"),
    # the charts across elections
    "abbr_presidential": ("Пред.", "Pres."),
    "abbr_parliamentary": ("Парл.", "Parl."),
    "abbr_provincial": ("Покр.", "Prov."),
    "abbr_local": ("Лок.", "Local"),
    "trend_invalid": ("Удео неважећих листића", "Share of invalid ballots"),
    "trend_here_place": ("Ово место", "This station"),
    "trend_here_mun": ("Ова општина", "This municipality"),
    "trend_ref_mun": ("Општина", "Municipality"),
    "trend_ref_all": ("Цели избори", "Whole election"),
    "trend_label": ("Графикони кроз изборе", "Charts across elections"),
    # the analysis at the top of the pages across elections (narrative.py)
    "an_heading": ("Укратко", "In short"),
    "an_note": ("Састављено из РИК-ових бројева, по истим правилима за свако место и сваког учесника. Место по реду рачуна се од највећег.", "Written from RIK's numbers, by the same rules for every place and every contestant. Ranks count from the highest."),
    "ar_context_mun": ("Најновији избори: {short} · поређење са општином", "Latest election: {short} · compared with the municipality"),
    "ar_context_all": ("Најновији избори: {short} · поређење са целим изборима", "Latest election: {short} · compared with the whole election"),
    "ar_flags_label": ("Ознаке", "Flags"),
    "ar_turnout_label": ("Излазност", "Turnout"),
    "ar_leader_label": ("Највише гласова", "Most votes"),
    "ar_place_label": ("Место", "The place"),
    "ar_stations_label": ("Бирачка места", "Polling stations"),
    "ar_records_label": ("Записници", "Records"),
    "ar_no_flags_one": ("Без ознаке", "No flags"),
    "ar_no_flags": ("Без ознаке ни на једним од {n} избора", "No flags in any of {n} elections"),
    "ar_flags": ("На {k} од {n} избора: {items}", "In {k} of {n} elections: {items}"),
    "ar_same": ("иста ознака више пута: {items}", "the same flag more than once: {items}"),
    "ar_invalid": ("неважећи {share} ({label} {ref})", "invalid ballots {share} ({label} {ref})"),
    "ar_invalid_above": ("већи него {cmp} на {j} од {n} избора", "higher than {cmp} in {j} of {n} elections"),
    "ar_invalid_never": ("никад већи него {cmp}", "never higher than {cmp}"),
    "ar_rank_invalid_mun": ("{r}. од {n} у општини", "{r} of {n} in the municipality"),
    "ar_rank_turnout_mun": ("{r}. од {n} у општини", "{r} of {n} in the municipality"),
    "ar_rank_invalid_all": ("{r}. од {n} општина", "{r} of {n} municipalities"),
    "ar_rank_turnout_all": ("{r}. од {n} општина", "{r} of {n} municipalities"),
    "ar_turnout_diff": ("{d} поена {dir} него {cmp}", "{d} points {dir} than {cmp}"),
    "ar_turnout_same": ("колико и {cmp}", "the same as {cmp}"),
    "ar_earlier_range": ("раније {lo}–{hi}", "earlier {lo}–{hi}"),
    "ar_earlier_one": ("раније {x} ({short})", "earlier {x} ({short})"),
    "ar_leader": ("{label} {share} ({ref_label} {ref})", "{label} {share} ({ref_label} {ref})"),
    "ar_same_leader": ("на {s} од {n} избора први и {cmp}", "also first {cmp} in {s} of {n} elections"),
    "ar_same_leader_all": ("на свим изборима први и {cmp}", "also first {cmp} in every election"),
    "ar_same_leader_none": ("ни на једним изборима први и {cmp}", "never also first {cmp}"),
    "ar_former": ("Раније БМ {items}", "Earlier No. {items}"),
    "ar_renamed": ("Раније назив {name} ({shorts})", "Earlier named {name} ({shorts})"),
    "ar_same_place": ("Исти број и назив на свим изборима", "The same number and name in every election"),
    "ar_registered": ("уписаних {a} ({first}) → {b}, {change}", "registered voters {a} ({first}) → {b}, {change}"),
    "ar_absent": ("није гласало на: {list}", "not part of: {list}"),
    "ar_mun_absent": ("општина није гласала на: {list}", "the municipality was not part of: {list}"),
    "ar_observers": ("О посматрачима за {k} од {n} избора", "Observers' record for {k} of {n} elections"),
    "ar_observers_missing": ("без: {items}", "none for: {items}"),
    "ar_observers_one": ("Записник о посматрачима објављен", "Observers' record published"),
    "ar_observers_none_one": ("Записник о посматрачима није објављен", "No observers' record published"),
    "ar_observers_none": ("О посматрачима ни за једне од {n} избора", "No observers' record in any of {n} elections"),
    "ar_mun_records": ("О посматрачима за {o} од {s} бирачких места", "Observers' records for {o} of {s} polling stations"),
    "ar_mun_flags": ("{f} од {s} бирачких места за проверу ({share}; укупно {overall})", "{f} of {s} polling stations to check ({share}; overall {overall})"),
    "ar_mun_repeat": ("места са ознаком на бар једним изборима: {a} · на бар двоје: {b}", "stations flagged in at least one election: {a} · in two or more: {b}"),
    "ar_mun_network": ("{a} ({first}) → {b}", "{a} ({first}) → {b}"),
    "ar_net_new": ("нових {n}", "new {n}"),
    "ar_net_gone": ("не користи се {n}", "no longer used {n}"),
    "ar_net_renum": ("са другим бројем {n}", "renumbered {n}"),
    "an_higher": ("више", "higher"),
    "an_lower": ("мање", "lower"),
    "an_cmp_mun": ("у општини", "in the municipality"),
    "an_label_mun": ("општина", "municipality"),
    "an_cmp_all": ("на целим изборима", "in the election as a whole"),
    "an_label_all": ("укупно", "overall"),
    "json_link": ("Исти подаци као JSON", "The same data as JSON"),
    "print": ("Штампај страну за дан избора", "Print this page for election day"),
    "mun_feed": ("Прати ову општину: Atom фид са новим ознакама", "Follow this municipality: Atom feed of new flags"),
    "feed_title_mun": ("{name} · Изборни подаци", "{name} · Election data"),
    "station_details": ("Детаљи места", "Station details"),
    "mun_result_heading": ("Резултат у општини", "Result in the municipality"),
    "mun_result_note": ("Гласови и удео у важећим гласовима у општини, од највише ка најмање; поред је удео у целој земљи.", "Votes and share of valid votes in the municipality, most first; beside them, the national share."),
    "by_station_heading": ("По бирачким местима", "By polling station"),
    "by_station_note": ("Удео у важећим гласовима на сваком месту за три листе са највише гласова у општини; тамније поље је већи удео. Број гласова је у облачићу.", "Share of valid votes at each station for the three lists with the most votes in the municipality; a darker cell is a larger share. Hover for the number of votes."),
    "by_station_note_pres": ("Удео у важећим гласовима на сваком месту за три кандидата са највише гласова у општини; тамније поље је већи удео. Број гласова је у облачићу.", "Share of valid votes at each station for the three candidates with the most votes in the municipality; a darker cell is a larger share. Hover for the number of votes."),
    "others_col": ("Остали", "Others"),
    "all_votes_details": ("Сви гласови по бирачким местима, као бројеви", "All votes by polling station, as numbers"),
    "repeat_what_q": ("Шта је ово?", "What is this?"),
    "repeat_what_a": ("Свако бирачко место пратимо кроз свих {n} избора у архиви, од 2022. до данас, и бројимо на колико је имало бар једну ознаку.", "We follow every polling station through all {n} elections in the archive, from 2022 to now, and count in how many it had at least one flag."),
    "repeat_why_q": ("Зашто је важно?", "Why does it matter?"),
    "repeat_why_a": ("Једна ознака може бити случајност или грешка у уносу. Место које се истиче на више избора вреди пратити: послати посматрача на дан избора и пажљиво прочитати записник.", "One flag can be chance or a typing error. A station that stands out in several elections is worth watching: send an observer on election day and read the minutes carefully."),
    "repeat_how_q": ("Како се чита?", "How to read it?"),
    "repeat_how_a": ("Места су груписана по броју избора са ознаком, од највише ка најмање. Клик на место отвара његову страну са свим изборима.", "Stations are grouped by the number of elections they were flagged in, most first. Click a station to open its page with every election."),
    "repeat_notes_summary": ("Напомене о подацима", "Notes on the data"),
    "repeat_groups_note": ("Места су груписана по томе на колико избора су имала ознаку: прво она са ознаком на највише избора. Унутар групе прво иду места са јачим ознакама. Свака колона су једни избори.", "Stations are grouped by how many elections they were flagged in, most first. Within a group, stations with stronger flags come first. Each column is one election."),
    "repeat_strip_key": ("Кружићи у сваком реду су избори, с лева на десно:", "The marks in each row are the elections, left to right:"),
    "repeat_strip_legend": ("Симбол: ознака на тим изборима (прва по јачини). Празан кружић: гласало, без ознаке. Цртица: место није гласало на тим изборима.", "Symbol: flagged in that election (the strongest flag). Hollow circle: voted, not flagged. Dash: the station was not part of that election."),
    "repeat_group_title": ("Ознака на {k} избора", "Flagged in {k} elections"),
    "repeat_group_count": ("{n} места", "{n} stations"),
    "repeat_no_flag_short": ("без ознаке", "no flag"),
    "repeat_not_there_short": ("није гласало", "not part of it"),
    "repeat_table_legend": ("„Без ознаке”: место је гласало, а ниједна провера није дала ознаку. „Није гласало”: место није било део тих избора (покрајински избори су само у Војводини, београдски само у Београду). ≠: место је тада имало други број.", "“No flag”: the station voted and no check flagged it. “Not part of it”: the station was not part of that election (provincial elections are in Vojvodina only, the Belgrade ones in Belgrade only). ≠: the station had another number then."),
    "repeat_group_count_one": ("{n} место", "{n} station"),
    "repeat_group_title_one": ("Ознака на једним изборима", "Flagged in one election"),
    "minor_lists": ("Остале листе са мање од 1%: {n}", "Other lists under 1%: {n}"),
    "minor_candidates": ("Остали кандидати са мање од 1%: {n}", "Other candidates under 1%: {n}"),
    "theme_dark": ("Тамна тема", "Dark theme"),
    "home_h1_rest": ("бирачких места има ознаку на бар једним изборима", "polling stations are flagged in at least one election"),
    "home_deck": ("То је {share} од свих бирачких места у архиви ({total}). Њих {repeated} има ознаку на бар двоје избора.", "That is {share} of all polling stations in the archive ({total}). {repeated} of them are flagged in at least two elections."),
    "home_repeat_button": ("Историја места · {n}", "Station history · {n}"),
    "home_latest_button": ("За проверу: {title}", "To check: {title}"),
    "home_appears": ("Шта се појављује", "What comes up"),
    "home_appears_note": ("Бирачка места са том ознаком на бар једним изборима.", "Polling stations with that flag in at least one election."),
    "repeat_same_note_short": ("Бирачка места на којима се иста ознака појавила на бар двоје избора.", "Polling stations where the same flag came up in at least two elections."),
    "home_example": ("Пример из архиве", "An example from the archive"),
    "home_example_k": ("Ознака на {k} од {n} избора на којима је гласало", "Flagged in {k} of the {n} elections it took part in"),
    "home_col_election": ("Избори", "Election"),
    "home_col_date": ("Датум", "Date"),
    "home_col_share": ("Удео", "Share"),
    "theme_light": ("Светла тема", "Light theme"),
    "all_rounds_kicker": ("Сви избори у архиви ({n})", "All elections in the archive ({n})"),
    "check_big_all": ("од {total} бирачких места у архиви ({share}) има ознаку на бар једним изборима", "of {total} polling stations in the archive ({share}) are flagged in at least one election"),
    "repeat_home_line": ("Од њих {n} има ознаку на бар двоје избора.", "{n} of them are flagged in at least two elections."),
    "repeat_title": ("Историја места", "Station history"),
    "repeat_lede": ("Бирачка места кроз све изборе у архиви: где су бројеви били необични и када. Једна ознака може бити случајност; иста ознака на истом месту на више избора вреди посебно проверити.", "Polling stations across every election in the archive: where the numbers were unusual, and when. One flag can be chance; the same flag at the same station in several elections deserves a closer look."),
    "repeat_caveat_scope": ("Покрајински избори покривају само Војводину, а београдски само Београд, зато пише „к / n”: на колико од избора на којима је место гласало је имало ознаку.", "Provincial elections cover only Vojvodina and the Belgrade ones only Belgrade, so the table says “k / n”: flagged in k of the n elections the station took part in."),
    "repeat_caveat_areas": ("Бирачко место се кроз изборе прати по адреси, затим по називу, па по броју; када се адреса или назив јасно разликују, то је друго место. ≠ значи да је место тада имало други број. Избори 2022. немају називе места у табели РИК-а, па се за њих место прати по броју.", "A station is followed through the elections by address, then name, then number; when the address or name clearly differs, it is another place. ≠ means the station had another number then. RIK's 2022 table has no station names, so for 2022 a station is followed by number."),
    "repeat_caveat_score": ("Скор сабира тежине ознака, а сваки старији избори вреде 70% новијих. Исти скор групе посматрача користе да одлуче где да оду.", "The score adds up the flags' weights, each older election counting 70% of the next one. Observer groups use the same score to decide where to go."),
    "repeat_big": ("бирачких места има ознаку на бар двоје избора; још {once} само на једним", "polling stations are flagged in at least two elections; {once} more in only one"),
    "repeat_same_heading": ("Иста ознака на више избора", "The same flag in several elections"),
    "repeat_same_note": ("Број бирачких места на којима се иста ознака појавила на бар двоје избора. Клик приказује та места.", "Number of polling stations where the same flag came up in at least two elections. Click to list them."),
    "repeat_columns_note": ("Избора са ознаком: на колико од избора на којима је место гласало је имало бар једну ознаку. Иста ознака више пута: иста ознака на истом месту на двоје или више избора. Колоне десно: ознаке на сваким изборима.", "Elections flagged: in how many of the elections the station took part in it had at least one flag. Same flag again: the same flag at the same station in two or more elections. Columns on the right: the flags in each election."),
    "repeat_times": ("на {n} избора", "in {n} elections"),
    "repeat_none": ("различите ознаке", "different flags"),
    "repeat_stations_heading": ("Бирачка места", "Polling stations"),
    "repeat_min": ("Избора са ознаком", "Elections flagged"),
    "repeat_same_only": ("Само где је иста ознака више пута", "Only where the same flag came up more than once"),
    "repeat_k": ("Избора са ознаком", "Elections flagged"),
    "repeat_score": ("Скор", "Score"),
    "repeat_same": ("Иста ознака више пута", "Same flag again"),
    "repeat_no_flag": ("Гласало, без ознаке", "Voted, not flagged"),
    "repeat_not_there": ("Није гласало на тим изборима", "Not part of that election"),
    "repeat_renamed": ("Место је тада имало други број", "The station had another number then"),
    "repeat_legend": ("— гласало без ознаке · није гласало на тим изборима · ≠ други број места", "— voted, not flagged · · not part of that election · ≠ another station number"),
    "repeat_mun_heading": ("Општине", "Municipalities"),
    "repeat_mun_note": ("Општине у којима је удео бирачких места за проверу био бар двоструко већи од просека земље на већини избора на којима су гласале (бар двоје), уз бар 5 бирачких места. Подебљано: изнад тог прага.", "Municipalities whose share of stations to check was at least twice the national share in most of the elections they took part in (at least two), with at least 5 stations. Bold: above that line."),
    "repeat_mun_none": ("Нема таквих општина.", "No such municipality."),
    "repeat_above": ("Избора изнад", "Elections above"),
    "repeat_national": ("земља {share}", "national {share}"),
    "short_presidential": ("Председнички", "Presidential"),
    "short_parliamentary": ("Парламентарни", "Parliamentary"),
    "short_provincial": ("Покрајински", "Provincial"),
    "short_local": ("Локални", "Local"),
    "check_big_rest": ("од {total} бирачких места ({share}) има бар једну ознаку", "of {total} polling stations ({share}) have at least one flag"),
    "groups_explained": ("Шта значе боје и које провере постоје", "What the colours mean and which checks exist"),
    "sort_by": ("Редослед", "Order"),
    "what_to_check": ("Шта проверити", "What to check"),
    "sort_strength": ("Најјачи сигнал прво", "Strongest signal first"),
    "sort_place": ("По општини и броју места", "By municipality and station number"),
    "hint_ballots_over_signed": ("У записнику упореди број листића у кутији са бројем заокружених бирача у изводу и прочитај примедбе одбора.", "In the minutes, compare the ballots in the box with the voters marked in the register extract, and read the board's remarks."),
    "hint_sum_mismatch": ("Сабери гласове свих листа у записнику и упореди са бројем важећих листића. Ако се записник слаже, грешка је у уносу.", "Add up every list's votes in the minutes and compare with the valid ballots. If the minutes add up, the error is in data entry."),
    "hint_ballot_mismatch": ("Упореди број листића у кутији са збиром важећих и неважећих у записнику и прочитај примедбе.", "Compare the ballots in the box with valid plus invalid in the minutes, and read the remarks."),
    "hint_signed_over_ballots": ("Више заокружених бирача него листића у кутији. Упореди оба броја у записнику и прочитај примедбе чланова одбора.", "More voters marked than ballots in the box. Compare both numbers in the minutes and read the board members' remarks."),
    "hint_signed_over_registered": ("Гласало више бирача него што их је уписано. Упореди бројеве у записнику и прочитај примедбе.", "More voters than registered. Compare the numbers in the minutes and read the remarks."),
    "hint_full_turnout_typo": ("Гласали су баш сви уписани, што је најчешће грешка у уносу. Упореди записник са објављеним бројевима.", "Every registered voter voted, which is most often a data-entry error. Compare the minutes with the published numbers."),
    "hint_correction_still_odd": ("Исправка је објављена, а бројеви и даље нису у реду. Упореди решење о исправци са записником.", "A correction was published and the numbers still don't add up. Compare the correction ruling with the minutes."),
    "hint_changed": ("Бројеви су промењени после прве објаве. Погледај страну Измене и потражи решење о исправци.", "The numbers changed after first publication. See the Changes page and look for a correction ruling."),
    "hint_minutes_replaced": ("Записник је замењен или додат после прве објаве. Отвори обе верзије и упореди бројеве и примедбе.", "The minutes were replaced or added after first publication. Open both versions and compare the numbers and remarks."),
    "hint_correction_unapplied": ("Постоји решење о исправци, а бројеви се нису променили. Погледај шта решење мења.", "There is a correction ruling and the numbers haven't changed. See what the ruling changes."),
    "hint_invalid_spike": ("Много неважећих листића. Прочитај примедбе у записнику и да ли је одбор објаснио зашто.", "Many invalid ballots. Read the remarks in the minutes and whether the board explained why."),
    "hint_turnout_jump": ("Излазност је порасла много више него у остатку општине. Упореди број заокружених у изводу са листићима, прочитај примедбе и провери да ли се подручје бирачког места променило.", "Turnout rose far more than in the rest of the municipality. Compare voters marked in the extract with ballots, read the remarks and check whether the station's area changed."),
    "hint_turnout_drop": ("Излазност је пала много више него у остатку општине. Провери да ли су се подручје или адреса бирачког места променили.", "Turnout fell far more than in the rest of the municipality. Check whether the station's area or address changed."),
    "hint_near_unanimity": ("Скоро сви гласови за једну листу уз високу излазност. Прочитај примедбе и погледај које листе су имале контролоре и да ли је било посматрача.", "Nearly all votes for one contestant with high turnout. Read the remarks and see which lists had controllers and whether observers were present."),
    "hint_voting_annulled": ("Прочитај решење о поништавању и записник са поновљеног гласања; упореди бројеве са првим записником.", "Read the ruling and the minutes of the repeat vote; compare their numbers with the first minutes."),
    "hint_results_undetermined": ("Прочитај решење: зашто се резултати не могу утврдити и шта је комисија одлучила.", "Read the ruling: why the results can't be determined and what the commission decided."),
    "hint_observer_remarks": ("Прочитај примедбе у записнику о посматрачима и упореди их са записником бирачког одбора.", "Read the remarks in the observers' record and compare them with the polling board's minutes."),
    "hint_remark_filed": ("Отвори примедбу и види на шта се односи; упореди је са записником и записником о посматрачима.", "Open the remark and see what it is about; compare it with the minutes and the observers' record."),
    "hint_high_turnout": ("Веома висока излазност. Упореди број заокружених у изводу са бројем листића и прочитај примедбе.", "Very high turnout. Compare voters marked in the extract with the ballots and read the remarks."),
    "flagged_share": ("% места за проверу", "% of stations to check"),
    "check_count": ("Бирачких места са бар једном ознаком: {n}", "Polling stations with at least one flag: {n}"),
    "see_all_flags": ("Сва бирачка места за проверу", "All polling stations to check"),
    "group_paper": ("Бројеви у записнику се не слажу", "The minutes' numbers don't add up"),
    "group_change": ("Измене после објаве", "Changes after publication"),
    "group_unusual": ("Необични резултати", "Unusual results"),
    "group_records": ("Записано на бирачком месту", "Recorded at the station"),
    "group_records_note": ("Примедбе и решења која је РИК објавио уз записник. Шта у њима пише, види се тек у документу: ознака каже да документ постоји.",
                           "Remarks and rulings RIK published with the minutes. What they say is only in the document: the flag says it exists."),
    "group_paper_note": ("Најјачи сигнали: бројеви истог записника се међусобно не слажу.",
                         "Strongest signals: the numbers in the same minutes don't agree with each other."),
    "group_change_note": ("Архива показује да су се бројеви, записник или решење мењали после прве објаве.",
                          "The archive shows numbers, minutes or rulings changing after they were first published."),
    "group_unusual_note": ("Често сасвим законити, на пример када мањинска средина гласа као блок. Зато имају најмању тежину.",
                           "Often entirely legitimate, for example a minority community voting as a bloc. They carry the least weight."),
    "municipalities_heading": ("Општине", "Municipalities"),
    "municipality": ("Општина", "Municipality"),
    "district": ("Округ", "District"),
    "stations": ("Бирачких места", "Polling stations"),
    "flagged": ("За проверу", "To check"),
    "abroad": ("Иностранство", "Abroad"),
    "prisons": ("Заводи за извршење кривичних санкција", "Prisons"),
    "context_heading": ("Статистика за цео изборни круг", "Statistics for the whole round"),
    "context_note": ("Ови тестови показују да ли се бројеви понашају као што се очекује у великом броју бирачких места. Слаби су сигнали и сами ништа не доказују.",
                     "These tests show whether the numbers behave as expected across many polling stations. They are weak signals and prove nothing on their own."),
    "digits_heading": ("Последње цифре", "Last digits"),
    "digits_note": ("За бројеве гласова од 100 и више, свака последња цифра требало би да се јавља око 10% пута. p је вероватноћа овако неравномерне расподеле случајно.",
                    "In vote counts of 100 or more, each final digit should appear about 10% of the time. p is the chance of a spread this uneven happening by chance."),
    "round_heading": ("Округли проценти", "Round percentages"),
    "round_note": ("Бирачка места са 500 и више уписаних где излазност или удео пада на 0,05 поена од целог процента. Случајно би требало око 10%.",
                   "Polling stations with 500 or more registered voters where turnout or a share falls within 0.05 points of a whole percent. About 10% should by chance."),
    "corr_heading": ("Излазност и удео", "Turnout and share"),
    "corr_note": ("Корелација излазности и удела у важећим гласовима по бирачком месту, за места са 100 и више уписаних.",
                  "Correlation between turnout and share of valid votes across polling stations with 100 or more registered voters."),
    "hist_heading": ("Излазност по бирачким местима", "Turnout across polling stations"),
    "hist_note": ("Број бирачких места у Србији са 100 и више уписаних, по излазности у корацима од једног поена.",
                  "Polling stations in Serbia with 100 or more registered voters, by turnout in one-point steps."),
    "counts": ("Бројева", "Counts"),
    "measure": ("Мера", "Measure"),
    "share_of": ("Удео: {name}", "Share: {name}"),
    "correlation": ("Корелација", "Correlation"),
    "station_no": ("БМ", "No."),
    "station": ("Бирачко место", "Polling station"),
    "minutes": ("Записник", "Minutes"),
    "doc_minutes": ("Записник", "Minutes"),
    "doc_observers": ("Посматрачи", "Observers"),
    "doc_remark": ("Примедба", "Remark"),
    "doc_correction": ("Исправка", "Correction"),
    "doc_annulled": ("Поништење", "Annulment"),
    "doc_undetermined": ("Решење", "Ruling"),
    "doc_audit": ("Контрола по узорку", "Sample audit"),
    "doc_other": ("Документ", "Document"),
    "board_docs": ("Решења о бирачком одбору", "Decisions on the polling board"),
    "commission_heading": ("Документи изборне комисије", "Electoral commission documents"),
    "commission_note": ("Записници са седница, извештаји, решења, одлуке и обавештења општинске изборне комисије, како их објављује РИК, по дану објављивања. Наслови се не преносе: пишу их комисије и могу садржати имена.", "Minutes of the municipal electoral commission's sessions, reports, decisions, resolutions and notices, as RIK publishes them, by the day each was published. Titles aren't copied: the commissions write them, and they may contain names."),
    "commission_session": ("Записници са седница", "Minutes of sessions"),
    "commission_report": ("Извештаји", "Reports"),
    "commission_decision": ("Решења", "Decisions"),
    "commission_resolution": ("Одлуке", "Resolutions"),
    "commission_notice": ("Обавештења", "Notices"),
    "commission_other": ("Остало", "Other"),
    "doc_board_standing": ("стални састав", "standing members"),
    "doc_board_standing_change": ("измена сталног", "change to standing"),
    "doc_board_extended": ("проширени састав", "extended members"),
    "doc_board_extended_change": ("измена проширеног", "change to extended"),
    "doc_board_refused": ("одбијен предлог", "proposal refused"),
    "doc_board_other": ("решење", "decision"),
    "doc_repeat": ("поновно гласање", "repeat vote"),
    "doc_repeat_note": (" (поновно гласање)", " (repeat vote)"),
    "review_checked": (" (прочитано {date})", " (read {date})"),
    "review_none": ("Записник о посматрачима прочитан{date}: без примедби посматрача", "Observers' record read{date}: no observers' remarks"),
    "doc_observers_title": ("Записник о посматрачима: ко је посматрао рад бирачког одбора и њихове примедбе", "Observers' record: who observed the polling board, and their remarks"),
    "correction": ("Решење", "Ruling"),
    "notes": ("Белешке", "Notes"),
    "flags": ("Ознаке", "Flags"),
    "votes_by_list": ("Гласови по листама", "Votes by list"),
    "votes_by_candidate": ("Гласови по кандидатима", "Votes by candidate"),
    "not_counted": ("Није обрађено", "Not counted yet"),
    "back_round": ("Назад на изборе", "Back to the election"),
    # flags page
    "filter_municipality": ("Општина", "Municipality"),
    "filter_all": ("Све", "All"),
    "filter_type": ("Врста ознаке", "Flag type"),
    "filter_search": ("Претрага", "Search"),
    "filter_shown": ("Приказано: {n}", "Showing: {n}"),
    "first_flagged": ("Прво уочено", "First seen"),
    "no_flags": ("Нема ознака.", "No flags."),
    # changes
    "changes_heading": ("Измене после прве објаве", "Changes after first publication"),
    "changes_note": ("Свака вредност која се променила на бирачком месту које је већ имало резултате. Претходне верзије датотеке чувају се у историји репозиторијума.",
                     "Every value that changed at a polling station that already had results. Earlier versions of the file are kept in the repository's history."),
    "time": ("Време", "Time"),
    "field": ("Поље", "Field"),
    "before": ("Пре", "Before"),
    "now": ("Сада", "Now"),
    "no_changes": ("Нема измена у архиви.", "No changes in the archive."),
    "snapshots_heading": ("Верзије датотеке", "Versions of the file"),
    "field_list": ("Листа {n}", "List {n}"),
    "field_candidate": ("Кандидат {n}", "Candidate {n}"),
    "field_minutes": ("Записник", "Minutes"),
    "field_correction": ("Решење о исправци", "Correction ruling"),
    "field_name": ("Назив бирачког места", "Polling station name"),
    "field_removed": ("Бирачко место уклоњено", "Polling station removed"),
    # notes
    "note_label": ("Навод у медијима, није потврђено", "Media report, not confirmed"),
    "note_archive": ("архивирана копија", "archived copy"),
    # feed and mail
    "feed_title": ("Изборни подаци: нове ознаке за проверу", "Election data: new flags to check"),
    "feed_entry": ("{title}: нове ознаке ({n})", "{title}: new flags ({n})"),
    "feed_more": ("и још {n}", "and {n} more"),
    "mail_subject": ("Нове ознаке за проверу: {n}", "New flags to check: {n}"),
    "mail_final": ("Бројање завршено: {title}", "Count complete: {title}"),
    "mail_intro": ("Нове ознаке од последње поруке:", "New flags since the last message:"),
    "mail_footer": ("Ознака је питање, не закључак. Проверите записник пре објављивања.",
                    "A flag is a question, not a verdict. Check the minutes before publishing."),
    # pages
    "nav_round": ("Изборни круг", "Election round"),
    "rounds_flagged": ("Бирачких места за проверу: {n} од {total} ({share})", "Polling stations to check: {n} of {total} ({share})"),
    "how_heading": ("Како ради", "How it works"),
    "how_1": ("Сваког сата, а док бројање траје свака 3 минута, сајт преузима датотеку са резултатима са сајта РИК-а.",
              "Every hour, and every 3 minutes while a count is open, the site downloads the results file from RIK's website."),
    "how_2": ("Свака нова верзија се чува, па се види шта је РИК објавио и када, и шта се касније променило.",
              "Every new version is saved, so you can see what RIK published and when, and what changed later."),
    "how_3": ("Свако бирачко место пролази исте провере, ко год да су учесници: да ли се бројеви у записнику слажу, шта се мењало после објаве и шта је необично.",
              "Every polling station goes through the same checks, whoever the contestants are: whether the numbers in the minutes add up, what changed after publication, and what is unusual."),
    "how_4": ("Свака ознака води до записника који је објавио РИК, да бисте сами проверили.",
              "Every flag links to the minutes RIK published, so you can check for yourself."),
    "search_mun": ("Пронађи општину", "Find a municipality"),
    "marker_note_threshold": ("Танка линија у колони означава цензус.", "The thin line in the bar column marks the threshold."),
    "marker_note_half": ("Танка линија у колони означава половину гласалих.", "The thin line in the bar column marks half of those who voted."),
    "check_explain": ("Бирачка места са најјачим сигналима су прва.", "Polling stations with the strongest signals come first."),
    "rules_link": ("Како раде провере", "How the checks work"),
    "stations_heading": ("Бирачка места", "Polling stations"),
    "total": ("Укупно", "Total"),
    "file_history": ("Историја датотеке у репозиторијуму", "History of the file in the repository"),
    "minutes_old": ("ранији", "earlier"),
    "minutes_new": ("нови", "new"),
    "not_found": ("Ова страница не постоји.", "This page doesn't exist."),
    "go_home": ("Почетна страница", "Home page"),
    "about_checks": ("Провере", "The checks"),
    "about_rule": ("Правило", "Rule"),
    "about_weight": ("Тежина", "Weight"),
    "ctrl_heading": ("Контролори у бирачким одборима", "Controllers on polling boards"),
    "ctrl_note": ("Које листе су именовале члана бирачког одбора у проширеном саставу, према решењима изборних комисија која објављује РИК. То је стање пре изборног дана: ко је стварно био присутан пише у записнику. Решења су углавном скенирана и читају се аутоматски, па понеко може да недостаје или да буде погрешно прочитано.",
                  "Which lists appointed a member to the extended polling board, according to the commissions' decisions RIK publishes. This is the picture before election day: who actually attended is in the minutes. Most decisions are scans read automatically, so some may be missing or misread."),
    "ctrl_read": ("Бирачких места са прочитаним решењем: {n} од {total}", "Polling stations with a decision read: {n} of {total}"),
    "ctrl_members": ("Чланова", "Members"),
    "ctrl_deputies": ("Заменика", "Deputies"),
    "ctrl_total": ("Контролора укупно", "Controllers in total"),
    "ctrl_lists": ("Контролори: листе {lists}", "Controllers: lists {lists}"),
    "ctrl_deputy_only": ("само заменик: {lists}", "deputy only: {lists}"),
    "ctrl_none_named": ("Контролори: ниједна листа", "Controllers: no list"),
    "ctrl_unreadable": ("Контролори: решење није могло да се прочита аутоматски", "Controllers: the decision couldn't be read automatically"),
    "ctrl_unknown": ("Контролори: решење још није прочитано", "Controllers: no decision read yet"),
    "address": ("Адреса", "Address"),
    "register_heading": ("Промена броја уписаних по општинама", "Change in registered voters by municipality"),
    "register_note": ("У поређењу са претходним изборима исте врсте ({title}). У целој земљи: {national}. Приказане су општине са највећим одступањем; границе бирачких места се мењају, па се број уписаних пореди по општини, не по бирачком месту.",
                      "Compared with the previous election of the same kind ({title}). Nationally: {national}. Shown are the municipalities that differ most; polling station areas get redrawn, so registered voters are compared by municipality, not by station."),
    "before_reg": ("Тада", "Then"),
    "now_reg": ("Сада", "Now"),
    "change": ("Промена", "Change"),
    "vs_national": ("Одступање", "Difference"),
    "rebuilt_note": ("Ови резултати су сложени бирачко место по бирачко место из РИК-ове апликације за резултате, јер РИК за ове изборе више не нуди преузимање датотеке. Листићи у кутији нису посебан податак, па се узима збир важећих и неважећих.",
                     "These results were put together station by station from RIK's results app, because RIK no longer offers the file for this election. Ballots in the box aren't reported separately, so valid plus invalid is used."),
    "minority_unchecked": ("Статус мањинских листа за ове изборе још није унет према одлукама РИК-а, па број мандата може да одступа.",
                           "The minority status of lists in this election hasn't been entered from RIK's decisions yet, so seat numbers may be off."),
}

# Check names and how each flag's numbers read.
CHECK_NAMES: dict[str, tuple[str, str]] = {
    "ballots_over_signed": ("Више листића него потписа", "More ballots than signatures"),
    "sum_mismatch": ("Гласови се не сабирају у важеће листиће", "Votes don't add up to valid ballots"),
    "ballot_mismatch": ("Важећи и неважећи се не сабирају у листиће у кутији", "Valid and invalid don't add up to the ballots in the box"),
    "signed_over_ballots": ("Више потписа него листића", "More signatures than ballots"),
    "signed_over_registered": ("Више гласалих него уписаних", "More voters than registered"),
    "full_turnout_typo": ("Могућа грешка у уносу: гласали сви уписани", "Likely typing error: everyone registered voted"),
    "correction_still_odd": ("Исправка објављена, бројеви се и даље не слажу", "Correction published, numbers still don't add up"),
    "changed": ("Бројеви промењени после објаве", "Numbers changed after publication"),
    "minutes_replaced": ("Записник замењен или додат", "Minutes replaced or added"),
    "correction_unapplied": ("Исправка објављена, бројеви непромењени", "Correction published, numbers unchanged"),
    "invalid_spike": ("Много неважећих листића", "Invalid-ballot spike"),
    "turnout_jump": ("Скок излазности", "Turnout jump"),
    "turnout_drop": ("Пад излазности", "Turnout drop"),
    "near_unanimity": ("Скоро једногласно", "Near-unanimity"),
    "high_turnout": ("Веома висока излазност", "Very high turnout"),
    "voting_annulled": ("Гласање поништено", "Voting annulled"),
    "results_undetermined": ("Резултати се не могу утврдити", "Results can't be determined"),
    "remark_filed": ("Примедба уз записник", "Remark filed with the minutes"),
    "observer_remarks": ("Примедбе посматрача", "Observers' remarks"),
}

CHECK_RULES: dict[str, tuple[str, str]] = {
    "ballots_over_signed": ("Листића у кутији има више него бирача који су се потписали у бирачки списак. Закон ово сматра озбиљном грешком.",
                            "More ballots in the box than voters who signed the voter list. The law treats this as a serious error."),
    "sum_mismatch": ("Збир гласова свих кандидата или листа није једнак броју важећих листића.",
                     "The votes of all contestants don't add up to the valid ballots."),
    "ballot_mismatch": ("Важећи плус неважећи листићи нису једнаки броју листића у кутији.",
                        "Valid plus invalid ballots don't equal the ballots in the box."),
    "signed_over_ballots": ("Потписа у бирачком списку има бар {signed_over_ballots_min} више него листића у кутији.",
                            "At least {signed_over_ballots_min} more signatures in the voter list than ballots in the box."),
    "signed_over_registered": ("Гласалих има више него уписаних бирача.", "More voters than registered voters."),
    "full_turnout_typo": ("Број гласалих тачно је једнак броју уписаних, а медијана излазности у општини је испод {typo_median_below_pct}.",
                          "Voters exactly equal registered voters, while the municipality's median turnout is below {typo_median_below_pct}."),
    "correction_still_odd": ("РИК је објавио решење о исправци записника, а бројеви и даље не пролазе аритметичку проверу.",
                             "RIK published a ruling correcting the minutes, but the numbers still fail an arithmetic check."),
    "changed": ("Неки број на бирачком месту разликује се од прве објављене вредности у архиви.",
                "A number at the station differs from its first published value in the archive."),
    "minutes_replaced": ("Веза ка записнику се променила или је додат нови записник, на пример са поновљеног гласања. Веза носи време отпремања, па се свака промена види.",
                         "The link to the minutes changed or another minutes document was added, for example from a repeat vote. The link carries an upload stamp, so every change shows."),
    "correction_unapplied": ("Решење о исправци појавило се после прве објаве, а ниједан број се од тада није променио.",
                             "A correction ruling appeared after first publication, and no number has changed since."),
    "invalid_spike": ("Бар {invalid_abs_share_pct} неважећих уз бар {invalid_abs_min_voted} гласалих, или бар {invalid_rel_factor}× медијане на истој адреси односно у општини.",
                      "At least {invalid_abs_share_pct} invalid with at least {invalid_abs_min_voted} voters, or at least {invalid_rel_factor}× the median at the same address or in the municipality."),
    "turnout_jump": ("Излазност на истом бирачком месту порасла је од претходних избора за бар {turnout_jump_pts} поена више од медијане осталих бирачких места у општини, уз бар {jump_min_registered} уписаних оба пута. Исто место се прати по адреси, називу и броју, па се преномеровано место пореди само са собом.",
                     "Turnout at the same polling station rose since the previous election by at least {turnout_jump_pts} points more than the median at the municipality's other stations, with at least {jump_min_registered} registered both times. The same place is followed by address, name and number, so a renumbered station is compared with itself."),
    "turnout_drop": ("Излазност на истом бирачком месту пала је од претходних избора за бар {turnout_jump_pts} поена више од медијане осталих бирачких места у општини, уз бар {jump_min_registered} уписаних оба пута. Чешће него скок долази од пресељења бирача или нових граница бирачких места.",
                     "Turnout at the same polling station fell since the previous election by at least {turnout_jump_pts} points more than the median at the municipality's other stations, with at least {jump_min_registered} registered both times. More often than a jump, this comes from voters moving or redrawn station areas."),
    "near_unanimity": ("Излазност бар {high_turnout_pct} и један кандидат или листа са бар {near_share_pct} важећих гласова, уз бар {min_registered} уписаних.",
                       "Turnout at least {high_turnout_pct} and one contestant with at least {near_share_pct} of valid votes, with at least {min_registered} registered."),
    "high_turnout": ("Излазност бар {high_turnout_pct}, уз бар {min_registered} уписаних.",
                     "Turnout at least {high_turnout_pct}, with at least {min_registered} registered."),
    "voting_annulled": ("Уз записник је објављено решење о поништавању гласања на бирачком месту (образац РГ-9); гласање се понавља.",
                        "A ruling annulling the vote at the station (form RG-9) was published with the minutes; the vote is repeated."),
    "results_undetermined": ("Уз записник је објављено решење да се на бирачком месту не могу утврдити резултати гласања (образац РГ-8).",
                             "A ruling that the station's results can't be determined (form RG-8) was published with the minutes."),
    "remark_filed": ("Уз записник је објављена посебна примедба на рад бирачког одбора. Ко ју је поднео и шта у њој пише, види се у документу.",
                     "A separate remark on the polling board's work was published with the minutes. Who filed it and what it says is in the document."),
    "observer_remarks": ("Човек је прочитао записник о посматрачима (образац РГ-11) и у њему нашао примедбе посматрача на поступак гласања. Кратак опис не именује никога.",
                         "A person read the observers' record (form RG-11) and found observers' remarks on how the vote was run in it. The short summary names no one."),
}


def t(key: str, loc: str, **kw) -> str:
    sr, en = S[key]
    text = en if loc == "en" else sr
    return text.format(**kw) if kw else text


def check_name(code: str, loc: str) -> str:
    sr, en = CHECK_NAMES[code]
    return en if loc == "en" else sr


def kind_name(kind: str, loc: str) -> str:
    return t(f"kind_{kind}" if f"kind_{kind}" in S else "kind_unknown", loc)


CYR_ORDER = "абвгдђежзијклљмнњопрстћуфхцчџш"
LAT_ORDER = ["a", "b", "c", "č", "ć", "d", "dž", "đ", "e", "f", "g", "h", "i", "j", "k", "l", "lj", "m", "n", "nj",
             "o", "p", "r", "s", "š", "t", "u", "v", "z", "ž"]


def collate(text: str, loc: str) -> tuple:
    """A sort key in Serbian alphabetical order: the Cyrillic alphabet's on Cyrillic pages, the Latin one (lj, nj
    and dž are letters of their own) on the others. Anything that isn't a letter sorts before the letters."""
    s = text.lower()
    if loc == "cyr":
        return tuple((1, CYR_ORDER.index(ch)) if ch in CYR_ORDER else (0, ord(ch)) for ch in s)
    s = latin(s)
    out, i = [], 0
    while i < len(s):
        two = s[i:i + 2]
        if two in ("lj", "nj", "dž"):
            out.append((1, LAT_ORDER.index(two)))
            i += 2
            continue
        out.append((1, LAT_ORDER.index(s[i])) if s[i] in LAT_ORDER else (0, ord(s[i])))
        i += 1
    return tuple(out)


# --- numbers and times ----------------------------------------------------------------------

def fmt_int(n: int | None, loc: str) -> str:
    if n is None:
        return "—"
    s = f"{n:,}"
    return s if loc == "en" else s.replace(",", ".")


def fmt_num(x: float | None, loc: str, digits: int = 1) -> str:
    if x is None:
        return "—"
    if round(x, digits) == 0:
        x = 0.0  # no "-0.00"
    s = f"{x:,.{digits}f}"
    if loc == "en":
        return s
    return s.replace(",", "\0").replace(".", ",").replace("\0", ".")


def fmt_pct(x: float | None, loc: str, digits: int = 1) -> str:
    if x is None:
        return "—"
    return fmt_num(100 * x, loc, digits) + "%"


def fmt_signed(n: int, loc: str) -> str:
    return ("+" if n > 0 else "−" if n < 0 else "") + fmt_int(abs(n), loc)


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        d = datetime.fromisoformat(value)
    except ValueError:
        try:
            d = datetime.strptime(value, "%d.%m.%Y %H:%M:%S").replace(tzinfo=BELGRADE)
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=BELGRADE)
    return d


MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def fmt_time(value, loc: str) -> str:
    d = value if isinstance(value, datetime) else parse_time(value)
    if d is None:
        return "—"
    d = d.astimezone(BELGRADE)
    if loc == "en":
        return f"{d.day} {MONTHS_EN[d.month - 1]} {d.year}, {d:%H:%M}"
    return f"{d.day}.{d.month}.{d.year}. {d:%H:%M}"


def fmt_date(iso: str | None, loc: str) -> str:
    """A day (YYYY-MM-DD) as 25.10.2026. or 25 Oct 2026; anything else as it is."""
    if not iso:
        return ""
    try:
        y, m, d = (int(x) for x in iso[:10].split("-"))
    except ValueError:
        return iso
    return f"{d} {MONTHS_EN[m - 1]} {y}" if loc == "en" else f"{d}.{m}.{y}."


def rule_values(rules: dict, loc: str) -> dict:
    """The check thresholds, formatted for the rule texts."""
    out = dict(rules)
    for k in ("typo_median_below", "high_turnout", "near_share", "invalid_abs_share"):
        out[f"{k}_pct"] = fmt_pct(rules[k], loc, 0)
    out["turnout_jump_pts"] = fmt_num(100 * rules["turnout_jump"], loc, 0)
    out["invalid_rel_factor"] = fmt_num(rules["invalid_rel_factor"], loc, 0)
    return out


def check_rule(code: str, loc: str, rules: dict) -> str:
    sr, en = CHECK_RULES[code]
    return (en if loc == "en" else sr).format(**rule_values(rules, loc))
