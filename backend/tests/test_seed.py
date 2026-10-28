from sqlalchemy.orm import sessionmaker

from app.models import Bid, Listing, ListingStatus, Notification, User
from scripts import seed


def test_seed_builds_every_auction_state_and_notifications(db_session, media_dir):
    result = seed.run_seed(db_session, "college.edu")
    status = {title: db_session.get(Listing, l.id).status for title, l in result["listings"].items()}

    assert len(result["users"]) == 5 and db_session.query(User).filter(User.is_verified).count() == 5
    assert set(status.values()) == {
        ListingStatus.active, ListingStatus.pending_approval, ListingStatus.reserved,
        ListingStatus.completed, ListingStatus.unsold, ListingStatus.cancelled,
    }
    assert status["Scientific calculator (Sharp)"] == ListingStatus.pending_approval  # waiting for Meera
    assert status["Hercules city cycle"] == ListingStatus.reserved
    assert status["Organic Chemistry textbook"] == ListingStatus.completed
    assert db_session.query(Bid).count() > 10
    assert db_session.query(Notification).count() > 10  # created naturally by the services


def test_one_auction_closes_in_about_ninety_seconds_and_nothing_open_has_ended(db_session, media_dir):
    from app.core.clock import utcnow

    result = seed.run_seed(db_session, "college.edu")
    live = db_session.get(Listing, result["listings"]["Hero Sprint 21-speed cycle"].id)
    remaining = (live.closes_at - utcnow()).total_seconds()
    assert 60 < remaining <= 90
    assert live.status == ListingStatus.active


def test_photos_are_real_images_on_disk(db_session, media_dir):
    from app.services.listings import sniff_image_ext

    seed.run_seed(db_session, "college.edu")
    files = list((media_dir / "listings").rglob("*.png"))
    assert len(files) >= 15
    assert all(sniff_image_ext(f.read_bytes()) == "png" for f in files)


def test_wipe_then_seed_again(db_session, media_dir):
    seed.run_seed(db_session, "college.edu")
    seed.wipe(db_session)
    assert db_session.query(User).count() == 0 and not (media_dir / "listings").exists()
    seed.run_seed(db_session, "college.edu")
    assert db_session.query(User).count() == 5
