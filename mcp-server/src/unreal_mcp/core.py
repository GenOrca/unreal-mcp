# Copyright (c) 2025 GenOrca. All Rights Reserved.

import asyncio
import socket
import json
import sys

# Custom Exception classes
class ToolInputError(Exception):
    pass

class UnrealExecutionError(Exception):
    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = details if details is not None else {}


async def send_unreal_action(action_module: str, params: dict) -> dict:
    """
    Convention-based wrapper for send_to_unreal.
    Auto-derives action_name from the calling function's name.
    Convention: caller 'foo_bar' → action 'ue_foo_bar'
    Also includes standard error handling.
    """
    caller_name = sys._getframe(1).f_code.co_name
    action_name = f"ue_{caller_name}"
    try:
        return await send_to_unreal(action_module, action_name, params)
    except UnrealExecutionError as e:
        return {"success": False, "message": str(e), "details": e.details}
    except Exception as e:
        return {"success": False, "message": f"An unexpected error occurred: {str(e)}"}

def _unwrap_result(response: dict) -> dict:
    """
    The TCP server's python_call path double-wraps the action's JSON return.
    The C++ server runs `print(execute_action(...))` and captures stdout into a
    string "result" field, so the wire shape is:

        {"success": <python-exec ok>, "message": ..., "result": "<action json string>"}

    The OUTER "success" is whether Python *ran*, NOT whether the action
    succeeded. The real action dict (with its own "success", "actor_label", ...)
    is the JSON string in "result". Unwrap it so callers get the action dict.
    """
    if not isinstance(response, dict):
        return response
    inner = response.get("result")
    if isinstance(inner, str):
        try:
            parsed = json.loads(inner)
        except (ValueError, TypeError):
            return response
        if isinstance(parsed, (dict, list)):
            return parsed
    return response


# Core send_to_unreal function
def _send_to_unreal_sync(
    action_module: str, action_name: str, params: dict
) -> dict:
    """
    Sends a command to the Unreal Engine Python script via socket communication.
    Args:
        action_module (str): The Python module in Unreal (e.g., 'actor_actions').
        action_name (str): The function name in the module (e.g., 'ue_spawn_actor_from_class').
        params (dict): A dictionary of parameters for the action.
    Returns:
        dict: The JSON response from Unreal.
    Raises:
        UnrealExecutionError: If any error occurs during socket communication or JSON processing.
        ToolInputError: If there's an issue with the input that can be determined client-side (though less common here).
    """
    HOST = '127.0.0.1'
    PORT = 12029
    command = {
        "type": "python_call",
        "module": action_module,
        "function": action_name,
        "args": params
    }
    response_str = ""
    try:
        json_str = json.dumps(command, ensure_ascii=False)
        message_bytes = json_str.encode('utf-8')

        # Using asyncio for socket communication would be better for a fully async server,
        # but standard socket is used here as per existing structure.
        # If FastMCP's .run() uses an async server like uvicorn, this blocking call
        # will run in a thread pool.
        with socket.create_connection((HOST, PORT), timeout=30) as sock:
            sock.sendall(message_bytes)
            response_buffer = b''
            while True:
                chunk = sock.recv(16384) 
                if not chunk:
                    break
                response_buffer += chunk
            
            if not response_buffer:
                raise UnrealExecutionError("No response received from Unreal.", details={"host": HOST, "port": PORT})

            response_str = response_buffer.decode('utf-8')
            response_json = json.loads(response_str)

            # Outer "success" is python-exec success. False = Python failed to run
            # (bad module/function, syntax error) → propagate as an error.
            if isinstance(response_json, dict) and response_json.get("success") is False:
                raise UnrealExecutionError(
                    response_json.get("message", "Unknown error from Unreal action."),
                    details=response_json.get("details")
                )

            # Python ran; unwrap the action's real result out of the "result" string.
            # The action's own success/failure is preserved in the unwrapped dict.
            return _unwrap_result(response_json)

    except socket.timeout:
        raise UnrealExecutionError(f"Socket timeout ({HOST}:{PORT}): No response from Unreal.", details={"host": HOST, "port": PORT})
    except ConnectionRefusedError:
        raise UnrealExecutionError(f"Connection refused ({HOST}:{PORT}). Ensure Unreal MCPython TCP server is active.", details={"host": HOST, "port": PORT})
    except json.JSONDecodeError as je:
        raise UnrealExecutionError(f"Failed to decode JSON response from Unreal: {je}. Raw response: '{response_str}'", details={"host": HOST, "port": PORT, "raw_response": response_str})
    except socket.error as se:
        raise UnrealExecutionError(f"Socket error ({HOST}:{PORT}): {se}", details={"host": HOST, "port": PORT})
    except UnrealExecutionError: # Re-raise if it's already our specific error type
        raise
    except Exception as e: # Catch any other unexpected errors
        raise UnrealExecutionError(f"An unexpected error occurred in send_to_unreal ({HOST}:{PORT}): {type(e).__name__} - {e}", details={"host": HOST, "port": PORT, "error_type": type(e).__name__})


async def send_to_unreal(
    action_module: str, action_name: str, params: dict
) -> dict:
    """Runs the blocking Unreal socket exchange without blocking the event loop."""
    return await asyncio.to_thread(
        _send_to_unreal_sync, action_module, action_name, params
    )


async def send_python_exec(code: str) -> dict:
    """
    Sends raw Python code to the Unreal Engine TCP server for execution.
    Uses the existing "type": "python" dispatch path.
    The C++ server executes the code and captures print() output.
    """
    HOST = '127.0.0.1'
    PORT = 12029
    TIMEOUT = 30
    command = {"type": "python", "code": code}
    response_str = ""
    try:
        json_str = json.dumps(command, ensure_ascii=False)
        message_bytes = json_str.encode('utf-8')

        with socket.create_connection((HOST, PORT), timeout=TIMEOUT) as sock:
            sock.sendall(message_bytes)
            response_buffer = b''
            while True:
                chunk = sock.recv(16384)
                if not chunk:
                    break
                response_buffer += chunk

            if not response_buffer:
                raise UnrealExecutionError(
                    "No response received from Unreal for Python execution.",
                    details={"host": HOST, "port": PORT}
                )

            response_str = response_buffer.decode('utf-8')
            response_json = json.loads(response_str)
            return response_json

    except socket.timeout:
        raise UnrealExecutionError(
            f"Socket timeout ({HOST}:{PORT}): Python execution did not complete within {TIMEOUT}s.",
            details={"host": HOST, "port": PORT}
        )
    except ConnectionRefusedError:
        raise UnrealExecutionError(
            f"Connection refused ({HOST}:{PORT}). Ensure Unreal MCPython TCP server is active.",
            details={"host": HOST, "port": PORT}
        )
    except json.JSONDecodeError as je:
        raise UnrealExecutionError(
            f"Failed to decode JSON response: {je}. Raw: '{response_str}'",
            details={"host": HOST, "port": PORT, "raw_response": response_str}
        )
    except UnrealExecutionError:
        raise
    except Exception as e:
        raise UnrealExecutionError(
            f"Unexpected error during Python execution: {type(e).__name__} - {e}",
            details={"host": HOST, "port": PORT, "error_type": type(e).__name__}
        )


async def send_livecoding_compile() -> dict:
    """
    Sends a livecoding_compile command to the Unreal Engine TCP server.
    Triggers C++ hot-reload via the LiveCoding module.
    Waits for compilation to complete before returning the result.
    """
    HOST = '127.0.0.1'
    PORT = 12029
    TIMEOUT = 180
    command = {"type": "livecoding_compile"}
    response_str = ""
    try:
        json_str = json.dumps(command, ensure_ascii=False)
        message_bytes = json_str.encode('utf-8')

        with socket.create_connection((HOST, PORT), timeout=TIMEOUT) as sock:
            sock.sendall(message_bytes)
            response_buffer = b''
            while True:
                chunk = sock.recv(16384)
                if not chunk:
                    break
                response_buffer += chunk

            if not response_buffer:
                raise UnrealExecutionError(
                    "No response received from Unreal for LiveCoding compile.",
                    details={"host": HOST, "port": PORT}
                )

            response_str = response_buffer.decode('utf-8')
            response_json = json.loads(response_str)

            if isinstance(response_json, dict) and response_json.get("success") is False:
                raise UnrealExecutionError(
                    response_json.get("message", "LiveCoding compile failed."),
                    details=response_json
                )
            return response_json

    except socket.timeout:
        raise UnrealExecutionError(
            f"Socket timeout ({HOST}:{PORT}): LiveCoding compilation did not complete within {TIMEOUT}s.",
            details={"host": HOST, "port": PORT}
        )
    except ConnectionRefusedError:
        raise UnrealExecutionError(
            f"Connection refused ({HOST}:{PORT}). Ensure Unreal MCPython TCP server is active.",
            details={"host": HOST, "port": PORT}
        )
    except json.JSONDecodeError as je:
        raise UnrealExecutionError(
            f"Failed to decode JSON response: {je}. Raw: '{response_str}'",
            details={"host": HOST, "port": PORT, "raw_response": response_str}
        )
    except UnrealExecutionError:
        raise
    except Exception as e:
        raise UnrealExecutionError(
            f"Unexpected error during LiveCoding compile: {type(e).__name__} - {e}",
            details={"host": HOST, "port": PORT, "error_type": type(e).__name__}
        )
