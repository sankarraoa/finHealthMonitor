"""Risk Planner Agent - LLM-based planning for data needs."""
import logging
import json
import re
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from app.agents.agents.world_state import WorldState
from app.agents.llm_engine import ToqanLLMEngine, OpenAILLMEngine

logger = logging.getLogger(__name__)


@dataclass
class DataRequest:
    """A request for additional data detail."""
    slice_type: str  # "invoices_ar", "invoices_ap", "bank_transactions", "manual_journals"
    filter_criteria: Dict[str, Any]  # {"top_n": 5, "due_before": "2026-01-15", etc.}
    reason: str  # Why this data is needed


@dataclass
class PlannerResponse:
    """Response from the risk planner."""
    need_more_data: bool
    requests: List[DataRequest]
    can_proceed: bool
    reasoning: str


class RiskPlannerAgent:
    """LLM-based agent that plans what additional data is needed."""
    
    def __init__(self, llm_client):
        """
        Initialize the Risk Planner Agent.
        
        Args:
            llm_client: LLM client (OpenAI or Toqan) for planning decisions
        """
        self.llm_client = llm_client
    
    async def plan(self, world_state: WorldState) -> PlannerResponse:
        """
        Analyze world state and determine if more data is needed.
        
        Args:
            world_state: Current world state with summaries
            
        Returns:
            PlannerResponse with data requests or proceed decision
        """
        logger.info("Risk Planner: Analyzing world state...")
        
        # Build planning prompt
        prompt = self._build_planning_prompt(world_state)
        
        # Call LLM for planning decision
        try:
            response_text = await self._call_llm(prompt)
            planner_response = self._parse_llm_response(response_text, world_state)
            return planner_response
        except Exception as e:
            logger.error(f"Error in risk planner: {e}", exc_info=True)
            # Default: proceed with current data
            return PlannerResponse(
                need_more_data=False,
                requests=[],
                can_proceed=True,
                reasoning=f"Planning error: {str(e)}. Proceeding with available data."
            )
    
    def _build_planning_prompt(self, world_state: WorldState) -> str:
        """Build the planning prompt for LLM."""
        return f"""You are a Risk Planner Agent for payroll risk analysis. Your job is to determine if you have enough data to make a confident payroll risk assessment, or if you need more detailed data slices.

**Current World State Summary:**

Organization: {world_state.org_name} ({world_state.org_id})
Base Currency: {world_state.base_currency}
As of Date: {world_state.as_of_date}

**Cash Position:**
- Current Cash: {world_state.cash_position.current_cash:.2f} {world_state.base_currency}
- Bank Accounts: {len(world_state.cash_position.bank_accounts)}

**Payroll Profile:**
- Cadence: {world_state.payroll_profile.cadence}
- Next Payroll Date: {world_state.payroll_profile.next_payroll_date or "Unknown"}
- Expected Net Payroll: {world_state.payroll_profile.expected_net_payroll:.2f} {world_state.base_currency}
- Confidence: {world_state.payroll_profile.confidence}
- Total Entries Found: {world_state.payroll_profile.total_entries_found}

**Accounts Receivable:**
- Total AR: {world_state.ar_profile.total_ar:.2f} {world_state.base_currency}
- Due Before Payroll: {world_state.ar_profile.due_before_payroll:.2f} {world_state.base_currency}
- Total Count: {world_state.ar_profile.total_count}

**Accounts Payable:**
- Total AP: {world_state.ap_profile.total_ap:.2f} {world_state.base_currency}
- Due Before Payroll: {world_state.ap_profile.due_before_payroll:.2f} {world_state.base_currency}
- Total Count: {world_state.ap_profile.total_count}

**Bank History (Last 90 Days):**
- Transactions: {world_state.bank_history.last_90_days_count}
- Net Flow: {world_state.bank_history.net_flow:.2f} {world_state.base_currency}

**Available Detail Slices:**
{world_state.get_available_slices_description()}

**Your Task:**

Analyze the world state and determine:
1. Do you have enough data to make a confident payroll risk assessment?
2. If not, what specific detail slices do you need?

**Available Detail Slices:**
- invoices_ar: AR invoices (can filter by top N, due dates, etc.)
- invoices_ap: AP invoices (can filter by top N, due dates, etc.)
- bank_transactions: Bank transaction details
- manual_journals: Manual journal entry details

**Response Format (JSON only):**

{{
  "need_more_data": true/false,
  "can_proceed": true/false,
  "reasoning": "Explanation of your decision",
  "requests": [
    {{
      "slice_type": "invoices_ar",
      "filter_criteria": {{"top_n": 5, "due_before": "2026-01-15"}},
      "reason": "Need to see largest AR invoices due before payroll"
    }}
  ]
}}

**Guidelines:**
- If payroll confidence is "Low" and you have < 2 payroll entries, you may need more journal details
- If AR/AP totals are large but you only have summaries, request top invoices
- If bank history is sparse (< 30 days), request more transaction details
- If you have sufficient data (payroll date known, cash position clear, AR/AP summarized), set can_proceed=true

Return ONLY the JSON object, no other text."""

    async def _call_llm(self, prompt: str) -> str:
        """Call LLM with planning prompt."""
        # Use the base LLM engine to make the call
        if isinstance(self.llm_client, ToqanLLMEngine):
            # Use Toqan
            conversation_id, _ = self.llm_client._create_conversation(prompt)
            conversations = self.llm_client._find_conversation(conversation_id)
            if isinstance(conversations, list) and len(conversations) > 1:
                last_message = conversations[-1]
                return last_message.get('message', '') if isinstance(last_message, dict) else str(last_message)
            else:
                raise ValueError("Unexpected conversation format from Toqan")
        elif isinstance(self.llm_client, OpenAILLMEngine):
            # Use OpenAI
            response = self.llm_client.client.chat.completions.create(
                model=self.llm_client.model,
                messages=[
                    {"role": "system", "content": "You are a risk planning agent. Return only JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=2000
            )
            return response.choices[0].message.content
        else:
            raise ValueError(f"Unsupported LLM client type: {type(self.llm_client)}")
    
    def _parse_llm_response(self, response_text: str, world_state: WorldState) -> PlannerResponse:
        """Parse LLM response into PlannerResponse."""
        try:
            import re
            # Try to extract JSON from response
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                response_json = json.loads(json_match.group(0))
            else:
                # Try parsing entire response
                response_json = json.loads(response_text)
            
            # Build requests
            requests = []
            for req_data in response_json.get("requests", []):
                requests.append(DataRequest(
                    slice_type=req_data.get("slice_type", ""),
                    filter_criteria=req_data.get("filter_criteria", {}),
                    reason=req_data.get("reason", "")
                ))
            
            return PlannerResponse(
                need_more_data=response_json.get("need_more_data", False),
                requests=requests,
                can_proceed=response_json.get("can_proceed", True),
                reasoning=response_json.get("reasoning", "")
            )
        except (json.JSONDecodeError, KeyError, Exception) as e:
            logger.error(f"Error parsing planner response: {e}")
            logger.debug(f"Response text: {response_text[:500]}")
            # Default: proceed with available data
            return PlannerResponse(
                need_more_data=False,
                requests=[],
                can_proceed=True,
                reasoning=f"Could not parse planner response: {str(e)}. Proceeding with available data."
            )
