"""Exceptions. Everything the framework raises on purpose derives from PipelineError."""


class PipelineError(Exception):
    """Base class: a problem the operator can fix (missing input, unreachable server, bad spec)."""


class ConfigError(PipelineError):
    """A setting is missing or malformed."""


class TransportError(PipelineError):
    """A model server could not be reached or answered with an error, after retries."""


class SpecError(PipelineError):
    """A page spec or workspace file does not have the expected shape."""


class GraphError(PipelineError):
    """The requested stages cannot be ordered (unknown stage, missing prerequisite, cycle)."""
