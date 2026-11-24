class GateError(RuntimeError):
    """Raised by every pipeline invariant gate."""


class RenderError(RuntimeError):
    """Raised when a number or string cannot be rendered from the manifests."""
