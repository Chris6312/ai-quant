"""Phase 8 CoinDesk sitemap ingestion tests."""

from __future__ import annotations

from datetime import date

from app.research.coindesk_sitemap_client import (
    build_coindesk_archive_page_url,
    parse_coindesk_archive_page,
)

COINDESK_ARCHIVE_HTML = """
<html>
  <body>
    <main>
      <a href="/markets/2025/12/30/bitcoin-rises-above-89000">
        Bitcoin rises above $89,000, showing rare gain in U.S. trading
      </a>
      <span>2025-12-30</span>
      <a href="/markets/2025/12/30/coindesk-20-ethereum-gains">
        CoinDesk 20 Performance Update: Ethereum (ETH) Gains 1.8% as Index Moves Higher
      </a>
      <span>2025-12-30</span>
      <a href="/markets/2025/12/30/dogecoin-breaks-support">
        Dogecoin breaks support as year-end selling drags DOGE to $0.123
      </a>
      <span>2025-12-30</span>
    </main>
  </body>
</html>
"""


def test_build_coindesk_archive_page_url_uses_year_and_page() -> None:
    """CoinDesk archive page one should omit the page suffix."""

    assert (
        build_coindesk_archive_page_url(
            base_url="https://www.coindesk.com/sitemap/archive",
            year=2025,
            page=1,
        )
        == "https://www.coindesk.com/sitemap/archive/2025"
    )
    assert (
        build_coindesk_archive_page_url(
            base_url="https://www.coindesk.com/sitemap/archive",
            year=2025,
            page=2,
        )
        == "https://www.coindesk.com/sitemap/archive/2025/2"
    )


def test_parse_coindesk_archive_page_extracts_title_date_url_rows() -> None:
    """Archive HTML should normalize title/date rows into scoring articles."""

    articles = parse_coindesk_archive_page(
        COINDESK_ARCHIVE_HTML,
        source_url="https://www.coindesk.com/sitemap/archive/2025",
    )

    assert len(articles) == 3
    assert articles[0].title == "Bitcoin rises above $89,000, showing rare gain in U.S. trading"
    assert articles[0].published_at.date() == date(2025, 12, 30)
    assert articles[0].url == (
        "https://www.coindesk.com/markets/2025/12/30/bitcoin-rises-above-89000"
    )
    assert articles[0].source == "CoinDesk:Sitemap"
    assert articles[1].title.startswith("CoinDesk 20 Performance Update: Ethereum")


def test_parse_coindesk_archive_page_can_use_plain_text_order() -> None:
    """Copied sitemap text should still parse when links are unavailable."""

    document = """
    2025 Archive
    Bitcoin slips below $88,000 as traders brace for options expiry
    2025-12-22
    Ethereum's upgrade slated for late 2026 as devs accelerate roadmap
    2025-12-21
    Page 1 of 18
    """

    articles = parse_coindesk_archive_page(
        document,
        source_url="https://www.coindesk.com/sitemap/archive/2025",
    )

    assert [article.title for article in articles] == [
        "Bitcoin slips below $88,000 as traders brace for options expiry",
        "Ethereum's upgrade slated for late 2026 as devs accelerate roadmap",
    ]
    assert articles[0].url.startswith(
        "https://www.coindesk.com/sitemap/archive/2025-12-22/"
    )
