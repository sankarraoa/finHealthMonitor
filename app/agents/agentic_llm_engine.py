"""Agentic LLM Engine - Multi-agent architecture for payroll risk analysis."""
import logging
import json
from typing import Dict, Any, Optional, Callable
from datetime import datetime

from app.config import config
from app.agents.llm_engine import BaseLLMEngine, OpenAILLMEngine, ToqanLLMEngine
from app.agents.agents.world_state import WorldState
from app.agents.agents.summarization_agent import SummarizationAgent
from app.agents.agents.risk_planner_agent import RiskPlannerAgent, PlannerResponse, DataRequest
from app.agents.models import PayrollRiskResult

logger = logging.getLogger(__name__)


class AgenticLLMEngine(BaseLLMEngine):
    """
    Agentic LLM Engine that uses multi-agent architecture:
    1. SummarizationAgent: Extracts structured summaries from raw data
    2. RiskPlannerAgent: Plans what additional data is needed
    3. Final LLM: Performs risk analysis with structured summaries
    """
    
    def __init__(self, base_llm_engine: Optional[BaseLLMEngine] = None):
        """
        Initialize Agentic LLM Engine.
        
        Args:
            base_llm_engine: Base LLM engine (OpenAI or Toqan) for final analysis
        """
        super().__init__()
        
        # Use provided engine or create default
        if base_llm_engine:
            self.base_llm_engine = base_llm_engine
        else:
            # Create default based on config
            if config.LLM_PROVIDER.lower() == "toqan":
                self.base_llm_engine = ToqanLLMEngine()
            else:
                self.base_llm_engine = OpenAILLMEngine(model=config.OPENAI_MODEL)
        
        # Initialize world state
        self.world_state = WorldState()
        
        # Initialize agents
        self.summarization_agent = SummarizationAgent(self.world_state)
        self.risk_planner_agent = RiskPlannerAgent(self.base_llm_engine)
    
    async def analyze_payroll_risk(
        self,
        data: Dict[str, Any],
        org_id: str,
        base_currency: str,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> PayrollRiskResult:
        """
        Analyze payroll risk using agentic architecture.
        
        Args:
            data: Collected Xero data from DataGatherer
            org_id: Organization ID
            base_currency: Base currency code
            progress_callback: Optional callback for progress updates
            
        Returns:
            PayrollRiskResult with analysis
        """
        logger.info("Starting Agentic LLM analysis for payroll risk")
        
        try:
            # Step 1: Summarize all data into structured world state
            if progress_callback:
                progress_callback(70, "📋 Organizing data into structured summaries...")
            logger.info("Step 1: Summarizing data into structured world state...")
            self.world_state = self.summarization_agent.summarize_all(data)
            self.world_state.org_id = org_id
            self.world_state.base_currency = base_currency
            
            # Step 2: Risk Planner - determine if more data is needed
            if progress_callback:
                progress_callback(80, "🎯 Planning what data we need...")
            logger.info("Step 2: Risk Planner analyzing data needs...")
            planner_response = await self._run_planner()
            
            # Step 3: Fetch additional data if needed
            if planner_response.need_more_data and planner_response.requests:
                if progress_callback:
                    progress_callback(82, f"🔍 Fetching {len(planner_response.requests)} additional data points...")
                logger.info(f"Step 3: Fetching {len(planner_response.requests)} additional data slices...")
                self._fetch_additional_data(planner_response.requests, data)
                # Re-summarize with additional data
                self.world_state = self.summarization_agent.summarize_all(data)
            
            # Step 4: Final LLM analysis with structured summaries
            if progress_callback:
                progress_callback(85, "🧠 AI is doing some serious thinking...")
            logger.info("Step 4: Running final LLM analysis with structured summaries...")
            result = await self._run_final_analysis(progress_callback)
            
            logger.info(f"Agentic LLM analysis complete. Health status: {result.health_status.value}")
            if progress_callback:
                progress_callback(95, "✨ Analysis complete! Finalizing results...")
            return result
            
        except Exception as e:
            logger.error(f"Error in agentic LLM analysis: {str(e)}", exc_info=True)
            return self._create_error_result(str(e))
    
    async def _run_planner(self) -> PlannerResponse:
        """Run the risk planner agent."""
        try:
            # Use LLM-based planning
            logger.info("Risk Planner: Using LLM-based planning")
            planner_response = await self.risk_planner_agent.plan(self.world_state)
            return planner_response
        except Exception as e:
            logger.warning(f"Error in LLM planning, falling back to heuristic: {e}")
            # Fallback to heuristic
            need_more = False
            if self.world_state.payroll_profile.confidence == "Low" and self.world_state.payroll_profile.total_entries_found < 2:
                need_more = True
                logger.info("Risk Planner: Low payroll confidence detected, but proceeding with available data")
            
            return PlannerResponse(
                need_more_data=need_more,
                requests=[],
                can_proceed=True,
                reasoning=f"Planning error: {str(e)}. Proceeding with available structured summaries."
            )
    
    def _fetch_additional_data(self, requests: list[DataRequest], raw_data: Dict[str, Any]):
        """Fetch additional data slices based on planner requests."""
        # This would fetch specific slices from raw_data based on requests
        # For now, we'll just log the requests
        for req in requests:
            logger.info(f"Data request: {req.slice_type} - {req.reason}")
            # In a full implementation, we would filter and extract specific slices
            # and add them to the world state's available_detail_slices
    
    async def _run_final_analysis(self, progress_callback: Optional[Callable[[int, str], None]] = None) -> PayrollRiskResult:
        """Run final LLM analysis with structured summaries."""
        # Build prompt with world state summaries
        prompt = self._build_final_analysis_prompt()
        
        # Save prompt for review
        self._save_prompt_to_file(prompt, self.world_state.org_id)
        
        if progress_callback:
            progress_callback(88, "💭 AI is calculating your payroll risk...")
        
        # Use base LLM engine but with our structured prompt
        # We'll create a custom prompt that includes the world state
        if isinstance(self.base_llm_engine, ToqanLLMEngine):
            return await self._run_toqan_analysis(prompt)
        else:
            return await self._run_openai_analysis(prompt)
    
    def _build_final_analysis_prompt(self) -> str:
        """Build final analysis prompt with world state summaries."""
        world_state_json = self.world_state.to_summary_json()
        
        return f"""{self.prompt_template}

**Organization:** {self.world_state.org_name} ({self.world_state.org_id})
**Base Currency:** {self.world_state.base_currency}
**As of Date:** {self.world_state.as_of_date}

**Structured Data Summaries (World State):**

{world_state_json}

**CRITICAL: YOU MUST RETURN VALID JSON ONLY**

Even if data is missing or contains errors, you MUST return a valid JSON object with this exact structure:

{{
  "model_version": "1.0.0",
  "org_id": "{self.world_state.org_id}",
  "as_of_utc": "ISO timestamp",
  "payroll_date": "{self.world_state.payroll_profile.next_payroll_date or ''}",
  "payroll_amount_net": {self.world_state.payroll_profile.expected_net_payroll},
  "payroll_employer_costs": {self.world_state.payroll_profile.employer_costs or 'null'},
  "payroll_amount_with_buffer": 0,
  "current_cash_available": {self.world_state.cash_position.current_cash},
  "projected_cash_on_payroll_date": 0,
  "payroll_coverage_ratio": 0,
  "health_status": "Red",
  "near_miss": false,
  "detection_tier": 4,
  "detection_confidence": "{self.world_state.payroll_profile.confidence}",
  "forecast_confidence": 0,
  "data_completeness_score": 0,
  "key_risk_drivers": ["List any issues"],
  "assumptions": ["List assumptions"],
  "scenarios": {{
    "base": {{"projected_cash": 0, "coverage_ratio": 0}},
    "optimistic": {{"projected_cash": 0, "coverage_ratio": 0}},
    "pessimistic": {{"projected_cash": 0, "coverage_ratio": 0}}
  }},
  "evidence": {{"bank_transactions": [], "invoices_ar": [], "bills_ap": [], "credit_notes": [], "journals": [], "payroll_objects": [], "report_refs": [], "fx_rates": []}},
  "used_endpoints": [],
  "warnings": ["Explain any errors or missing data here"],
  "missing_data": ["List missing data sources"],
  "recommended_actions": ["List actions"],
  "advisory_narrative": "Explain the situation in ≤140 words"
}}

**IMPORTANT**: 
- Return ONLY the JSON object, no text before or after
- Use the structured summaries provided in the world state
- Calculate projected_cash_on_payroll_date based on current_cash + AR inflows - AP outflows
- Calculate payroll_coverage_ratio = projected_cash / payroll_amount_with_buffer
- Always return valid JSON, never plain text explanations"""

    async def _run_toqan_analysis(self, prompt: str) -> PayrollRiskResult:
        """Run analysis using Toqan LLM."""
        if not isinstance(self.base_llm_engine, ToqanLLMEngine):
            raise ValueError("Base engine is not ToqanLLMEngine")
        
        # Create conversation
        conversation_id, _ = self.base_llm_engine._create_conversation(prompt)
        
        # Wait for response
        conversations = self.base_llm_engine._find_conversation(conversation_id)
        
        # Extract and parse response
        if isinstance(conversations, list) and len(conversations) > 1:
            last_message = conversations[-1]
            ai_message = last_message.get('message', '') if isinstance(last_message, dict) else str(last_message)
            
            # Parse response using base engine's parsing logic
            cleaned_message = self.base_llm_engine._clean_ai_message(ai_message)
            result = self.base_llm_engine._parse_llm_response(cleaned_message)
            
            # Set metadata
            result.org_id = self.world_state.org_id
            result.as_of_utc = self._get_current_utc()
            
            return result
        else:
            raise ValueError(f"Unexpected conversation format from Toqan")
    
    async def _run_openai_analysis(self, prompt: str) -> PayrollRiskResult:
        """Run analysis using OpenAI LLM."""
        if not isinstance(self.base_llm_engine, OpenAILLMEngine):
            raise ValueError("Base engine is not OpenAILLMEngine")
        
        # Call OpenAI API
        response = self.base_llm_engine.client.chat.completions.create(
            model=self.base_llm_engine.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a financial risk analysis expert. Always return valid JSON followed by a narrative."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=4000
        )
        
        # Parse response
        response_text = response.choices[0].message.content
        result = self.base_llm_engine._parse_llm_response(response_text)
        
        # Set metadata
        result.org_id = self.world_state.org_id
        result.as_of_utc = self._get_current_utc()
        
        return result
    
    def _get_current_utc(self) -> str:
        """Get current UTC timestamp."""
        from datetime import timezone
        return datetime.now(timezone.utc).isoformat()
    
    def _create_error_result(self, error_message: str) -> PayrollRiskResult:
        """Create error result."""
        result = PayrollRiskResult()
        result.org_id = self.world_state.org_id
        result.as_of_utc = self._get_current_utc()
        result.warnings = [f"Agentic analysis error: {error_message}"]
        result.advisory_narrative = f"An error occurred during agentic analysis: {error_message}"
        return result
