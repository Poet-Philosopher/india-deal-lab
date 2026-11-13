"""Core data structures for India Deal Lab.

All money values are in INR crore (1 crore = 10 million) unless stated.
Share counts are in crore shares so that equity value / shares gives INR per share.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import List, Optional

CRORE = 1e7


@dataclass
class CompanyData:
    ticker: str
    name: str
    sector: str = ""
    industry: str = ""
    summary: str = ""
    currency: str = "INR"
    price: Optional[float] = None
    shares_cr: Optional[float] = None
    market_cap: Optional[float] = None
    total_debt: Optional[float] = None
    cash: Optional[float] = None
    years: List[str] = field(default_factory=list)
    revenue: List[float] = field(default_factory=list)
    ebitda: List[float] = field(default_factory=list)
    ebit: List[float] = field(default_factory=list)
    net_income: List[float] = field(default_factory=list)
    da: List[float] = field(default_factory=list)
    capex: List[float] = field(default_factory=list)
    nwc: Optional[float] = None
    tax_rate: float = 0.2517
    beta: Optional[float] = None
    week52_low: Optional[float] = None
    week52_high: Optional[float] = None
    source: str = "unknown"  # live | snapshot | sample
    as_of: str = ""
    warnings: List[str] = field(default_factory=list)

    # ---- derived -------------------------------------------------------
    @property
    def net_debt(self) -> Optional[float]:
        if self.total_debt is None or self.cash is None:
            return None
        return self.total_debt - self.cash

    @property
    def enterprise_value(self) -> Optional[float]:
        if self.market_cap is None or self.net_debt is None:
            return None
        return self.market_cap + self.net_debt

    @property
    def ltm_revenue(self) -> Optional[float]:
        return self.revenue[-1] if self.revenue else None

    @property
    def ltm_ebitda(self) -> Optional[float]:
        return self.ebitda[-1] if self.ebitda else None

    @property
    def ltm_net_income(self) -> Optional[float]:
        return self.net_income[-1] if self.net_income else None

    def is_complete(self) -> bool:
        """True when the fields every module needs are present and positive."""
        needed = [self.price, self.shares_cr, self.market_cap, self.total_debt, self.cash]
        if any(v is None for v in needed):
            return False
        if not self.revenue or not self.ebitda:
            return False
        return self.ltm_revenue > 0 and self.ltm_ebitda > 0 and self.shares_cr > 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "CompanyData":
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)
