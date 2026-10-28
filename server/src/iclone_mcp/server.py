from __future__ import annotations

import asyncio
import base64
import inspect
from typing import Annotated, Any, Literal

from mcp.server import MCPServer
from mcp.types import CallToolResult, ImageContent, ToolAnnotations
from pydantic import Field

from .connection import ICloneConnection
from .upstream_catalog import UPSTREAM_TOOL_CATALOG
from .window_capture import capture_window_png


Vector3 = Annotated[
    list[float],
    Field(min_length=3, max_length=3, description="Three numeric XYZ components."),
]
Point3 = Annotated[
    dict[str, float],
    Field(description="An XYZ object; omitted components keep their current value."),
]
ObjectIds = Annotated[
    list[str],
    Field(description="Stable object IDs returned by iClone scene inspection tools."),
]
NonEmptyObjectIds = Annotated[
    list[str],
    Field(
        min_length=1,
        description="One or more stable object IDs returned by scene inspection tools.",
    ),
]

mcp = MCPServer(
    "iClone MCP",
    instructions=(
        "Inspect the iClone scene before changing it. Operate on stable object IDs, "
        "not names. After mutations, verify the result with object/scene inspection "
        "or `render_image`."
    ),
)
connection = ICloneConnection()

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
MUTATION = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=False,
)


async def capture_window() -> CallToolResult:
    """Capture the visible app window by HWND from the MCP host."""
    status = await connection.request("get_status")
    process_id = status.get("application_pid")
    if isinstance(process_id, bool) or not isinstance(process_id, int) or process_id <= 0:
        raise RuntimeError("Window capture requires the updated plugin application_pid; deploy and reload the plugin.")
    application = str(status.get("application", "")).casefold()
    if "character creator" in application:
        executable_name = "CharacterCreator.exe"
    elif "iclone" in application:
        executable_name = "iClone.exe"
    else:
        executable_name = "iClone.exe"

    image_data, metadata = await asyncio.to_thread(
        capture_window_png, executable_name, process_id
    )
    return CallToolResult(
        content=[
            ImageContent(
                data=base64.b64encode(image_data).decode("ascii"),
                mimeType="image/png",
            )
        ],
        structuredContent=metadata,
    )


@mcp.tool(title="Get iClone status", annotations=READ_ONLY)
async def get_iclone_status(
    include: Annotated[
        list[str] | str | None,
        Field(
            description=(
                "Optional status sections to attach: application, api, license, "
                "system, runtime, network, mocap, ping."
            ),
        ),
    ] = None,
) -> dict[str, Any]:
    """Check the local iClone bridge, application version, and listener endpoint."""
    params: dict[str, Any] = {}
    if include is not None:
        params["include"] = include
    return await connection.request("get_status", params)


@mcp.tool(title="Inspect iClone scene", annotations=READ_ONLY)
async def get_scene_info(
    limit: Annotated[
        int,
        Field(ge=1, le=500, description="Maximum object summaries to return."),
    ] = 100,
) -> dict[str, Any]:
    """Inspect timeline state, selection, camera, and top-level scene objects."""
    return await connection.request("get_scene_info", {"limit": limit})


@mcp.tool(title="Inspect iClone object", annotations=READ_ONLY)
async def get_object_info(object_id: str) -> dict[str, Any]:
    """Inspect one object by stable ID, including transforms and world bounds."""
    return await connection.request("get_object_info", {"object_id": object_id})


@mcp.tool(
    title="Select iClone objects",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    ),
)
async def select_objects(object_ids: ObjectIds) -> dict[str, Any]:
    """Replace the iClone selection; pass an empty array to clear it."""
    return await connection.request("select_objects", {"object_ids": object_ids})


@mcp.tool(
    title="Set iClone object transform",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    ),
)
async def set_transform(
    object_id: str | None = None,
    name: str | None = None,
    position_cm: Vector3 | None = None,
    position: Point3 | None = None,
    rotation_deg_xyz: Vector3 | None = None,
    rotation_degrees: Point3 | None = None,
    scale_xyz: Vector3 | None = None,
    scale: Point3 | None = None,
    time_ms: Annotated[
        int | None,
        Field(ge=0, description="Timeline time in milliseconds; current time if omitted."),
    ] = None,
    frame: Annotated[
        int | None,
        Field(ge=0, description="Timeline frame; current time if omitted."),
    ] = None,
) -> dict[str, Any]:
    """Key supplied local transform components by stable ID or scene name."""
    params: dict[str, Any] = {}
    if object_id is not None:
        params["object_id"] = object_id
    if name is not None:
        params["name"] = name
    if position_cm is not None:
        params["position_cm"] = position_cm
    if position is not None:
        params["position"] = position
    if rotation_deg_xyz is not None:
        params["rotation_deg_xyz"] = rotation_deg_xyz
    if rotation_degrees is not None:
        params["rotation_degrees"] = rotation_degrees
    if scale_xyz is not None:
        params["scale_xyz"] = scale_xyz
    if scale is not None:
        params["scale"] = scale
    if time_ms is not None:
        params["time_ms"] = time_ms
    if frame is not None:
        params["frame"] = frame
    return await connection.request("set_transform", params)


@mcp.tool(title="Import iClone asset", annotations=MUTATION)
async def import_asset(path: str, name: str | None = None) -> dict[str, Any]:
    """Import a supported object asset from an absolute local filesystem path."""
    params: dict[str, Any] = {"path": path}
    if name is not None:
        params["name"] = name
    return await connection.request("import_asset", params)


@mcp.tool(
    title="Delete iClone objects",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=False,
        open_world_hint=False,
    ),
)
async def delete_objects(object_ids: NonEmptyObjectIds) -> dict[str, Any]:
    return await connection.request("delete_objects", {"object_ids": object_ids})


@mcp.tool(title="Undo iClone action", annotations=MUTATION)
async def undo() -> dict[str, bool]:
    """Undo the latest iClone action."""
    return await connection.request("undo")


@mcp.tool(title="Redo iClone action", annotations=MUTATION)
async def redo() -> dict[str, bool]:
    """Redo the latest undone iClone action."""
    return await connection.request("redo")


def _schema_annotation(schema: dict[str, Any]) -> Any:
    schema_type = schema.get("type")
    if schema.get("enum"):
        annotation = Literal[tuple(schema["enum"])]
    elif schema_type == "string":
        annotation = str
    elif schema_type == "integer":
        annotation = int
    elif schema_type == "number":
        annotation = float
    elif schema_type == "boolean":
        annotation = bool
    elif schema_type == "array":
        item_schema = schema.get("items", {})
        annotation = list[_schema_annotation(item_schema)]
    elif schema_type == "object":
        annotation = dict[str, Any]
    else:
        annotation = Any

    field_kwargs: dict[str, Any] = {}
    if schema.get("description"):
        field_kwargs["description"] = schema["description"]
    if schema_type in {"integer", "number"}:
        if "minimum" in schema:
            field_kwargs["ge"] = schema["minimum"]
        if "exclusiveMinimum" in schema:
            field_kwargs["gt"] = schema["exclusiveMinimum"]
        if "maximum" in schema:
            field_kwargs["le"] = schema["maximum"]
        if "exclusiveMaximum" in schema:
            field_kwargs["lt"] = schema["exclusiveMaximum"]
    if field_kwargs:
        return Annotated[annotation, Field(**field_kwargs)]
    return annotation


def _upstream_annotations(name: str, metadata: dict[str, Any] | None = None) -> ToolAnnotations:
    meta = metadata or UPSTREAM_TOOL_CATALOG.get(name, {})
    if meta.get("destructive") or name in {
        "delete_object",
        "run_python_file",
        "render_job",
        "clear_scene_animations",
        "transform_key",
    }:
        return ToolAnnotations(
            read_only_hint=False,
            destructive_hint=True,
            idempotent_hint=False,
            open_world_hint=False,
        )
    if name.startswith("clear_"):
        return ToolAnnotations(
            read_only_hint=False,
            destructive_hint=True,
            idempotent_hint=False,
            open_world_hint=False,
        )
    if meta.get("read_only") or name.startswith("get_") or name.startswith("list_"):
        return READ_ONLY
    return MUTATION


def _register_upstream_tools() -> None:
    for name, metadata in UPSTREAM_TOOL_CATALOG.items():
        if name in {"import_asset", "set_transform", "capture_window"}:
            continue
        if metadata.get("advertise") is False:
            continue

        schema = metadata.get("inputSchema", {})
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        parameters = []
        for parameter_name, parameter_schema in properties.items():
            default = (
                inspect.Parameter.empty
                if parameter_name in required
                else None
            )
            parameters.append(
                inspect.Parameter(
                    parameter_name,
                    inspect.Parameter.KEYWORD_ONLY,
                    annotation=_schema_annotation(parameter_schema),
                    default=default,
                )
            )

        async def invoke(_command=name, **kwargs: Any) -> dict[str, Any]:
            return await connection.request(
                _command,
                {key: value for key, value in kwargs.items() if value is not None},
            )

        invoke.__name__ = name
        invoke.__signature__ = inspect.Signature(
            parameters,
            return_annotation=dict[str, Any],
        )
        description = metadata.get("description", "")
        if name == "delete_object":
            description = (
                "Deletes one object by name and records the deletion for undo."
            )
        mcp.add_tool(
            invoke,
            name=name,
            title=name.replace("_", " ").title(),
            description=description,
            annotations=_upstream_annotations(name, metadata),
            structured_output=True,
        )


_register_upstream_tools()
mcp.add_tool(
    capture_window,
    name="capture_window",
    title="Capture iClone window",
    description=UPSTREAM_TOOL_CATALOG["capture_window"]["description"],
    annotations=READ_ONLY,
    structured_output=False,
)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
