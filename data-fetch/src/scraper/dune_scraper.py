"""
Dune Analytics scraper - multi-step API execution.
Implements execute → poll → fetch pattern for Dune queries.
"""

import os
import time
import requests
from typing import Dict, Any, Optional, List

import pandas as pd

from .base_scraper import BaseScraper, ScraperResult
from ..utils.logger import get_logger
from ..utils.config_manager import SiteConfig
from ..extractor.json_extractor import JsonExtractor


class DuneScraper(BaseScraper):
    """
    Scraper for Dune Analytics API.
    Implements the 3-step process: execute query, poll status, fetch results.
    """
    
    API_BASE = "https://api.dune.com/api/v1"
    
    def __init__(
        self,
        config: Optional[SiteConfig] = None,
        api_key: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize Dune scraper.
        
        Args:
            config: Site configuration
            api_key: Dune API key (uses DUNE_API_KEY env var if not provided)
        """
        super().__init__(config=config, **kwargs)
        self.api_key = api_key or os.getenv("DUNE_API_KEY")
        if not self.api_key:
            self.logger.warning("DUNE_API_KEY not found in environment variables")
        self.json_extractor = JsonExtractor()
        self._execution_cache: Dict[str, str] = {}  # Cache execution IDs
    
    def get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers for Dune API."""
        if not self.api_key:
            raise ValueError("DUNE_API_KEY is required for Dune API access")
        return {
            "x-dune-api-key": self.api_key,
            "Content-Type": "application/json",
        }
    
    def execute_query(
        self,
        query_id: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Execute a Dune query and return execution ID.
        
        Args:
            query_id: Dune query ID
            parameters: Optional query parameters
        
        Returns:
            Execution ID
        """
        if not self.api_key:
            raise ValueError("DUNE_API_KEY is required")
        
        url = f"{self.API_BASE}/query/{query_id}/execute"
        
        payload = {}
        if parameters:
            payload["query_parameters"] = parameters
        
        try:
            response = requests.post(
                url,
                headers=self.get_auth_headers(),
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            
            data = response.json()
            execution_id = data.get("execution_id")
            
            if not execution_id:
                raise ValueError(f"No execution_id in response: {data}")
            
            self.logger.info(f"Query {query_id} executed, execution_id: {execution_id}")
            return execution_id
            
        except requests.RequestException as e:
            self.logger.error(f"Failed to execute query {query_id}: {e}")
            raise
    
    def poll_query_status(
        self,
        query_id: str,
        execution_id: str,
        max_attempts: int = 30,
        poll_interval: int = 2,
    ) -> Dict[str, Any]:
        """
        Poll query execution status until complete.
        
        Args:
            query_id: Dune query ID
            execution_id: Execution ID from execute_query
            max_attempts: Maximum number of polling attempts
            poll_interval: Seconds between polls
        
        Returns:
            Status response dict
        """
        url = f"{self.API_BASE}/query/{query_id}/status"
        
        for attempt in range(max_attempts):
            try:
                response = requests.get(
                    url,
                    headers=self.get_auth_headers(),
                    params={"execution_id": execution_id},
                    timeout=self.timeout,
                )
                response.raise_for_status()
                
                data = response.json()
                state = data.get("state", "").lower()
                
                self.logger.debug(f"Query status (attempt {attempt + 1}): {state}")
                
                if state == "completed":
                    self.logger.info(f"Query {query_id} completed successfully")
                    return data
                elif state in ["failed", "cancelled"]:
                    error = data.get("error", "Unknown error")
                    raise ValueError(f"Query execution {state}: {error}")
                elif state == "pending" or state == "executing":
                    # Continue polling
                    time.sleep(poll_interval)
                else:
                    # Unknown state, continue polling
                    self.logger.warning(f"Unknown query state: {state}")
                    time.sleep(poll_interval)
                    
            except requests.RequestException as e:
                if attempt < max_attempts - 1:
                    self.logger.warning(f"Poll attempt {attempt + 1} failed: {e}, retrying...")
                    time.sleep(poll_interval)
                else:
                    raise
        
        raise TimeoutError(
            f"Query {query_id} did not complete within {max_attempts * poll_interval} seconds"
        )
    
    def fetch_query_results(
        self,
        query_id: str,
        execution_id: str,
    ) -> Dict[str, Any]:
        """
        Fetch results from a completed query execution.
        
        Args:
            query_id: Dune query ID
            execution_id: Execution ID from execute_query
        
        Returns:
            Results response dict
        """
        url = f"{self.API_BASE}/query/{query_id}/results"
        
        try:
            response = requests.get(
                url,
                headers=self.get_auth_headers(),
                params={"execution_id": execution_id},
                timeout=self.timeout,
            )
            response.raise_for_status()
            
            data = response.json()
            self.logger.info(f"Fetched results for query {query_id}")
            return data
            
        except requests.RequestException as e:
            self.logger.error(f"Failed to fetch results for query {query_id}: {e}")
            raise
    
    def fetch_raw(self, url: str) -> Dict[str, Any]:
        """
        Fetch raw data from Dune API using 3-step process.
        
        Args:
            url: Not used directly, query_id comes from config
        
        Returns:
            Dict with query results
        """
        if not self.config:
            raise ValueError("Site configuration required for Dune scraper")
        
        # Get query ID from config
        query_id = self.config.data_source.query_id
        
        if not query_id:
            # Try to extract from endpoint URL
            endpoint = self.config.data_source.endpoint
            if endpoint and "/query/" in endpoint:
                parts = endpoint.split("/query/")
                if len(parts) > 1:
                    query_id = parts[1].split("/")[0]
        
        if not query_id:
            raise ValueError("Query ID not found in configuration. Please set query_id in data_source.")
        
        # Check cache for recent execution
        parameters = self.config.data_source.parameters or {}
        cache_key = f"{query_id}_{parameters}"
        if cache_key in self._execution_cache:
            execution_id = self._execution_cache[cache_key]
            self.logger.info(f"Using cached execution_id: {execution_id}")
        else:
            # Step 1: Execute query
            execution_id = self.execute_query(query_id, parameters)
            self._execution_cache[cache_key] = execution_id
        
        # Step 2: Poll status
        max_attempts = self.config.data_source.max_poll_attempts
        poll_interval = self.config.data_source.poll_interval
        status_data = self.poll_query_status(query_id, execution_id, max_attempts, poll_interval)
        
        # Step 3: Fetch results
        results_data = self.fetch_query_results(query_id, execution_id)
        
        return {
            "type": "api_json",
            "content": results_data,
            "query_id": query_id,
            "execution_id": execution_id,
        }
    
    def parse_raw(self, raw_data: Dict[str, Any]) -> pd.DataFrame:
        """
        Parse Dune query results into DataFrame.
        
        Args:
            raw_data: Raw results from fetch_raw
        
        Returns:
            Parsed DataFrame
        """
        results_data = raw_data.get("content", {})
        
        if not results_data:
            self.logger.error("No results data to parse")
            return pd.DataFrame()
        
        # Dune API returns results in different formats
        # Format 1: { "result": { "rows": [...], "metadata": {...} } }
        # Format 2: { "rows": [...], "metadata": {...} }
        
        rows = None
        if "result" in results_data and "rows" in results_data["result"]:
            rows = results_data["result"]["rows"]
        elif "rows" in results_data:
            rows = results_data["rows"]
        elif isinstance(results_data, list):
            rows = results_data
        
        if not rows:
            self.logger.error("No rows found in results")
            return pd.DataFrame()
        
        # Convert to DataFrame
        df = pd.DataFrame(rows)
        
        # Apply field mappings if available
        if self.config and self.config.field_mappings:
            rename_map = {v: k for k, v in self.config.field_mappings.items()}
            df = df.rename(columns=rename_map)
        
        self.logger.info(f"Parsed {len(df)} rows from Dune query")
        return df

