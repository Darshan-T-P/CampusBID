from fastapi import HTTPException, status

from app.services.errors import ListingError

_LISTING_STATUS = {
    "invalid": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "not_found": status.HTTP_404_NOT_FOUND,
    "forbidden": status.HTTP_403_FORBIDDEN,
    "conflict": status.HTTP_409_CONFLICT,
    "has_bids": status.HTTP_409_CONFLICT,
}


def listing_http_error(e: ListingError) -> HTTPException:
    """Turn a service-layer ListingError into the matching HTTP error."""
    return HTTPException(_LISTING_STATUS[e.code], e.message)
