"""The weekly look at the municipalities' sites: which links are kept, which pages followed; nothing of a
document's text or title is kept."""
from izbori import watch


def test_kind_of_links():
    assert watch.kind_of("Одлука о одређивању бирачких места за изборе 25.10.2026 odluka.pdf") == "stations"
    assert watch.kind_of("Rešenje o utvrđivanju biračkih mesta") == "stations"
    assert watch.kind_of("Решење о именовању чланова бирачких одбора у сталном саставу БМ 3") == "boards"
    assert watch.kind_of("Пословник Општинске изборне комисије") == "commission"
    assert watch.kind_of("Јавни позив за легализацију објеката") is None
    assert watch.kind_of("Бирачка места – обавештење") is None  # about stations but no act


def test_crawl_follows_election_pages_and_keeps_documents(tmp_path):
    pages = {
        "https://primer.rs/": '<a href="/izbori-2026/">Избори 2026</a> <a href="/vesti/">Вести</a> '
                              '<a href="https://drugi.rs/odluka-biracka-mesta.pdf">Одлука о одређивању бирачких места</a>',
        "https://primer.rs/izbori-2026/": '<a href="/files/Odluka%20o%20odredjivanju%20birackih%20mesta.pdf">Одлука</a> '
                                          '<a href="/files/resenje-bo-bm-12.pdf">Решење о именовању бирачког одбора БМ 12</a> '
                                          '<a href="/files/budzet.pdf">Буџет</a>',
        "https://primer.rs/vesti/": '<a href="/files/resenje-bo-bm-13.pdf">Решење о именовању бирачког одбора БМ 13</a>',
    }
    asked = []

    def fetcher(url):
        asked.append(url)
        if url.startswith("https://primer.rs/?s="):
            return '<a href="/files/odluka-bm-2023.docx">Одлука о бирачким местима 2023</a>'
        return pages.get(url, "")

    found = watch.crawl("primer.rs", fetcher=fetcher, sleep=lambda s: None)
    assert found == {"https://primer.rs/files/Odluka%20o%20odredjivanju%20birackih%20mesta.pdf": "stations",
                     "https://primer.rs/files/resenje-bo-bm-12.pdf": "boards",
                     "https://primer.rs/files/odluka-bm-2023.docx": "stations"}  # another site's file and the news page are not followed
    assert "https://primer.rs/vesti/" not in asked and "https://primer.rs/izbori-2026/" in asked
    (tmp_path / "municipal_sites.csv").write_text("municipality_code,name,domain,note\n70017,Пример,primer.rs,\n70025,Други,,webmail\n",
                                                 encoding="utf-8")
    logged = []
    assert watch.run(tmp_path, "2026-11-08", logged.append, fetcher, lambda s: None) == 3
    store = watch.load_store(tmp_path)
    assert all(set(v) == {"m", "k", "seen"} for v in store["docs"].values())  # no titles, no text
    assert any("candidate for station_lists.csv" in m for m in logged)
    assert watch.run(tmp_path, "2026-11-09", logged.append, fetcher, lambda s: None) == 0  # nothing new the next time
