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
        
        for obj in self.stream_objects():
            if not isinstance(obj, dict):
                continue
                
            if obj.get("_type") == "metadata":
                metadata.update({k: v for k, v in obj.items() if k != "messages"})
                if "messages" in obj:
                    messages.extend(obj["messages"])
            elif "role" in obj:
                messages.append(obj)
            elif "messages" in obj:
                # Full session dump style
                metadata.update({k: v for k, v in obj.items() if k != "messages"})
                messages.extend(obj["messages"])
                
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
