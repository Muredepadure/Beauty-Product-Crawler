import pytest

from beautycrawler.crawler.robots import RobotsTxt, product_token

UA = "BeautyCrawler/0.1 (+https://github.com/Muredepadure/Beauty-Product-Crawler)"
SITE = "https://shop.example.ro"


def allowed(robots: str, path: str, ua: str = UA) -> bool:
    return RobotsTxt.parse(robots).can_fetch(ua, f"{SITE}{path}")


def test_product_token() -> None:
    assert product_token(UA) == "beautycrawler"
    assert product_token("Googlebot") == "googlebot"
    assert product_token("  Some Bot 1.0") == "some"


@pytest.mark.parametrize(
    ("path", "ok"),
    [
        ("/produse-cosmetice", True),
        ("/produse-cosmetice?page=2", True),
        ("/produse-cosmetice?sort=pret", False),  # Disallow: /*?sort=
        ("/produse-cosmetice?page=2&sort=pret", False),  # Disallow: /*&sort=
        ("/collections/par+uscat", False),  # Disallow: /collections/*+*
        ("/collections/par", True),
        ("/catalog/file.pdf", False),  # Disallow: /*.pdf$
        ("/catalog/file.pdf?v=2", True),  # `$` anchors the end
        ("/cos", False),
        ("/cosmetice", False),  # plain prefix match, like the RFC says
    ],
)
def test_wildcards(path: str, ok: bool) -> None:
    robots = (
        "User-agent: *\n"
        "Disallow: /*?sort=\n"
        "Disallow: /*&sort=\n"
        "Disallow: /collections/*+*\n"
        "Disallow: /*.pdf$\n"
        "Disallow: /cos\n"
    )
    assert allowed(robots, path) is ok


@pytest.mark.parametrize(
    ("path", "ok"),
    [
        ("/p/1", False),
        ("/p/public/1", True),  # longer Allow beats shorter Disallow
        ("/p/public/secret", False),  # ... and a longer Disallow beats it again
        ("/same", True),  # equal length: Allow wins
    ],
)
def test_longest_match_wins(path: str, ok: bool) -> None:
    robots = (
        "User-agent: *\n"
        "Disallow: /p/\n"
        "Allow: /p/public/\n"
        "Disallow: /p/public/secret\n"
        "Disallow: /same\n"
        "Allow: /same\n"
    )
    assert allowed(robots, path) is ok


def test_all_star_groups_are_merged() -> None:
    # Farmacia Tei's layout: a permissive `*` group, then named bots, then `Disallow: /`
    # in a second `*` group. urllib.robotparser kept only the first `*` group.
    robots = (
        "User-agent: *\nDisallow: /checkout\n\n"
        "User-agent: Googlebot\nAllow: /\n\n"
        "User-agent: *\nDisallow: /\n"
    )
    assert allowed(robots, "/produs") is False
    assert allowed(robots, "/produs", ua="Googlebot/2.1") is True


def test_named_group_replaces_star_group() -> None:
    robots = "User-agent: *\nDisallow: /\n\nUser-agent: BeautyCrawler\nDisallow: /cos\n"
    assert allowed(robots, "/produs") is True
    assert allowed(robots, "/cos") is False


def test_consecutive_user_agents_share_a_group() -> None:
    robots = "User-agent: OtherBot\nUser-agent: beautycrawler\nDisallow: /x\n"
    assert allowed(robots, "/x") is False
    assert allowed(robots, "/x", ua="ThirdBot/1.0") is True  # no group, no `*`: all allowed


def test_empty_disallow_comments_and_junk() -> None:
    robots = (
        "# comment\nDisallow: /before-any-group\n"
        "User-agent: * # everyone\nDisallow:\nnot a rule\nDisallow: /tmp # temp files\n"
    )
    assert allowed(robots, "/before-any-group") is True
    assert allowed(robots, "/") is True
    assert allowed(robots, "/tmp/a") is False


def test_percent_encoding_is_compared_decoded() -> None:
    robots = "User-agent: *\nDisallow: /îngrijire\nDisallow: /a%20b\n"
    assert allowed(robots, "/%C3%AEngrijire-ten") is False
    assert allowed(robots, "/a b") is False


def test_robots_txt_itself_is_always_allowed() -> None:
    assert allowed("User-agent: *\nDisallow: /\n", "/robots.txt") is True


def test_crawl_delay_and_sitemaps() -> None:
    robots = RobotsTxt.parse(
        "Sitemap: https://shop.example.ro/sitemap-index.xml\n"
        "User-agent: *\nCrawl-delay: 10\nDisallow:\n"
        "User-agent: Googlebot\nCrawl-delay: 1\n"
        "User-agent: *\nCrawl-delay: abc\n"
        "Sitemap: https://shop.example.ro/products.xml\n"
    )
    assert robots.crawl_delay(UA) == 10.0
    assert robots.crawl_delay("Googlebot") == 1.0
    assert robots.sitemaps == [
        "https://shop.example.ro/sitemap-index.xml",
        "https://shop.example.ro/products.xml",
    ]
    assert RobotsTxt.parse("User-agent: *\nDisallow: /x\n").crawl_delay(UA) is None
