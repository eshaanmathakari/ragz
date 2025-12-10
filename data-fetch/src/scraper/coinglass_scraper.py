"""
CoinGlass scraper - browser-based extraction for crypto derivatives data.
Uses browser automation to extract data from CoinGlass pages.
"""

import json
import re
import asyncio
from typing import Dict, Any, Optional
from dataclasses import dataclass

import pandas as pd
from bs4 import BeautifulSoup

from .base_scraper import BaseScraper, ScraperResult
from ..utils.logger import get_logger
from ..utils.browser import BrowserManager
from ..utils.config_manager import SiteConfig
from ..utils.stealth import StealthManager
from ..extractor.dom_extractor import DomExtractor, ExtractionSelector
from ..extractor.js_data_extractor import JsDataExtractor
from ..extractor.financial_normalizer import FinancialNormalizer


@dataclass
class CoinGlassMetrics:
    """Structure for CoinGlass metrics."""
    btc_price: Optional[float] = None
    futures_volume_24h: Optional[float] = None
    spot_volume_24h: Optional[float] = None
    open_interest: Optional[float] = None
    net_inflow_24h: Optional[float] = None
    net_inflow_5min: Optional[float] = None
    net_inflow_1h: Optional[float] = None
    net_inflow_4h: Optional[float] = None
    net_inflow_12h: Optional[float] = None
    btc_volatility_1d: Optional[float] = None
    eth_volatility_1d: Optional[float] = None
    sol_volatility_1d: Optional[float] = None
    xrp_volatility_1d: Optional[float] = None
    doge_volatility_1d: Optional[float] = None


class CoinGlassScraper(BaseScraper):
    """
    Browser-based scraper for CoinGlass.
    Extracts data from rendered pages using DOM extraction and JavaScript evaluation.
    """
    
    def __init__(
        self,
        config: Optional[SiteConfig] = None,
        use_stealth: bool = True,
        **kwargs
    ):
        """
        Initialize CoinGlass scraper.
        
        Args:
            config: Site configuration
            use_stealth: Enable stealth mode for browser
        """
        super().__init__(config=config, **kwargs)
        self.use_stealth = use_stealth
        self.stealth_manager = StealthManager(randomize=use_stealth) if use_stealth else None
        self.dom_extractor = DomExtractor()
        self.js_extractor = JsDataExtractor()
        self.normalizer = FinancialNormalizer()
    
    def fetch_raw(self, url: str) -> Dict[str, Any]:
        """
        Fetch raw data from CoinGlass page using browser automation.
        
        Args:
            url: URL to scrape
        
        Returns:
            Dict with HTML content and metadata
        """
        self.logger.info(f"Loading CoinGlass page: {url}")
        
        # Use browser to load page
        async def _fetch():
            # Configure browser with stealth if enabled
            user_agent = self.user_agent
            if self.use_stealth and self.stealth_manager:
                fingerprint = self.stealth_manager.get_fingerprint()
                user_agent = fingerprint.user_agent
            
            async with BrowserManager(
                headless=True,
                user_agent=user_agent,
            ) as browser:
                # Inject stealth scripts if enabled
                if self.use_stealth and self.stealth_manager:
                    stealth_scripts = self.stealth_manager.inject_stealth_scripts()
                    for script in stealth_scripts:
                        await browser._context.add_init_script(script)
                
                page = await browser._context.new_page()
                
                # Inject stealth scripts into page as well
                if self.use_stealth and self.stealth_manager:
                    stealth_scripts = self.stealth_manager.inject_stealth_scripts()
                    for script in stealth_scripts:
                        await page.add_init_script(script)
                
                try:
                    # Load page with longer timeout for dynamic content
                    await page.goto(url, timeout=30000, wait_until="networkidle")
                    
                    # Wait for content to load (CoinGlass uses React)
                    await asyncio.sleep(3)
                    
                    # Try to wait for specific elements that indicate data is loaded
                    try:
                        # Wait for price or volume elements
                        await page.wait_for_selector(
                            "[class*='price'], [class*='volume'], [data-testid*='price']",
                            timeout=10000
                        )
                    except Exception:
                        # Continue anyway if selector not found
                        pass
                    
                    # Additional wait for JavaScript to render
                    await asyncio.sleep(2)
                    
                    # Get HTML content
                    html = await page.content()
                    
                    # Try to capture network requests for API data
                    network_data = None
                    try:
                        # Evaluate JavaScript to get data from window objects
                        js_data = await page.evaluate("""
                            () => {
                                const data = {};
                                // Try common data variable names
                                if (window.__INITIAL_STATE__) data.initialState = window.__INITIAL_STATE__;
                                if (window.chartData) data.chartData = window.chartData;
                                if (window.marketData) data.marketData = window.marketData;
                                if (window.__NEXT_DATA__) data.nextData = window.__NEXT_DATA__;
                                return JSON.stringify(data);
                            }
                        """)
                        if js_data and js_data != "{}":
                            network_data = json.loads(js_data)
                    except Exception as e:
                        self.logger.debug(f"Could not extract JS data: {e}")
                    
                    return {
                        "type": "dom_js_extraction",
                        "content": html,
                        "url": url,
                        "js_data": network_data,
                    }
                    
                finally:
                    await page.close()
            
            return {
                "type": "dom_js_extraction",
                "content": "",
                "url": url,
            }
        
        result = asyncio.run(_fetch())
        return result
    
    def parse_raw(self, raw_data: Dict[str, Any]) -> pd.DataFrame:
        """
        Parse raw HTML/JS data into DataFrame.
        
        Args:
            raw_data: Raw data from fetch_raw
        
        Returns:
            Parsed DataFrame
        """
        html = raw_data.get("content", "")
        url = raw_data.get("url", "")
        js_data = raw_data.get("js_data")
        
        if not html:
            self.logger.error("No HTML content to parse")
            return pd.DataFrame()
        
        soup = BeautifulSoup(html, "lxml")
        metrics = CoinGlassMetrics()
        
        # Extract based on page type
        if "/currencies/BTC" in url or "/currencies/bitcoin" in url.lower():
            # BTC Overview page
            metrics = self._extract_btc_overview(soup, html, js_data)
        elif "inflow" in url.lower() or "outflow" in url.lower():
            # Spot Inflow/Outflow page
            metrics = self._extract_spot_flows(soup, html, js_data)
        elif "volatility" in url.lower():
            # Volatility page
            metrics = self._extract_volatility(soup, html, js_data)
        else:
            # Try to extract all metrics from any page
            metrics = self._extract_all_metrics(soup, html, js_data)
        
        # Convert to DataFrame
        data_dict = {
            "timestamp": pd.Timestamp.now(),
        }
        
        # Add all non-None metrics
        for field_name, value in metrics.__dict__.items():
            if value is not None:
                data_dict[field_name] = value
        
        if not data_dict or len(data_dict) == 1:  # Only timestamp
            self.logger.warning("No metrics extracted from page")
            return pd.DataFrame()
        
        df = pd.DataFrame([data_dict])
        
        # Normalize financial values
        df = self.normalizer.normalize_dataframe(df)
        
        return df
    
    def _extract_btc_overview(
        self,
        soup: BeautifulSoup,
        html: str,
        js_data: Optional[Dict],
    ) -> CoinGlassMetrics:
        """Extract metrics from BTC Overview page."""
        metrics = CoinGlassMetrics()
        
        # Try multiple extraction methods
        # Method 1: Extract from text patterns
        patterns = {
            "btc_price": [
                r'\$?([\d,]+\.?\d*)\s*BTC',
                r'BTC[:\s]*\$?([\d,]+\.?\d*)',
                r'Price[:\s]*\$?([\d,]+\.?\d*)',
            ],
            "futures_volume_24h": [
                r'Futures\s+Volume[:\s]*\$?([\d,]+\.?\d*[BMK]?)',
                r'24h\s+Futures[:\s]*\$?([\d,]+\.?\d*[BMK]?)',
            ],
            "spot_volume_24h": [
                r'Spot\s+Volume[:\s]*\$?([\d,]+\.?\d*[BMK]?)',
                r'24h\s+Spot[:\s]*\$?([\d,]+\.?\d*[BMK]?)',
            ],
            "open_interest": [
                r'Open\s+Interest[:\s]*\$?([\d,]+\.?\d*[BMK]?)',
                r'OI[:\s]*\$?([\d,]+\.?\d*[BMK]?)',
            ],
            "net_inflow_24h": [
                r'Net\s+Inflow[:\s]*\$?([\d,]+\.?\d*[BMK]?)',
                r'24h\s+Net\s+Inflow[:\s]*\$?([\d,]+\.?\d*[BMK]?)',
            ],
        }
        
        for field_name, pattern_list in patterns.items():
            for pattern in pattern_list:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    value = self._parse_numeric_value(match.group(1))
                    if value is not None:
                        setattr(metrics, field_name, value)
                        break
        
        # Method 2: Extract from data attributes or specific selectors
        # Look for elements with data attributes containing values
        value_elements = soup.find_all(attrs={"data-value": True})
        for elem in value_elements:
            text = elem.get_text(strip=True)
            data_value = elem.get("data-value")
            
            # Try to match to field based on context
            parent_text = ""
            if elem.parent:
                parent_text = elem.parent.get_text()
            
            if "price" in parent_text.lower() and metrics.btc_price is None:
                metrics.btc_price = self._parse_numeric_value(data_value or text)
            elif "futures" in parent_text.lower() and "volume" in parent_text.lower():
                if metrics.futures_volume_24h is None:
                    metrics.futures_volume_24h = self._parse_numeric_value(data_value or text)
            elif "spot" in parent_text.lower() and "volume" in parent_text.lower():
                if metrics.spot_volume_24h is None:
                    metrics.spot_volume_24h = self._parse_numeric_value(data_value or text)
            elif "open" in parent_text.lower() and "interest" in parent_text.lower():
                if metrics.open_interest is None:
                    metrics.open_interest = self._parse_numeric_value(data_value or text)
            elif "inflow" in parent_text.lower() or "outflow" in parent_text.lower():
                if metrics.net_inflow_24h is None:
                    metrics.net_inflow_24h = self._parse_numeric_value(data_value or text)
        
        # Method 3: Extract from JavaScript data
        if js_data:
            metrics = self._extract_from_js_data(js_data, metrics)
        
        return metrics
    
    def _extract_spot_flows(
        self,
        soup: BeautifulSoup,
        html: str,
        js_data: Optional[Dict],
    ) -> CoinGlassMetrics:
        """Extract spot inflow/outflow metrics."""
        metrics = CoinGlassMetrics()
        
        # Extract different timeframes
        timeframes = {
            "net_inflow_5min": r'5\s*min[:\s]*\$?([\d,]+\.?\d*[BMK]?)',
            "net_inflow_1h": r'1\s*h[:\s]*\$?([\d,]+\.?\d*[BMK]?)',
            "net_inflow_4h": r'4\s*h[:\s]*\$?([\d,]+\.?\d*[BMK]?)',
            "net_inflow_12h": r'12\s*h[:\s]*\$?([\d,]+\.?\d*[BMK]?)',
            "net_inflow_24h": r'24\s*h[:\s]*\$?([\d,]+\.?\d*[BMK]?)',
        }
        
        for field_name, pattern in timeframes.items():
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                value = self._parse_numeric_value(match.group(1))
                if value is not None:
                    setattr(metrics, field_name, value)
        
        # Also try to extract from JS data
        if js_data:
            metrics = self._extract_from_js_data(js_data, metrics)
        
        return metrics
    
    def _extract_volatility(
        self,
        soup: BeautifulSoup,
        html: str,
        js_data: Optional[Dict],
    ) -> CoinGlassMetrics:
        """Extract volatility metrics for different coins."""
        metrics = CoinGlassMetrics()
        
        # Extract volatility for each coin
        coins = {
            "btc_volatility_1d": ["BTC", "Bitcoin"],
            "eth_volatility_1d": ["ETH", "Ethereum"],
            "sol_volatility_1d": ["SOL", "Solana"],
            "xrp_volatility_1d": ["XRP", "Ripple"],
            "doge_volatility_1d": ["DOGE", "Dogecoin"],
        }
        
        for field_name, coin_names in coins.items():
            for coin_name in coin_names:
                pattern = rf'{coin_name}[:\s]*([\d,]+\.?\d*)\s*%?'
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    value = self._parse_numeric_value(match.group(1))
                    if value is not None:
                        setattr(metrics, field_name, value)
                        break
        
        # Also try to extract from JS data
        if js_data:
            metrics = self._extract_from_js_data(js_data, metrics)
        
        return metrics
    
    def _extract_all_metrics(
        self,
        soup: BeautifulSoup,
        html: str,
        js_data: Optional[Dict],
    ) -> CoinGlassMetrics:
        """Try to extract all metrics from any page."""
        # Combine all extraction methods
        metrics = self._extract_btc_overview(soup, html, js_data)
        flow_metrics = self._extract_spot_flows(soup, html, js_data)
        vol_metrics = self._extract_volatility(soup, html, js_data)
        
        # Merge metrics (prefer non-None values)
        for field_name in CoinGlassMetrics.__dataclass_fields__:
            value = getattr(flow_metrics, field_name) or getattr(vol_metrics, field_name)
            if value is not None and getattr(metrics, field_name) is None:
                setattr(metrics, field_name, value)
        
        return metrics
    
    def _extract_from_js_data(
        self,
        js_data: Dict,
        metrics: CoinGlassMetrics,
    ) -> CoinGlassMetrics:
        """Extract metrics from JavaScript data objects."""
        # Try to find metrics in nested JS data structures
        def find_value(data, keys):
            """Recursively search for value by key names."""
            if isinstance(data, dict):
                for key, value in data.items():
                    if any(k.lower() in key.lower() for k in keys):
                        if isinstance(value, (int, float)):
                            return value
                        elif isinstance(value, str):
                            return self._parse_numeric_value(value)
                    elif isinstance(value, (dict, list)):
                        result = find_value(value, keys)
                        if result is not None:
                            return result
            elif isinstance(data, list):
                for item in data:
                    result = find_value(item, keys)
                    if result is not None:
                        return result
            return None
        
        # Map field names to search keys
        field_mappings = {
            "btc_price": ["price", "btc", "bitcoin"],
            "futures_volume_24h": ["futures", "volume", "24h"],
            "spot_volume_24h": ["spot", "volume", "24h"],
            "open_interest": ["open", "interest", "oi"],
            "net_inflow_24h": ["inflow", "net", "24h"],
        }
        
        for field_name, search_keys in field_mappings.items():
            if getattr(metrics, field_name) is None:
                value = find_value(js_data, search_keys)
                if value is not None:
                    setattr(metrics, field_name, value)
        
        return metrics
    
    def _parse_numeric_value(self, value: str) -> Optional[float]:
        """Parse numeric value from string, handling currency, suffixes, etc."""
        if not value:
            return None
        
        # Remove whitespace and currency symbols
        value = value.strip().replace("$", "").replace(",", "")
        
        # Handle negative values
        is_negative = value.startswith("-") or value.startswith("–")
        if is_negative:
            value = value[1:].strip()
        
        # Handle suffixes (B, M, K)
        multipliers = {
            "B": 1e9,
            "b": 1e9,
            "M": 1e6,
            "m": 1e6,
            "K": 1e3,
            "k": 1e3,
        }
        
        multiplier = 1
        for suffix, mult in multipliers.items():
            if value.endswith(suffix):
                multiplier = mult
                value = value[:-1]
                break
        
        try:
            num = float(value) * multiplier
            return -num if is_negative else num
        except ValueError:
            return None

