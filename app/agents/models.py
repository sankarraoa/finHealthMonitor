"""Data models for Payroll Risk Early Warning System."""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime


class HealthStatus(Enum):
    """Payroll risk health status."""
    GREEN = "Green"
    YELLOW = "Yellow"
    RED = "Red"


class DetectionTier(Enum):
    """Payroll detection confidence tier."""
    TIER_0 = 0  # Xero Payroll data (Very High)
    TIER_1 = 1  # GL mappings/journals (High)
    TIER_2 = 2  # Known payroll providers (Medium)
    TIER_3 = 3  # Recurring patterns (Medium-Low)
    TIER_4 = 4  # Statistical inference (Low)


@dataclass
class Scenario:
    """Cash flow scenario projection."""
    projected_cash: float
    coverage_ratio: float


@dataclass
class Evidence:
    """Evidence references from Xero data."""
    bank_transactions: List[str] = field(default_factory=list)
    bank_transfers: List[str] = field(default_factory=list)
    invoices_ar: List[str] = field(default_factory=list)
    bills_ap: List[str] = field(default_factory=list)
    credit_notes: List[str] = field(default_factory=list)
    journals: List[str] = field(default_factory=list)
    payroll_objects: List[str] = field(default_factory=list)
    report_refs: List[str] = field(default_factory=list)
    fx_rates: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class PayrollRiskResult:
    """Complete payroll risk assessment result."""
    # Core metadata
    model_version: str = "1.0.0"
    org_id: str = ""
    as_of_utc: str = ""
    
    # Payroll information
    payroll_date: str = ""
    payroll_amount_net: float = 0.0
    payroll_employer_costs: Optional[float] = None
    payroll_amount_with_buffer: float = 0.0
    
    # Cash position
    current_cash_available: float = 0.0
    projected_cash_on_payroll_date: float = 0.0
    payroll_coverage_ratio: float = 0.0
    
    # Classification
    health_status: HealthStatus = HealthStatus.RED
    near_miss: bool = False
    
    # Detection metadata
    detection_tier: DetectionTier = DetectionTier.TIER_4
    detection_confidence: str = "VeryLow"  # High|Medium|Low|VeryLow
    forecast_confidence: int = 0  # 0-100
    data_completeness_score: int = 0  # 0-100
    
    # Analysis
    key_risk_drivers: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    scenarios: Dict[str, Scenario] = field(default_factory=dict)
    
    # Evidence & audit
    evidence: Evidence = field(default_factory=Evidence)
    used_endpoints: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    missing_data: Optional[List[str]] = None
    
    # Actions
    recommended_actions: List[str] = field(default_factory=list)
    
    # Narrative
    advisory_narrative: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "model_version": self.model_version,
            "org_id": self.org_id,
            "as_of_utc": self.as_of_utc,
            "payroll_date": self.payroll_date,
            "payroll_amount_net": self.payroll_amount_net,
            "payroll_employer_costs": self.payroll_employer_costs,
            "payroll_amount_with_buffer": self.payroll_amount_with_buffer,
            "current_cash_available": self.current_cash_available,
            "projected_cash_on_payroll_date": self.projected_cash_on_payroll_date,
            "payroll_coverage_ratio": self.payroll_coverage_ratio,
            "health_status": self.health_status.value,
            "near_miss": self.near_miss,
            "detection_tier": self.detection_tier.value,
            "detection_confidence": self.detection_confidence,
            "forecast_confidence": self.forecast_confidence,
            "data_completeness_score": self.data_completeness_score,
            "key_risk_drivers": self.key_risk_drivers,
            "assumptions": self.assumptions,
            "scenarios": {
                k: {"projected_cash": v.projected_cash, "coverage_ratio": v.coverage_ratio}
                for k, v in self.scenarios.items()
            },
            "evidence": {
                "bank_transactions": self.evidence.bank_transactions,
                "bank_transfers": self.evidence.bank_transfers,
                "invoices_ar": self.evidence.invoices_ar,
                "bills_ap": self.evidence.bills_ap,
                "credit_notes": self.evidence.credit_notes,
                "journals": self.evidence.journals,
                "payroll_objects": self.evidence.payroll_objects,
                "report_refs": self.evidence.report_refs,
                "fx_rates": self.evidence.fx_rates,
            },
            "used_endpoints": self.used_endpoints,
            "warnings": self.warnings,
            "missing_data": self.missing_data,
            "recommended_actions": self.recommended_actions,
            "advisory_narrative": self.advisory_narrative,
        }

