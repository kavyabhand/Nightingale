import sys
import argparse
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from nightingale.config import config
from nightingale.demo.scenario import run_demo
from nightingale.api.webhook import run_webhook_server


def main():
    parser = argparse.ArgumentParser(
        description=f"{config.get('project_name')} v{config.get('version')} - Autonomous CI SRE Agent"
    )
    parser.add_argument(
        "--demo", 
        action="store_true", 
        help="Run the demo scenario with a broken test"
    )
    parser.add_argument(
        "--webhook",
        action="store_true",
        help="Start the FastAPI webhook server"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for webhook server (default: 8000)"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host for webhook server (default: 0.0.0.0)"
    )
    
    args = parser.parse_args()
    
    # Check for API key
    if not os.getenv("GEMINI_API_KEY"):
        print("⚠️  Warning: GEMINI_API_KEY not set")
        print("   Set it with: set GEMINI_API_KEY=your_key (Windows)")
        print("   Or: export GEMINI_API_KEY=your_key (Linux/Mac)")
        if not args.demo:
            sys.exit(1)

    if args.demo:
        run_demo()
    elif args.webhook:
        print(f"🐦 Starting Nightingale Webhook Server on {args.host}:{args.port}")
        run_webhook_server(host=args.host, port=args.port)
    else:
        print(f"""
🐦 Nightingale v{config.get('version')} - Autonomous CI SRE Agent

Usage:
  python main.py --demo      Run demo scenario
  python main.py --webhook   Start webhook server

For more info, see README.md
        """)

if __name__ == "__main__":
    main()
