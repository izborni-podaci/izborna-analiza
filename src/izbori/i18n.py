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
    "nav_guide": ("Водич за посматраче", "Observer guide"),
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
    "search_flagged": ("ознака на {k} од {n} избора", "flagged in {k} of {n} elections"),
    "search_clean": ("без ознаке ни на једним изборима", "never flagged"),
    "intents_heading": ("Шта можете овде", "What you can do here"),
    "intent1_kicker": ("Последњи избори · {title}", "Latest election · {title}"),
    "intent1_title": ("Шта је необично", "What looks unusual"),
    "intent1_body": ("{n} од {total} бирачких места има бар једну ознаку.", "{n} of {total} polling stations have at least one flag."),
    "intent1_cta": ("Листа за проверу", "The list to check"),
    "intent2_kicker": ("Сви избори у архиви", "All elections in the archive"),
    "intent2_title": ("Необично више пута", "Unusual more than once"),
    "intent2_body": ("Иста бирачка места на којима су бројеви били необични на двоје или више избора, а не само једном. Таквих је {n}.", "The same polling stations whose numbers were unusual in two or more elections, not just once. There are {n}."),
    "intent3_kicker": ("За посматраче", "For observers"),
    "intent3_title": ("Пре изборног дана", "Before election day"),
    "intent3_body": ("Шта пратити на бирачком месту, шта забележити и како користити листу за проверу.", "What to watch at the polling station, what to write down and how to use the list to check."),
    "intent3_cta": ("Водич за посматраче", "Observer guide"),
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
    "repeat_caveat_areas": ("Бирачко место се препознаје по општини и броју. Подручја и адресе се између избора мењају: ≠ значи да се назив места тада очигледно разликовао од најновијег. Избори 2022. немају називе места у табели РИК-а.", "A station is recognised by municipality and number. Areas and addresses change between elections: ≠ means the station's name then clearly differed from its newest one. RIK's 2022 table has no station names."),
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
    "repeat_renamed": ("Назив места се разликује од најновијег", "The station's name differs from its newest one"),
    "repeat_legend": ("— гласало без ознаке · није гласало на тим изборима · ≠ други назив места", "— voted, not flagged · · not part of that election · ≠ a different station name"),
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
    "hint_high_turnout": ("Веома висока излазност. Упореди број заокружених у изводу са бројем листића и прочитај примедбе.", "Very high turnout. Compare voters marked in the extract with the ballots and read the remarks."),
    "flagged_share": ("% места за проверу", "% of stations to check"),
    "check_count": ("Бирачких места са бар једном ознаком: {n}", "Polling stations with at least one flag: {n}"),
    "see_all_flags": ("Сва бирачка места за проверу", "All polling stations to check"),
    "group_paper": ("Бројеви у записнику се не слажу", "The minutes' numbers don't add up"),
    "group_change": ("Измене после објаве", "Changes after publication"),
    "group_unusual": ("Необични резултати", "Unusual results"),
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
    "turnout_jump": ("Излазност на истом бирачком месту порасла је од претходних избора за бар {turnout_jump_pts} поена више од медијане осталих бирачких места у општини, уз бар {jump_min_registered} уписаних оба пута. Места чији се назив очигледно променио се прескачу.",
                     "Turnout at the same polling station rose since the previous election by at least {turnout_jump_pts} points more than the median at the municipality's other stations, with at least {jump_min_registered} registered both times. Stations whose name clearly changed are skipped."),
    "turnout_drop": ("Излазност на истом бирачком месту пала је од претходних избора за бар {turnout_jump_pts} поена више од медијане осталих бирачких места у општини, уз бар {jump_min_registered} уписаних оба пута. Чешће него скок долази од пресељења бирача или нових граница бирачких места.",
                     "Turnout at the same polling station fell since the previous election by at least {turnout_jump_pts} points more than the median at the municipality's other stations, with at least {jump_min_registered} registered both times. More often than a jump, this comes from voters moving or redrawn station areas."),
    "near_unanimity": ("Излазност бар {high_turnout_pct} и један кандидат или листа са бар {near_share_pct} важећих гласова, уз бар {min_registered} уписаних.",
                       "Turnout at least {high_turnout_pct} and one contestant with at least {near_share_pct} of valid votes, with at least {min_registered} registered."),
    "high_turnout": ("Излазност бар {high_turnout_pct}, уз бар {min_registered} уписаних.",
                     "Turnout at least {high_turnout_pct}, with at least {min_registered} registered."),
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
