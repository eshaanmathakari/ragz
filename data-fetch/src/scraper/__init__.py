"""Scraper modules for extracting data from websites."""

from .base_scraper import BaseScraper
from .universal_scraper import UniversalScraper
from .coinglass_scraper import CoinGlassScraper
from .dune_scraper import DuneScraper
from .theblock_scraper import TheBlockScraper

__all__ = [
    "BaseScraper",
    "UniversalScraper",
    "CoinGlassScraper",
    "DuneScraper",
    "TheBlockScraper",
]

