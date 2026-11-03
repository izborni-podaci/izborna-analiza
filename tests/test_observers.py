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
    assert describe(flags[0], "en") == ("Observers wrote remarks in the observers' record (read 2026-11-04): "
                                        "Voters voted without an ID card")
    assert describe(flags[0], "cyr").endswith(": Бирачи гласали без личне карте")
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
