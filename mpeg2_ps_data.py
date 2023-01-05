from typing import NamedTuple, Union


class Mpeg2PesPacketType1(NamedTuple):
    stream_id: int
    PES_packet_length: int
    PES_header_data_length: int
    PTS_DTS_flags: int
    pts: int
    dts: int
    # PES_packet_data_byte: bytes


class Mpeg2PesPacketType2(NamedTuple):
    stream_id: int
    data: bytes


class Mpeg2PesPacketType3(NamedTuple):
    stream_id: int
    PES_packet_lengt: int


Mpeg2PesPacket = Union[Mpeg2PesPacketType1,
                       Mpeg2PesPacketType2, Mpeg2PesPacketType3]


class Mpeg2PsPackHeader(NamedTuple):
    system_clock_reference_base: int
    system_clock_reference_extension: int
    program_mux_rate: int
    pack_stuffing_length: int


class Mpeg2PsSystemHeaderPStdInfo(NamedTuple):
    stream_id: int
    P_STD_buffer_bound_scale: int
    P_STD_buffer_size_bound: int


class Mpeg2PsSystemHeader(NamedTuple):
    rate_bound: int
    audio_bound: int
    fixed_flag: int
    CSPS_flag: int
    system_audio_lock_flag: int
    system_video_lock_flag: int
    video_bound: int
    packet_rate_restriction_flag: int
    P_STD_info: list[Mpeg2PsSystemHeaderPStdInfo]


class Mpeg2GenericDescriptor(NamedTuple):
    descriptor_tag: int
    data: bytes


class Mpeg2AvcVideoDescriptor(NamedTuple):
    profile_idc: int
    constraint_set0_flag: int
    constraint_set1_flag: int
    constraint_set2_flag: int
    constraint_set3_flag: int
    constraint_set4_flag: int
    constraint_set5_flag: int
    AVC_compatible_flags: int
    level_idc: int
    AVC_still_present: int
    AVC_24_hour_picture_flag: int
    Frame_Packing_SEI_not_present_flag: int


class Mpeg2AacAudioDescriptor(NamedTuple):
    MPEG_2_AAC_profile: int
    MPEG_2_AAC_channel_configuration: int
    MPEG_2_AAC_additional_information: int


class Mpeg2HevcVideoDescriptor(NamedTuple):
    profile_space: int
    tier_flag: int
    profile_idc: int
    profile_compatibility_indication: int
    progressive_source_flag: int
    interlaced_source_flag: int
    non_packed_constraint_flag: int
    frame_only_constraint_flag: int
    copied_44bits: int
    level_idc: int
    temporal_layer_subset_flag: int
    HEVC_still_present_flag: int
    HEVC_24hr_picture_present_flag: int
    sub_pic_hrd_params_not_present_flag: int
    HDR_WCG_idc: int
    # Optional fields
    temporal_id_min: int
    temporal_id_max: int


Mpeg2Descriptor = Union[Mpeg2GenericDescriptor, Mpeg2AvcVideoDescriptor,
                        Mpeg2AacAudioDescriptor, Mpeg2HevcVideoDescriptor]


class Mpeg2PsElementaryStreamMapEntry(NamedTuple):
    stream_type: int
    elementary_stream_id: int
    elementary_stream_info: list[Mpeg2Descriptor]


class Mpeg2PsProgramStreamMap(NamedTuple):
    current_next_indicator: int
    program_stream_map_version: int
    program_stream_info: list[Mpeg2Descriptor]
    elementary_stream_map: list[Mpeg2PsElementaryStreamMapEntry]
