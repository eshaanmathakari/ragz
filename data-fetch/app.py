"""
Streamlit frontend for Data-Fetch framework.
Simple monochrome interface for scraping financial data.
"""

import streamlit as st
import pandas as pd
from pathlib import Path
import sys
import os

# Load environment variables from .env file FIRST, before any other imports
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=True)  # override=True ensures env vars take precedence
    else:
        # Try parent directory
        parent_env = Path(__file__).parent.parent / ".env"
        if parent_env.exists():
            load_dotenv(parent_env, override=True)
        else:
            load_dotenv(override=True)  # Try default locations
except ImportError:
    # dotenv not installed, skip
    pass

# Add src to path - ensure we can import from src directory
app_dir = Path(__file__).parent.absolute()
# Add the app directory to Python path (where src/ folder is located)
if str(app_dir) not in sys.path:
    sys.path.insert(0, str(app_dir))

from src.api.frontend_api import FrontendAPI

# Startup checks
def check_environment():
    """Check environment setup and display warnings if needed."""
    warnings = []
    
    # Check OpenAI API key
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        # Try Streamlit secrets (only available in Streamlit Cloud)
        try:
            openai_key = st.secrets.get("OPENAI_API_KEY", None)
        except (AttributeError, FileNotFoundError):
            # Secrets not available (local development without secrets.toml)
            pass
    
    if not openai_key:
        warnings.append("⚠️ OpenAI API key not found. LLM-powered data detection will be disabled.")
    
    # Check Alpha Vantage API key
    alphavantage_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if not alphavantage_key:
        # Try Streamlit secrets (only available in Streamlit Cloud)
        try:
            alphavantage_key = st.secrets.get("ALPHA_VANTAGE_API_KEY", None)
        except (AttributeError, FileNotFoundError):
            # Secrets not available (local development without secrets.toml)
            pass
    
    if not alphavantage_key:
        warnings.append("⚠️ Alpha Vantage API key not found. Alpha Vantage data sources will be disabled.")
    
    # Check Playwright browsers (non-blocking check)
    # Note: On Streamlit Cloud, browsers are installed automatically via post-install
    try:
        from playwright.sync_api import sync_playwright
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                browser.close()
        except Exception as e:
            error_msg = str(e).lower()
            # Check if it's a missing browser error
            if any(keyword in error_msg for keyword in ["executable", "browser", "not found", "no such file"]):
                warnings.append("⚠️ Playwright browsers not installed. Browser automation will be disabled. The app will attempt to install browsers automatically when needed.")
            else:
                warnings.append(f"⚠️ Playwright browser check failed: {str(e)[:100]}")
    except ImportError:
        warnings.append("⚠️ Playwright not installed. Browser automation will not work.")
    except Exception as e:
        # Don't block app startup if Playwright check fails
        warnings.append(f"⚠️ Playwright check failed: {str(e)[:100]}")
    
    return warnings

# Run startup checks (only once, cached)
@st.cache_resource
def get_startup_warnings():
    return check_environment()

startup_warnings = get_startup_warnings()

# Page configuration
st.set_page_config(
    page_title="Data-Fetch: Financial Data Scraper",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for monochrome theme
st.markdown("""
    <style>
    .main {
        background-color: #FFFFFF;
    }
    .stButton>button {
        background-color: #000000;
        color: #FFFFFF;
        border: 1px solid #000000;
    }
    .stButton>button:hover {
        background-color: #333333;
        border: 1px solid #333333;
    }
    .stTextInput>div>div>input {
        border: 1px solid #CCCCCC;
    }
    .stSelectbox>div>div>select {
        border: 1px solid #CCCCCC;
    }
    .stCheckbox>label {
        color: #000000;
    }
    h1, h2, h3 {
        color: #000000;
    }
    .stDataFrame {
        border: 1px solid #CCCCCC;
    }
    </style>
    """, unsafe_allow_html=True)

# Initialize API
@st.cache_resource
def get_api():
    return FrontendAPI()

api = get_api()

# Header
st.title("📊 Data-Fetch: Financial Data Scraper")
st.markdown("---")
st.markdown("Extract financial data from websites and download as Excel files.")

# Display startup warnings if any
if startup_warnings:
    with st.expander("⚠️ Environment Warnings", expanded=True):
        for warning in startup_warnings:
            st.warning(warning)

# Sidebar
with st.sidebar:
    st.header("Configuration")
    
    # Scraping options
    use_stealth = st.checkbox("Enable Stealth Mode", value=True, help="Bypass basic bot detection")
    override_robots = st.checkbox("Override robots.txt", value=False, help="Proceed even if robots.txt is UNKNOWN")
    use_fallbacks = st.checkbox("Use Fallback Sources", value=True, help="Try alternative data sources if primary fails")
    
    st.markdown("---")
    
    # Configured sites
    st.subheader("Configured Sites")
    sites = api.get_configured_sites()
    if sites:
        site_options = ["None"] + [f"{s['id']} - {s['name']}" for s in sites]
        selected_site = st.selectbox("Select a configured site:", site_options)
        
        # Show site info if selected
        if selected_site != "None":
            site_id = selected_site.split(" - ")[0]
            site_info = next((s for s in sites if s["id"] == site_id), None)
            if site_info:
                with st.expander("Site Information", expanded=False):
                    st.write(f"**URL:** {site_info['page_url']}")
                    st.write(f"**Strategy:** {site_info.get('extraction_strategy', 'N/A')}")
                    st.write(f"**API Key:** {site_info.get('api_key_status', 'N/A')}")
                    if site_info.get('requires_subscription'):
                        st.warning("⚠️ This site requires a paid subscription")
                    st.write(f"**Robots.txt:** {site_info.get('robots_status', 'UNKNOWN')}")
    else:
        selected_site = "None"
        st.info("No sites configured. Use URL input instead.")

# Main content
tab1, tab2, tab3, tab4 = st.tabs([
    "Scrape from URL", 
    "Scrape from Configured Site", 
    "📰 Fintech News",
    "📈 Market Sentiment"  # New tab for FRED market sentiment data
])

with tab1:
    st.header("Scrape from URL")
    
    url_input = st.text_input(
        "Enter website URL:",
        placeholder="https://www.example.com/financial-data",
        help="Enter the URL of the financial data page you want to scrape"
    )
    
    col1, col2 = st.columns([1, 4])
    with col1:
        scrape_button = st.button("Scrape Data", type="primary")
    
    if scrape_button and url_input:
        if not url_input.startswith(("http://", "https://")):
            st.error("Please enter a valid URL starting with http:// or https://")
        else:
            with st.spinner("Scraping data... This may take a moment."):
                # Show progress
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                status_text.text("Step 1/4: Discovering data sources...")
                progress_bar.progress(25)
                
                # Scrape
                result = api.scrape_url(
                    url=url_input,
                    use_stealth=use_stealth,
                    override_robots=override_robots,
                    use_fallbacks=use_fallbacks,
                )
                
                progress_bar.progress(100)
                status_text.text("Complete!")
                
                # Display results
                if result["success"]:
                    st.success(f"✅ Successfully extracted {result['rows']} rows of data!")
                    
                    # Show warnings if any
                    if result["warnings"]:
                        with st.expander("⚠️ Validation Warnings", expanded=False):
                            for warning in result["warnings"]:
                                st.warning(warning)
                    
                    # Data preview
                    st.subheader("Data Preview")
                    preview_rows = st.slider("Rows to display:", 10, min(100, result["rows"]), 50)
                    st.dataframe(result["data"].head(preview_rows), width='stretch')
                    
                    # Data statistics
                    with st.expander("📊 Data Statistics", expanded=False):
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Total Rows", result["rows"])
                        with col2:
                            st.metric("Total Columns", len(result["columns"]))
                        with col3:
                            if result["metadata"].get("date_range"):
                                date_range = result["metadata"]["date_range"]
                                if date_range[0] and date_range[1]:
                                    st.metric("Date Range", f"{str(date_range[0])[:10]} to {str(date_range[1])[:10]}")
                    
                    # Download section
                    st.subheader("Download")
                    excel_bytes, filename = api.export_to_excel(result["data"])
                    
                    if excel_bytes:
                        st.download_button(
                            label="📥 Download Excel File",
                            data=excel_bytes,
                            file_name=filename,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            type="primary",
                        )
                        st.info(f"File size: {len(excel_bytes) / 1024:.2f} KB")
                    else:
                        st.error("Failed to generate Excel file")
                
                else:
                    st.error(f"❌ Scraping failed: {result['error']}")
                    if result["warnings"]:
                        with st.expander("Warnings", expanded=False):
                            for warning in result["warnings"]:
                                st.warning(warning)

with tab2:
    st.header("Scrape from Configured Site")
    
    if selected_site and selected_site != "None":
        site_id = selected_site.split(" - ")[0]
        site_info = next((s for s in sites if s["id"] == site_id), None)
        
        if site_info:
            st.info(f"**Site:** {site_info['name']}\n\n**URL:** {site_info['page_url']}")
            
            col1, col2 = st.columns([1, 4])
            with col1:
                scrape_site_button = st.button("Scrape This Site", type="primary")
            
            if scrape_site_button:
                with st.spinner("Scraping data... This may take a moment."):
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    status_text.text("Step 1/3: Loading site configuration...")
                    progress_bar.progress(33)
                    
                    result = api.scrape_configured_site(
                        site_id=site_id,
                        use_stealth=use_stealth,
                        override_robots=override_robots,
                    )
                    
                    progress_bar.progress(100)
                    status_text.text("Complete!")
                    
                    if result["success"]:
                        st.success(f"✅ Successfully extracted {result['rows']} rows of data!")
                        
                        # Show warnings if any
                        if result["warnings"]:
                            with st.expander("⚠️ Validation Warnings", expanded=False):
                                for warning in result["warnings"]:
                                    st.warning(warning)
                        
                        # Data preview
                        st.subheader("Data Preview")
                        preview_rows = st.slider("Rows to display:", 10, min(100, result["rows"]), 50, key="site_preview")
                        st.dataframe(result["data"].head(preview_rows), width='stretch')
                        
                        # Download section
                        st.subheader("Download")
                        excel_bytes, filename = api.export_to_excel(result["data"], filename=f"{site_id}_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}")
                        
                        if excel_bytes:
                            st.download_button(
                                label="📥 Download Excel File",
                                data=excel_bytes,
                                file_name=filename,
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                type="primary",
                            )
                            st.info(f"File size: {len(excel_bytes) / 1024:.2f} KB")
                        else:
                            st.error("Failed to generate Excel file")
                    
                    else:
                        st.error(f"❌ Scraping failed: {result['error']}")
    else:
        st.info("Select a configured site from the sidebar to scrape data.")

with tab3:
    st.header("📰 Latest Fintech News")
    st.markdown("Stay updated with the latest financial technology news and market insights.")
    
    # News sources configuration
    news_sources = [
        {
            "name": "CoinDesk",
            "url": "https://www.coindesk.com",
            "description": "Cryptocurrency and blockchain news"
        },
        {
            "name": "The Block",
            "url": "https://www.theblock.co",
            "description": "Crypto markets and data"
        },
        {
            "name": "Decrypt",
            "url": "https://decrypt.co",
            "description": "Crypto news and analysis"
        },
        {
            "name": "CoinTelegraph",
            "url": "https://cointelegraph.com",
            "description": "Bitcoin and cryptocurrency news"
        },
    ]
    
    # Display news sources
    st.subheader("Available News Sources")
    cols = st.columns(2)
    
    for idx, source in enumerate(news_sources):
        with cols[idx % 2]:
            with st.container():
                st.markdown(f"### {source['name']}")
                st.caption(source['description'])
                st.markdown(f"[Visit Website →]({source['url']})")
                st.markdown("---")
    
    # News scraping section
    st.subheader("Scrape News Articles")
    st.info("💡 Tip: Use the 'Scrape from URL' tab to extract news articles from these sources.")
    
    # Quick links to scrape news
    st.markdown("### Quick Scrape Links")
    news_url_input = st.text_input(
        "Enter news article URL:",
        placeholder="https://www.coindesk.com/...",
        key="news_url"
    )
    
    if st.button("Scrape News Article", key="scrape_news"):
        if news_url_input:
            if not news_url_input.startswith(("http://", "https://")):
                st.error("Please enter a valid URL starting with http:// or https://")
            else:
                with st.spinner("Scraping news article... This may take a moment."):
                    result = api.scrape_url(
                        url=news_url_input,
                        use_stealth=use_stealth,
                        override_robots=override_robots,
                        use_fallbacks=use_fallbacks,
                    )
                    
                    if result["success"]:
                        st.success(f"✅ Successfully extracted {result['rows']} rows of data!")
                        st.dataframe(result["data"], width='stretch')
                    else:
                        st.error(f"❌ Scraping failed: {result.get('error', 'Unknown error')}")

with tab4:
    st.header("📈 Market Sentiment Indicators")
    st.markdown("Fetch economic indicators from FRED (Federal Reserve Economic Data) API.")
    
    # Check for FRED API key
    fred_api_key = os.getenv("FRED_API_KEY")
    if not fred_api_key:
        st.warning("⚠️ FRED_API_KEY not found in environment variables. Please set it in your .env file.")
        st.info("Get your API key from: https://fred.stlouisfed.org/docs/api/api_key.html")
    else:
        st.success("✅ FRED API key found")
    
    # Get FRED sentiment sites
    fred_sites = [s for s in sites if s.get("id", "").startswith("fred_")]
    
    if fred_sites:
        st.subheader("Available Market Sentiment Indicators")
        
        # Display indicators in columns
        cols = st.columns(2)
        for idx, site in enumerate(fred_sites):
            with cols[idx % 2]:
                with st.container():
                    st.markdown(f"### {site['name']}")
                    st.caption(site.get('metadata', {}).get('notes', 'No description'))
                    st.markdown(f"[View on FRED →]({site['page_url']})")
                    st.markdown("---")
        
        # Bulk scraping option
        st.subheader("Fetch Market Sentiment Data")
        
        col1, col2 = st.columns([1, 4])
        with col1:
            scrape_all_button = st.button("Fetch All Indicators", type="primary")
        
        if scrape_all_button:
            if not fred_api_key:
                st.error("FRED API key is required. Please set FRED_API_KEY in your .env file.")
            else:
                with st.spinner("Fetching market sentiment data from FRED... This may take a moment."):
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    all_data = []
                    latest_values = {}
                    
                    for idx, site in enumerate(fred_sites):
                        site_id = site["id"]
                        progress = (idx + 1) / len(fred_sites)
                        progress_bar.progress(progress)
                        status_text.text(f"Fetching {site['name']}... ({idx + 1}/{len(fred_sites)})")
                        
                        try:
                            result = api.scrape_configured_site(
                                site_id=site_id,
                                use_stealth=False,  # Not needed for API
                                override_robots=False,
                            )
                            
                            if result["success"] and result["data"] is not None and not result["data"].empty:
                                df = result["data"].copy()
                                # Add series name if not present
                                if "series_name" not in df.columns:
                                    df["series_name"] = site["name"]
                                
                                all_data.append(df)
                                
                                # Get latest value
                                if "value" in df.columns and "date" in df.columns:
                                    latest_row = df.iloc[0]  # Already sorted by date desc
                                    latest_values[site["name"]] = {
                                        "value": latest_row.get("value"),
                                        "date": latest_row.get("date"),
                                    }
                        except Exception as e:
                            st.warning(f"Failed to fetch {site['name']}: {str(e)[:100]}")
                    
                    progress_bar.progress(100)
                    status_text.text("Complete!")
                    
                    if all_data:
                        # Combine all data
                        combined_df = pd.concat(all_data, ignore_index=True)
                        
                        st.success(f"✅ Successfully fetched data from {len(all_data)} indicators!")
                        
                        # Display latest values as metrics
                        st.subheader("Latest Values")
                        metric_cols = st.columns(len(latest_values))
                        for idx, (name, data) in enumerate(latest_values.items()):
                            with metric_cols[idx % len(metric_cols)]:
                                value = data.get("value")
                                date = data.get("date")
                                if pd.notna(value):
                                    st.metric(
                                        label=name.split(" - ")[-1] if " - " in name else name,
                                        value=f"{float(value):.2f}" if isinstance(value, (int, float)) else str(value),
                                        delta=None
                                    )
                                    if pd.notna(date):
                                        st.caption(f"Date: {date}")
                        
                        # Display time series chart
                        st.subheader("Time Series Data")
                        if "date" in combined_df.columns and "value" in combined_df.columns:
                            # Pivot for charting
                            chart_df = combined_df.pivot_table(
                                index="date",
                                columns="series_name",
                                values="value",
                                aggfunc="first"
                            )
                            st.line_chart(chart_df)
                        
                        # Data preview
                        st.subheader("Data Preview")
                        preview_rows = st.slider("Rows to display:", 10, min(100, len(combined_df)), 50, key="sentiment_preview")
                        st.dataframe(combined_df.head(preview_rows), width='stretch')
                        
                        # Export option
                        if st.button("Export to Excel", key="export_sentiment"):
                            try:
                                excel_bytes, filename = api.export_to_excel(combined_df)
                                if excel_bytes:
                                    st.success("✅ Excel file generated successfully!")
                                    st.download_button(
                                        label="Download Excel File",
                                        data=excel_bytes,
                                        file_name=filename,
                                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                                    )
                                else:
                                    st.error("Failed to generate Excel file")
                            except Exception as e:
                                st.error(f"Export failed: {str(e)}")
                    else:
                        st.error("No data was successfully fetched. Please check your API key and try again.")
    else:
        st.info("No FRED market sentiment indicators configured. Please add them to websites.yaml.")

# Footer
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #666666;'>"
    "Data-Fetch Framework | Financial Data Scraper"
    "</div>",
    unsafe_allow_html=True
)

