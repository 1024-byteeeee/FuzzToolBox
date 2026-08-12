import argparse
import asyncio
import json
import sys

from .engine import ScanCancelled, Scanner
from .models import ScanConfig
from ...core.network_info import get_network_info
from .targets import parse_ports, parse_target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fuzztoolbox scan", description="FuzzToolBox 跨平台 IPv4 主机扫描器"
    )
    parser.add_argument("target", help="CIDR、单个 IP 或起止范围")
    parser.add_argument("--method", choices=["tcp", "ping"], default="tcp")
    parser.add_argument("--ports", default="22,80,443,445,3389,8080")
    parser.add_argument("--timeout", type=float, default=0.5)
    parser.add_argument("--concurrency", type=int, default=256)
    parser.add_argument("--retries", type=int, default=0)
    parser.add_argument("--resolve-hostname", action="store_true")
    parser.add_argument("--include-dead", action="store_true")
    parser.add_argument("--json", action="store_true", help="输出 JSON Lines")
    return parser


async def run(args: argparse.Namespace) -> int:
    targets = parse_target(args.target)
    config = ScanConfig(
        method=args.method,
        ports=parse_ports(args.ports),
        timeout=args.timeout,
        concurrency=args.concurrency,
        retries=args.retries,
        resolve_hostname=args.resolve_hostname,
        include_dead=args.include_dead,
    )
    scanner = Scanner(config, get_network_info())

    def show_results(batch):
        for result in batch:
            if args.json:
                print(json.dumps(result.to_dict(), ensure_ascii=False))
            else:
                ports = ",".join(map(str, result.open_ports)) or "-"
                status = "在线" if result.is_alive else "离线"
                print(f"{result.ip:<15} {status:<4} 端口={ports} 延迟={result.response_time_ms or '-'}ms")

    def show_progress(progress):
        print(
            f"\r已扫描 {progress.scanned}/{progress.total}，在线 {progress.alive}，"
            f"{progress.rate:.1f} IP/s",
            end="",
            file=sys.stderr,
        )

    try:
        results = await scanner.scan(targets, show_results, show_progress)
    except ScanCancelled:
        print("\n扫描已取消", file=sys.stderr)
        return 130
    print(f"\n完成：发现 {sum(item.is_alive for item in results)} 台主机", file=sys.stderr)
    return 0


def main() -> None:
    args = build_parser().parse_args()
    try:
        raise SystemExit(asyncio.run(run(args)))
    except ValueError as exc:
        print(f"参数错误：{exc}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
