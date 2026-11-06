class MigException(Exception):
    """
    Base class for all exceptions raised by Mig
    """

class NonEmptyDirectoryInitError(MigException):
    """
    Raised when initializing MIG in a non-empty directory without --force.
    """
