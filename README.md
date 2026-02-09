# Nightingale 🐦

> Autonomous CI/CD Repair Agent powered by Gemini 3

[![Gemini 3 Hackathon](https://img.shields.io/badge/Gemini%203-Hackathon-blue)](https://gemini3.devpost.com/)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## What is Nightingale?

Nightingale is an **autonomous SRE agent** that monitors your CI/CD pipelines and automatically repairs failures using Gemini 3's advanced reasoning capabilities.

When your tests break at 2 AM, Nightingale:
1. **Analyzes** the failure logs
2. **Reasons** about root causes using Gemini 3
3. **Generates** minimal, targeted fixes
4. **Verifies** in an isolated sandbox
5. **Decides** to auto-resolve or escalate

## Quick Start

```bash
# Clone and install
git clone https://github.com/yourusername/nightingale.git
cd nightingale
pip install -r requirements.txt

# Set your Gemini API key
export GEMINI_API_KEY=your_key_here  # Linux/Mac
set GEMINI_API_KEY=your_key_here     # Windows

# Run the demo
python main.py --demo
```

## Features

### Reflective Reasoning Loop
- Up to 3 fix attempts
- Learns from verification failures
- Feeds logs back for root cause revision

### Weighted Confidence Scoring
```
confidence = 
    35% × test_pass_ratio +
    25% × inverse_blast_radius +
    15% × attempt_penalty +
    15% × risk_modifier +
    10% × self_consistency
```

### Safety First
- Sandbox isolation (never touches production)
- Blast radius analysis
- Automatic escalation when uncertain
- See [SAFETY.md](SAFETY.md) for details

### GitHub Integration
- Webhook listener for CI events
- Dynamic workflow parsing
- No hardcoded test commands

## Usage

### Demo Mode
```bash
python main.py --demo
```

### Webhook Server
```bash
python main.py --webhook --port 8000
```

### API Endpoints
- `GET /health` - Health check
- `POST /webhook/github` - GitHub webhook receiver
- `POST /incident` - Direct incident submission

## Architecture

See [ARCHITECTURE_DIAGRAM.md](ARCHITECTURE_DIAGRAM.md) for the full system architecture.

```
Incident → Parse → Context → [Analyze → Fix → Test]×3 → Score → Decide → Report
                              └─── Reflective Loop ───┘
```

## Documentation

- [ARCHITECTURE_DIAGRAM.md](ARCHITECTURE_DIAGRAM.md) - System architecture
- [SAFETY.md](SAFETY.md) - Safety and blast radius mitigation
- [TELEMETRY.md](TELEMETRY.md) - Metrics and logging
- [DEMO_SCRIPT.md](DEMO_SCRIPT.md) - 3-minute pitch script

## Gemini 3 Integration

Nightingale leverages Gemini 3's capabilities:

- **Advanced Reasoning**: Multi-step root cause analysis
- **Structured Output**: JSON schema validation for reliable parsing
- **Large Context**: Full repository context for informed decisions
- **Self-Correction**: Reflective loop for iterative improvement