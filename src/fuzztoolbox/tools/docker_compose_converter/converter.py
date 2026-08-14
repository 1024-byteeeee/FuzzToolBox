"""Dependency-free Docker Run to Compose conversion."""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class OptionSpec:
    kind: str = "value"
    repeatable: bool = False


BOOLEAN_OPTIONS = {
    "detach",
    "help",
    "interactive",
    "tty",
    "init",
    "no-healthcheck",
    "oom-kill-disable",
    "privileged",
    "publish-all",
    "quiet",
    "read-only",
    "rm",
    "sig-proxy",
    "use-api-socket",
}
REPEATABLE_OPTIONS = {
    "add-host",
    "annotation",
    "attach",
    "blkio-weight-device",
    "cap-add",
    "cap-drop",
    "device",
    "device-cgroup-rule",
    "device-read-bps",
    "device-read-iops",
    "device-write-bps",
    "device-write-iops",
    "dns",
    "dns-option",
    "dns-search",
    "env",
    "env-file",
    "expose",
    "group-add",
    "label",
    "label-file",
    "link",
    "link-local-ip",
    "log-opt",
    "mount",
    "network",
    "network-alias",
    "publish",
    "security-opt",
    "storage-opt",
    "sysctl",
    "tmpfs",
    "ulimit",
    "volume",
    "volumes-from",
}
VALUE_OPTIONS = {
    "add-host",
    "annotation",
    "attach",
    "blkio-weight",
    "blkio-weight-device",
    "cap-add",
    "cap-drop",
    "cgroup-parent",
    "cgroupns",
    "cidfile",
    "cpu-count",
    "cpu-percent",
    "cpu-period",
    "cpu-quota",
    "cpu-rt-period",
    "cpu-rt-runtime",
    "cpu-shares",
    "cpus",
    "cpuset-cpus",
    "cpuset-mems",
    "detach-keys",
    "device",
    "device-cgroup-rule",
    "device-read-bps",
    "device-read-iops",
    "device-write-bps",
    "device-write-iops",
    "dns",
    "dns-option",
    "dns-search",
    "domainname",
    "entrypoint",
    "env",
    "env-file",
    "expose",
    "gpus",
    "group-add",
    "health-cmd",
    "health-interval",
    "health-retries",
    "health-start-interval",
    "health-start-period",
    "health-timeout",
    "hostname",
    "io-maxbandwidth",
    "io-maxiops",
    "ip",
    "ip6",
    "ipc",
    "isolation",
    "label",
    "label-file",
    "link",
    "link-local-ip",
    "log-driver",
    "log-opt",
    "mac-address",
    "memory",
    "memory-reservation",
    "memory-swap",
    "memory-swappiness",
    "mount",
    "name",
    "network",
    "network-alias",
    "oom-score-adj",
    "pid",
    "pids-limit",
    "platform",
    "publish",
    "pull",
    "restart",
    "runtime",
    "security-opt",
    "shm-size",
    "stop-signal",
    "stop-timeout",
    "storage-opt",
    "sysctl",
    "tmpfs",
    "ulimit",
    "user",
    "userns",
    "uts",
    "volume",
    "volume-driver",
    "volumes-from",
    "workdir",
}
OPTION_SPECS = {
    name: OptionSpec("bool" if name in BOOLEAN_OPTIONS else "value", name in REPEATABLE_OPTIONS)
    for name in BOOLEAN_OPTIONS | VALUE_OPTIONS
}
SHORT_ALIASES = {
    "a": "attach",
    "c": "cpu-shares",
    "d": "detach",
    "e": "env",
    "h": "hostname",
    "i": "interactive",
    "l": "label",
    "m": "memory",
    "p": "publish",
    "P": "publish-all",
    "q": "quiet",
    "t": "tty",
    "u": "user",
    "v": "volume",
    "w": "workdir",
}
LONG_ALIASES = {"net": "network"}
RUNTIME_ONLY = {
    "attach": "Compose 只能控制是否收集日志，不能保留指定的附加流",
    "cidfile": "Compose 不输出容器 ID 文件",
    "detach-keys": "这是 CLI 会话参数",
    "publish-all": "Compose 无法预先表示随机宿主机端口",
    "rm": "Compose 没有自动删除已退出服务容器的服务字段",
    "sig-proxy": "这是 CLI 信号代理参数",
}
INFORMATIONAL_OPTIONS = {
    "detach": "无需写入 Compose；是否后台运行由 docker compose up -d 决定",
    "help": "CLI 帮助开关，无需写入 Compose",
    "quiet": "CLI 输出控制参数，无需写入 Compose",
}


@dataclass
class ConversionResult:
    yaml: str
    service_count: int
    mapped_option_count: int
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _split(command: str) -> list[str]:
    normalized = command.replace("\\\r\n", " ").replace("\\\n", " ").strip()
    sentinel = "\ue000"
    normalized = re.sub(
        r"(?i)([a-z]:\\[^\s\"']*)",
        lambda match: match.group(1).replace("\\", sentinel),
        normalized,
    )
    try:
        return [token.replace(sentinel, "\\") for token in shlex.split(normalized, posix=True)]
    except ValueError as exc:
        raise ValueError(f"命令引号不完整：{exc}") from exc


def _commands(source: str) -> list[str]:
    normalized = source.replace("\\\r\n", " ").replace("\\\n", " ")
    starts = list(re.finditer(r"(?m)^\s*(?:\$\s*)?(?=(?:docker|podman)\s+)", normalized))
    if not starts:
        return [normalized.strip()] if normalized.strip() else []
    return [
        normalized[
            match.start() : starts[index + 1].start() if index + 1 < len(starts) else None
        ].strip()
        for index, match in enumerate(starts)
    ]


def _store_option(options: dict[str, Any], name: str, value: Any):
    spec = OPTION_SPECS[name]
    if spec.repeatable:
        options.setdefault(name, []).append(value)
    else:
        options[name] = value


def _parse_short(token: str, tokens: list[str], index: int, options: dict[str, Any]):
    cluster = token[1:]
    offset = 0
    while offset < len(cluster):
        short = cluster[offset]
        name = SHORT_ALIASES.get(short)
        if name is None:
            raise ValueError(f"未识别参数 -{short}")
        spec = OPTION_SPECS[name]
        if spec.kind == "bool":
            _store_option(options, name, True)
            offset += 1
            continue
        inline = cluster[offset + 1 :]
        if inline:
            _store_option(options, name, inline)
            return index
        index += 1
        if index >= len(tokens):
            raise ValueError(f"参数 -{short} 缺少值")
        _store_option(options, name, tokens[index])
        return index
    return index


def _parse_run(command: str):
    tokens = _split(command)
    if tokens[:1] == ["$"]:
        tokens.pop(0)
    if len(tokens) < 3 or tokens[0] not in {"docker", "podman"}:
        raise ValueError("请输入以 docker run 或 podman run 开头的命令")
    if tokens[1:3] == ["container", "run"]:
        index = 3
    elif tokens[1] in {"run", "create"}:
        index = 2
    else:
        raise ValueError("当前仅支持 docker/podman run、docker create 和 docker container run")

    options: dict[str, Any] = {}
    warnings = []
    while index < len(tokens) and tokens[index].startswith("-") and tokens[index] != "--":
        token = tokens[index]
        if token.startswith("--"):
            raw = token[2:]
            inline = None
            if "=" in raw:
                raw, inline = raw.split("=", 1)
            name = LONG_ALIASES.get(raw, raw)
            spec = OPTION_SPECS.get(name)
            if spec is None:
                warnings.append(f"未识别参数 --{raw}，可能来自较新的 Docker 版本")
                if inline is None and index + 1 < len(tokens) and tokens[index + 1].startswith("-"):
                    index += 1
                    continue
                if inline is None and index + 2 < len(tokens):
                    index += 1
                index += 1
                continue
            if spec.kind == "bool":
                value = True if inline is None else inline.casefold() not in {"false", "0", "no"}
            else:
                if inline is None:
                    index += 1
                    if index >= len(tokens):
                        raise ValueError(f"参数 --{raw} 缺少值")
                    inline = tokens[index]
                value = inline
            _store_option(options, name, value)
        else:
            index = _parse_short(token, tokens, index, options)
        index += 1
    if index < len(tokens) and tokens[index] == "--":
        index += 1
    if index >= len(tokens):
        raise ValueError("命令中缺少镜像名称")
    return tokens[index], tokens[index + 1 :], options, warnings


def _service_name(image: str, used: set[str]) -> str:
    base = image.rsplit("/", 1)[-1].split("@", 1)[0].split(":", 1)[0]
    base = re.sub(r"[^a-zA-Z0-9_.-]+", "-", base).strip("-.").lower() or "app"
    name, suffix = base, 2
    while name in used:
        name, suffix = f"{base}-{suffix}", suffix + 1
    used.add(name)
    return name


def _key_values(values: list[str], warnings: list[str], label: str) -> dict[str, str]:
    result = {}
    for item in values:
        if "=" not in item:
            warnings.append(f"{label}参数 {item} 缺少键值")
            continue
        key, value = item.split("=", 1)
        result[key] = value
    return result


def _device_limits(values: list[str], warnings: list[str], label: str):
    result = []
    for item in values:
        if ":" not in item:
            warnings.append(f"{label}参数 {item} 缺少设备路径或限制值")
            continue
        path, rate = item.rsplit(":", 1)
        result.append({"path": path, "rate": rate})
    return result


def _weight_devices(values: list[str], warnings: list[str]):
    result = []
    for item in values:
        if ":" not in item:
            warnings.append(f"块设备权重参数 {item} 格式无效")
            continue
        path, weight = item.rsplit(":", 1)
        result.append({"path": path, "weight": int(weight) if weight.isdigit() else weight})
    return result


def _parse_ulimits(values: list[str], warnings: list[str]):
    result = {}
    for item in values:
        if "=" not in item:
            warnings.append(f"ulimit 参数 {item} 缺少名称")
            continue
        name, limit = item.split("=", 1)
        if ":" in limit:
            soft, hard = limit.split(":", 1)
            result[name] = {
                "soft": int(soft) if soft.lstrip("-").isdigit() else soft,
                "hard": int(hard) if hard.lstrip("-").isdigit() else hard,
            }
        else:
            result[name] = int(limit) if limit.lstrip("-").isdigit() else limit
    return result


def _parse_mount(value: str, warnings: list[str]):
    raw = {}
    flags = set()
    for part in value.split(","):
        if "=" in part:
            key, item = part.split("=", 1)
            raw[key] = item
        else:
            flags.add(part)
    mount_type = raw.get("type", "volume")
    mount = {"type": mount_type}
    source = raw.get("source", raw.get("src"))
    target = raw.get("target", raw.get("dst", raw.get("destination")))
    if source:
        mount["source"] = source
    if target:
        mount["target"] = target
    else:
        warnings.append(f"mount 参数缺少 target：{value}")
    if "readonly" in flags or "ro" in flags:
        mount["read_only"] = True
    if raw.get("consistency"):
        mount["consistency"] = raw["consistency"]
    if mount_type == "bind":
        bind = {}
        if raw.get("bind-propagation"):
            bind["propagation"] = raw["bind-propagation"]
        if "bind-nonrecursive" in flags:
            bind["recursive"] = "disabled"
        if bind:
            mount["bind"] = bind
    elif mount_type == "volume" and "volume-nocopy" in flags:
        mount["volume"] = {"nocopy": True}
    elif mount_type == "tmpfs":
        tmpfs = {}
        if raw.get("tmpfs-size"):
            tmpfs["size"] = raw["tmpfs-size"]
        if raw.get("tmpfs-mode"):
            tmpfs["mode"] = raw["tmpfs-mode"]
        if tmpfs:
            mount["tmpfs"] = tmpfs
    return mount


def _network_config(options: dict[str, Any], warnings: list[str]):
    networks = list(options.get("network", []))
    network_details = any(
        options.get(name) for name in ("ip", "ip6", "network-alias", "link-local-ip")
    )
    if not networks and network_details:
        networks = ["default"]
    if not networks:
        return None, {}
    if len(networks) == 1 and (
        networks[0] in {"host", "none", "bridge"} or networks[0].startswith("container:")
    ):
        if network_details:
            warnings.append(f"{networks[0]} 网络模式无法在 Compose 中同时表达固定地址或网络别名")
        if networks[0] == "host" and options.get("publish"):
            warnings.append("host 网络模式下端口映射不会生效")
        return networks[0], {}
    service_networks = {}
    aliases = options.get("network-alias", [])
    for index, network in enumerate(networks):
        name = "default" if network == "default" else network
        config = {}
        if index == 0:
            if options.get("ip"):
                config["ipv4_address"] = options["ip"]
            if options.get("ip6"):
                config["ipv6_address"] = options["ip6"]
            if options.get("mac-address"):
                config["mac_address"] = options["mac-address"]
            if aliases:
                config["aliases"] = aliases
            if options.get("link-local-ip"):
                config["link_local_ips"] = options["link-local-ip"]
        service_networks[name] = config or None
    return None, service_networks


def _gpu_reservation(value: str):
    request: dict[str, Any] = {"capabilities": ["gpu"]}
    if value == "all":
        request["count"] = "all"
    elif value.isdigit():
        request["count"] = int(value)
    elif value.startswith("device="):
        request["device_ids"] = [item for item in value[7:].split(",") if item]
    else:
        request["driver"] = value
    return {"resources": {"reservations": {"devices": [request]}}}


def _build_service(image, command, options, warnings, notes):
    service: dict[str, Any] = {"image": image}
    mapped = 0
    for option, reason in RUNTIME_ONLY.items():
        if option in options:
            warnings.append(f"--{option} 无法写入 Compose：{reason}")
    for option, explanation in INFORMATIONAL_OPTIONS.items():
        if option in options:
            notes.append(f"--{option}：{explanation}")

    logging = {}
    if "log-driver" in options:
        logging["driver"] = options["log-driver"]
        mapped += 1
    if "log-opt" in options:
        logging["options"] = _key_values(options["log-opt"], warnings, "日志")
        mapped += len(logging["options"])
    if logging:
        service["logging"] = logging

    direct = {
        "name": "container_name",
        "hostname": "hostname",
        "domainname": "domainname",
        "user": "user",
        "workdir": "working_dir",
        "entrypoint": "entrypoint",
        "privileged": "privileged",
        "read-only": "read_only",
        "init": "init",
        "shm-size": "shm_size",
        "platform": "platform",
        "stop-signal": "stop_signal",
        "pull": "pull_policy",
        "restart": "restart",
        "runtime": "runtime",
        "ipc": "ipc",
        "pid": "pid",
        "isolation": "isolation",
        "userns": "userns_mode",
        "uts": "uts",
        "cgroup-parent": "cgroup_parent",
        "cgroupns": "cgroup",
        "cpu-count": "cpu_count",
        "cpu-percent": "cpu_percent",
        "cpu-period": "cpu_period",
        "cpu-quota": "cpu_quota",
        "cpu-rt-period": "cpu_rt_period",
        "cpu-rt-runtime": "cpu_rt_runtime",
        "cpu-shares": "cpu_shares",
        "cpus": "cpus",
        "cpuset-cpus": "cpuset",
        "memory": "mem_limit",
        "memory-reservation": "mem_reservation",
        "memory-swap": "memswap_limit",
        "memory-swappiness": "mem_swappiness",
        "oom-kill-disable": "oom_kill_disable",
        "oom-score-adj": "oom_score_adj",
        "pids-limit": "pids_limit",
        "use-api-socket": "use_api_socket",
        "mac-address": "mac_address",
    }
    arrays = {
        "publish": "ports",
        "volume": "volumes",
        "env-file": "env_file",
        "cap-add": "cap_add",
        "cap-drop": "cap_drop",
        "dns": "dns",
        "dns-option": "dns_opt",
        "dns-search": "dns_search",
        "add-host": "extra_hosts",
        "annotation": "annotations",
        "label": "labels",
        "label-file": "label_file",
        "device": "devices",
        "tmpfs": "tmpfs",
        "expose": "expose",
        "security-opt": "security_opt",
        "group-add": "group_add",
        "volumes-from": "volumes_from",
        "link": "links",
        "device-cgroup-rule": "device_cgroup_rules",
    }
    for option, field_name in direct.items():
        if option in options:
            service[field_name] = options[option]
            mapped += 1
    for option, field_name in arrays.items():
        if option in options:
            service[field_name] = options[option]
            mapped += len(options[option])
    if options.get("interactive"):
        service["stdin_open"] = True
        mapped += 1
    if options.get("tty"):
        service["tty"] = True
        mapped += 1
    if "env" in options:
        service["environment"] = options["env"]
        mapped += len(options["env"])
    if "mount" in options:
        service.setdefault("volumes", []).extend(
            _parse_mount(item, warnings) for item in options["mount"]
        )
        mapped += len(options["mount"])
    if "storage-opt" in options:
        service["storage_opt"] = _key_values(options["storage-opt"], warnings, "存储")
        mapped += len(service["storage_opt"])
    if "sysctl" in options:
        service["sysctls"] = _key_values(options["sysctl"], warnings, "sysctl")
        mapped += len(service["sysctls"])
    if "ulimit" in options:
        service["ulimits"] = _parse_ulimits(options["ulimit"], warnings)
        mapped += len(service["ulimits"])
    if "gpus" in options:
        service["deploy"] = _gpu_reservation(options["gpus"])
        mapped += 1
    if "stop-timeout" in options:
        value = options["stop-timeout"]
        service["stop_grace_period"] = value if re.search(r"[a-zA-Z]", value) else f"{value}s"
        mapped += 1
    if "volume-driver" in options:
        mapped += 1

    health_map = {
        "health-interval": "interval",
        "health-timeout": "timeout",
        "health-retries": "retries",
        "health-start-period": "start_period",
        "health-start-interval": "start_interval",
    }
    health = {}
    if "health-cmd" in options:
        health["test"] = ["CMD-SHELL", options["health-cmd"]]
        mapped += 1
    for option, field_name in health_map.items():
        if option in options:
            value = options[option]
            health[field_name] = (
                int(value) if field_name == "retries" and value.isdigit() else value
            )
            mapped += 1
    if options.get("no-healthcheck"):
        health["disable"] = True
        mapped += 1
    if health:
        service["healthcheck"] = health

    blkio = {}
    if "blkio-weight" in options:
        value = options["blkio-weight"]
        blkio["weight"] = int(value) if value.isdigit() else value
        mapped += 1
    if "blkio-weight-device" in options:
        blkio["weight_device"] = _weight_devices(options["blkio-weight-device"], warnings)
        mapped += len(blkio["weight_device"])
    for option, field_name in {
        "device-read-bps": "device_read_bps",
        "device-read-iops": "device_read_iops",
        "device-write-bps": "device_write_bps",
        "device-write-iops": "device_write_iops",
    }.items():
        if option in options:
            blkio[field_name] = _device_limits(options[option], warnings, option)
            mapped += len(blkio[field_name])
    if blkio:
        service["blkio_config"] = blkio

    network_mode, networks = _network_config(options, warnings)
    if network_mode:
        service["network_mode"] = network_mode
        mapped += 1
    elif networks:
        service["networks"] = networks
        mapped += len(options.get("network", []))
        mapped += sum(
            len(options[name]) if isinstance(options.get(name), list) else 1
            for name in ("ip", "ip6", "network-alias", "link-local-ip")
            if options.get(name)
        )

    unsupported_platform = {
        "cpuset-mems": "Compose 没有 cpuset mems 服务字段",
        "io-maxbandwidth": "Windows IO 总带宽限制没有对应 Compose 字段",
        "io-maxiops": "Windows IO 总 IOPS 限制没有对应 Compose 字段",
    }
    for option, reason in unsupported_platform.items():
        if option in options:
            warnings.append(f"--{option} 未转换：{reason}")
    if command:
        service["command"] = command
    return service, mapped


def _scalar(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    safe = re.fullmatch(r"[A-Za-z0-9_./@+-]+", text) and text.casefold() not in {
        "true",
        "false",
        "null",
        "yes",
        "no",
        "on",
        "off",
    }
    return text if safe else json.dumps(text, ensure_ascii=False)


def _yaml(value: Any, indent=0) -> list[str]:
    pad = " " * indent
    lines = []
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, dict) and not item:
                lines.append(f"{pad}{key}: {{}}")
            elif isinstance(item, list) and not item:
                lines.append(f"{pad}{key}: []")
            elif isinstance(item, (dict, list)):
                lines.append(f"{pad}{key}:")
                lines.extend(_yaml(item, indent + 2))
            else:
                lines.append(f"{pad}{key}: {_scalar(item)}")
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                if not item:
                    lines.append(f"{pad}- {{}}")
                    continue
                first_key, first_value = next(iter(item.items()))
                if isinstance(first_value, (dict, list)):
                    lines.append(f"{pad}- {first_key}:")
                    lines.extend(_yaml(first_value, indent + 4))
                else:
                    lines.append(f"{pad}- {first_key}: {_scalar(first_value)}")
                lines.extend(_yaml(dict(list(item.items())[1:]), indent + 2))
            elif isinstance(item, list):
                lines.append(f"{pad}-")
                lines.extend(_yaml(item, indent + 2))
            else:
                lines.append(f"{pad}- {_scalar(item)}")
    return lines


def convert_docker_run(source: str) -> ConversionResult:
    commands = _commands(source)
    if not commands:
        raise ValueError("请输入 Docker Run 命令")
    services = {}
    top_networks = {}
    top_volumes = {}
    used = set()
    warnings = []
    notes = []
    mapped = 0
    for command_text in commands:
        image, command, options, command_warnings = _parse_run(command_text)
        name = _service_name(image, used)
        command_notes = []
        service, count = _build_service(
            image, command, options, command_warnings, command_notes
        )
        services[name] = service
        mapped += count
        warnings.extend(command_warnings)
        notes.extend(command_notes)
        for network in options.get("network", []):
            if network not in {"host", "none", "bridge"} and not network.startswith("container:"):
                top_networks[network] = {"external": True}
        if not options.get("network") and any(
            options.get(name) for name in ("ip", "ip6", "network-alias", "link-local-ip")
        ):
            top_networks["default"] = {"external": True, "name": "bridge"}
        volume_driver = options.get("volume-driver")
        volume_values = list(options.get("volume", []))
        for mount_value in options.get("mount", []):
            fields = dict(part.split("=", 1) for part in mount_value.split(",") if "=" in part)
            if fields.get("type", "volume") == "volume" and fields.get("source", fields.get("src")):
                volume_values.append(fields.get("source", fields.get("src")))
        defined_volume = False
        for volume in volume_values:
            source = (
                volume.split(":", 2)[0] + ":" + volume.split(":", 2)[1]
                if re.match(r"^[A-Za-z]:[\\/]", volume)
                else volume.split(":", 1)[0]
            )
            is_windows_path = bool(re.match(r"^[A-Za-z]:[\\/]", source))
            if source and not source.startswith(("/", "./", "../", "~")) and not is_windows_path:
                top_volumes[source] = {"driver": volume_driver} if volume_driver else {}
                defined_volume = True
        if volume_driver and not defined_volume:
            warnings.append("--volume-driver 未转换：命令中没有可声明驱动的命名卷")
    document: dict[str, Any] = {"services": services}
    if top_networks:
        document["networks"] = top_networks
    if top_volumes:
        document["volumes"] = top_volumes
    yaml = "version: '3.9'\n" + "\n".join(_yaml(document)) + "\n"
    return ConversionResult(
        yaml=yaml,
        service_count=len(services),
        mapped_option_count=mapped,
        warnings=warnings,
        notes=notes,
    )
