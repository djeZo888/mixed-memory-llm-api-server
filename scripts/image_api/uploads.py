"""Streaming multipart parser with memory-only, explicitly bounded ownership."""
from python_multipart import MultipartParser
from python_multipart.multipart import parse_options_header
from .protocol import ENVELOPE_LIMIT, FILE_LIMIT, JSON_LIMIT, TOTAL_LIMIT, Refusal, strict_json


async def read_json(request):
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > JSON_LIMIT:
            raise Refusal(413, 'input_too_large')
        data.extend(chunk)
    return strict_json(data)


class Uploads:
    def __init__(self, content_type):
        kind, options = parse_options_header(content_type)
        boundary = options.get(b'boundary')
        if kind != b'multipart/form-data' or not boundary or len(boundary) > 70:
            raise Refusal()
        self.fields, self.images = {}, []
        self.total = self.file_total = self.parts = 0
        self.ended = False
        self.image_field = None
        self.buffer = bytearray()
        self.parser = MultipartParser(boundary, {name: getattr(self, name) for name in (
            'on_part_begin', 'on_header_field', 'on_header_value', 'on_header_end',
            'on_headers_finished', 'on_part_data', 'on_part_end', 'on_end')})

    def on_part_begin(self):
        self.parts += 1
        if self.parts > 9:
            raise Refusal()
        self.headers, self.hkey, self.hvalue = {}, bytearray(), bytearray()
        self.buffer = bytearray()
        self.header_bytes = 0

    def header(self, target, data, start, end):
        self.header_bytes += end - start
        if self.header_bytes > 8192:
            raise Refusal(413, 'input_too_large')
        target.extend(data[start:end])

    def on_header_field(self, data, start, end):
        self.header(self.hkey, data, start, end)

    def on_header_value(self, data, start, end):
        self.header(self.hvalue, data, start, end)

    def on_header_end(self):
        key = bytes(self.hkey).lower()
        if key not in (b'content-disposition', b'content-type') or key in self.headers:
            raise Refusal()
        self.headers[key] = bytes(self.hvalue)
        self.hkey.clear()
        self.hvalue.clear()

    def on_headers_finished(self):
        kind, options = parse_options_header(self.headers.get(b'content-disposition', b''))
        if kind != b'form-data' or b'name' not in options:
            raise Refusal()
        self.name = options[b'name'].decode('ascii')
        self.file = b'filename' in options
        if self.file:
            if self.name not in ('image', 'image[]') or len(self.images) >= 2:
                raise Refusal()
            if self.image_field is not None and self.image_field != self.name:
                raise Refusal()
            self.image_field = self.name
        elif (self.name not in {'prompt', 'model', 'n', 'size', 'seed', 'response_format', 'background'}
              or self.name in self.fields):
            raise Refusal()

    def on_part_data(self, data, start, end):
        amount = end - start
        if len(self.buffer) + amount > (FILE_LIMIT if self.file else 16384):
            raise Refusal(413, 'input_too_large')
        if self.file:
            self.file_total += amount
            if self.file_total > TOTAL_LIMIT:
                raise Refusal(413, 'input_too_large')
        self.buffer.extend(data[start:end])

    def on_part_end(self):
        if self.file:
            self.images.append(bytes(self.buffer))
        else:
            value = self.buffer.decode('utf-8')
            if self.name in ('n', 'seed'):
                if not value.isascii() or not value.isdecimal() or len(value) > 19:
                    raise Refusal()
                value = int(value)
            self.fields[self.name] = value
        self.buffer.clear()

    def on_end(self):
        self.ended = True

    async def read(self, request):
        try:
            async for chunk in request.stream():
                self.total += len(chunk)
                if self.total > TOTAL_LIMIT + ENVELOPE_LIMIT:
                    raise Refusal(413, 'input_too_large')
                self.parser.write(chunk)
                if self.total - self.file_total > ENVELOPE_LIMIT:
                    raise Refusal(413, 'input_too_large')
            self.parser.finalize()
            if not self.ended:
                raise Refusal()
            return self.fields, self.images
        except (ValueError, UnicodeError):
            raise Refusal() from None
        finally:
            self.buffer.clear()

    def clear(self):
        self.buffer.clear()
        self.images.clear()
        self.fields.clear()
