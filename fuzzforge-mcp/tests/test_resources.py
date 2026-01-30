"""TODO."""

from datetime import UTC, datetime
from http import HTTPMethod
from json import loads
from typing import TYPE_CHECKING, cast

from fuzzforge_sdk.api.responses.executions import (
    GetFuzzForgeModuleExecutionsResponse,
    GetFuzzForgeWorkflowExecutionsResponse,
    ModuleExecutionSummary,
    WorkflowExecutionSummary,
)
from fuzzforge_sdk.api.responses.modules import (
    GetFuzzForgeModuleDefinitionResponse,
    GetFuzzForgeModuleDefinitionsResponse,
    ModuleDefinitionSummary,
)
from fuzzforge_types import FuzzForgeExecutionStatus, FuzzForgeModule

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastmcp import Client
    from fastmcp.client import FastMCPTransport
    from fuzzforge_types import (
        FuzzForgeExecutionIdentifier,
        FuzzForgeModuleIdentifier,
        FuzzForgeProjectIdentifier,
        FuzzForgeWorkflowIdentifier,
    )
    from mcp.types import TextResourceContents
    from pytest_httpx import HTTPXMock


async def test_get_fuzzforge_module_when_server_returns_valid_data(
    httpx_mock: HTTPXMock,
    mcp_client: Client[FastMCPTransport],
    random_module_description: Callable[[], str],
    random_module_identifier: Callable[[], FuzzForgeModuleIdentifier],
    random_module_name: Callable[[], str],
) -> None:
    """TODO."""
    module = GetFuzzForgeModuleDefinitionResponse(
        module_description=random_module_description(),
        module_identifier=random_module_identifier(),
        module_name=random_module_name(),
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
    )
    httpx_mock.add_response(
        json=module.model_dump(mode="json"),
        method=HTTPMethod.GET,
        url=f"http://127.0.0.1:8000/modules/{module.module_identifier}",
    )
    response = FuzzForgeModule.model_validate_json(
        json_data=cast(
            "TextResourceContents",
            (await mcp_client.read_resource(f"fuzzforge://modules/{module.module_identifier}"))[0],
        ).text,
    )
    assert response.module_description == module.module_description
    assert response.module_identifier == module.module_identifier
    assert response.module_name == module.module_name


async def test_get_fuzzforge_modules_when_server_returns_valid_data(
    httpx_mock: HTTPXMock,
    mcp_client: Client[FastMCPTransport],
    random_module_description: Callable[[], str],
    random_module_identifier: Callable[[], FuzzForgeModuleIdentifier],
    random_module_name: Callable[[], str],
) -> None:
    """TODO."""
    modules = [
        ModuleDefinitionSummary(
            module_description=random_module_description(),
            module_identifier=random_module_identifier(),
            module_name=random_module_name(),
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        ),
        ModuleDefinitionSummary(
            module_description=random_module_description(),
            module_identifier=random_module_identifier(),
            module_name=random_module_name(),
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        ),
    ]
    httpx_mock.add_response(
        json=GetFuzzForgeModuleDefinitionsResponse(
            modules=modules,
            total=2,
            limit=100,
            offset=0,
        ).model_dump(mode="json"),
        method=HTTPMethod.GET,
        url="http://127.0.0.1:8000/modules",
    )
    response = [
        ModuleDefinitionSummary.model_validate(entry)
        for entry in loads(
            cast("TextResourceContents", (await mcp_client.read_resource("fuzzforge://modules/"))[0]).text
        )
    ]
    assert len(response) == len(modules)
    for expected, module in zip(modules, response, strict=True):
        assert module.module_description == expected.module_description
        assert module.module_identifier == expected.module_identifier
        assert module.module_name == expected.module_name


async def test_get_executions_when_server_returns_valid_data(
    httpx_mock: HTTPXMock,
    mcp_client: Client[FastMCPTransport],
    random_module_identifier: Callable[[], FuzzForgeModuleIdentifier],
    random_module_execution_identifier: Callable[[], FuzzForgeExecutionIdentifier],
    random_workflow_identifier: Callable[[], FuzzForgeWorkflowIdentifier],
    random_workflow_execution_identifier: Callable[[], FuzzForgeExecutionIdentifier],
) -> None:
    """TODO."""
    project_identifier: FuzzForgeProjectIdentifier = mcp_client.transport.server._lifespan_result.PROJECT_IDENTIFIER  # type: ignore[union-attr] # noqa: SLF001
    modules = [
        ModuleExecutionSummary(
            execution_identifier=random_module_execution_identifier(),
            module_identifier=random_module_identifier(),
            execution_status=FuzzForgeExecutionStatus.PENDING,
            error=None,
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        ),
        ModuleExecutionSummary(
            execution_identifier=random_module_execution_identifier(),
            module_identifier=random_module_identifier(),
            execution_status=FuzzForgeExecutionStatus.PENDING,
            error=None,
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        ),
    ]
    workflows = [
        WorkflowExecutionSummary(
            execution_identifier=random_workflow_execution_identifier(),
            workflow_identifier=random_workflow_identifier(),
            workflow_status=FuzzForgeExecutionStatus.PENDING,
            error=None,
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        ),
        WorkflowExecutionSummary(
            execution_identifier=random_workflow_execution_identifier(),
            workflow_identifier=random_workflow_identifier(),
            workflow_status=FuzzForgeExecutionStatus.PENDING,
            error=None,
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        ),
    ]
    httpx_mock.add_response(
        json=GetFuzzForgeModuleExecutionsResponse(
            executions=modules,
            project_identifier=project_identifier,
            total=2,
        ).model_dump(mode="json"),
        method=HTTPMethod.GET,
        url=f"http://127.0.0.1:8000/projects/{project_identifier}/modules",
    )
    httpx_mock.add_response(
        json=GetFuzzForgeWorkflowExecutionsResponse(
            workflows=workflows,
            project_identifier=project_identifier,
            total=2,
        ).model_dump(mode="json"),
        method=HTTPMethod.GET,
        url=f"http://127.0.0.1:8000/projects/{project_identifier}/workflows",
    )
    response = loads(cast("TextResourceContents", (await mcp_client.read_resource("fuzzforge://executions/"))[0]).text)
    assert len(response) == len(modules) + len(workflows)
    for expected_module, module in zip(
        modules, [ModuleExecutionSummary.model_validate(entry) for entry in response[: len(modules)]], strict=True
    ):
        assert module.execution_identifier == expected_module.execution_identifier
        assert module.module_identifier == expected_module.module_identifier
    for expected_workflow, workflow in zip(
        workflows, [WorkflowExecutionSummary.model_validate(entry) for entry in response[len(workflows) :]], strict=True
    ):
        assert workflow.execution_identifier == expected_workflow.execution_identifier
        assert workflow.workflow_identifier == expected_workflow.workflow_identifier
