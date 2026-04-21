from __future__ import annotations

import argparse
import logging
from typing import Any

from .server import UtermServer


def create_app(server: UtermServer) -> Any:
    from fastapi import FastAPI

    app = FastAPI(title="Uterm API", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/sessions")
    def sessions() -> dict[str, object]:
        items: list[dict[str, object]] = []
        with server._lock:
            for client_id, runtime in server._clients.items():
                items.append(
                    {
                        "clientId": client_id,
                        "lastSeenAt": runtime.channel.last_seen_at,
                        "stats": {
                            "retransmissions": runtime.channel.stats.retransmissions,
                            "duplicates": runtime.channel.stats.duplicates,
                            "acksSent": runtime.channel.stats.acks_sent,
                            "packetsSent": runtime.channel.stats.packets_sent,
                            "packetsReceived": runtime.channel.stats.packets_received,
                        },
                    }
                )
        return {"sessions": items}

    return app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Uterm management API (OpenAPI/Swagger)")
    parser.add_argument("--host", default="0.0.0.0", help="HTTP bind host")
    parser.add_argument("--port", type=int, default=8080, help="HTTP bind port")
    parser.add_argument("--udp-host", default="0.0.0.0", help="UDP bind host")
    parser.add_argument("--udp-port", type=int, default=9527, help="UDP bind port")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser


def main() -> None:
    import uvicorn

    args = build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    server = UtermServer(args.udp_host, args.udp_port)
    server.start()

    app = create_app(server)
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level.lower())


if __name__ == "__main__":
    main()
