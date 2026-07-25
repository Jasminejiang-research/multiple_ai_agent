# Tavily Search Integration

The controlled `search_web(...)` interface uses Tavily as its real search
provider. Create a Tavily API key, copy `.env.example` to `.env`, and set:

```dotenv
TAVILY_API_KEY=your-key-here
```

The provider forwards `allowed_domains`, `recency`, and `max_results` to Tavily
and converts results to `WebSearchResult`. A missing key, provider/API failure,
timeout, malformed response, and HTTP 429 rate limit produce explicit provider
exceptions. A valid response with no results returns an empty list.

Unit tests mock the HTTP client and never call Tavily. Real API calls are
optional local integration checks and must not run in CI:

```powershell
$env:TAVILY_API_KEY = "your-key-here"
python -c "from tools import search_web; print(search_web('European AI market', max_results=1))"
```

Do not commit `.env` or API keys.
