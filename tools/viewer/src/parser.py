import json
import logging
from pathlib import Path
from typing import Generator, Any, Dict, Optional

logger = logging.getLogger("session-viewer")

class SessionParser:
    """Handles incremental parsing of session files (JSONL or pretty-printed)."""

    def __init__(self, filepath: Path, chunk_size: int = 65536):
        self.filepath = filepath
        self.chunk_size = chunk_size

    def stream_objects(self) -> Generator[Dict[str, Any], None, None]:
        """Generator that yields top-level JSON objects from the file."""
        if not self.filepath.exists():
            return

        with open(self.filepath, "r", encoding="utf-8") as f:
            buffer = ""
            depth = 0
            start_index = -1
            
            while True:
                chunk = f.read(self.chunk_size)
                if not chunk:
                    break
                
                # Append chunk to memory and scan for objects
                for i, char in enumerate(chunk):
                    if char == '{':
                        if depth == 0:
                            start_index = len(buffer) + i
                        depth += 1
                    elif char == '}':
                        depth -= 1
                        if depth == 0 and start_index != -1:
                            # Full object captured
                            full_text = buffer + chunk
                            end_index = i + 1
                            obj_str = full_text[start_index:len(buffer) + end_index]
                            
                            try:
                                yield json.loads(obj_str)
                            except json.JSONDecodeError as e:
                                logger.error(f"Failed to parse object: {e}")
                            
                            start_index = -1

                # Update buffer and adjust start_index if we are mid-object
                buffer += chunk
                if start_index == -1:
                    buffer = "" # Object finished, clear buffer
                else:
                    # Keep everything from start_index onwards
                    buffer = buffer[start_index:]
                    start_index = 0

    def load_full(self) -> Dict[str, Any]:
        """Convenience method to load everything into a standard structure."""
        metadata = {}
        messages = []
        all_usages = []
        
        for obj in self.stream_objects():
            if not isinstance(obj, dict):
                continue
                
            if obj.get("_type") == "metadata":
                metadata.update({k: v for k, v in obj.items() if k != "messages"})
                if "messages" in obj:
                    messages.extend(obj["messages"])
            elif obj.get("_type") == "usage":
                all_usages.append(obj)
            elif "role" in obj:
                messages.append(obj)
            elif "messages" in obj:
                # Full session dump style
                metadata.update({k: v for k, v in obj.items() if k != "messages"})
                messages.extend(obj["messages"])

        # Group into turns by "user" role boundary
        turns = []
        current_turn_msgs = []
        for m in messages:
            if m.get("role") == "user" and current_turn_msgs:
                turns.append(current_turn_msgs)
                current_turn_msgs = []
            current_turn_msgs.append(m)
        if current_turn_msgs:
            turns.append(current_turn_msgs)
            
        usage_idx = 0
        for turn_messages in turns:
            assistant_messages = [m for m in turn_messages if m.get("role") == "assistant"]
            k = len(assistant_messages)
            if k == 0:
                continue
                
            turn_usages = all_usages[usage_idx : usage_idx + k]
            usage_idx += k
            
            if turn_usages:
                aggregated = {
                    "prompt_tokens": sum(u.get("prompt_tokens", 0) for u in turn_usages),
                    "completion_tokens": sum(u.get("completion_tokens", 0) for u in turn_usages),
                    "total_tokens": sum(u.get("total_tokens", 0) for u in turn_usages),
                    "cached_tokens": sum(u.get("cached_tokens", 0) for u in turn_usages),
                    "requests": k
                }
                last_assistant = assistant_messages[-1]
                last_assistant["usage"] = aggregated
                
        return {
            "metadata": metadata,
            "messages": messages,
            "total": len(messages)
        }

    @staticmethod
    def get_metadata_only(filepath: Path) -> Optional[Dict[str, Any]]:
        """Fast extraction of metadata row only (usually first line)."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                # Most Nanobot files have metadata on line 1
                first_line = f.readline().strip()
                if first_line.startswith("{") and '"_type": "metadata"' in first_line:
                    data = json.loads(first_line)
                    return {
                        "key": data.get("key", filepath.stem),
                        "filename": filepath.name,
                        "created_at": data.get("created_at"),
                        "updated_at": data.get("updated_at"),
                        "size_bytes": filepath.stat().st_size
                    }
                
                # Fallback: scan incrementally for the metadata object
                parser = SessionParser(filepath)
                for obj in parser.stream_objects():
                    if obj.get("_type") == "metadata":
                        return {
                            "key": obj.get("key", filepath.stem),
                            "filename": filepath.name,
                            "created_at": obj.get("created_at"),
                            "updated_at": obj.get("updated_at"),
                            "size_bytes": filepath.stat().st_size
                        }
        except Exception as e:
            logger.error(f"Metadata read error {filepath}: {e}")
            
        return {
            "key": filepath.stem,
            "filename": filepath.name,
            "size_bytes": filepath.stat().st_size
        }
