"""Validate launcher ownership and containment without touching a real server."""

import json
import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell launcher")
IMAGE = "sha256:e0ae5354a9e4c85160df4698a45ae360cd0c12ef90e484b12fc870c28f491892"
NAME = "breakmyquery-llama32"


def owned_container():
    runtime = ROOT / ".cache/ollama/runtime"
    return {
        "Image": IMAGE,
        "State": {"Running": True},
        "Config": {"Labels": {"breakmyquery.repo": str(ROOT)}},
        "HostConfig": {
            "ReadonlyRootfs": True,
            "LogConfig": {"Type": "none"},
            "PortBindings": {"11434/tcp": [{"HostIp": "127.0.0.1", "HostPort": "11435"}]},
        },
        "Mounts": [
            {"Type": "bind", "Destination": target, "Source": str(source)}
            for target, source in [
                ("/models", ROOT / ".cache/ollama/models"), ("/runtime", runtime),
                ("/tmp", runtime / "tmp"), ("/root", runtime / "profile"),
            ]
        ],
    }


def invoke(tmp_path, container, *arguments):
    state = tmp_path / "state.json"
    state.write_text(json.dumps(container), encoding="utf-8")
    calls = tmp_path / "calls.jsonl"
    fake_python = tmp_path / "fake_docker.py"
    fake_python.write_text(
        "import json, os, pathlib, sys\n"
        "args = sys.argv[1:]\n"
        "for name in ('TEMP', 'TMP', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA'):\n"
        "    assert pathlib.Path(os.environ[name]).is_relative_to(pathlib.Path(os.environ['BMQ_TEST_ROOT']))\n"
        "with open(os.environ['BMQ_TEST_CALLS'], 'a', encoding='utf-8') as f: f.write(json.dumps(args)+'\\n')\n"
        "args = args[4:]  # --config PATH --host PIPE\n"
        "state = json.loads(pathlib.Path(os.environ['BMQ_TEST_STATE']).read_text())\n"
        "if args[0] == 'ps': print('breakmyquery-llama32' if state else '')\n"
        "elif args[0] == 'inspect': print(json.dumps([state]))\n"
        "elif args[0] == 'stop': print('breakmyquery-llama32')\n"
        "else: sys.exit(91)\n",
        encoding="utf-8",
    )
    fake_command = tmp_path / "fake_docker.cmd"
    fake_command.write_text(
        f'@"{ROOT / ".venv/Scripts/python.exe"}" "{fake_python}" %*\r\n', encoding="utf-8"
    )
    quote = lambda value: "'" + str(value).replace("'", "''") + "'"
    harness = tmp_path / "harness.ps1"
    harness.write_text(
        "function Get-Command { param($Name) [pscustomobject]@{Source=" + quote(fake_command) + "} }\n"
        "function Invoke-RestMethod { param($Uri, $Method, $Body, $ContentType, $TimeoutSec)\n"
        " if ($Uri -like '*/api/generate') {\n"
        "   @{uri=$Uri;method=$Method;body=($Body | ConvertFrom-Json);content_type=$ContentType;timeout=$TimeoutSec} |\n"
        "     ConvertTo-Json -Depth 8 -Compress | Set-Content -LiteralPath $env:BMQ_TEST_REST_CALLS\n"
        "   [pscustomobject]@{done=$true}; return\n"
        " }\n"
        " if ($Uri -like '*/api/version') { [pscustomobject]@{version='0.15.1'} }\n"
        " else { [pscustomobject]@{models=@([pscustomobject]@{name='llama3.2:latest'})} }\n"
        "}\n"
        "& " + quote(ROOT / "scripts/start-local-model.ps1") + " " + " ".join(arguments) + "\n",
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment.update(BMQ_TEST_STATE=str(state), BMQ_TEST_CALLS=str(calls), BMQ_TEST_ROOT=str(ROOT),
                       BMQ_TEST_REST_CALLS=str(tmp_path / "rest.json"))
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(harness)],
        cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=30,
    )
    recorded = [json.loads(line)[4:] for line in calls.read_text().splitlines()] if calls.exists() else []
    return result, recorded


@pytest.mark.parametrize("argument", ["-Status", ""])
def test_running_owned_runtime_is_idempotent_from_another_directory(tmp_path, argument):
    result, calls = invoke(tmp_path, owned_container(), argument)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["model"] == "llama3.2:latest"
    assert [call[0] for call in calls] == ["ps", "inspect"]


def test_stop_only_targets_the_owned_dedicated_container(tmp_path):
    result, calls = invoke(tmp_path, owned_container(), "-Stop")
    assert result.returncode == 0, result.stderr
    assert calls[-1] == ["stop", "--time", "10", NAME]
    assert not any("rag-ollama" in call for call in calls)


@pytest.mark.parametrize("bad_setting", ["owner", "port", "extra_binding", "extra_port", "mount", "writable", "logs"])
def test_rejects_foreign_or_uncontained_existing_runtime(tmp_path, bad_setting):
    container = owned_container()
    if bad_setting == "owner":
        container["Config"]["Labels"]["breakmyquery.repo"] = r"D:\Other"
    elif bad_setting == "port":
        container["HostConfig"]["PortBindings"]["11434/tcp"][0]["HostIp"] = "0.0.0.0"
    elif bad_setting == "extra_binding":
        container["HostConfig"]["PortBindings"]["11434/tcp"].append(
            {"HostIp": "0.0.0.0", "HostPort": "11436"}
        )
    elif bad_setting == "extra_port":
        container["HostConfig"]["PortBindings"]["8080/tcp"] = [
            {"HostIp": "0.0.0.0", "HostPort": "8080"}
        ]
    elif bad_setting == "mount":
        container["Mounts"][0]["Source"] = r"C:\Other"
    elif bad_setting == "writable":
        container["HostConfig"]["ReadonlyRootfs"] = False
    else:
        container["HostConfig"]["LogConfig"]["Type"] = "json-file"
    result, calls = invoke(tmp_path, container, "-Stop")
    assert result.returncode != 0
    assert [call[0] for call in calls] == ["ps", "inspect"]


def test_status_of_absent_runtime_does_not_start_or_copy(tmp_path):
    result, calls = invoke(tmp_path, None, "-Status")
    assert result.returncode != 0
    assert "not running" in result.stderr
    assert [call[0] for call in calls] == ["ps"]


def test_explicit_warmup_uses_empty_prompt_bounded_timeout_and_matching_context(tmp_path):
    result, calls = invoke(tmp_path, owned_container(), "-Warmup")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["warmed"] is True
    request = json.loads((tmp_path / "rest.json").read_text(encoding="utf-8-sig"))
    assert request == {
        "uri": "http://127.0.0.1:11435/api/generate", "method": "Post",
        "content_type": "application/json", "timeout": 240,
        "body": {"model": "llama3.2:latest", "prompt": "", "stream": False,
                 "keep_alive": "30m", "options": {"num_ctx": 8192}},
    }
    assert [call[0] for call in calls] == ["ps", "inspect"]


@pytest.mark.parametrize("flags", [("-Warmup", "-Status"), ("-Warmup", "-Stop"), ("-Status", "-Stop")])
def test_conflicting_actions_are_rejected_before_docker_calls(tmp_path, flags):
    result, calls = invoke(tmp_path, owned_container(), *flags)
    assert result.returncode != 0
    assert not calls
