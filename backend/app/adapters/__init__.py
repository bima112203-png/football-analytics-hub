from app.adapters.base import FootballDataProvider
from app.adapters.football_data import FootballDataOrgAdapter
from app.adapters.api_football import ApiFootballAdapter
from app.adapters.fotmob import FotMobAdapter
from app.adapters.footystats import FootyStatsAdapter
from app.adapters.mock_seed import MockSeedAdapter
from app.config import settings


def get_provider() -> FootballDataProvider:
    """Factory adapter sumber data sesuai konfigurasi DATA_PROVIDER."""
    provider = settings.DATA_PROVIDER.lower().strip()
    if provider == "football-data" and settings.FOOTBALL_DATA_API_KEY:
        return FootballDataOrgAdapter(settings.FOOTBALL_DATA_API_KEY)
    if provider == "api-football" and settings.API_FOOTBALL_KEY:
        return ApiFootballAdapter(settings.API_FOOTBALL_KEY)
    if provider == "fotmob":
        return FotMobAdapter()
    if provider == "footystats" and settings.FOOTYSTATS_API_KEY:
        return FootyStatsAdapter(settings.FOOTYSTATS_API_KEY)
    return MockSeedAdapter()
