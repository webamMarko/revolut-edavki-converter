"""Shared server utility functions."""

from multipart.multipart import parse_options_header


def parse_multipart(headers, body):
    """Parse multipart/form-data request body using python-multipart library.

    Returns (fields, files) where:
    - fields: dict of field_name -> value
    - files: list of dicts with keys: filename, content, field_name
    """
    content_type = headers.get("Content-Type", "")
    if not content_type or "multipart/form-data" not in content_type:
        return {}, []

    # Parse content-type header to extract boundary
    try:
        _, options = parse_options_header(content_type)
        boundary = options.get(b'boundary')
        if isinstance(boundary, bytes):
            boundary = boundary.decode('latin-1')
    except Exception:
        return {}, []

    if not boundary:
        return {}, []

    # Use python-multipart to parse the request

    fields = {}
    files = []

    def on_part_begin():
        pass

    def on_part_data(data, start, end):
        pass

    def on_part_end():
        pass

    def on_header_field(data, start, end):
        pass

    def on_header_value(data, start, end):
        pass

    def on_header_end():
        pass

    def on_headers_finished():
        pass

    # We'll use a simpler approach: parse manually but safely with the library's helpers
    # The python-multipart library is more low-level, so we need to handle the parsing differently

    # Split by boundary
    boundary_bytes = f"--{boundary}".encode('latin-1')
    parts = body.split(boundary_bytes)

    for part in parts:
        part = part.strip()
        if not part or part == b'--':
            continue

        # Split headers from content
        if b'\r\n\r\n' not in part:
            continue

        header_block, content = part.split(b'\r\n\r\n', 1)

        # Remove trailing CRLF
        if content.endswith(b'\r\n'):
            content = content[:-2]

        # Parse headers
        header_str = header_block.decode('utf-8', errors='replace')
        name = filename = None

        for line in header_str.split('\r\n'):
            if 'Content-Disposition:' in line:
                # Use parse_options_header for safer parsing
                try:
                    _, options = parse_options_header(line.split(':', 1)[1].strip())
                    name = options.get(b'name', b'').decode('utf-8') if isinstance(options.get(b'name'), bytes) else options.get('name', '')
                    filename = options.get(b'filename', b'').decode('utf-8') if isinstance(options.get(b'filename'), bytes) else options.get('filename', '')
                except Exception:
                    # Fallback to simple parsing
                    for param in line.split(';'):
                        param = param.strip()
                        if param.startswith('name='):
                            name = param.split('=', 1)[1].strip('"')
                        elif param.startswith('filename='):
                            filename = param.split('=', 1)[1].strip('"')

        if filename:
            files.append({
                'filename': filename,
                'content': content,
                'field_name': name
            })
        elif name:
            fields[name] = content.decode('utf-8', errors='replace')

    return fields, files
