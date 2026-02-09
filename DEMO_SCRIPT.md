# Nightingale Demo Script (3 Minutes)

## Opening (0:00 - 0:30)

**[Show terminal with Nightingale banner]**

> "Meet Nightingale - an autonomous CI repair agent powered by Gemini 3.
> 
> When your CI pipeline breaks at 2 AM, Nightingale wakes up, diagnoses the issue, 
> generates a fix, verifies it works, and either auto-resolves or escalates to you 
> with a detailed report.
>
> Let me show you how it works."

---

## Demo: Broken Test (0:30 - 2:00)

**[Show the broken test file]**

```python
def test_subtract():
    assert subtract(2, 2) == 1  # Bug: 2-2=0, not 1
```

> "Here's a simple bug - a test with a wrong assertion. In real projects, 
> these small mistakes can break entire pipelines."

**[Run the demo]**

```bash
set GEMINI_API_KEY=your_key
python main.py --demo
```

**[Narrate as it runs]**

> "Watch Nightingale in action:
>
> 1. **Context Loading** - It reads the repository and parses GitHub Actions
> 2. **Gemini Analysis** - Using Gemini 3's reasoning to find the root cause
> 3. **Fix Generation** - Proposing minimal, targeted changes
> 4. **Sandbox Testing** - Running tests in isolation
> 5. **Confidence Scoring** - Multi-factor analysis
> 6. **Decision** - Auto-resolve or escalate"

**[Show the fix being applied and tests passing]**

---

## Key Features (2:00 - 2:30)

**[Show architecture diagram briefly]**

> "Key innovations:
>
> - **Reflective Reasoning Loop**: Up to 3 attempts, learning from failures
> - **Weighted Confidence Scoring**: Test ratios, blast radius, risk analysis
> - **Dynamic Workflow Parsing**: No hardcoded commands
> - **Safety First**: Sandbox isolation, never touches production directly"

---

## Closing (2:30 - 3:00)

> "Nightingale transforms CI failures from 2 AM emergencies into autonomous 
> recoveries with human-grade reasoning.
>
> Built with Gemini 3's advanced reasoning capabilities, it doesn't just 
> fix bugs - it explains its thinking, measures confidence, and knows when 
> to ask for help.
>
> Thank you."

---

## Commands Reference

```bash
# Run demo
set GEMINI_API_KEY=your_key
python main.py --demo

# Start webhook server
python -m nightingale.api.webhook

# Direct test
cd demo_repo && python -m pytest -v
```
