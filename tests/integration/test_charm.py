#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Indico charm integration tests."""

import juju.action
import pytest
import requests
from ops.model import ActiveStatus, Application
from pytest_operator.plugin import OpsTest

from charm import CELERY_PROMEXP_PORT, NGINX_PROMEXP_PORT, STATSD_PROMEXP_PORT


@pytest.mark.asyncio
@pytest.mark.abort_on_fail
async def test_active(app: Application):
    """Check that the charm is active.

    Assume that the charm has already been built and is running.
    """
    # Application actually does have units
    assert app.units[0].workload_status == ActiveStatus.name  # type: ignore


@pytest.mark.asyncio
@pytest.mark.abort_on_fail
async def test_indico_is_up(ops_test: OpsTest, app: Application):
    """Check that the bootstrap page is reachable.

    Assume that the charm has already been built and is running.
    """
    assert ops_test.model
    # Read the IP address of indico
    status = await ops_test.model.get_status()
    unit = list(status.applications[app.name].units)[0]
    address = status["applications"][app.name]["units"][unit]["address"]
    # Send request to bootstrap page and set Host header to app_name (which the application
    # expects)
    response = requests.get(
        f"http://{address}:8080/bootstrap", headers={"Host": f"{app.name}.local"}, timeout=10
    )
    assert response.status_code == 200


@pytest.mark.asyncio
@pytest.mark.abort_on_fail
async def test_prom_exporters_are_up(app: Application):
    """
    arrange: given charm in its initial state
    act: when the metrics endpoints are scraped
    assert: the response is 200 (HTTP OK)
    """
    # Application actually does have units
    indico_unit = app.units[0]  # type: ignore
    prometheus_targets = [
        f"localhost:{NGINX_PROMEXP_PORT}",
        f"localhost:{STATSD_PROMEXP_PORT}",
        f"localhost:{CELERY_PROMEXP_PORT}",
    ]
    # Send request to /metrics for each target and check the response
    for target in prometheus_targets:
        cmd = f"curl http://{target}/metrics"
        action = await indico_unit.run(cmd)
        result = await action.wait()
        code = result.results.get("return-code")
        stdout = result.results.get("stdout")
        stderr = result.results.get("stderr")
        assert code == 0, f"{cmd} failed ({code}): {stderr or stdout}"


@pytest.mark.asyncio
@pytest.mark.abort_on_fail
async def test_health_checks(app: Application):
    """Runs health checks for each container.

    Assume that the charm has already been built and is running.
    """
    container_list = ["indico", "indico-nginx", "indico-celery"]
    # Application actually does have units
    indico_unit = app.units[0]  # type: ignore
    for container in container_list:
        cmd = f"PEBBLE_SOCKET=/charm/containers/{container}/pebble.socket /charm/bin/pebble checks"
        action = await indico_unit.run(cmd)
        result = await action.wait()
        code = result.results.get("return-code")
        stdout = result.results.get("stdout")
        stderr = result.results.get("stderr")
        assert code == 0, f"{cmd} failed ({code}): {stderr or stdout}"
        # When executing the checks, `0/3` means there are 0 errors of 3.
        # Each check has it's own `0/3`, so we will count `n` times,
        # where `n` is the number of checks for that container.
        if container != "indico-nginx":
            assert stdout.count("0/3") == 1
        else:
            assert stdout.count("0/3") == 2


@pytest.mark.asyncio
@pytest.mark.abort_on_fail
async def test_add_admin(app: Application):
    """
    arrange: given charm in its initial state
    act: run the add-admin action
    assert: check the output in the action result
    """

    # Application actually does have units
    assert app.units[0]  # type: ignore

    email = "sample@email.com"
    # This is a test password
    password = "somepassword"  # nosec

    # Application actually does have units
    action: juju.action.Action = await app.units[0].run_action(  # type: ignore
        "add-admin", email=email, password=password
    )
    await action.wait()
    assert action.status == "completed"
    assert action.results["user"] == email
    assert f'Admin with email "{email}" correctly created' in action.results["output"]
