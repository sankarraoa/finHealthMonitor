"""World State management for agentic architecture."""
import logging
from typing import Dict, Any, Optional
from datetime import datetime, date
from dataclasses import dataclass, field, asdict
import json

logger = logging.getLogger(__name__)


@dataclass
class CashPosition:
    """Current cash position summary."""
    current_cash: float = 0.0
    bank_accounts: list = field(default_factory=list)  # [{name, code, balance, currency}]
    last_update: Optional[str] = None
    pending_transactions: list = field(default_factory=list)
    

@dataclass
class PayrollProfile:
    """Payroll information summary."""
    cadence: str = "Unknown"  # "Bi-weekly", "Monthly", "Weekly", etc.
    next_payroll_date: Optional[str] = None  # ISO format
    expected_net_payroll: float = 0.0
    employer_costs: Optional[float] = None
    last_4_runs: list = field(default_factory=list)  # [{date, amount, journal_id}]
    total_entries_found: int = 0
    confidence: str = "Low"  # "High", "Medium", "Low"


@dataclass
class ARProfile:
    """Accounts Receivable summary."""
    total_ar: float = 0.0
    due_before_payroll: float = 0.0
    largest_5: list = field(default_factory=list)  # [{invoice_id, contact, amount, due_date}]
    total_count: int = 0
    aged_buckets: Dict[str, float] = field(default_factory=dict)  # {"0-30": amount, "31-60": amount, etc.}


@dataclass
class APProfile:
    """Accounts Payable summary."""
    total_ap: float = 0.0
    due_before_payroll: float = 0.0
    largest_5: list = field(default_factory=list)  # [{invoice_id, contact, amount, due_date}]
    total_count: int = 0
    aged_buckets: Dict[str, float] = field(default_factory=dict)


@dataclass
class BankHistoryProfile:
    """Bank transaction history summary."""
    last_90_days_count: int = 0
    total_inflow: float = 0.0
    total_outflow: float = 0.0
    net_flow: float = 0.0
    average_daily_flow: float = 0.0
    largest_transactions: list = field(default_factory=list)  # [{date, amount, type, description}]
    bank_fees_total: float = 0.0


@dataclass
class JournalProfile:
    """Manual journal entries summary."""
    payroll_journals: list = field(default_factory=list)  # POSTED only
    other_journals_count: int = 0
    total_posted: int = 0
    total_voided: int = 0


@dataclass
class WorldState:
    """Complete world state for agentic analysis."""
    org_id: str = ""
    org_name: str = ""
    base_currency: str = "USD"
    timezone: str = ""
    as_of_date: str = ""  # ISO format
    
    cash_position: CashPosition = field(default_factory=CashPosition)
    payroll_profile: PayrollProfile = field(default_factory=PayrollProfile)
    ar_profile: ARProfile = field(default_factory=ARProfile)
    ap_profile: APProfile = field(default_factory=APProfile)
    bank_history: BankHistoryProfile = field(default_factory=BankHistoryProfile)
    journal_profile: JournalProfile = field(default_factory=JournalProfile)
    
    # Metadata
    data_completeness: Dict[str, bool] = field(default_factory=dict)
    data_quality: Dict[str, str] = field(default_factory=dict)  # {"bank_history_days": "92", "payroll_confidence": "high"}
    
    # Available detail slices (for planner to request)
    available_detail_slices: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "org_id": self.org_id,
            "org_name": self.org_name,
            "base_currency": self.base_currency,
            "timezone": self.timezone,
            "as_of_date": self.as_of_date,
            "cash_position": asdict(self.cash_position),
            "payroll_profile": asdict(self.payroll_profile),
            "ar_profile": asdict(self.ar_profile),
            "ap_profile": asdict(self.ap_profile),
            "bank_history": asdict(self.bank_history),
            "journal_profile": asdict(self.journal_profile),
            "data_completeness": self.data_completeness,
            "data_quality": self.data_quality,
            "available_detail_slices": self.available_detail_slices
        }
    
    def to_summary_json(self) -> str:
        """Convert to JSON string for LLM consumption."""
        return json.dumps(self.to_dict(), indent=2, default=str)
    
    def get_available_slices_description(self) -> str:
        """Get human-readable description of available detail slices."""
        slices = []
        if self.available_detail_slices.get("invoices_ar"):
            slices.append(f"- AR Invoices: {len(self.available_detail_slices['invoices_ar'])} available")
        if self.available_detail_slices.get("invoices_ap"):
            slices.append(f"- AP Invoices: {len(self.available_detail_slices['invoices_ap'])} available")
        if self.available_detail_slices.get("bank_transactions"):
            slices.append(f"- Bank Transactions: {len(self.available_detail_slices['bank_transactions'])} available")
        if self.available_detail_slices.get("manual_journals"):
            slices.append(f"- Manual Journals: {len(self.available_detail_slices['manual_journals'])} available")
        if not slices:
            return "No additional detail slices available."
        return "\n".join(slices)
