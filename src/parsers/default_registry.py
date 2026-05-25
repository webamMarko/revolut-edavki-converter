"""Build and return the default BrokerRegistry with all bundled adapters registered."""

from __future__ import annotations

from .registry import BrokerRegistry
from .revolut_stock import RevolutStockAdapter
from .revolut_cfd import RevolutCfdAdapter
from .revolut_crypto import RevolutCryptoAdapter
from .revolut_savings import RevolutSavingsAdapter
from .ilirika import IlirikaAdapter
from .ibkr import IbkrAdapter
from .trading212 import Trading212Adapter
from .degiro import DegiroAdapter


def build_default_registry() -> BrokerRegistry:
    """Return a BrokerRegistry with all bundled CSV adapters pre-registered.

    Ordering matters: more specific detectors (IBKR, Trading212, Degiro, Ilirika)
    are registered before the generic Revolut ones so they win when column sets overlap.
    """
    reg = BrokerRegistry()
    # External brokers first (more specific column fingerprints)
    reg.register(IbkrAdapter())
    reg.register(Trading212Adapter())
    reg.register(DegiroAdapter())
    reg.register(IlirikaAdapter())
    # Revolut variants
    reg.register(RevolutCfdAdapter())
    reg.register(RevolutCryptoAdapter())
    reg.register(RevolutSavingsAdapter())
    reg.register(RevolutStockAdapter())   # fallback — broadest Revolut match
    return reg
