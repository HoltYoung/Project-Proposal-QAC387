# Build 3: HITL + Tool Router Agent

This is the Build 3 assignment for QAC387 - a Human-in-the-Loop (HITL) data analysis agent with tool routing and Langfuse tracing.

## Purpose

This application demonstrates an AI agent that:
1. Accepts user questions about a dataset
2. Routes requests to either pre-built tools OR generates Python code
3. Requires human approval before executing code (HITL safety)
4. Provides natural language summaries of results
5. Traces all operations via Langfuse for evaluation

## Quick Start

### 1. Set up environment

```bash
cd build3
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Set API Keys

Create a `.env` file in the project root:

```bash
# Required: Choose your LLM provider
LLM_PROVIDER=kimi  # Options: kimi, openai, anthropic

# API Keys (at least one required)
KIMI_API_KEY=your_kimi_key_here
OPENAI_API_KEY=your_openai_key_here
ANTHROPIC_API_KEY=your_anthropic_key_here

# Langfuse Tracing (required for assignment)
LANGFUSE_PUBLIC_KEY=your_public_key
LANGFUSE_SECRET_KEY=your_secret_key
LANGFUSE_HOST=http://localhost:3000  # Or your Langfuse instance
```

### 3. Start Langfuse (if using local Docker)

```bash
cd langfuse-docker  # Your existing setup
docker-compose up -d
```

Then open http://localhost:3000 to view traces.

### 4. Run the Agent

```bash
python build3_hitl_tool_router_agent.py --data ../data/adult.csv --report_dir reports --tags build3
```

## Usage Commands

Once running, you can use these commands:

- `help` - Show all commands
- `schema` - Display dataset schema
- `suggest <question>` - Get analysis suggestions from LLM
- `ask <request>` - **Router mode**: Agent decides tool vs code generation
- `tool <request>` - **Force tool mode**: Use pre-built analysis tools
- `code <request>` - **Force code mode**: Generate Python script
- `run` - Execute last approved code
- `exit` - Quit

### Example Session

```
> schema
[Shows Adult dataset columns]

> ask what is the relationship between education and income?
[Router decides: use correlation tool]
Approve execution? (y/n): y
[Results shown with interpretation]

> code create a visualization of age distribution by income level
[Code generated]
Approve and save? (y/n): y
Code saved!

> run
Execute now? (y/n): y
[Script runs and saves outputs]
```

## Project Structure

```
build3/
├── build3_hitl_tool_router_agent.py  # Main agent
├── src/
│   ├── __init__.py
│   ├── tools.py                      # Tool registry (Build0)
│   ├── data_utils.py                 # Data loading utilities
│   └── llm_provider.py               # Multi-LLM support
├── reports/                          # Generated outputs
├── requirements.txt
└── README.md
```

## Deliverables for Assignment

1. ✅ `build3_hitl_tool_router_agent.py` - Main code file
2. ✅ `README.md` - This file
3. ✅ `requirements.txt` - Dependencies
4. ✅ Dataset - Uses `../data/adult.csv`
5. 📄 Langfuse tracing document - Generate after running

To generate the tracing document:
1. Run the agent with several commands
2. Go to Langfuse dashboard (http://localhost:3000)
3. Export traces or take screenshots
4. Write summary of performance and any issues

## Cautions

- **API Costs**: Each LLM call costs money. Monitor your usage.
- **Code Execution**: Generated code runs locally. Review before approving.
- **Data Privacy**: Dataset is sent to external LLM APIs.
- **Tool Limitations**: Pre-built tools only support specific analyses.

## Troubleshooting

**Langfuse not connecting?**
- Check LANGFUSE_HOST in .env
- Verify Docker containers are running: `docker ps`
- Default local URL: http://localhost:3000

**API errors?**
- Verify your API key in .env
- Check LLM_PROVIDER matches the key you have
- Ensure you have credits/billing set up

**Import errors?**
- Make sure you're in the virtual environment
- Re-install: `pip install -r requirements.txt`
