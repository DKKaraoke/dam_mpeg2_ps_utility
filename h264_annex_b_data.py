from typing import NamedTuple


class H264NalUnit(NamedTuple):
    is_start_code_long: bool
    nal_ref_idc: int
    nal_unit_type: int
    rbsp: bytes
