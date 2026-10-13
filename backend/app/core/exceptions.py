class AppError(Exception):
    """Base class for domain errors raised by the service layer.

    The API layer converts these into HTTP responses, so services stay
    independent of FastAPI.
    """

    status_code = 500

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class BadRequestError(AppError):
    status_code = 400


class PaymentRequiredError(AppError):
    status_code = 402


class ForbiddenError(AppError):
    status_code = 403


class NotFoundError(AppError):
    status_code = 404


class ConflictError(AppError):
    status_code = 409


class ServiceUnavailableError(AppError):
    status_code = 503
