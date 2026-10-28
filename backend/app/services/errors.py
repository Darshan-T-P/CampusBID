class ListingError(Exception):
    """A listing action was refused.

    `code` decides the HTTP status in the route layer:
    invalid -> 422, not_found -> 404, forbidden -> 403, conflict -> 409.
    """

    def __init__(self, message: str, code: str = "invalid"):
        super().__init__(message)
        self.message = message
        self.code = code


class AccountError(Exception):
    """An account action was refused.

    `code` decides the HTTP status in the route layer:
    invalid -> 422, conflict -> 409, forbidden -> 403, rate_limited -> 429.
    """

    def __init__(self, message: str, code: str = "invalid"):
        super().__init__(message)
        self.message = message
        self.code = code
