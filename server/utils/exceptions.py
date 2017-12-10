"""
Exceptions for Arx!
"""

class CommandError(Exception):
    pass


class PayError(CommandError):
    pass


class ActionSubmissionError(CommandError):
    pass
