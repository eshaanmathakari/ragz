# Replit Setup Guide

This guide will help you migrate and deploy the Data-Fetch Streamlit application to Replit.

## Overview

Replit provides native support for Playwright browsers and better control over system dependencies compared to Streamlit Cloud. This migration ensures all browser automation features work correctly.

## Prerequisites

- A Replit account (free tier works)
- Your API keys ready (see `env.example` for list)

## Step 1: Import Project to Replit

1. **Create a new Repl**
   - Go to [Replit](https://replit.com)
   - Click "Create Repl"
   - Select "Import from GitHub" (if your repo is on GitHub)
   - OR use "Template" → "Python" and upload your files

2. **Set the root directory**
   - If importing the entire repo, make sure to set the working directory to `data-fetch/`
   - Or create the Repl directly in the `data-fetch/` folder

## Step 2: Configure Secrets (Environment Variables)

Replit uses a Secrets tool instead of `.streamlit/secrets.toml`. All secrets are automatically available as environment variables.

1. **Open Secrets Tool**
   - Click the lock icon (🔒) in the left sidebar
   - Or go to Tools → Secrets

2. **Add Required Secrets**
   
   Add the following secrets (one per line, key=value format):
   
   ```
   OPENAI_API_KEY=sk-your-openai-key-here
   ```
   
   **Optional API Keys** (add if you plan to use these services):
   ```
   COINGECKO_API_KEY=your-coingecko-key-here
   COINGECKO_USE_PRO=false
   COINDESK_API_KEY=your-coindesk-key-here
   CRYPTOCOMPARE_API_KEY=your-cryptocompare-key-here
   ALPHA_VANTAGE_API_KEY=your-alpha-vantage-key-here
   DUNE_API_KEY=your-dune-api-key-here
   FRED_API_KEY=your-fred-api-key-here
   ```
   
   **Optional Configuration**:
   ```
   USER_AGENT=DataFetchBot/1.0 (Educational purposes)
   LOG_LEVEL=INFO
   USE_STEALTH_MODE=true
   COOKIE_STORAGE_PATH=~/.data-fetch/cookies
   SESSION_TIMEOUT=3600
   AUTH_RETRY_ATTEMPTS=2
   ```

3. **Save Secrets**
   - Click "Save" or "Add Secret" for each one
   - Secrets are automatically available as environment variables in your app

## Step 3: Install Dependencies

Replit will automatically install Python dependencies from `requirements.txt` when you first run the app. However, you can also install manually:

1. **Open the Shell** (bottom panel or Tools → Shell)
2. **Install Python packages**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Install Playwright browsers** (this happens automatically via `onBoot` in `.replit`, but you can run manually):
   ```bash
   python -m playwright install chromium --with-deps
   ```

## Step 4: Run the Application

1. **Click the "Run" button** in Replit
   - The app will start automatically using the configuration in `.replit`
   - Streamlit will run on port 8501

2. **Access the App**
   - Replit will show a webview with your app
   - Or use the public URL provided by Replit (if deployed)

## Step 5: Deploy (Optional)

To make your app publicly accessible:

1. **Open Deployment Settings**
   - Click the "Deploy" button in the sidebar
   - Or go to Tools → Deployment

2. **Configure Deployment**
   - The `.replit` file already has deployment settings configured
   - Select "Replit Cloud" or your preferred deployment target
   - Click "Deploy"

3. **Access Public URL**
   - Once deployed, you'll get a public URL
   - Share this URL to access your app from anywhere

## File Structure in Replit

```
data-fetch/
├── .replit              # Replit configuration (entrypoint, run commands)
├── replit.nix           # System dependencies (Nix packages)
├── app.py               # Main Streamlit application
├── requirements.txt     # Python dependencies
├── config/
│   └── websites.yaml    # Site configurations
├── src/                 # Source code (all scrapers)
└── outputs/             # Output directory
```

## Key Differences from Streamlit Cloud

### 1. Secrets Management
- **Streamlit Cloud**: `.streamlit/secrets.toml` or dashboard
- **Replit**: Secrets tool (lock icon) → automatically available as `os.getenv()`

### 2. System Dependencies
- **Streamlit Cloud**: `packages.txt` (Debian packages)
- **Replit**: `replit.nix` (Nix packages) + Playwright `onBoot` command

### 3. Browser Installation
- **Streamlit Cloud**: Post-install script (limited on free tier)
- **Replit**: `onBoot` command in `.replit` file (works reliably)

### 4. Configuration
- **Streamlit Cloud**: `.streamlit/config.toml`
- **Replit**: `.replit` file (TOML format)

### 5. Port Configuration
- **Streamlit Cloud**: Automatic (port 8501)
- **Replit**: Explicit in `.replit` file (port 8501, address 0.0.0.0)

## Troubleshooting

### Issue: Playwright browsers not installing

**Solution**: 
1. Check the Shell output for errors
2. Manually run: `python -m playwright install chromium --with-deps`
3. Verify system dependencies are installed via `replit.nix`

### Issue: Environment variables not found

**Solution**:
1. Verify secrets are set in Replit Secrets tool (lock icon)
2. Check that secret names match exactly (case-sensitive)
3. Restart the Repl after adding secrets
4. Use `os.getenv("KEY_NAME")` in code (already implemented)

### Issue: Port binding errors

**Solution**:
1. Ensure `.replit` file has correct port configuration:
   ```toml
   [[ports]]
   localPort = 8501
   externalPort = 80
   ```
2. Check that `--server.address=0.0.0.0` is in the run command

### Issue: App not starting

**Solution**:
1. Check Shell output for error messages
2. Verify `requirements.txt` dependencies are installed
3. Ensure `app.py` is the entrypoint in `.replit`
4. Check that all imports work (run `python -c "import streamlit"`)

### Issue: Browser automation not working

**Solution**:
1. Verify Playwright is installed: `python -m playwright --version`
2. Check browsers are installed: `python -m playwright install chromium`
3. Verify system dependencies via `replit.nix`
4. Check browser launch in code (should work automatically)

### Issue: Deployment fails

**Solution**:
1. Check deployment logs in Replit
2. Verify `.replit` deployment section is correct
3. Ensure all dependencies are in `requirements.txt`
4. Check that port 8501 is accessible

## Migration Checklist

- [x] Create `.replit` file with proper configuration
- [x] Create `replit.nix` with system dependencies
- [x] Update `app.py` to remove Streamlit secrets dependency
- [x] Configure port binding (port 8501)
- [x] Set up Playwright browser installation via `onBoot`
- [ ] Import project to Replit
- [ ] Add secrets via Replit Secrets tool
- [ ] Test app runs correctly
- [ ] Verify Playwright browsers work
- [ ] Test all scrapers (CoinGlass, dental ETFs, etc.)
- [ ] Deploy and verify public URL works

## Next Steps

1. **Test Locally**: Run the app in Replit and verify all features work
2. **Test Scrapers**: Try scraping from CoinGlass, dental ETFs, and market sentiment sources
3. **Deploy**: Deploy to get a public URL
4. **Monitor**: Check logs for any errors or warnings

## Support

If you encounter issues:
1. Check the troubleshooting section above
2. Review Replit documentation: https://docs.replit.com
3. Check app logs in Replit Shell
4. Verify all secrets are set correctly

## Notes

- The `.streamlit/` directory is hidden in Replit (not needed)
- `packages.txt` is replaced by `replit.nix`
- All secrets must be set via Replit Secrets tool (not `.env` file in production)
- Playwright browsers are installed automatically on boot via `onBoot` command
