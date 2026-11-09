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
    assert watch.kind_of("Извештај о укупним резултатима избора за одборнике Скупштине града") == "results"
    assert watch.kind_of("Збирна изборна листа кандидата за одборнике") == "lists"
    assert watch.kind_of("Резултати такмичења") is None


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


def test_crawl_reads_wordpress_uploads_and_sitemaps():
    pages = {
        "https://primer.rs/": "<p>почетна</p>",
        "https://primer.rs/sitemap.xml": "<sitemapindex><sitemap><loc>https://primer.rs/page-sitemap.xml</loc></sitemap></sitemapindex>",
        "https://primer.rs/page-sitemap.xml": "<urlset><url><loc>https://primer.rs/izborna-komisija/</loc></url>"
                                              "<url><loc>https://primer.rs/files/odluka-o-odredjivanju-birackih-mesta.pdf</loc></url>"
                                              "<url><loc>https://primer.rs/turizam/</loc></url></urlset>",
        "https://primer.rs/izborna-komisija/": '<a href="/files/resenje-bo-bm-4.pdf">Решење о именовању бирачког одбора</a>',
    }
    asked = []

    def fetcher(url):
        asked.append(url)
        if "wp-json/wp/v2/media" in url and "search=%D0%B1%D0%B8%D1%80%D0%B0%D1%87%D0%BA" in url:
            return ('[{"source_url": "https://primer.rs/wp-content/uploads/2026/09/BM.pdf",'
                    ' "title": {"rendered": "Решење о утврђивању бирачких места"}},'
                    ' {"source_url": "https://drugi.rs/x.pdf", "title": {"rendered": "Решење о утврђивању бирачких места"}}]')
        if "wp-json" in url:
            return "[]"
        if url in pages:
            return pages[url]
        raise OSError("404")

    found = watch.crawl("primer.rs", fetcher=fetcher, sleep=lambda s: None)
    assert found == {"https://primer.rs/wp-content/uploads/2026/09/BM.pdf": "stations",
                     "https://primer.rs/files/odluka-o-odredjivanju-birackih-mesta.pdf": "stations",
                     "https://primer.rs/files/resenje-bo-bm-4.pdf": "boards"}
    assert "https://primer.rs/turizam/" not in asked


def test_why_says_what_failed():
    import urllib.error
    assert watch.why(urllib.error.URLError("timed out")) == "URLError timed out"
    assert watch.why(urllib.error.HTTPError("u", 403, "Forbidden", {}, None)).startswith("HTTPError Forbidden")


def test_other_spellings_of_a_site(tmp_path):
    assert watch.variants("valjevo.org.rs") == ["valjevo.rs", "valjevo.ls.gov.rs", "valjevo.gov.rs"]
    assert watch.variants("bojnik.ls.gov.rs")[0] == "bojnik.rs"
    assert watch.variants("grad.zrenjanin.rs") == []
    (tmp_path / "municipal_sites.csv").write_text(
        "municipality_code,name,domain,note\n70360,Ваљево,valjevo.org.rs,rik-adresar\n", encoding="utf-8")

    def fetcher(url):
        if "valjevo.rs" not in url:
            raise OSError("down")
        return '<a href="/izbori/odluka-o-odredjivanju-birackih-mesta.pdf">Одлука о одређивању бирачких места</a>'
    logged = []
    assert watch.run(tmp_path, "2026-11-09", logged.append, fetcher, lambda s: None) == 1
    sites = watch.load_sites(tmp_path / "municipal_sites.csv")
    assert sites[0]["domain"] == "valjevo.rs" and "was valjevo.org.rs" in sites[0]["note"]
    assert any("valjevo.org.rs doesn't answer, valjevo.rs does" in m for m in logged)


def test_others_only_skips_the_domain_itself(tmp_path):
    (tmp_path / "municipal_sites.csv").write_text(
        "municipality_code,name,domain,note\n70360,Ваљево,valjevo.org.rs,\n70017,Пример,primer.rs,\n", encoding="utf-8")
    asked = []

    def fetcher(url):
        asked.append(url)
        raise OSError("down")
    logged = []
    watch.run(tmp_path, "2026-11-09", logged.append, fetcher, lambda s: None, only={"70360"}, others_only=True)
    assert not any("valjevo.org.rs" in u for u in asked) and any("valjevo.rs" in u for u in asked)
    assert not any("primer" in u for u in asked)
    assert any("no other spelling of valjevo.org.rs answers" in m for m in logged)


def test_a_broken_link_or_a_crash_does_not_stop_the_run(tmp_path):
    assert watch.links_of('<a href="http://[broken/x.pdf">x</a><a href="/a.pdf">a</a>', "https://p.rs/") == [("https://p.rs/a.pdf", "a")]
    (tmp_path / "municipal_sites.csv").write_text(
        "municipality_code,name,domain,note\n70017,Први,prvi.rs,\n70025,Други,drugi.rs,\n", encoding="utf-8")

    def fetcher(url):
        if "prvi" in url:
            return '<a href="/izbori/">Избори</a>' if url.endswith("prvi.rs/") else 1 / 0
        return '<a href="/o.pdf">Одлука о одређивању бирачких места</a>'
    logged = []
    assert watch.run(tmp_path, "2026-11-09", logged.append, fetcher, lambda s: None) == 1
