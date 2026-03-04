import argparse
import asyncio

from gateway.server import DEFAULT_HOST, DEFAULT_PORT, run
from gateway.utils import ensure_web_node_modules, find_web_dist


def main() -> None:
    parser = argparse.ArgumentParser(description="Zac Gateway Server")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Bind address (default: localhost)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port (default: 8765)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--web-dir", help="Directory to serve web UI from (auto-detected if omitted)")
    parser.add_argument("--no-web", action="store_true", help="Disable web UI serving")
    parser.add_argument("--tls-cert", help="TLS certificate file (e.g. from tailscale cert)")
    parser.add_argument("--tls-key", help="TLS private key file")
    parser.add_argument("--log-file", help="Also write logs to this file")
    parser.add_argument("--model", help="OpenRouter model ID (e.g. anthropic/claude-sonnet-4)")
    parser.add_argument("--system-prompt", help="System prompt for the agent")
    parser.add_argument("--conversation-log", metavar="FILE", help="Log all requests/responses to/from OpenRouter to FILE")
    args = parser.parse_args()

    # Ensure web dependencies are installed before starting
    ensure_web_node_modules()

    web_dir = args.web_dir
    if not web_dir and not args.no_web:
        web_dir = find_web_dist()

    asyncio.run(run(
        host=args.host,
        port=args.port,
        debug=args.debug,
        web_dir=web_dir,
        tls_cert=args.tls_cert,
        tls_key=args.tls_key,
        log_file=args.log_file,
        model=args.model,
        system_prompt=args.system_prompt,
        conversation_log_file=args.conversation_log,
    ))


main()
