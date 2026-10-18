"""Creative CODE containers and their checksum-protected load records.

CODE headers and record fields use big-endian integers. Record payloads are
kept verbatim; their byte counts do not establish CPU memory-space mappings.
Reference for the related EDOC structure: rockbox/utils/mkzenboot/mkzenboot.c.
"""

import struct

from extract_zen_firmware import sha256, verify_signature


def validate_code(decoded):
    if len(decoded) < 8 or decoded[:4] not in (b"CODE", b"EDOC"):
        raise ValueError("Decrypted data does not have a CODE header")
    endian = ">" if decoded[:4] == b"CODE" else "<"
    code_end = 8 + struct.unpack_from(endian + "I", decoded, 4)[0]
    if code_end > len(decoded):
        raise ValueError("CODE length exceeds available data")
    trailer = decoded[code_end:]
    signed = trailer.startswith(b"NULL")
    if signed:
        if len(trailer) < 28 or trailer[4:8] != struct.pack("<I", 20):
            raise ValueError("Unexpected program signature length")
        verify_signature(decoded, code_end)
        trailer = trailer[28:]
    if len(trailer) > 7 or trailer not in (b"\0" * len(trailer), b"\xff" * len(trailer)):
        raise ValueError("Unexpected bytes after CODE container")
    return {"code_end": code_end, "hmac_sha1_verified": signed,
            "padding_size": len(trailer), "padding_hex": trailer.hex()}


def code_word_checksum(payload):
    if len(payload) % 2:
        raise ValueError("CODE payload length is not a multiple of a 16-bit word")
    return sum(word[0] for word in struct.iter_unpack(">H", payload)) & 0xFFFF


def raw_byte_overlaps(blocks):
    overlaps = []
    for index, left in enumerate(blocks):
        for right in blocks[index + 1:]:
            start = max(left["address_field"], right["address_field"])
            end = min(left["raw_byte_view_end_exclusive"], right["raw_byte_view_end_exclusive"])
            if start < end:
                overlaps.append({"block_indices": [left["index"], right["index"]],
                                 "raw_byte_view_start": start, "raw_byte_view_end_exclusive": end})
    return overlaps


def parse_code_image(image):
    """Return exact record payloads and a manifest, validating every checksum."""
    if len(image) < 12 or image[:4] != b"CODE":
        raise ValueError("Expected a big-endian CODE image with a 12-byte header")
    container = validate_code(image)
    code_end = container["code_end"]
    if code_end < 12:
        raise ValueError("Declared CODE length does not include its full header")
    files = {}
    blocks = []
    offset = 12
    while offset < code_end:
        index = len(blocks)
        if offset + 12 > code_end:
            raise ValueError(f"Truncated CODE record header at 0x{offset:x}")
        address, size, stored_checksum = struct.unpack_from(">III", image, offset)
        start, end = offset + 12, offset + 12 + size
        if end > code_end:
            raise ValueError(f"CODE block {index} extends beyond its container")
        payload = image[start:end]
        computed_checksum = code_word_checksum(payload)
        if computed_checksum != stored_checksum:
            raise ValueError(f"CODE block {index} checksum mismatch: stored 0x{stored_checksum:08x}, "
                             f"computed 0x{computed_checksum:04x}")
        filename = f"block_{index:02d}_{address:08x}.bin"
        files[filename] = payload
        blocks.append({
            "index": index,
            "filename": filename,
            "record_header_file_offset": offset,
            "record_header_hex": image[offset:start].hex(),
            "payload_file_offset": start,
            "payload_size_bytes": size,
            "address_field": address,
            "address_hex": f"0x{address:08x}",
            "raw_byte_view_end_exclusive": address + size,
            "classification": "unclassified",
            "checksum_stored": stored_checksum,
            "checksum_computed": computed_checksum,
            "checksum_verified": True,
            "sha256": sha256(payload),
        })
        offset = end
    if not blocks:
        raise ValueError("CODE image does not contain any load records")
    return files, {
        "format": "CODE",
        "container_field_byte_order": "big",
        "source_size_bytes": len(image),
        "source_sha256": sha256(image),
        "declared_size_field": struct.unpack_from(">I", image, 4)[0],
        "code_end_file_offset": code_end,
        "container_header_hex": image[:12].hex(),
        "header_word_0x08": {"value": struct.unpack_from(">I", image, 8)[0],
                             "interpretation": "not established"},
        "trailer_hex": image[code_end:].hex(),
        "inner_hmac_sha1_verified": container["hmac_sha1_verified"],
        "block_count": len(blocks),
        "payload_total_bytes": sum(block["payload_size_bytes"] for block in blocks),
        "checksum_algorithm": "sum of big-endian unsigned 16-bit payload words modulo 65536",
        "payload_byte_order": "preserved verbatim; not converted for disassembly",
        "address_map": {
            "address_values": "raw values stored in CODE record headers",
            "range_convention": "address_field + payload_size_bytes (exclusive end)",
            "cpu_address_space_mapping": "not established",
            "cpu_mapping_verified": False,
            "program_address_unit": "C55x program addresses are bytes (CPU documentation)",
            "data_address_unit": "C55x data addresses are 16-bit words (CPU documentation)",
            "raw_byte_view_overlaps": raw_byte_overlaps(blocks),
        },
        "blocks": blocks,
    }
