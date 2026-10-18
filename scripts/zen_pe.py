"""PE section handling for Creative updater extraction and firmware insertion."""

import struct


def align(value, boundary):
    return (value + boundary - 1) // boundary * boundary


def read_pe(exe):
    if len(exe) < 64 or exe[:2] != b"MZ":
        raise ValueError("Not a DOS/PE executable")
    pe = struct.unpack_from("<I", exe, 0x3C)[0]
    if pe + 24 > len(exe) or exe[pe:pe + 4] != b"PE\0\0":
        raise ValueError("Invalid PE header")
    count = struct.unpack_from("<H", exe, pe + 6)[0]
    optional_size = struct.unpack_from("<H", exe, pe + 20)[0]
    optional = pe + 24
    if optional + optional_size > len(exe) or optional_size < 96:
        raise ValueError("Truncated PE optional header")
    magic = struct.unpack_from("<H", exe, optional)[0]
    if magic == 0x10B:
        image_base = struct.unpack_from("<I", exe, optional + 28)[0]
        directories = optional + 96
    elif magic == 0x20B and optional_size >= 112:
        image_base = struct.unpack_from("<Q", exe, optional + 24)[0]
        directories = optional + 112
    else:
        raise ValueError("Unsupported PE optional header")
    directory_count = struct.unpack_from("<I", exe, directories - 4)[0]
    if directories + directory_count * 8 > optional + optional_size:
        raise ValueError("Truncated PE data directories")
    security = struct.unpack_from("<II", exe, directories + 32) if directory_count > 4 else (0, 0)
    section_alignment, file_alignment = struct.unpack_from("<II", exe, optional + 32)
    if (not file_alignment or file_alignment & (file_alignment - 1)
            or section_alignment < file_alignment
            or section_alignment & (section_alignment - 1)):
        raise ValueError("Invalid PE alignments")
    table = optional + optional_size
    if not count or table + count * 40 > len(exe):
        raise ValueError("Truncated PE section table")
    sections = []
    for index in range(count):
        header = table + index * 40
        virtual_size, rva, raw_size, raw_offset = struct.unpack_from("<IIII", exe, header + 8)
        if raw_size and raw_offset + raw_size > len(exe):
            raise ValueError("Truncated PE section data")
        sections.append({
            "name": exe[header:header + 8].rstrip(b"\0").decode("ascii"),
            "header_offset": header, "virtual_size": virtual_size, "rva": rva,
            "raw_size": raw_size, "raw_offset": raw_offset,
        })
    return {
        "pe_offset": pe, "optional_offset": optional, "magic": magic,
        "machine": struct.unpack_from("<H", exe, pe + 4)[0],
        "section_table_offset": table, "sections": sections, "image_base": image_base,
        "section_alignment": section_alignment, "file_alignment": file_alignment,
        "size_of_headers": struct.unpack_from("<I", exe, optional + 60)[0],
        "checksum_offset": optional + 64, "security_directory": security,
    }


def section_named(pe, name):
    matches = [section for section in pe["sections"] if section["name"] == name]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one PE section named {name}")
    return matches[0]


def code_references(exe, pe, address):
    """Use the same size-field reference search as Rockbox update_patch."""
    text = section_named(pe, ".text")
    references = []
    for offset in range(text["raw_offset"], text["raw_offset"] + text["raw_size"] - 3):
        value = struct.unpack_from("<I", exe, offset)[0]
        if address <= value <= address + 3:
            references.append({"file_offset": offset, "address": value})
    return references


def append_firmware_section(exe, pe, packet):
    if any(section["name"] == ".firm" for section in pe["sections"]):
        raise ValueError("Updater already has .firm; use the original updater as input")
    header = pe["section_table_offset"] + len(pe["sections"]) * 40
    first_raw = min(section["raw_offset"] for section in pe["sections"] if section["raw_size"])
    if header + 40 > min(pe["size_of_headers"], first_raw) or any(exe[header:header + 40]):
        raise ValueError("No unused section-header space for .firm")
    raw_offset = align(len(exe), pe["file_alignment"])
    raw_size = align(len(packet), pe["file_alignment"])
    rva = align(max(section["rva"] + max(section["virtual_size"], section["raw_size"])
                    for section in pe["sections"]), pe["section_alignment"])
    patched = bytearray(exe)
    patched.extend(b"\0" * (raw_offset - len(patched)))
    patched.extend(packet)
    patched.extend(b"\0" * (raw_size - len(packet)))
    struct.pack_into("<8sIIIIIIHHI", patched, header, b".firm\0\0\0", len(packet), rva,
                     raw_size, raw_offset, 0, 0, 0, 0, 0xC0000040)
    struct.pack_into("<H", patched, pe["pe_offset"] + 6, len(pe["sections"]) + 1)
    optional = pe["optional_offset"]
    initialized = struct.unpack_from("<I", patched, optional + 8)[0]
    struct.pack_into("<I", patched, optional + 8, initialized + raw_size)
    struct.pack_into("<I", patched, optional + 56,
                     align(rva + max(len(packet), raw_size), pe["section_alignment"]))
    return patched, raw_offset, pe["image_base"] + rva


def pe_checksum(exe, checksum_offset):
    """Windows PE checksum: 16-bit one's-complement sum plus file length."""
    total = 0
    for offset in range(0, len(exe), 2):
        if checksum_offset <= offset < checksum_offset + 4:
            continue
        word = exe[offset] | ((exe[offset + 1] if offset + 1 < len(exe) else 0) << 8)
        total += word
        total = (total & 0xFFFF) + (total >> 16)
    total = (total & 0xFFFF) + (total >> 16)
    return (total + len(exe)) & 0xFFFFFFFF
