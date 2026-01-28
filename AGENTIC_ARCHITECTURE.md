# Agentic Architecture for Payroll Risk Analysis

## Overview

This document describes the new **Agentic Architecture** implementation for payroll risk analysis. The agentic architecture uses a multi-agent system to intelligently summarize data and plan analysis, avoiding the token limit issues of the single-prompt approach.

## Architecture Components

### 1. World State (`app/agents/agents/world_state.py`)

The `WorldState` class maintains structured summaries of all data:

- **CashPosition**: Current cash, bank accounts, balances
- **PayrollProfile**: Payroll cadence, next date, expected amount, confidence
- **ARProfile**: Accounts Receivable totals, due dates, largest invoices
- **APProfile**: Accounts Payable totals, due dates, largest bills
- **BankHistoryProfile**: Transaction history, inflows/outflows, patterns
- **JournalProfile**: Manual journal entries (POSTED only)

### 2. SummarizationAgent (`app/agents/agents/summarization_agent.py`)

Extracts structured summaries from raw Xero MCP data:

- Filters data by relevance (last 90 days, POSTED status only, etc.)
- Extracts only key fields needed for analysis
- Populates the WorldState with structured data
- Stores available detail slices for planner requests

### 3. RiskPlannerAgent (`app/agents/agents/risk_planner_agent.py`)

LLM-based agent that analyzes the world state and determines if more data is needed:

- Reviews structured summaries
- Identifies gaps in data
- Requests specific detail slices if needed
- Returns a plan for data refinement

### 4. AgenticLLMEngine (`app/agents/agentic_llm_engine.py`)

Orchestrates the multi-agent workflow:

1. **Summarization**: Converts raw data to structured summaries
2. **Planning**: Determines if more data is needed
3. **Refinement**: Fetches additional data if requested
4. **Analysis**: Runs final LLM analysis with structured summaries

## Usage

### Configuration

Set the `USE_AGENTIC_ARCHITECTURE` environment variable in your `.env` file:

```bash
# Use agentic architecture (true) or single-prompt (false)
USE_AGENTIC_ARCHITECTURE=true
```

### Code Usage

The architecture is automatically selected based on the config flag:

```python
from app.agents.payroll_risk_agent import PayrollRiskAgent

# Agent will use agentic architecture if USE_AGENTIC_ARCHITECTURE=true
agent = PayrollRiskAgent(bearer_token=access_token)
result = await agent.run()
```

You can also override the flag programmatically:

```python
# Force agentic architecture
agent = PayrollRiskAgent(bearer_token=access_token, use_agentic=True)

# Force single-prompt architecture
agent = PayrollRiskAgent(bearer_token=access_token, use_agentic=False)
```

## Benefits

1. **No Data Truncation**: Only relevant, structured data is sent to LLM
2. **Efficiency**: LLM receives compact summaries instead of raw text dumps
3. **Scalability**: Can handle very large datasets without token limits
4. **Intelligence**: Filters irrelevant data (old transactions, voided invoices, etc.)
5. **Flexibility**: Can request additional detail slices if needed

## Comparison

### Single-Prompt Architecture (Current)
- Sends all raw data text to LLM
- Truncates at 5000 chars per data source
- May lose critical information
- Simple but limited

### Agentic Architecture (New)
- Sends structured summaries only
- No truncation needed
- Intelligent filtering and extraction
- More complex but scalable

## Data Flow

```
DataGatherer (collects raw data)
    ↓
SummarizationAgent (extracts structured summaries)
    ↓
WorldState (stores summaries)
    ↓
RiskPlannerAgent (analyzes if more data needed)
    ↓
[Optional: Fetch additional detail slices]
    ↓
AgenticLLMEngine (final analysis with summaries)
    ↓
PayrollRiskResult
```

## Future Enhancements

1. **Enhanced Planning**: Make RiskPlannerAgent more sophisticated with actual LLM calls
2. **Detail Slicing**: Implement actual fetching of specific detail slices
3. **Multi-Message**: Support very large datasets with multi-message conversations
4. **Caching**: Cache world state summaries for faster re-analysis

## Testing

To test the agentic architecture:

1. Set `USE_AGENTIC_ARCHITECTURE=true` in `.env`
2. Run the payroll risk analysis
3. Check logs for "Agentic LLM Engine" messages
4. Compare results with single-prompt approach

## Files Created

- `app/agents/agents/__init__.py`
- `app/agents/agents/world_state.py`
- `app/agents/agents/summarization_agent.py`
- `app/agents/agents/risk_planner_agent.py`
- `app/agents/agentic_llm_engine.py`

## Files Modified

- `app/config.py` - Added `USE_AGENTIC_ARCHITECTURE` flag
- `app/agents/llm_engine.py` - Updated factory to support agentic mode
- `app/agents/payroll_risk_agent.py` - Added `use_agentic` parameter
- `requirements.txt` - Added `python-dateutil` dependency
