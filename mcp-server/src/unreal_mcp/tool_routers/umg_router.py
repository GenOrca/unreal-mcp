# Copyright (c) 2025 GenOrca. All Rights Reserved.

# MCP Router for UMG (Unreal Motion Graphics) Widget Tools

from typing import Annotated, Optional
from pydantic import Field
from fastmcp import FastMCP

from unreal_mcp.core import send_unreal_action, ToolInputError

UMG_ACTIONS_MODULE = "UnrealMCPython.umg_actions"

umg_mcp = FastMCP(name="UmgMCP", description="Tools for creating and editing UMG Widget Blueprints in Unreal Engine.")

@umg_mcp.tool(
    name="create_widget_blueprint",
    description="Creates a new UMG Widget Blueprint asset at the specified content browser path.",
    tags={"unreal", "umg", "widget", "blueprint", "create"}
)
async def create_widget_blueprint(
    name: Annotated[str, Field(description="Name of the new Widget Blueprint asset.", min_length=1)],
    path: Annotated[str, Field(description="Content browser path where the asset will be created (e.g., '/Game/UI').", min_length=1)],
    parent_class: Annotated[Optional[str], Field(description="Parent class name for the widget (default: 'UserWidget').")] = "UserWidget"
) -> dict:
    """Creates a new Widget Blueprint asset."""
    params = {"name": name, "path": path, "parent_class": parent_class}
    return await send_unreal_action(UMG_ACTIONS_MODULE, params)


@umg_mcp.tool(
    name="get_widget_blueprint_info",
    description="Returns the widget tree hierarchy and widget list of an existing Widget Blueprint.",
    tags={"unreal", "umg", "widget", "info", "hierarchy"}
)
async def get_widget_blueprint_info(
    asset_path: Annotated[str, Field(description="Full content path to the Widget Blueprint (e.g., '/Game/UI/MyWidget.MyWidget').", min_length=1)]
) -> dict:
    """Returns widget tree info for a Widget Blueprint."""
    params = {"asset_path": asset_path}
    return await send_unreal_action(UMG_ACTIONS_MODULE, params)


@umg_mcp.tool(
    name="add_widget",
    description=(
        "Adds a new widget component to a Widget Blueprint's widget tree. "
        "Supported widget_type values: CanvasPanel, TextBlock, Button, Image, "
        "HorizontalBox, VerticalBox, Border, Overlay, ScrollBox, SizeBox, "
        "CheckBox, EditableText, EditableTextBox, ProgressBar, Slider."
    ),
    tags={"unreal", "umg", "widget", "add", "hierarchy"}
)
async def add_widget(
    asset_path: Annotated[str, Field(description="Full content path to the Widget Blueprint.", min_length=1)],
    widget_type: Annotated[str, Field(description="Type of widget to add (e.g., 'TextBlock', 'Button', 'CanvasPanel').", min_length=1)],
    widget_name: Annotated[str, Field(description="Unique name for the new widget within the blueprint.", min_length=1)],
    parent_name: Annotated[Optional[str], Field(description="Name of the parent panel widget. If omitted, the widget becomes the root or is added to the existing root panel.")] = None
) -> dict:
    """Adds a widget component to a Widget Blueprint."""
    params = {"asset_path": asset_path, "widget_type": widget_type, "widget_name": widget_name, "parent_name": parent_name}
    return await send_unreal_action(UMG_ACTIONS_MODULE, params)


@umg_mcp.tool(
    name="set_widget_properties",
    description=(
        "Sets properties on a widget within a Widget Blueprint. "
        "Common widget properties: text (str), visibility (str: visible/collapsed/hidden), "
        "color_and_opacity ([r,g,b,a]), background_color ([r,g,b,a]), font_size (int), hint_text (str), percent (float). "
        "Canvas slot properties (when parent is CanvasPanel): slot_position ([x,y]), slot_size ([w,h]), "
        "slot_alignment ([x,y]), slot_z_order (int)."
    ),
    tags={"unreal", "umg", "widget", "properties", "set"}
)
async def set_widget_properties(
    asset_path: Annotated[str, Field(description="Full content path to the Widget Blueprint.", min_length=1)],
    widget_name: Annotated[str, Field(description="Name of the widget to modify.", min_length=1)],
    properties: Annotated[dict, Field(description="Dictionary of property names to values to set on the widget.")]
) -> dict:
    """Sets properties on a widget in a Widget Blueprint."""
    if not properties:
        raise ToolInputError("'properties' must be a non-empty dictionary.")
    params = {"asset_path": asset_path, "widget_name": widget_name, "properties": properties}
    return await send_unreal_action(UMG_ACTIONS_MODULE, params)


@umg_mcp.tool(
    name="remove_widget",
    description="Removes a widget from the Widget Blueprint's widget tree.",
    tags={"unreal", "umg", "widget", "remove", "delete"}
)
async def remove_widget(
    asset_path: Annotated[str, Field(description="Full content path to the Widget Blueprint.", min_length=1)],
    widget_name: Annotated[str, Field(description="Name of the widget to remove.", min_length=1)]
) -> dict:
    """Removes a widget from a Widget Blueprint."""
    params = {"asset_path": asset_path, "widget_name": widget_name}
    return await send_unreal_action(UMG_ACTIONS_MODULE, params)


@umg_mcp.tool(
    name="compile_widget_blueprint",
    description="Compiles a Widget Blueprint and returns the compilation result.",
    tags={"unreal", "umg", "widget", "compile"}
)
async def compile_widget_blueprint(
    asset_path: Annotated[str, Field(description="Full content path to the Widget Blueprint.", min_length=1)]
) -> dict:
    """Compiles a Widget Blueprint."""
    params = {"asset_path": asset_path}
    return await send_unreal_action(UMG_ACTIONS_MODULE, params)
