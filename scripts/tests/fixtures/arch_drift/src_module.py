"""Drift fixture: module is declared but also has an undeclared public function."""


def greet() -> str:
    """Say hello."""
    return "hello"


def undeclared_fn() -> str:
    """This function is NOT declared in architecture.yml — lint must fail."""
    return "undeclared"
