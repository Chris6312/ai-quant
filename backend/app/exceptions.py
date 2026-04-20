"""Domain exceptions for the backend."""


class AppError(Exception):
    """Base class for application errors."""


class DatabaseUnavailableError(AppError):
    """Raised when the database cannot be reached."""


class CacheUnavailableError(AppError):
    """Raised when Redis cannot be reached."""


class RepositoryError(AppError):
    """Raised when a repository operation fails."""


class ResearchServiceError(AppError):
    """Raised when a research workflow fails."""


class ResearchAPIError(ResearchServiceError):
    """Raised when an external research API request fails."""


class ResearchParseError(ResearchServiceError):
    """Raised when a research payload cannot be parsed."""


class WatchlistPromotionError(ResearchServiceError):
    """Raised when a watchlist promotion or demotion fails."""


class TrainingDataValidationError(AppError):
    """Raised when training data fails validation rules."""


class CandleValidationError(AppError):
    """Raised when a market candle fails validation rules."""
