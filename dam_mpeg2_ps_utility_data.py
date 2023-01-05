from typing import NamedTuple


class GopIndexEntry(NamedTuple):
    ps_pack_header_position: int
    access_unit_size: int
    pts: int


class GopIndex(NamedTuple):
    sub_stream_id: int
    version: int
    stream_id: int
    page_number: int
    page_count: int
    gops: list[GopIndexEntry]
