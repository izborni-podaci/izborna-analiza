"""Observers' records: reviews by a person, and the OCR score that orders what to read."""

import shutil

import pytest

from izbori import observers
from izbori.checks import review_flags
from izbori.describe import describe
from izbori.observers import Word, blocks, ink, load_reviews, score_pages


def test_reviews_become_flags(tmp_path):
    (tmp_path / observers.REVIEWS).write_text(
        "municipality_code,station,remarks,summary_sr,summary_en,checked\n"
        "70092,1,да,Бирачи гласали без личне карте,Voters voted without an ID card,2026-11-04\n"
        "70092,2,ne,,,2026-11-04\n"
        "70092,3,можда,,,\n", encoding="utf-8")  # an unclear answer is skipped
    reviews = load_reviews(tmp_path)
    assert set(reviews) == {"70092/1", "70092/2"} and not reviews["70092/2"].remarks
    flags = review_flags(reviews)
    assert [(f.station, f.code) for f in flags] == [("70092/1", "observer_remarks")]
    assert describe(flags[0], "en") == ("Observers wrote remarks in the observers' record (read 4 Nov 2026): "
                                        "Voters voted without an ID card")
    assert describe(flags[0], "cyr").endswith(" (прочитано 4.11.2026.): Бирачи гласали без личне карте")
    assert load_reviews(tmp_path / "missing") == {}


def page(written: bool, w: int = 400, h: int = 600) -> tuple[int, int, bytes, list[Word]]:
    """A form page: the "су следеће:" line at y 40, a printed rule at y 100, "(примедбе уписује" at y 160."""
    img = bytearray([255]) * (w * h)
    for x in range(20, 380):  # the printed rule
        img[100 * w + x] = 0
        img[101 * w + x] = 0
    if written:  # handwriting on the line
        for y in range(80, 98):
            for x in range(40, 300, 3):
                img[y * w + x] = 60
    words = [Word("ПРИМЕДБЕ", 90, 20, 40, 120, 15, ("1", "1", "1", "1")),
             Word("следеће:", 90, 300, 40, 80, 15, ("1", "1", "1", "1")),
             Word("(примедбе", 90, 20, 160, 100, 15, ("1", "1", "2", "1")),
             Word("уписује", 90, 130, 160, 80, 15, ("1", "1", "2", "1"))]
    return w, h, bytes(img), words


def test_score_counts_ink_in_the_remark_lines_only():
    w, h, img, words = page(False)
    found = blocks(words, w, h)
    assert len(found) == 1 and found[0][2] > 55 and found[0][3] < 160  # between the two printed lines
    assert ink(img, w, *found[0][:4])[0] == 0  # the printed rule doesn't count
    blank, written = score_pages([page(False)]), score_pages([page(True)])
    assert blank["ok"] and blank["score"] == 0 and written["score"] > 3
    assert score_pages([(w, h, img, [])]) == {"ok": False, "pages": 1, "blocks": 0, "score": None}


def test_read_pgm(tmp_path):
    p = tmp_path / "x.pgm"
    p.write_bytes(b"P5\n# a comment\n3 2\n255\n" + bytes([0, 128, 255, 255, 128, 0]))
    assert observers.read_pgm(p) == (3, 2, bytes([0, 128, 255, 255, 128, 0]))


@pytest.mark.skipif(not shutil.which("tesseract") or not shutil.which("pdftoppm"), reason="needs tesseract")
def test_read_pdf_without_remark_lines_is_not_scored():
    pytest.importorskip("PIL")
    import io

    from PIL import Image
    buf = io.BytesIO()
    Image.new("L", (800, 600), 255).save(buf, format="PDF", resolution=100)
    assert observers.read_pdf(buf.getvalue(), lang="eng")["ok"] is False


def test_header_read_as_a_remark_line_opens_no_area():
    """OCR may read the header's "следећи представници" as "следеће"; the end line closes the nearest start above."""
    w, h = 400, 600
    line = lambda n: ("1", "1", str(n), "1")  # noqa: E731
    words = [Word("следеће", 90, 200, 20, 80, 15, line(1)),                       # the header, misread
             Word("испред", 90, 20, 60, 60, 15, line(2)), Word("часова.", 90, 100, 60, 60, 15, line(2)),
             Word("ПРИМЕДБЕ", 90, 20, 100, 120, 15, line(3)), Word("следеће:", 90, 300, 100, 80, 15, line(3)),
             Word("(примедбе", 90, 20, 200, 100, 15, line(4)), Word("уписује", 90, 130, 200, 80, 15, line(4))]
    found = blocks(words, w, h)
    assert len(found) == 1 and found[0][2] > 110 and found[0][3] < 200


def test_landscape_page_is_read_column_by_column():
    """On a landscape record OCR joins a line of the left column with the line beside it in the right one: the
    areas still stay in their own column, and a handwritten line beside a remark line is in none."""
    w, h = 3300, 2330
    line = lambda n: ("1", "1", str(n), "1")  # noqa: E731
    words = [
        Word("НА", 96, 336, 321, 60, 40, line(1)), Word("СПРОВОЂЕЊУ", 96, 420, 321, 300, 40, line(1)),
        Word("ПРИМЕДБЕ", 92, 1863, 321, 200, 40, line(1)), Word("следеће:", 96, 2700, 321, 124, 40, line(1)),
        Word("Александровац", 40, 600, 487, 500, 80, line(2)),  # handwritten, in the left column
        Word("(примедбе", 96, 1863, 549, 150, 26, line(3)), Word("уписује", 96, 2030, 549, 120, 26, line(3)),
        Word("прилогу,", 96, 3000, 549, 130, 26, line(3)),
        Word("ПРИМЕДБЕ", 92, 196, 910, 200, 31, line(4)), Word("следеће:", 96, 1050, 910, 126, 31, line(4)),
        Word("ПРИМЕДБЕ", 92, 1863, 910, 200, 31, line(4)), Word("следеће:", 96, 2700, 910, 124, 31, line(4)),
        Word("(примедбе", 96, 214, 1138, 150, 28, line(5)), Word("уписује", 96, 380, 1138, 120, 28, line(5)),
        Word("прилогу,", 96, 1350, 1138, 130, 28, line(5)), Word("(примедбе", 96, 1863, 1138, 150, 28, line(5)),
        Word("уписује", 96, 2030, 1138, 120, 28, line(5)), Word("прилогу,", 96, 3000, 1138, 130, 28, line(5)),
        Word("ПРИМЕДБЕ", 92, 194, 1500, 200, 27, line(6)), Word("следеће:", 95, 1050, 1500, 126, 27, line(6)),
        Word("(примедбе", 96, 212, 1728, 150, 24, line(7)), Word("уписује", 96, 380, 1728, 120, 24, line(7)),
        Word("прилогу,", 96, 1350, 1728, 130, 24, line(7)),
    ]
    found = blocks(words, w, h)
    assert [(x0 < w / 2 < x1, y0 // 10, y1 // 10) for x0, x1, y0, y1, _ in found] == [
        (False, 94, 113), (False, 153, 172), (False, 36, 54), (False, 94, 113)]
    assert [x0 < w / 2 for x0, *_ in found] == [True, True, False, False]
    assert all(not inside for *_, inside in found)


def test_merge_a_filled_in_review_list(tmp_path):
    """Rows of the review list with a yes or no go into observer_reviews.csv, one per station; the rest stay out."""
    (tmp_path / observers.REVIEWS).write_text(
        "municipality_code,station,remarks,summary_sr,summary_en,checked\n"
        "70017,50,ne,,,2026-11-01\n33000,52,da,Старо,Old,2026-11-01\n", encoding="utf-8")
    filled = tmp_path / "observers-review.csv"
    filled.write_text(
        "score,municipality,station_name,observers_record,other,municipality_code,station,remarks,summary_sr,"
        "summary_en,checked\n"
        "11.6,Inostranstvo,X,https://rik.test/a.pdf,,33000,52,da,Десетак бирача враћено јер нису били на списку,"
        "About ten voters turned away as they were not on the list,\n"
        "10.9,Aranđelovac,Y,https://rik.test/b.pdf,,70033,7,ne,,,2026-11-02\n"
        "9.0,Aranđelovac,Z,https://rik.test/c.pdf,,70033,8,,,,\n"
        "8.0,Aranđelovac,W,https://rik.test/d.pdf,,70033,9,možda,,,\n", encoding="utf-8")
    assert observers.merge_reviews(tmp_path, filled, "2026-11-03") == (1, 1)
    reviews = load_reviews(tmp_path)
    assert sorted(reviews) == ["33000/52", "70017/50", "70033/7"]
    assert reviews["33000/52"].remarks and reviews["33000/52"].checked == "2026-11-03"  # summary rewritten today
    assert reviews["33000/52"].summary("en") == "About ten voters turned away as they were not on the list"
    assert not reviews["70033/7"].remarks and reviews["70033/7"].checked == "2026-11-02"
    assert observers.merge_reviews(tmp_path, filled, "2026-11-04") == (0, 0)  # the same list again changes nothing


def test_merge_a_list_saved_by_a_spreadsheet(tmp_path):
    """Excel in a Serbian locale saves with ; and a byte order mark, and writes dates as 3.11.2026."""
    filled = tmp_path / "observers-review.csv"
    filled.write_bytes("﻿score;municipality;station_name;observers_record;other;municipality_code;station;remarks;"
                       "summary_sr;summary_en;checked\r\n"
                       "15,4;Inostranstvo;X;https://rik.test/a.pdf;;33000;55;Da;\"Примедба у два\nреда\";;3.11.2026.\r\n"
                       .encode("utf-8"))
    assert observers.merge_reviews(tmp_path, filled, "2026-11-04") == (1, 0)
    review = load_reviews(tmp_path)["33000/55"]
    assert review.remarks and review.checked == "2026-11-03" and review.summary_sr == "Примедба у два\nреда"
    from izbori.i18n import fmt_date
    assert (fmt_date(review.checked, "cyr"), fmt_date(review.checked, "en"), fmt_date("лане", "cyr")) == (
        "3.11.2026.", "3 Nov 2026", "лане")
