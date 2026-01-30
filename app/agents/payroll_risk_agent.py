"""Main Payroll Risk Agent Orchestrator."""
import logging
from typing import Optional, Callable
from datetime import datetime, timezone

from app.mcp_client import XeroMCPClient
from app.agents.data_gatherer import DataGatherer
from app.agents.llm_engine import create_llm_engine
from app.agents.models import PayrollRiskResult

logger = logging.getLogger(__name__)


class PayrollRiskAgent:
    """
    Agentic system for Payroll Risk Early Warning.
    
    Orchestrates the full workflow:
    1. Data Gathering (iterative, exhaustive)
    2. LLM Analysis (payroll detection, cash forecasting)
    3. Result Generation (JSON + narrative)
    """
    
    def __init__(self, bearer_token: str, tenant_id: Optional[str] = None, llm_model: Optional[str] = None, use_agentic: Optional[bool] = None, progress_callback: Optional[Callable[[int, str], None]] = None):
        """
        Initialize the Payroll Risk Agent.
        
        Args:
            bearer_token: Xero access token
            tenant_id: Optional tenant/organization ID to use for API calls
            llm_model: Optional LLM model name (for OpenAI only, ignored for Toqan)
            use_agentic: Optional flag to override config.USE_AGENTIC_ARCHITECTURE
            progress_callback: Optional callback function(progress: int, message: str) for progress updates
        """
        self.mcp_client = XeroMCPClient(bearer_token=bearer_token, tenant_id=tenant_id)
        self.data_gatherer = DataGatherer(self.mcp_client)
        self.data_gatherer.set_progress_callback(progress_callback)
        self.llm_engine = create_llm_engine(model=llm_model, use_agentic=use_agentic)
        self.progress_callback = progress_callback
        self._initialized = False
    
    async def run(self) -> PayrollRiskResult:
        """
        Execute the full agent workflow.
        
        Returns:
            PayrollRiskResult with complete analysis
        """
        logger.info("Starting Payroll Risk Agent workflow")
        
        try:
            # Step 1: Initialize MCP connection
            if not self._initialized:
                logger.info("Initializing MCP client...")
                await self.mcp_client.initialize()
                self._initialized = True
            
            # Step 2: Gather all data
            logger.info("Step 1: Gathering data from Xero...")
            data, completeness_score = await self.data_gatherer.gather_all()
            
            # Check for blocking missing data
            missing_critical = self.data_gatherer.get_missing_critical_data()
            if missing_critical:
                logger.error(f"Missing critical data: {missing_critical}")
                result = PayrollRiskResult()
                result.data_completeness_score = completeness_score
                result.missing_data = missing_critical
                result.warnings = [f"Missing critical data: {', '.join(missing_critical)}"]
                result.advisory_narrative = f"Cannot complete analysis: missing critical data sources ({', '.join(missing_critical)}). Please ensure Xero connection is active."
                return result
            
            # Extract organization info
            org_data = data.get("organisation")
            if not org_data:
                logger.error("No organization data found")
                result = PayrollRiskResult()
                result.missing_data = ["organisation"]
                result.advisory_narrative = "Cannot complete analysis: organization data not available."
                return result
            
            # Parse organization details from text response
            org_id = self._extract_org_id(org_data)
            base_currency = self._extract_base_currency(org_data)
            
            # Step 3: LLM Analysis
            if self.progress_callback:
                self.progress_callback(65, "🤖 AI is thinking... Let me analyze your payroll risk")
            logger.info("Step 2: Running LLM analysis...")
            result = await self.llm_engine.analyze_payroll_risk(
                data=data,
                org_id=org_id,
                base_currency=base_currency,
                progress_callback=self.progress_callback
            )
            
            # Update completeness score
            result.data_completeness_score = completeness_score
            
            # Step 4: Add evidence from collected data
            self._add_evidence(result, data)
            
            logger.info(f"Agent workflow complete. Status: {result.health_status.value}")
            return result
            
        except Exception as e:
            logger.error(f"Error in agent workflow: {str(e)}", exc_info=True)
            result = PayrollRiskResult()
            result.warnings = [f"Workflow error: {str(e)}"]
            result.advisory_narrative = f"An error occurred during analysis: {str(e)}"
            return result
        
        finally:
            # Cleanup
            try:
                if self._initialized:
                    await self.mcp_client.close()
            except Exception as e:
                logger.warning(f"Error closing MCP client: {str(e)}")
    
    def _extract_org_id(self, org_data: any) -> str:
        """Extract organization ID from org data."""
        if isinstance(org_data, list):
            # Text response from MCP
            for item in org_data:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text", "")
                    if "Organisation ID:" in text:
                        # Extract ID from text
                        lines = text.split("\n")
                        for line in lines:
                            if "Organisation ID:" in line:
                                return line.split("Organisation ID:")[-1].strip()
        elif isinstance(org_data, dict):
            return org_data.get("organisationID", "")
        return "unknown"
    
    def _extract_base_currency(self, org_data: any) -> str:
        """Extract base currency from org data."""
        if isinstance(org_data, list):
            # Text response from MCP
            for item in org_data:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text", "")
                    if "Base Currency:" in text:
                        lines = text.split("\n")
                        for line in lines:
                            if "Base Currency:" in line:
                                return line.split("Base Currency:")[-1].strip()
        elif isinstance(org_data, dict):
            return org_data.get("baseCurrency", "USD")
        return "USD"
    
    def _add_evidence(self, result: PayrollRiskResult, data: dict):
        """Add evidence references from collected data."""
        # Extract IDs from various data sources
        if data.get("bank_transactions"):
            # Extract transaction IDs from text responses
            for item in data["bank_transactions"]:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text", "")
                    if "Bank Transaction ID:" in text:
                        # Extract ID
                        for line in text.split("\n"):
                            if "Bank Transaction ID:" in line:
                                tx_id = line.split("Bank Transaction ID:")[-1].strip()
                                if tx_id:
                                    result.evidence.bank_transactions.append(tx_id)
                                break
        
        # Similar extraction for other evidence types
        # (This is simplified - in production, you'd parse more thoroughly)
        if data.get("invoices"):
            result.evidence.invoices_ar = [f"invoice_{i}" for i in range(min(10, len(data["invoices"])))]
        
        if data.get("manual_journals"):
            result.evidence.journals = [f"journal_{i}" for i in range(min(10, len(data["manual_journals"])))]
        
        # Add used endpoints
        result.used_endpoints = list(self.data_gatherer.DATA_SOURCES)

