import sys
import argparse
from nightingale.config import config
from nightingale.demo.scenario import run_demo

def main():
    parser = argparse.ArgumentParser(description=f"{config.get('project_name')} v{config.get('version')}")
    parser.add_argument("--demo", action="store_true", help="Run the demo scenario")
    args = parser.parse_args()

    if args.demo:
        run_demo()
    else:
        print("Starting in standard mode (listener not fully implemented for CLI yet)")
        print("Run with --demo to see the autonomous agent in action.")
    
if __name__ == "__main__":
    main()
