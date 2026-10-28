from app.models import Category, Condition, Listing, ListingStatus, User
from tests.conftest import auth_header


def test_market_pulse_returns_insights_and_fast_moving_products(client, db_session):
    # 1. Check endpoint returns 200 with complete MarketPulse structure
    res = client.get("/analytics/market-pulse")
    assert res.status_code == 200, res.text
    data = res.json()

    assert "total_active_listings" in data
    assert "total_completed_sales" in data
    assert "total_volume_traded" in data
    assert "total_bids_placed" in data
    assert "overall_sell_through_rate" in data
    assert "fast_moving" in data
    assert "category_trends" in data
    assert "student_interests" in data
    assert "recent_successful_sales" in data

    # Verify categories structure
    categories = data["category_trends"]
    assert len(categories) == 6
    cat_names = [c["category"] for c in categories]
    assert "cycle" in cat_names
    assert "calculator" in cat_names

    # Check student interests structure
    interests = data["student_interests"]
    assert len(interests) >= 1
    assert "keyword" in interests[0]
    assert "unfilled_demand" in interests[0]
