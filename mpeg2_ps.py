import bitstring
from customized_logger import getLogger
import io
from mpeg2_ps_data import Mpeg2PsProgramEnd, Mpeg2PesPacketType1, Mpeg2PesPacketType2, Mpeg2PesPacketType3, Mpeg2PesPacket, Mpeg2PsPackHeader, Mpeg2PsSystemHeaderPStdInfo,  Mpeg2PsSystemHeader, Mpeg2GenericDescriptor, Mpeg2AvcVideoDescriptor, Mpeg2AacAudioDescriptor, Mpeg2HevcVideoDescriptor, Mpeg2Descriptor, Mpeg2PsElementaryStreamMapEntry, Mpeg2PsProgramStreamMap, Mpeg2PsPacket
import os


class Mpeg2Ps:
    """MPEG2-PS
    """

    PACKET_START_CODE = b'\x00\x00\x01'

    __logger = getLogger('Mpeg2Ps')

    @staticmethod
    def crc32(buffer: bytes):
        crc = 0xffffffff
        for value in buffer:
            crc ^= value << 24
            for _ in range(8):
                msb = crc >> 31
                crc <<= 1
                crc ^= (0 - msb) & 0x104c11db7
        return crc

    @staticmethod
    def seek_packet(stream: bitstring.BitStream, packet_id: int | None = None):
        zero_count = 0
        while True:
            current_byte: int
            try:
                current_byte = stream.read('uint:8')
            except bitstring.ReadError:
                # End of stream
                break
            if 2 <= zero_count and current_byte == 0x01:
                try:
                    current_byte = stream.read('uint:8')
                except bitstring.ReadError:
                    # End of stream
                    break
                if packet_id is None:
                    stream.bytepos -= 4
                    return current_byte
                else:
                    if current_byte == packet_id:
                        stream.bytepos -= 4
                        return current_byte
            # Count zero
            if current_byte == 0x00:
                zero_count += 1
            else:
                zero_count = 0

    # @staticmethod
    # def index_packets(stream: io.BufferedReader, packet_id: int | None = None):
    #     start_position = stream.tell()

    #     index: list[tuple[int, int]] = []
    #     current_start = -1
    #     while True:
    #         packet_id = Mpeg2Ps.seek_packet(stream, packet_id)
    #         position = stream.tell()
    #         if packet_id is None:
    #             break
    #         stream.seek(4, os.SEEK_CUR)
    #         if current_start != -1:
    #             size = position - current_start
    #             index.append((current_start, size))
    #         current_start = position
    #     if current_start != -1:
    #         size = len(stream.read()) - current_start
    #         index.append((current_start, size))

    #     stream.seek(start_position)

    #     return index

    @staticmethod
    def peek_packet_id(stream: bitstring.BitStream):
        buffer: bytes = stream.peek('bytes:4').bytes
        if buffer[0:3] != Mpeg2Ps.PACKET_START_CODE:
            Mpeg2Ps.__logger.warning('Invalid packet start code.')
            return
        return buffer[3]

    @staticmethod
    def read_pes_packet(stream: bitstring.BitStream):
        packet_start_code_prefix: bytes = stream.read('bytes:3')
        if packet_start_code_prefix != Mpeg2Ps.PACKET_START_CODE:
            raise RuntimeError('Invalid packet_start_code_prefix.')
        stream_id: int = stream.read('uint:8')
        PES_packet_length: int = stream.read('uintbe:16')
        PES_packet_stream = bitstring.BitStream(
            stream.read(8 * PES_packet_length))
        if stream_id != 0xbc and stream_id != 0xbe and stream_id != 0xbf and stream_id != 0xf0 and stream_id != 0xf1 and stream_id != 0xbc and 0xff and stream_id != 0xf2 and stream_id != 0xf8:
            # Skip '10'
            PES_packet_stream.pos += 2
            PES_scrambling_control: int = PES_packet_stream.read('uint:2')
            PES_priority: int = PES_packet_stream.read('uint:1')
            data_alignment_indicator: int = PES_packet_stream.read('uint:1')
            copyright: int = PES_packet_stream.read('uint:1')
            original_or_copy: int = PES_packet_stream.read('uint:1')
            PTS_DTS_flags: int = PES_packet_stream.read('uint:2')
            ESCR_flag: int = PES_packet_stream.read('uint:1')
            ES_rate_flag: int = PES_packet_stream.read('uint:1')
            DSM_trick_mode_flag: int = PES_packet_stream.read('uint:1')
            additional_copy_info_flag: int = PES_packet_stream.read('uint:1')
            PES_CRC_flag: int = PES_packet_stream.read('uint:1')
            PES_extension_flag: int = PES_packet_stream.read('uint:1')
            PES_header_data_length: int = PES_packet_stream.read('uint:8')
            PES_header_data_stream: int = bitstring.BitStream(
                PES_packet_stream.read(8 * PES_header_data_length))
            pts: int | None = None
            dts: int | None = None
            if PTS_DTS_flags == 0x02:
                raw_PTS: int = PES_header_data_stream.read('uintbe:40')
                pts = (raw_PTS >> 3) & (0x0007 << 30)
                pts |= (raw_PTS >> 2) & (0x7fff << 15)
                pts |= (raw_PTS >> 1) & 0x7fff
            if PTS_DTS_flags == 0x03:
                raw_PTS: int = PES_header_data_stream.read('uintbe:40')
                pts = (raw_PTS >> 3) & (0x0007 << 30)
                pts |= (raw_PTS >> 2) & (0x7fff << 15)
                pts |= (raw_PTS >> 1) & 0x7fff
                raw_DTS: int = PES_header_data_stream.read('uintbe:40')
                dts = (raw_DTS >> 3) & (0x0007 << 30)
                dts |= (raw_DTS >> 2) & (0x7fff << 15)
                dts |= (raw_DTS >> 1) & 0x7fff
            PES_packet_data: bytes = PES_packet_stream.read('bytes')
            return Mpeg2PesPacketType1(stream_id, PES_scrambling_control, PES_priority, data_alignment_indicator, copyright, original_or_copy, PTS_DTS_flags, ESCR_flag, ES_rate_flag, DSM_trick_mode_flag, additional_copy_info_flag, PES_CRC_flag, PES_extension_flag, pts, dts, PES_packet_data)
        elif stream_id == 0xbc or stream_id == 0xbf or stream_id == 0xf0 or stream_id == 0xf1 or stream_id == 0xbc and 0xff or stream_id == 0xf2 or stream_id == 0xf8:
            PES_packet_data: bytes = PES_packet_stream.read(
                8 * PES_packet_length).bytes
            return Mpeg2PesPacketType2(stream_id, PES_packet_data)
        elif stream_id == 0xbe:
            return Mpeg2PesPacketType3(stream_id, PES_packet_length)

    @staticmethod
    def write_pes_packet(stream: bitstring.BitStream, data: Mpeg2PesPacket):
        stream.append(Mpeg2Ps.PACKET_START_CODE)
        stream.append(bitstring.pack('uint:8', data.stream_id))
        PES_packet_stream = bitstring.BitStream()
        if isinstance(data, Mpeg2PesPacketType1):
            PES_packet_stream.append(bitstring.BitArray(bin='10'))
            PES_packet_stream.append(bitstring.pack(
                'uint:2', data.PES_scrambling_control))
            PES_packet_stream.append(
                bitstring.pack('uint:1', data.PES_priority))
            PES_packet_stream.append(bitstring.pack(
                'uint:1', data.data_alignment_indicator))
            PES_packet_stream.append(bitstring.pack('uint:1', data.copyright))
            PES_packet_stream.append(bitstring.pack(
                'uint:1', data.original_or_copy))
            PES_packet_stream.append(
                bitstring.pack('uint:2', data.PTS_DTS_flags))
            PES_packet_stream.append(bitstring.pack('uint:1', data.ESCR_flag))
            PES_packet_stream.append(
                bitstring.pack('uint:1', data.ES_rate_flag))
            PES_packet_stream.append(bitstring.pack(
                'uint:1', data.DSM_trick_mode_flag))
            PES_packet_stream.append(bitstring.pack(
                'uint:1', data.additional_copy_info_flag))
            PES_packet_stream.append(
                bitstring.pack('uint:1', data.PES_CRC_flag))
            PES_packet_stream.append(bitstring.pack(
                'uint:1', data.PES_extension_flag))

            PES_header_data_stream = bitstring.BitStream()
            if data.PTS_DTS_flags == 0x02:
                raw_PTS = 0x2100010001
                raw_PTS |= (data.pts & (0x0007 << 30)) << 3
                raw_PTS |= (data.pts & (0x7fff << 15)) << 2
                raw_PTS |= (data.pts & 0x7fff) << 1
                PES_header_data_stream.append(
                    bitstring.pack('uintbe:40', raw_PTS))
            elif data.PTS_DTS_flags == 0x03:
                raw_PTS = 0x3100010001
                raw_PTS |= (data.pts & (0x0007 << 30)) << 3
                raw_PTS |= (data.pts & (0x7fff << 15)) << 2
                raw_PTS |= (data.pts & 0x7fff) << 1
                PES_header_data_stream.append(
                    bitstring.pack('uintbe:40', raw_PTS))
                raw_DTS = 0x1100010001
                raw_DTS |= (data.dts & (0x0007 << 30)) << 3
                raw_DTS |= (data.dts & (0x7fff << 15)) << 2
                raw_DTS |= (data.dts & 0x7fff) << 1
                PES_header_data_stream.append(
                    bitstring.pack('uintbe:40', raw_DTS))
            PES_header_data_buffer = PES_header_data_stream.tobytes()
            PES_packet_stream.append(bitstring.pack(
                'uint:8', len(PES_header_data_buffer)))
            PES_packet_stream.append(PES_header_data_buffer)

            PES_packet_stream.append(data.PES_packet_data)

            PES_packet_buffer = PES_packet_stream.tobytes()
            stream.append(bitstring.pack(
                'uintbe:16', len(PES_packet_buffer)))
            stream.append(PES_packet_buffer)

            return
        elif isinstance(data, Mpeg2PesPacketType2):
            stream.append(bitstring.pack(
                'uintbe:16', len(data.PES_packet_data)))
            stream.append(data.PES_packet_data)
            return
        elif isinstance(data, Mpeg2PesPacketType3):
            stream.append(bitstring.pack(
                'uintbe:16', data.PES_packet_length))
            for _ in range(data.PES_packet_length):
                stream.append(b'\xff')

    @staticmethod
    def read_ps_pack_header(stream: bitstring.BitStream):
        pack_start_code: bytes = stream.read('bytes:4')
        if pack_start_code != (Mpeg2Ps.PACKET_START_CODE + b'\xba'):
            raise RuntimeError('Invalid pack_start_code.')
        system_clock_reference_raw: int = stream.read('uintbe:48')
        system_clock_reference_base = (
            system_clock_reference_raw >> 13) & (0x03 << 30)
        system_clock_reference_base |= (
            system_clock_reference_raw >> 12) & (0x7fff << 15)
        system_clock_reference_base |= (
            system_clock_reference_raw >> 11) & 0x7fff
        system_clock_reference_extension = (
            system_clock_reference_raw >> 1) & 0x01ff
        program_mux_rate: int = stream.read('uintbe:24') >> 2
        # Skip marker_bits and Reserved
        stream.pos += 5
        pack_stuffing_length: int = stream.read('uint:3')
        return Mpeg2PsPackHeader(system_clock_reference_base, system_clock_reference_extension, program_mux_rate, pack_stuffing_length)

    @staticmethod
    def write_ps_pack_header(stream: bitstring.BitStream, data: Mpeg2PsPackHeader):
        stream.append(Mpeg2Ps.PACKET_START_CODE + b'\xba')
        system_clock_reference_raw = 0x440004000401
        system_clock_reference_raw |= (
            data.system_clock_reference_base & (0x03 << 30)) << 13
        system_clock_reference_raw |= (
            data.system_clock_reference_base & (0x7fff << 15)) << 12
        system_clock_reference_raw |= (
            data.system_clock_reference_base & 0x7fff) << 11
        system_clock_reference_raw |= (
            data.system_clock_reference_extension & 0x01ff) << 1
        stream.append(bitstring.pack('uintbe:48', system_clock_reference_raw))
        program_mux_rate_raw = 0x000003
        program_mux_rate_raw |= (data.program_mux_rate & 0x3fffff) << 2
        stream.append(bitstring.pack('uintbe:24', program_mux_rate_raw))
        pack_stuffing_length_raw = 0xf8
        pack_stuffing_length_raw |= data.pack_stuffing_length & 0x03
        stream.append(bitstring.pack('uint:8', pack_stuffing_length_raw))
        for _ in range(data.pack_stuffing_length):
            stream.append(b'\0xff')

    @staticmethod
    def read_ps_system_header(stream: bitstring.BitStream):
        system_header_start_code: bytes = stream.read('bytes:4')
        if system_header_start_code != (Mpeg2Ps.PACKET_START_CODE + b'\xbb'):
            raise RuntimeError('Invalid system_header_start_code.')
        header_length: int = stream.read('uintbe:16')
        header_stream = bitstring.BitStream(stream.read(8 * header_length))

        rate_bound: int = (header_stream.read('uintbe:24') >> 1) & 0x3fffff
        audio_bound: int = header_stream.read('uint:6')
        fixed_flag: int = header_stream.read('uint:1')
        CSPS_flag: int = header_stream.read('uint:1')
        system_audio_lock_flag: int = header_stream.read('uint:1')
        system_video_lock_flag: int = header_stream.read('uint:1')
        # Skip marker_bit
        header_stream.pos += 1
        video_bound: int = header_stream.read('uint:5')
        packet_rate_restriction_flag: int = header_stream.read('uint:1')
        # Skip reserved_bits
        header_stream.pos += 7

        P_STD_info: list[Mpeg2PsSystemHeaderPStdInfo] = []
        while True:
            stream_id: int
            try:
                stream_id = header_stream.read('uint:8')
            except bitstring.ReadError:
                # End of stream
                break
            if stream_id & 0x80 != 0x80:
                # P-STD info not found
                header_stream.pos -= 8
                break
            temp: int = header_stream.read('uintbe:16')
            P_STD_buffer_bound_scale = (temp >> 13) & 0x01
            P_STD_buffer_size_bound = temp & 0x1fff
            P_STD_info.append(Mpeg2PsSystemHeaderPStdInfo(
                stream_id, P_STD_buffer_bound_scale, P_STD_buffer_size_bound))

        return Mpeg2PsSystemHeader(rate_bound, audio_bound, fixed_flag, CSPS_flag, system_audio_lock_flag, system_video_lock_flag, video_bound, packet_rate_restriction_flag, P_STD_info)

    @staticmethod
    def write_ps_system_header(stream: bitstring.BitStream, data: Mpeg2PsSystemHeader):
        stream.append(Mpeg2Ps.PACKET_START_CODE + b'\xbb')

        header_stream = bitstring.BitStream()
        header_stream.append(bitstring.pack(
            'uintbe:24', 0x800001 | ((data.rate_bound & 0x3fffff) << 1)))
        header_stream.append(bitstring.pack('uint:6', data.audio_bound))
        header_stream.append(bitstring.pack('uint:1', data.fixed_flag))
        header_stream.append(bitstring.pack('uint:1', data.CSPS_flag))
        header_stream.append(bitstring.pack(
            'uint:1', data.system_audio_lock_flag))
        header_stream.append(bitstring.pack(
            'uint:1', data.system_video_lock_flag))
        # marker_bit
        header_stream.append(bitstring.pack('uint:1', 1))
        header_stream.append(bitstring.pack('uint:5', data.video_bound))
        header_stream.append(bitstring.pack('uint:1',
                             data.packet_rate_restriction_flag))
        # reserved_bits
        header_stream.append(bitstring.BitArray(bin='1111111'))
        for P_STD_info_entry in data.P_STD_info:
            header_stream.append(bitstring.pack('uint:8',
                                                P_STD_info_entry.stream_id))
            temp = 0xc000
            temp |= (P_STD_info_entry.P_STD_buffer_bound_scale & 0x01) << 13
            temp |= P_STD_info_entry.P_STD_buffer_size_bound & 0x1fff
            header_stream.append(bitstring.pack('uintbe:16', temp))

        header_bytes = header_stream.tobytes()
        stream.append(bitstring.pack('uintbe:16', len(header_bytes)))
        stream.append(header_bytes)

    @staticmethod
    def __read_descriptor(stream: bitstring.BitStream) -> Mpeg2Descriptor | None:
        descriptor_tag: int
        try:
            descriptor_tag = stream.peek('uint:8')
        except bitstring.ReadError:
            # End of stream
            return
        if descriptor_tag == 0x28:
            descriptor = Mpeg2Ps.__read_avc_video_descriptor(stream)
            if descriptor is not None:
                return descriptor
        elif descriptor_tag == 0x2b:
            descriptor = Mpeg2Ps.__read_mpeg2_aac_audio_descriptor(stream)
            if descriptor is not None:
                return descriptor
            return
        elif descriptor_tag == 0x38:
            descriptor = Mpeg2Ps.__read_hevc_video_descriptor(stream)
            if descriptor is not None:
                return descriptor
        else:
            return Mpeg2Ps.__read_generic_descriptor(stream)

    @staticmethod
    def __read_generic_descriptor(stream: bitstring.BitStream):
        descriptor_tag = stream.read('uint:8')
        descriptor_length = stream.read('uint:8')
        data_buffer: bytes = stream.read(8 * descriptor_length).bytes
        return Mpeg2GenericDescriptor(descriptor_tag, data_buffer)

    @staticmethod
    def __read_avc_video_descriptor(stream: bitstring.BitStream):
        descriptor_tag: int = stream.read('uint:8')
        if descriptor_tag != 0x28:
            raise RuntimeError('Invalid descriptor_tag.')
        descriptor_length: int = stream.read('uint:8')
        data_stream = bitstring.BitStream(stream.read(8 * descriptor_length))
        profile_idc: int = data_stream.read('uint:8')
        constraint_set0_flag: int = data_stream.read('uint:1')
        constraint_set1_flag: int = data_stream.read('uint:1')
        constraint_set2_flag: int = data_stream.read('uint:1')
        constraint_set3_flag: int = data_stream.read('uint:1')
        constraint_set4_flag: int = data_stream.read('uint:1')
        constraint_set5_flag: int = data_stream.read('uint:1')
        AVC_compatible_flags: int = data_stream.read('uint:2')
        level_idc: int = data_stream.read('uint:8')
        AVC_still_present: int = data_stream.read('uint:1')
        AVC_24_hour_picture_flag: int = data_stream.read('uint:1')
        Frame_Packing_SEI_not_present_flag: int = data_stream.read('uint:1')
        # Skip reserved
        data_stream.pos += 5
        return Mpeg2AvcVideoDescriptor(profile_idc, constraint_set0_flag, constraint_set1_flag, constraint_set2_flag, constraint_set3_flag, constraint_set4_flag, constraint_set5_flag, AVC_compatible_flags, level_idc, AVC_still_present, AVC_24_hour_picture_flag, Frame_Packing_SEI_not_present_flag)

    @staticmethod
    def __read_mpeg2_aac_audio_descriptor(stream: io.BufferedReader):
        descriptor_tag: int = stream.read('uint:8')
        if descriptor_tag != 0x2b:
            raise RuntimeError('Invalid descriptor_tag.')
        descriptor_length: int = stream.read('uint:8')
        data_stream = bitstring.BitStream(stream.read(8 * descriptor_length))
        MPEG_2_AAC_profile: int = data_stream.read('uint:8')
        MPEG_2_AAC_channel_configuration: int = data_stream.read('uint:8')
        MPEG_2_AAC_additional_information: int = data_stream.read('uint:8')
        return Mpeg2AacAudioDescriptor(MPEG_2_AAC_profile, MPEG_2_AAC_channel_configuration, MPEG_2_AAC_additional_information)

    @staticmethod
    def __read_hevc_video_descriptor(stream: io.BufferedReader):
        descriptor_tag: int = stream.read('uint:8')
        if descriptor_tag != 0x38:
            raise RuntimeError('Invalid descriptor_tag.')
        descriptor_length: int = stream.read('uint:8')
        data_stream = bitstring.BitStream(stream.read(8 * descriptor_length))
        profile_space: int = data_stream.read('uint:2')
        tier_flag: int = data_stream.read('uint:1')
        profile_idc: int = data_stream.read('uint:5')
        profile_compatibility_indication: int = data_stream.read('uintbe:32')
        progressive_source_flag: int = data_stream.read('uint:1')
        interlaced_source_flag: int = data_stream.read('uint:1')
        non_packed_constraint_flag: int = data_stream.read('uint:1')
        frame_only_constraint_flag: int = data_stream.read('uint:1')
        copied_44bits: int = data_stream.read('uintbe:44')
        level_idc: int = data_stream.read('uint:8')
        temporal_layer_subset_flag: int = data_stream.read('uint:1')
        HEVC_still_present_flag: int = data_stream.read('uint:1')
        HEVC_24hr_picture_present_flag: int = data_stream.read('uint:1')
        sub_pic_hrd_params_not_present_flag: int = data_stream.read('uint:1')
        # Skip reserved
        data_stream.pos += 2
        HDR_WCG_idc: int = data_stream.read('uint:2')
        temporal_id_min: int | None = None
        temporal_id_max: int | None = None
        if temporal_layer_subset_flag == 0x01:
            temporal_id_min: int = data_stream.read('uint:3')
            # Skip reserved
            data_stream.pos += 5
            temporal_id_max: int = data_stream.read('uint:3')
            # Skip reserved
            data_stream.pos += 5
        return Mpeg2HevcVideoDescriptor(profile_space, tier_flag, profile_idc, profile_compatibility_indication, progressive_source_flag, interlaced_source_flag, non_packed_constraint_flag, frame_only_constraint_flag, copied_44bits, level_idc, temporal_layer_subset_flag, HEVC_still_present_flag, HEVC_24hr_picture_present_flag, sub_pic_hrd_params_not_present_flag, HDR_WCG_idc, temporal_id_min, temporal_id_max)

    @staticmethod
    def __write_descriptor(stream: bitstring.BitStream, data: Mpeg2Descriptor):
        if isinstance(data, Mpeg2GenericDescriptor):
            return Mpeg2Ps.__write_generic_descriptor(stream, data)
        elif isinstance(data, Mpeg2AvcVideoDescriptor):
            return Mpeg2Ps.__write_avc_video_descriptor(stream, data)
        elif isinstance(data, Mpeg2AacAudioDescriptor):
            return Mpeg2Ps.__write_aac_audio_descriptor(stream, data)
        elif isinstance(data, Mpeg2HevcVideoDescriptor):
            return Mpeg2Ps.__write_hevc_video_descriptor(stream, data)

    @staticmethod
    def __write_generic_descriptor(stream: bitstring.BitStream, data: Mpeg2GenericDescriptor):
        stream.append(bitstring.pack('uint:8', data.descriptor_tag))
        stream.append(bitstring.pack('uint:8', len(data.data)))
        stream.append(data.data)

    @staticmethod
    def __write_avc_video_descriptor(stream: bitstring.BitStream, data: Mpeg2AvcVideoDescriptor):
        stream.append(b'\x28\x04')
        stream.append(bitstring.pack('uint:8', data.profile_idc))
        stream.append(bitstring.pack('uint:1', data.constraint_set0_flag))
        stream.append(bitstring.pack('uint:1', data.constraint_set1_flag))
        stream.append(bitstring.pack('uint:1', data.constraint_set2_flag))
        stream.append(bitstring.pack('uint:1', data.constraint_set3_flag))
        stream.append(bitstring.pack('uint:1', data.constraint_set4_flag))
        stream.append(bitstring.pack('uint:1', data.constraint_set5_flag))
        stream.append(bitstring.pack('uint:2', data.AVC_compatible_flags))
        stream.append(bitstring.pack('uint:8', data.level_idc))
        stream.append(bitstring.pack('uint:1', data.AVC_still_present))
        stream.append(bitstring.pack('uint:1', data.AVC_24_hour_picture_flag))
        stream.append(bitstring.pack(
            'uint:1', data.Frame_Packing_SEI_not_present_flag))
        # reserved
        stream.append(bitstring.BitArray(bin='11111'))

    @staticmethod
    def __write_aac_audio_descriptor(stream: bitstring.BitStream, data: Mpeg2AacAudioDescriptor):
        stream.append(b'\x2b\x03')
        stream.append(bitstring.pack('uint:8', data.MPEG_2_AAC_profile))
        stream.append(bitstring.pack(
            'uint:8', data.MPEG_2_AAC_channel_configuration))
        stream.append(bitstring.pack(
            'uint:8', data.MPEG_2_AAC_additional_information))

    @staticmethod
    def __write_hevc_video_descriptor(stream: bitstring.BitStream, data: Mpeg2HevcVideoDescriptor):
        stream.append(b'\x2b')
        if data.temporal_layer_subset_flag & 0x01 == 0x01:
            stream.append(b'\x0f')
        else:
            stream.append(b'\x0d')
        stream.append(bitstring.pack('uint:2', data.profile_space))
        stream.append(bitstring.pack('uint:1', data.tier_flag))
        stream.append(bitstring.pack('uint:5', data.profile_idc))
        stream.append(bitstring.pack(
            'uintbe:32', data.profile_compatibility_indication))
        stream.append(bitstring.pack('uint:1', data.progressive_source_flag))
        stream.append(bitstring.pack('uint:1', data.interlaced_source_flag))
        stream.append(bitstring.pack(
            'uint:1', data.non_packed_constraint_flag))
        stream.append(bitstring.pack(
            'uint:1', data.frame_only_constraint_flag))
        stream.append(bitstring.pack('uintbe:44', data.copied_44bits))
        stream.append(bitstring.pack('uint:8', data.level_idc))
        stream.append(bitstring.pack(
            'uint:1', data.temporal_layer_subset_flag))
        stream.append(bitstring.pack('uint:1', data.HEVC_still_present_flag))
        stream.append(bitstring.pack(
            'uint:1', data.HEVC_24hr_picture_present_flag))
        stream.append(bitstring.pack(
            'uint:1', data.sub_pic_hrd_params_not_present_flag))
        # reserved
        stream.append(bitstring.BitArray(bin='11'))
        stream.append(bitstring.pack('uint:2', data.HDR_WCG_idc))
        if data.temporal_layer_subset_flag & 0x01 == 0x01:
            stream.append(bitstring.pack('uint:3', data.temporal_id_min))
            # reserved
            stream.append(bitstring.BitArray(bin='11111'))
            stream.append(bitstring.pack('uint:3', data.temporal_id_max))
            # reserved
            stream.append(bitstring.BitArray(bin='11111'))

    @staticmethod
    def read_program_stream_map(stream: bitstring.BitStream):
        packet_start_code_prefix: bytes = stream.read('bytes:3')
        if packet_start_code_prefix != Mpeg2Ps.PACKET_START_CODE:
            raise RuntimeError('Invalid packet_start_code_prefix.')
        map_stream_id: int = stream.read('uint:8')
        if map_stream_id != 0xbc:
            raise RuntimeError('Invalid map_stream_id.')
        program_stream_map_length: int = stream.read('uintbe:16')
        program_stream_map_stream = bitstring.BitStream(
            stream.read(8 * program_stream_map_length))

        current_next_indicator: int = program_stream_map_stream.read('uint:1')
        # Skip Reserved
        program_stream_map_stream.pos += 2
        program_stream_map_version = program_stream_map_stream.read('uint:5')
        # Skip Reserved and marker_bit
        program_stream_map_stream.pos += 8

        program_stream_info: list[Mpeg2Descriptor] = []
        program_stream_info_length: int = program_stream_map_stream.read(
            'uintbe:16')
        program_stream_info_stream = bitstring.BitStream(
            program_stream_map_stream.read(8 * program_stream_info_length))
        while True:
            descriptor = Mpeg2Ps.__read_descriptor(program_stream_info_stream)
            if descriptor is None:
                break
            program_stream_info.append(descriptor)

        elementary_stream_map: list[Mpeg2PsElementaryStreamMapEntry] = []
        elementary_stream_map_length: int = program_stream_map_stream.read(
            'uintbe:16')
        elementary_stream_map_stream = bitstring.BitStream(
            program_stream_map_stream.read(8 * elementary_stream_map_length))
        while True:
            stream_type: int
            try:
                stream_type = elementary_stream_map_stream.read('uint:8')
            except bitstring.ReadError:
                # End of stream
                break
            if stream_type == 0x00:
                Mpeg2Ps.__logger.warning('Reserved stream_id 0x00 detected.')
                break
            elementary_stream_id = elementary_stream_map_stream.read('uint:8')

            elementary_stream_info: list[Mpeg2Descriptor] = []
            elementary_stream_info_length: int = elementary_stream_map_stream.read(
                'uintbe:16')
            elementary_stream_info_stream = bitstring.BitStream(
                elementary_stream_map_stream.read(8 * elementary_stream_info_length))
            while True:
                descriptor = Mpeg2Ps.__read_descriptor(
                    elementary_stream_info_stream)
                if descriptor is None:
                    break
                elementary_stream_info.append(descriptor)
            elementary_stream_map.append(Mpeg2PsElementaryStreamMapEntry(
                stream_type, elementary_stream_id,  elementary_stream_info))

        crc32 = program_stream_map_stream.read('uintbe:32')

        return Mpeg2PsProgramStreamMap(current_next_indicator, program_stream_map_version, program_stream_info, elementary_stream_map)

    @staticmethod
    def write_program_stream_map(stream: bitstring.BitStream, data: Mpeg2PsProgramStreamMap):
        stream.append(Mpeg2Ps.PACKET_START_CODE + b'\xbc')

        program_stream_map_stream = bitstring.BitStream()
        program_stream_map_stream.append(
            bitstring.pack('uint:1', data.current_next_indicator))
        # Reserved
        program_stream_map_stream.append(bitstring.BitArray(bin='11'))
        program_stream_map_stream.append(bitstring.pack(
            'uint:5', data.program_stream_map_version))
        # Reserved and marker_bit
        program_stream_map_stream.append(b'\xff')

        program_stream_info_stream = bitstring.BitStream()
        for descriptor in data.program_stream_info:
            Mpeg2Ps.__write_descriptor(program_stream_info_stream, descriptor)
        program_stream_info_buffer = program_stream_info_stream.tobytes()
        program_stream_map_stream.append(bitstring.pack(
            'uintbe:16', len(program_stream_info_buffer)))
        program_stream_map_stream.append(program_stream_info_buffer)

        elementary_stream_map_stream = bitstring.BitStream()
        for entry in data.elementary_stream_map:
            elementary_stream_map_stream.append(
                bitstring.pack('uint:8', entry.stream_type))
            elementary_stream_map_stream.append(
                bitstring.pack('uint:8', entry.elementary_stream_id))

            elementary_stream_info_stream = bitstring.BitStream()
            for descriptor in entry.elementary_stream_info:
                Mpeg2Ps.__write_descriptor(
                    elementary_stream_info_stream, descriptor)
            elementary_stream_info_buffer = elementary_stream_info_stream.tobytes()
            elementary_stream_map_stream.append(bitstring.pack(
                'uintbe:16', len(elementary_stream_info_buffer)))
            elementary_stream_map_stream.append(elementary_stream_info_buffer)
        elementary_stream_map_buffer = elementary_stream_map_stream.tobytes()
        program_stream_map_stream.append(bitstring.pack(
            'uintbe:16', len(elementary_stream_map_buffer)))
        program_stream_map_stream.append(elementary_stream_map_buffer)

        program_stream_map_buffer = program_stream_map_stream.tobytes()
        stream.append(bitstring.pack(
            'uintbe:16', len(program_stream_map_buffer) + 4))
        stream.append(program_stream_map_buffer)

        buffer = stream.tobytes()
        crc32 = Mpeg2Ps.crc32(buffer)
        stream.append(bitstring.pack('uintbe:32', crc32))

    @staticmethod
    def read_ps_packet(stream: bitstring.BitStream) -> Mpeg2PsPacket | None:
        packet_id = Mpeg2Ps.seek_packet(stream)
        if packet_id is None:
            return

        if packet_id == 0xb9:
            stream.bytepos += 4
            return Mpeg2PsProgramEnd()
        elif packet_id == 0xba:
            return Mpeg2Ps.read_ps_pack_header(stream)
        elif packet_id == 0xbb:
            return Mpeg2Ps.read_ps_system_header(stream)
        elif packet_id == 0xbc:
            return Mpeg2Ps.read_program_stream_map(stream)
        else:
            return Mpeg2Ps.read_pes_packet(stream)

    @staticmethod
    def write_ps_packet(stream: bitstring.BitStream, data: Mpeg2PsPacket):
        if isinstance(data, Mpeg2PsProgramEnd):
            stream.append(b'\x00\x00\x01\xb9')
        elif isinstance(data, Mpeg2PsPackHeader):
            Mpeg2Ps.write_ps_pack_header(stream, data)
        elif isinstance(data, Mpeg2PsSystemHeader):
            Mpeg2Ps.write_ps_system_header(stream, data)
        elif isinstance(data, Mpeg2PsProgramStreamMap):
            Mpeg2Ps.write_program_stream_map(stream, data)
        elif isinstance(data, Mpeg2PesPacket):
            Mpeg2Ps.write_pes_packet(stream, data)
