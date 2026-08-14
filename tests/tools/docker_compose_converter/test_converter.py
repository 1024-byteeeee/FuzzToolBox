import unittest

from fuzztoolbox.tools.docker_compose_converter.converter import (
    BOOLEAN_OPTIONS,
    OPTION_SPECS,
    VALUE_OPTIONS,
    convert_docker_run,
)


class DockerComposeConverterTests(unittest.TestCase):
    def test_converts_common_run_options(self):
        result = convert_docker_run(
            "docker run -d --name web -p 8080:80 -e MODE=prod "
            "-v ./data:/data:ro --restart unless-stopped nginx:latest"
        )
        self.assertTrue(result.yaml.startswith("version: '3.9'\nservices:"))
        self.assertIn("container_name: web", result.yaml)
        self.assertIn('      - "8080:80"', result.yaml)
        self.assertIn('      - "MODE=prod"', result.yaml)
        self.assertIn('image: "nginx:latest"', result.yaml)
        self.assertEqual(result.service_count, 1)

    def test_supports_line_continuations_and_container_command(self):
        result = convert_docker_run(
            "docker run \\\n+          --name worker \\\n+          python:3.12 python -m http.server 8000"
        )
        self.assertIn("worker", result.yaml)
        self.assertIn("command:", result.yaml)
        self.assertIn("http.server", result.yaml)

    def test_merges_multiple_commands_and_external_network(self):
        result = convert_docker_run(
            "docker run --network app-net redis\ndocker run --network app-net -p 8080:80 nginx"
        )
        self.assertEqual(result.service_count, 2)
        self.assertIn("networks:", result.yaml)
        self.assertIn("external: true", result.yaml)

    def test_warns_for_unknown_and_runtime_only_options(self):
        result = convert_docker_run("docker run --rm --mystery value alpine")
        self.assertTrue(any("--rm" in warning for warning in result.warnings))
        self.assertTrue(any("未识别参数" in warning for warning in result.warnings))

    def test_detach_is_an_informational_note_not_a_conversion_warning(self):
        result = convert_docker_run("docker run -d nginx")
        self.assertEqual(result.warnings, [])
        self.assertTrue(any("docker compose up -d" in note for note in result.notes))
        self.assertFalse(any("未转换" in note for note in result.notes))

    def test_preserves_windows_bind_mount_path(self):
        result = convert_docker_run(r"docker run -v C:\data:/data nginx")
        self.assertIn(r"C:\\data:/data", result.yaml)

    def test_converts_logging_options_with_correct_yaml_indentation(self):
        result = convert_docker_run(
            "docker run -p 80:80 "
            "-v /var/run/docker.sock:/tmp/docker.sock:ro "
            "--restart always --log-opt max-size=1g nginx"
        )
        self.assertEqual(
            result.yaml,
            "version: '3.9'\n"
            "services:\n"
            "  nginx:\n"
            "    image: nginx\n"
            "    logging:\n"
            "      options:\n"
            "        max-size: 1g\n"
            "    restart: always\n"
            "    ports:\n"
            '      - "80:80"\n'
            "    volumes:\n"
            '      - "/var/run/docker.sock:/tmp/docker.sock:ro"\n',
        )

    def test_rejects_invalid_commands(self):
        for source in ("", "docker ps", "docker run --name test"):
            with self.subTest(source=source), self.assertRaises(ValueError):
                convert_docker_run(source)

    def test_every_registered_official_option_is_parsed_and_classified(self):
        for option in sorted(OPTION_SPECS):
            argument = f"--{option}" if option in BOOLEAN_OPTIONS else f"--{option} x"
            with self.subTest(option=option):
                result = convert_docker_run(f"docker run {argument} alpine")
                self.assertFalse(any("未识别参数" in item for item in result.warnings))
                self.assertTrue(result.mapped_option_count > 0 or result.warnings or result.notes)

    def test_official_option_registry_has_expected_surface(self):
        expected = {
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
            "detach",
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
            "help",
            "hostname",
            "init",
            "interactive",
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
            "no-healthcheck",
            "oom-kill-disable",
            "oom-score-adj",
            "pid",
            "pids-limit",
            "platform",
            "privileged",
            "publish",
            "publish-all",
            "pull",
            "quiet",
            "read-only",
            "restart",
            "rm",
            "runtime",
            "security-opt",
            "shm-size",
            "sig-proxy",
            "stop-signal",
            "stop-timeout",
            "storage-opt",
            "sysctl",
            "tmpfs",
            "tty",
            "ulimit",
            "use-api-socket",
            "user",
            "userns",
            "uts",
            "volume",
            "volume-driver",
            "volumes-from",
            "workdir",
        }
        self.assertEqual(set(OPTION_SPECS), expected)
        self.assertEqual(set(OPTION_SPECS), BOOLEAN_OPTIONS | VALUE_OPTIONS)

    def test_complex_resource_network_mount_and_limit_mapping(self):
        result = convert_docker_run(
            "docker run --network app-net --ip 172.20.0.8 --network-alias api "
            "--mount type=bind,src=./data,dst=/data,readonly "
            "--ulimit nofile=1024:2048 --device-read-bps /dev/sda:1mb "
            "--gpus device=0,1 --health-retries 4 alpine"
        )
        self.assertIn("ipv4_address: 172.20.0.8", result.yaml)
        self.assertIn("aliases:", result.yaml)
        self.assertIn("type: bind", result.yaml)
        self.assertIn("read_only: true", result.yaml)
        self.assertIn("soft: 1024", result.yaml)
        self.assertIn("device_read_bps:", result.yaml)
        self.assertIn("device_ids:", result.yaml)
        self.assertIn("retries: 4", result.yaml)

    def test_combined_short_flags_and_attached_values(self):
        result = convert_docker_run("docker run -itd -p8080:80 -eMODE=prod alpine sh")
        self.assertIn("stdin_open: true", result.yaml)
        self.assertIn("tty: true", result.yaml)
        self.assertIn('      - "8080:80"', result.yaml)
        self.assertIn('      - "MODE=prod"', result.yaml)

    def test_fixed_ip_without_network_reuses_docker_default_bridge(self):
        result = convert_docker_run("docker run --ip 172.17.0.20 nginx")
        self.assertIn("ipv4_address: 172.17.0.20", result.yaml)
        self.assertIn("external: true", result.yaml)
        self.assertIn("name: bridge", result.yaml)
