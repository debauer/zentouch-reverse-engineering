# SPDX-License-Identifier: GPL-2.0-or-later
# Based on zenutils, Copyright 2007 Rasmus Ry.
"""Creative CENC codec; reference: rockbox/utils/zenutils/source/shared/cenc.cpp."""


def decode_cenc(source, expected_size):
    if expected_size <= 0:
        raise ValueError("CENC output length must be positive")
    output = bytearray()
    position = 0
    while len(output) < expected_size:
        if position >= len(source):
            raise ValueError("Truncated CENC stream")
        code = source[position]
        position += 1
        mode = code & 0xC0
        args = code & 0x3F
        parameters = (2 if mode == 0x80 else
                      1 if mode in (0x00, 0xC0) or not code & 0x20 else 0)
        if position + parameters > len(source):
            raise ValueError("Truncated CENC opcode")
        if mode == 0x00:
            repeats = source[position] + 2
            position += 1
            length = args + 2
            block = source[position:position + length]
            if len(block) != length:
                raise ValueError("Truncated CENC repeat pattern")
            position += length
            output.extend(block * repeats)
        elif mode == 0x40:
            if code & 0x20:
                length = (code & 0x1F) + 1
            else:
                length = ((code & 0x1F) << 8) + source[position] + 0x21
                position += 1
            if (position ^ len(output)) & 1:
                position += 1
            block = source[position:position + length]
            if len(block) != length:
                raise ValueError("Truncated CENC literal block")
            output.extend(((value << 3) & 0xF8) | (value >> 5) for value in block)
            position += length
        elif mode == 0x80:
            length = (args << 8) + source[position] + 0x42
            value = source[position + 1]
            position += 2
            value = ((value & 7) << 5) | (value >> 3)
            output.extend(bytes([value]) * length)
        else:
            length = args + 2
            value = source[position]
            position += 1
            value = ((value & 3) << 6) | (value >> 2)
            output.extend(bytes([value]) * length)
        if len(output) > expected_size:
            raise ValueError("CENC output exceeds declared length")
    if len(source) - position > 7 or any(source[position:]):
        raise ValueError("Unexpected data after CENC stream")
    return bytes(output)


def _encode_run(output, value, length):
    while length:
        count = min(length, 0x4041)
        if length - count == 1:
            count -= 1  # A run opcode cannot represent a single remaining byte.
        if count <= 0x41:
            output.extend((0xC0 | (count - 2), ((value & 0x3F) << 2) | (value >> 6)))
        else:
            size = count - 0x42
            output.extend((0x80 | (size >> 8), size & 0xFF,
                           ((value & 0x1F) << 3) | (value >> 5)))
        length -= count


def _encode_block(output, source, start, end):
    while start < end:
        count = min(end - start, 0x2020)
        if count <= 0x20:
            output.append(0x60 | (count - 1))
        else:
            size = count - 0x21
            output.extend((0x40 | (size >> 8), size & 0xFF))
        if (len(output) ^ start) & 1:
            output.append(0)
        output.extend(((value & 7) << 5) | (value >> 3)
                      for value in source[start:start + count])
        start += count


def encode_cenc(source):
    """Encode literals and byte runs, as the Rockbox zenutils encoder does."""
    if not source:
        raise ValueError("CENC input must not be empty")
    output = bytearray()
    position = 0
    while position < len(source):
        start = position
        value = source[position]
        position += 1
        while position < len(source) and source[position] == value:
            position += 1
        if position - start >= 2:
            _encode_run(output, value, position - start)
        else:
            while position < len(source):
                if position + 1 < len(source) and source[position] == source[position + 1]:
                    break
                position += 1
            _encode_block(output, source, start, position)
    return bytes(output)
