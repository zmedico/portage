
from portage.exception import PortageException


class RequiredUseException(PortageException):
    """A problem with a REQUIRED_USE string has been encountered"""


class InvalidRequiredUse(RequiredUseException):
    """An invalid REQUIRED_USE string has been encountered"""
    def __init__(self, value, errors=None):
        RequiredUseException.__init__(self, value)
        self.errors = errors


class ImmutabilityError(RequiredUseException):
    def __init__(self, flag_name):
        super(ImmutabilityError, self).__init__(
            'Immutability error: value of %s mismatches' % flag_name)
        self.flag_name = flag_name


class InfiniteLoopError(RequiredUseException):
    def __init__(self):
        super(InfiniteLoopError, self).__init__(
            'Constraints cause infinite loop')


class MaxIterationsError(RequiredUseException):
    def __init__(self, iterations):
        super(MaxIterationsError, self).__init__(
            'Constraints not solved within {} iterations'.format(iterations))
