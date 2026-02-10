"""
Nightingale — Autonomous CI SRE Agent
Entry point with all commands
"""
import sys
import os
import shutil
import argparse
import importlib


def require_api_key():
    """Check GEMINI_API_KEY is set. Print clear error and exit if not."""
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        print("""
ERROR: GEMINI_API_KEY not set.

Set it using:

  PowerShell:
    $env:GEMINI_API_KEY = 'your_key_here'

  Linux/macOS:
    export GEMINI_API_KEY='your_key_here'
""")
        sys.exit(1)
    return key


def cmd_verify_api():
    """Minimal API key verification — one tiny request."""
    require_api_key()

    from nightingale.core.gemini_client import verify_api_key

    print("Verifying Gemini API key...")
    result = verify_api_key()
    print()

    if result["reachable"]:
        print(f"  API reachable:  YES")
        print(f"  SDK:            {result.get('sdk', 'unknown')}")
        print(f"  Model:          {result['model']}")
        print(f"  Latency:        {result['latency_ms']}ms")
        print(f"  Tokens used:    {result['tokens']}")
        print(f"  Response:       \"{result['response']}\"")
        print()
        print("API key is valid and working.")
        return True

    if result.get("quota_exhausted"):
        print(f"  API reachable:  YES (key valid)")
        print(f"  Model:          {result.get('model', 'unknown')}")
        print(f"  Latency:        {result['latency_ms']}ms")
        print(f"  Status:         QUOTA EXHAUSTED")
        print()
        print("API key is VALID but the free-tier quota is exhausted.")
        print("Wait for quota to reset or upgrade your API plan.")
        print()
        print("To use cached responses in the meantime:")
        print("  python main.py --demo --record-mode")
        return True  # Key itself is valid

    print(f"  API reachable:  NO")
    print(f"  Error:          {result['error']}")
    if "latency_ms" in result:
        print(f"  Latency:        {result['latency_ms']}ms")
    print()
    print("API key verification FAILED. Check your key.")
    sys.exit(1)



def cmd_self_check():
    """Run 9-point system diagnostic."""
    print("Running Nightingale self-check...\n")
    results = []

    # 1. API key present
    key = os.getenv("GEMINI_API_KEY", "")
    results.append(("API key present", bool(key), "$env:GEMINI_API_KEY = 'your_key'"))

    # 2. API responds (or at least key is valid)
    api_ok = False
    api_note = "Check your API key and internet connection"
    if key:
        from nightingale.core.gemini_client import verify_api_key
        r = verify_api_key()
        api_ok = r["reachable"] or r.get("quota_exhausted", False)
        if r.get("quota_exhausted"):
            api_note = "Key valid but quota exhausted — wait or upgrade"
    results.append(("API responds", api_ok, api_note))

    # 3. Demo repo exists
    from nightingale.config import config
    demo_path = os.path.abspath(config.get("demo.repo_path", "."))
    demo_exists = os.path.isdir(demo_path)
    results.append(("Demo repo exists", demo_exists, f"Create directory: {demo_path}"))

    # 4. Workflow file detected
    wf_dir = os.path.join(demo_path, ".github", "workflows")
    wf_found = os.path.isdir(wf_dir) and any(
        f.endswith((".yml", ".yaml")) for f in os.listdir(wf_dir)
    ) if os.path.isdir(wf_dir) else False
    results.append(("Workflow file detected", wf_found,
                     f"Create {wf_dir}/test.yml"))

    # 5. Sandbox directory writable
    sandbox_dir = os.path.join(demo_path, config.get("sandbox_dir", ".sandbox"))
    try:
        os.makedirs(sandbox_dir, exist_ok=True)
        test_file = os.path.join(sandbox_dir, ".write_test")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        sandbox_ok = True
    except Exception:
        sandbox_ok = False
    results.append(("Sandbox dir writable", sandbox_ok,
                     f"Check permissions on {sandbox_dir}"))

    # 6. Cache directory writable
    cache_dir = ".nightingale_cache"
    try:
        os.makedirs(cache_dir, exist_ok=True)
        test_file = os.path.join(cache_dir, ".write_test")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        cache_ok = True
    except Exception:
        cache_ok = False
    results.append(("Cache dir writable", cache_ok,
                     f"Check permissions on {cache_dir}"))

    # 7. Dependencies installed
    deps_ok = True
    missing = []
    for mod in ["google.genai", "pydantic", "fastapi", "uvicorn",
                 "rich", "yaml", "git"]:
        try:
            importlib.import_module(mod)
        except ImportError:
            deps_ok = False
            missing.append(mod)
    results.append(("Dependencies installed", deps_ok,
                     f"pip install: {', '.join(missing)}" if missing else ""))

    # 8. Reflective loop max attempts > 1
    from nightingale.agents.marathon import MarathonAgent
    max_attempts = MarathonAgent.MAX_ATTEMPTS
    results.append(("Reflective loop attempts > 1", max_attempts > 1,
                     "MarathonAgent.MAX_ATTEMPTS must be > 1"))

    # 9. Confidence weights sum to 1.0
    from nightingale.analysis.confidence import ConfidenceScorer
    weight_sum = sum(ConfidenceScorer.WEIGHTS.values())
    weights_ok = abs(weight_sum - 1.0) < 0.001
    results.append(("Confidence weights sum to 1.0", weights_ok,
                     f"Current sum: {weight_sum:.3f}"))

    # Print table
    all_pass = True
    print(f"  {'#':<3} {'Check':<35} {'Status':<8} {'Fix'}")
    print(f"  {'─'*3} {'─'*35} {'─'*8} {'─'*40}")
    for i, (name, passed, fix) in enumerate(results, 1):
        status = "PASS" if passed else "FAIL"
        fix_str = "" if passed else fix
        print(f"  {i:<3} {name:<35} {status:<8} {fix_str}")
        if not passed:
            all_pass = False

    print()
    if all_pass:
        print("All checks PASSED. System is ready.")
    else:
        print("Some checks FAILED. Fix the issues above and re-run.")
        sys.exit(1)

    return all_pass


def cmd_prep_demo():
    """Prepare system for demo recording."""
    print("=" * 60)
    print("  NIGHTINGALE DEMO PREP")
    print("=" * 60)
    print()

    # Step 1: Clear cache
    cache_dir = ".nightingale_cache"
    if os.path.exists(cache_dir):
        shutil.rmtree(cache_dir)
        print("[1/5] Cleared .nightingale_cache")
    else:
        print("[1/5] No cache to clear")

    # Step 2: Clear sandbox
    from nightingale.config import config
    demo_path = os.path.abspath(config.get("demo.repo_path", "."))
    sandbox_dir = os.path.join(demo_path, config.get("sandbox_dir", ".sandbox"))
    if os.path.exists(sandbox_dir):
        shutil.rmtree(sandbox_dir)
        print("[2/5] Cleared .sandbox")
    else:
        print("[2/5] No sandbox to clear")

    # Step 3: Verify API
    print("[3/5] Verifying API key...")
    from nightingale.core.gemini_client import verify_api_key
    result = verify_api_key()
    if not result["reachable"]:
        print(f"  FAILED: {result.get('error', 'Unknown error')}")
        print("  Fix your API key and try again.")
        sys.exit(1)
    print(f"  API OK (latency: {result['latency_ms']}ms)")

    # Step 4: Run demo
    print("[4/5] Running full demo...")
    from nightingale.core.gemini_client import reset_gemini_client
    reset_gemini_client()

    from nightingale.demo.scenario import run_demo
    try:
        run_demo(record_mode=False)
        demo_ok = True
    except Exception as e:
        print(f"  Demo failed: {e}")
        demo_ok = False

    # Step 5: Report
    print()
    if demo_ok:
        print("=" * 60)
        print("  YOUR SYSTEM IS READY TO RECORD.")
        print()
        print("  Next steps:")
        print("    1. Start screen recording")
        print("    2. Run: python main.py --demo")
        print("    3. Narrate using DEMO_VIDEO_GUIDE.md")
        print("=" * 60)
    else:
        print("=" * 60)
        print("  DEMO PREP FAILED.")
        print("  Fix the error above and run --prep-demo again.")
        print("=" * 60)
        sys.exit(1)


def cmd_demo(record_mode: bool = False):
    """Run demo scenario."""
    require_api_key() if not record_mode else None

    from nightingale.core.gemini_client import reset_gemini_client
    if record_mode:
        os.environ["NIGHTINGALE_RECORD_MODE"] = "1"
        print("[record-mode] Using cached API responses only\n")
    reset_gemini_client()

    from nightingale.demo.scenario import run_demo
    run_demo(record_mode=record_mode)


def cmd_webhook(host: str, port: int):
    """Start webhook server."""
    require_api_key()
    from nightingale.api.webhook import run_webhook_server
    print(f"Starting Nightingale Webhook Server on {host}:{port}")
    run_webhook_server(host=host, port=port)


def main():
    from nightingale.config import config

    parser = argparse.ArgumentParser(
        description=f"Nightingale v{config.get('version')} — Autonomous CI SRE Agent"
    )
    parser.add_argument("--demo", action="store_true",
                        help="Run demo with a broken test scenario")
    parser.add_argument("--webhook", action="store_true",
                        help="Start FastAPI webhook server")
    parser.add_argument("--verify-api", action="store_true",
                        help="Verify API key with one minimal request")
    parser.add_argument("--self-check", action="store_true",
                        help="Run full system diagnostic (9 checks)")
    parser.add_argument("--prep-demo", action="store_true",
                        help="Prepare system for demo recording")
    parser.add_argument("--record-mode", action="store_true",
                        help="Replay cached Gemini responses (no API calls)")
    parser.add_argument("--port", type=int, default=8000,
                        help="Webhook server port")
    parser.add_argument("--host", type=str, default="0.0.0.0",
                        help="Webhook server host")

    args = parser.parse_args()

    if args.verify_api:
        cmd_verify_api()
    elif args.self_check:
        cmd_self_check()
    elif args.prep_demo:
        cmd_prep_demo()
    elif args.demo:
        cmd_demo(record_mode=args.record_mode)
    elif args.webhook:
        cmd_webhook(args.host, args.port)
    else:
        print(f"""
Nightingale v{config.get('version')} — Autonomous CI SRE Agent

Commands:
  python main.py --verify-api      Verify API key (one minimal request)
  python main.py --self-check      Run 9-point system diagnostic
  python main.py --demo            Run demo scenario
  python main.py --demo --record-mode  Replay from cached responses
  python main.py --prep-demo       Full demo preparation
  python main.py --webhook         Start webhook server
""")


if __name__ == "__main__":
    main()
