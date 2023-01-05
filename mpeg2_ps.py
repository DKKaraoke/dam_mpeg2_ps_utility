from customized_logger import getLogger
import io
from mpeg2_ps_data import Mpeg2PesPacketType1, Mpeg2PesPacketType2, Mpeg2PesPacketType3, Mpeg2PsPackHeader, Mpeg2PsSystemHeaderPStdInfo,  Mpeg2PsSystemHeader, Mpeg2GenericDescriptor, Mpeg2AvcVideoDescriptor, Mpeg2AacAudioDescriptor, Mpeg2HevcVideoDescriptor, Mpeg2Descriptor, Mpeg2PsElementaryStreamMapEntry, Mpeg2PsProgramStreamMap
import os


class Mpeg2Ps:
    """MPEG2-PS
    """

    PACKET_START_CODE = b'\x00\x00\x01'

    __logger = getLogger('Mpeg2Ps')

    # @staticmethod
    # def crc32(buffer: bytes):
    #     crc = 0xffffffff
    #     for value in buffer:
    #         crc ^= value << 24
    #         for _ in range(8):
    #             msb = crc >> 31
    #             crc <<= 1
    #             crc ^= (0 - msb) & 0x104c11db7
    #     return crc

    @staticmethod
    def crc32(buffer: bytes, crc=0xffffffff):
        for value in buffer:
            crc ^= value << 24
            for _ in range(8):
                crc = crc << 1 if (crc & 0x80000000) == 0 else (
                    crc << 1) ^ 0x104c11db7
        return crc

    @staticmethod
    def seek_packet(stream: io.BufferedReader, packet_id: int | None = None):
        zero_count = 0
        packet_start_code_detected = False
        while True:
            buffer = stream.read(1)
            # End of stream
            if len(buffer) == 0:
                break
            current_byte = int.from_bytes(buffer)
            if not packet_start_code_detected:
                if 2 <= zero_count and current_byte == 0x01:
                    packet_start_code_detected = True
            else:
                if packet_id is None:
                    stream.seek(-4, os.SEEK_CUR)
                    return current_byte
                else:
                    if current_byte == packet_id:
                        stream.seek(-4, os.SEEK_CUR)
                        return current_byte
                packet_start_code_detected = False
            # Count zero
            if current_byte == 0x00:
                zero_count += 1
            else:
                zero_count = 0

    @staticmethod
    def index_packets(stream: io.BufferedReader, packet_id: int | None = None):
        start_position = stream.tell()

        index: list[tuple[int, int]] = []
        current_start = -1
        while True:
            packet_id = Mpeg2Ps.seek_packet(stream, packet_id)
            position = stream.tell()
            if packet_id is None:
                break
            stream.seek(4, os.SEEK_CUR)
            if current_start != -1:
                size = position - current_start
                index.append((current_start, size))
            current_start = position
        if current_start != -1:
            size = len(stream.read()) - current_start
            index.append((current_start, size))

        stream.seek(start_position)

        return index

    @staticmethod
    def read_packet_id(stream: io.BufferedReader, restore_position=True):
        start_position = stream.tell()
        buffer = stream.read(4)
        if restore_position:
            stream.seek(start_position)
        if len(buffer) != 4:
            Mpeg2Ps.__logger.warning('Invalid buffer length')
            return
        if buffer[0:3] != Mpeg2Ps.PACKET_START_CODE:
            Mpeg2Ps.__logger.warning('Invalid packet start code')
            return
        return buffer[3]

    @staticmethod
    def read_pes_packet(stream: io.BufferedReader):
        header_buffer = stream.read(6)
        if len(header_buffer) != 6:
            Mpeg2Ps.__logger.warning('Invalid header_buffer length')
            return

        packet_start_code_prefix = header_buffer[0:3]
        if packet_start_code_prefix != Mpeg2Ps.PACKET_START_CODE:
            Mpeg2Ps.__logger.warning('Invalid packet_start_code_prefix')
            return
        stream_id = header_buffer[3]
        PES_packet_length = int.from_bytes(header_buffer[4:6], byteorder='big')
        if stream_id != 0xbc and stream_id != 0xbe and stream_id != 0xbf and stream_id != 0xf0 and stream_id != 0xf1 and stream_id != 0xbc and 0xff and stream_id != 0xf2 and stream_id != 0xf8:
            extension_buffer = stream.read(3)
            if len(extension_buffer) != 3:
                Mpeg2Ps.__logger.warning('Invalid extension_buffer length')
                return
            flags = int.from_bytes(extension_buffer[0:2], byteorder='big')
            PTS_DTS_flags = (flags >> 6) & 0x02
            PES_header_data_length = extension_buffer[2]
            pts: int | None = None
            dts: int | None = None
            if PTS_DTS_flags == 0x02:
                PTS_buffer = stream.read(5)
                if len(PTS_buffer) != 5:
                    Mpeg2Ps.__logger.warning('Invalid PTS_buffer length')
                    return
                raw_PTS = int.from_bytes(PTS_buffer, byteorder='big')
                pts = (raw_PTS >> 3) & (0x0007 << 30)
                pts |= (raw_PTS >> 2) & (0x7fff << 15)
                pts |= (raw_PTS >> 1) & 0x7fff
            if PTS_DTS_flags == 0x03:
                PTS_DTS_buffer = stream.read(10)
                if len(PTS_DTS_buffer) != 10:
                    Mpeg2Ps.__logger.warning('Invalid PTS_DTS_buffer length')
                    return
                raw_PTS = int.from_bytes(PTS_DTS_buffer[0:5], byteorder='big')
                pts = (raw_PTS >> 3) & (0x0007 << 30)
                pts |= (raw_PTS >> 2) & (0x7fff << 15)
                pts |= (raw_PTS >> 1) & 0x7fff
                raw_DTS = int.from_bytes(PTS_DTS_buffer[5:10], byteorder='big')
                dts = (raw_DTS >> 3) & (0x0007 << 30)
                dts |= (raw_DTS >> 2) & (0x7fff << 15)
                dts |= (raw_DTS >> 1) & 0x7fff
            return Mpeg2PesPacketType1(stream_id, PES_packet_length, PES_header_data_length, PTS_DTS_flags, pts, dts)
        elif stream_id == 0xbc or stream_id == 0xbf or stream_id == 0xf0 or stream_id == 0xf1 or stream_id == 0xbc and 0xff or stream_id == 0xf2 or stream_id == 0xf8:
            data_buffer = stream.read(PES_packet_length)
            if len(data_buffer) != PES_packet_length:
                Mpeg2Ps.__logger.warning('Invalid data_buffer length')
                return
            return Mpeg2PesPacketType2(stream_id, data_buffer)
        elif stream_id == 0xbe:
            return Mpeg2PesPacketType3(stream_id, PES_packet_length)
        else:
            return

    @staticmethod
    def serialize_pes_packet(stream_id: int, data: bytes):
        return Mpeg2Ps.PACKET_START_CODE + stream_id.to_bytes(length=1) + len(data).to_bytes(length=2) + data

    @staticmethod
    def read_ps_pack_header(stream: io.BufferedReader):
        buffer = stream.read(14)
        if len(buffer) != 14:
            return

        pack_start_code = buffer[0:4]
        if pack_start_code != (Mpeg2Ps.PACKET_START_CODE + b'\xba'):
            Mpeg2Ps.__logger.warning('Invalid pack_start_code')
            return
        system_clock_reference_raw = int.from_bytes(
            buffer[4:10], byteorder='big')
        system_clock_reference_base = (
            system_clock_reference_raw >> 13) & (0x03 << 30)
        system_clock_reference_base |= (
            system_clock_reference_raw >> 12) & (0x7fff << 15)
        system_clock_reference_base |= (
            system_clock_reference_raw >> 11) & 0x7fff
        system_clock_reference_extension = (
            system_clock_reference_raw >> 1) & 0x01ff
        program_mux_rate_raw = int.from_bytes(buffer[10:13], byteorder='big')
        program_mux_rate = program_mux_rate_raw >> 2
        pack_stuffing_length = buffer[13] & 0x03

        stuffing_bytes = stream.read(pack_stuffing_length)
        if len(stuffing_bytes) != pack_stuffing_length:
            Mpeg2Ps.__logger.warning('Invalid stuffing_bytes length')
            return
        for stuffing_byte in stuffing_bytes:
            if stuffing_byte != 0xff:
                Mpeg2Ps.__logger.warning('Invalid stuffing_byte')
                return

        return Mpeg2PsPackHeader(system_clock_reference_base, system_clock_reference_extension, program_mux_rate, pack_stuffing_length)

    @staticmethod
    def serialize_ps_pack_header(data: Mpeg2PsPackHeader):
        buffer = Mpeg2Ps.PACKET_START_CODE + b'\xba'
        system_clock_reference_raw = 0x440004000401
        system_clock_reference_raw |= (
            data.system_clock_reference_base & 0xe0000000) << 13
        system_clock_reference_raw |= (
            data.system_clock_reference_base & 0x7fff0000) << 12
        system_clock_reference_raw |= (
            data.system_clock_reference_base & 0x7fff) << 11
        system_clock_reference_raw |= (
            data.system_clock_reference_extension & 0x01ff) << 1
        buffer += system_clock_reference_raw.to_bytes(6, byteorder='big')
        program_mux_rate_raw = 0x000003
        program_mux_rate_raw |= (data.program_mux_rate & 0x3fffff) << 2
        buffer += program_mux_rate_raw.to_bytes(3, byteorder='big')
        pack_stuffing_length_raw = 0xf8
        pack_stuffing_length_raw |= data.pack_stuffing_length & 0x03
        buffer += pack_stuffing_length_raw.to_bytes(1, byteorder='big')
        for _ in range(data.pack_stuffing_length):
            buffer += b'\0xff'
        return buffer

    @staticmethod
    def read_ps_system_header(stream: io.BufferedReader):
        packet_header_buffer = stream.read(6)
        if len(packet_header_buffer) != 6:
            return

        system_header_start_code = packet_header_buffer[0:4]
        if system_header_start_code != (Mpeg2Ps.PACKET_START_CODE + b'\xbb'):
            Mpeg2Ps.__logger.warning('Invalid system_header_start_code')
            return
        header_length = int.from_bytes(
            packet_header_buffer[4:6], byteorder='big')
        header_buffer = stream.read(header_length)
        if header_length < 6:
            Mpeg2Ps.__logger.warning('Invalid header_length')
            return
        if len(header_buffer) != header_length:
            Mpeg2Ps.__logger.warning('Invalid header_buffer length')
            return
        header_stream = io.BytesIO(header_buffer)

        rate_bound_raw = int.from_bytes(header_buffer[0:3], byteorder='big')
        rate_bound = (rate_bound_raw >> 1) & 0x3fffff
        audio_bound = header_buffer[3] >> 2
        fixed_flag = header_buffer[3] >> 1 & 0x01
        CSPS_flag = header_buffer[3] & 0x01
        system_audio_lock_flag = header_buffer[4] >> 7
        system_video_lock_flag = (header_buffer[4] >> 6) & 0x01
        video_bound = header_buffer[4] & 0x1f
        packet_rate_restriction_flag = header_buffer[5] >> 7
        reserved_bits = header_buffer[5] & 0x7f
        if reserved_bits != 0x7f:
            Mpeg2Ps.__logger.warning('Invalid reserved_bits')
            return

        P_STD_info: list[Mpeg2PsSystemHeaderPStdInfo] = []
        header_stream.seek(6)
        while True:
            stream_id_buffer = header_stream.read(1)
            if len(stream_id_buffer) != 1:
                header_stream.seek(-1, os.SEEK_CUR)
                break
            stream_id = int.from_bytes(stream_id_buffer)
            if stream_id & 0x80 != 0x80:
                header_stream.seek(-1, os.SEEK_CUR)
                break
            temp_buffer = header_stream.read(2)
            if len(temp_buffer) != 2:
                Mpeg2Ps.__logger.warning('Invalid a P_STD_info entry')
                return
            temp = int.from_bytes(temp_buffer, byteorder='big')
            P_STD_buffer_bound_scale = (temp >> 13) & 0x01
            P_STD_buffer_size_bound = temp & 0x1fff
            P_STD_info.append(Mpeg2PsSystemHeaderPStdInfo(
                stream_id, P_STD_buffer_bound_scale, P_STD_buffer_size_bound))

        return Mpeg2PsSystemHeader(rate_bound, audio_bound, fixed_flag, CSPS_flag, system_audio_lock_flag, system_video_lock_flag, video_bound, packet_rate_restriction_flag, P_STD_info)

    @staticmethod
    def serialize_ps_system_header(data: Mpeg2PsSystemHeader):
        buffer = Mpeg2Ps.PACKET_START_CODE + b'\xbb'

        header_buffer = b''
        rate_bound_raw = 0x800001
        rate_bound_raw |= (data.rate_bound & 0x3fffff) << 1
        header_buffer += rate_bound_raw.to_bytes(3, byteorder='big')
        temp = (data.audio_bound & 0x3f) << 2
        temp |= (data.fixed_flag & 0x01) << 1
        temp |= data.CSPS_flag & 0x01
        header_buffer += temp.to_bytes(1)
        temp = 0x20
        temp |= (data.system_audio_lock_flag & 0x01) << 7
        temp |= (data.system_video_lock_flag & 0x01) << 6
        temp |= data.video_bound & 0x1f
        header_buffer += temp.to_bytes(1)
        temp = 0x7f
        temp |= (data.packet_rate_restriction_flag & 0x01) << 7
        header_buffer += temp.to_bytes(1)
        for P_STD_info_entry in data.P_STD_info:
            header_buffer += P_STD_info_entry.stream_id.to_bytes(1)
            temp = 0xc000
            temp |= (P_STD_info_entry.P_STD_buffer_bound_scale & 0x01) << 13
            temp |= P_STD_info_entry.P_STD_buffer_size_bound & 0x1fff
            header_buffer += temp.to_bytes(2, byteorder='big')

        buffer += len(header_buffer).to_bytes(2, byteorder='big')
        buffer += header_buffer

        return buffer

    @staticmethod
    def __read_descriptor(stream: io.BufferedReader) -> Mpeg2Descriptor | None:
        descriptor_header_buffer = stream.read(2)
        if len(descriptor_header_buffer) == 0:
            return
        if len(descriptor_header_buffer) != 2:
            Mpeg2Ps.__logger.warning('Invalid descriptor_header_buffer length')
            return
        descriptor_tag = descriptor_header_buffer[0]

        stream.seek(-2, os.SEEK_CUR)
        if descriptor_tag == 0x28:
            descriptor = Mpeg2Ps.__read_avc_video_descriptor(stream)
            if descriptor is not None:
                return descriptor
        if descriptor_tag == 0x2b:
            descriptor = Mpeg2Ps.__read_mpeg2_aac_audio_descriptor(stream)
            if descriptor is not None:
                return descriptor
            return
        if descriptor_tag == 0x38:
            descriptor = Mpeg2Ps.__read_hevc_video_descriptor(stream)
            if descriptor is not None:
                return descriptor

        return Mpeg2Ps.__read_generic_descriptor(stream)

    @staticmethod
    def __read_generic_descriptor(stream: io.BufferedReader):
        descriptor_header_buffer = stream.read(2)
        if len(descriptor_header_buffer) == 0:
            return
        if len(descriptor_header_buffer) != 2:
            Mpeg2Ps.__logger.warning('Invalid descriptor_header_buffer length')
            return
        descriptor_tag = descriptor_header_buffer[0]
        descriptor_length = descriptor_header_buffer[1]
        data_buffer = stream.read(descriptor_length)
        if len(data_buffer) != descriptor_length:
            Mpeg2Ps.__logger.warning('Invalid data_buffer length')
            return
        return Mpeg2GenericDescriptor(descriptor_tag, data_buffer)

    @staticmethod
    def __read_avc_video_descriptor(stream: io.BufferedReader):
        descriptor_header_buffer = stream.read(2)
        if len(descriptor_header_buffer) == 0:
            return
        if len(descriptor_header_buffer) != 2:
            Mpeg2Ps.__logger.warning('Invalid descriptor_header_buffer length')
            return
        descriptor_tag = descriptor_header_buffer[0]
        if descriptor_tag != 0x28:
            Mpeg2Ps.__logger.warning('Invalid descriptor_tag')
            return
        descriptor_length = descriptor_header_buffer[1]
        if descriptor_length != 4:
            Mpeg2Ps.__logger.warning('Invalid descriptor_length')
            return
        data_buffer = stream.read(descriptor_length)
        if len(data_buffer) != descriptor_length:
            Mpeg2Ps.__logger.warning('Invalid data_buffer length')
            return
        profile_idc = data_buffer[0]
        flags_1 = data_buffer[1]
        constraint_set0_flag = flags_1 >> 7
        constraint_set1_flag = (flags_1 >> 6) & 0x01
        constraint_set2_flag = (flags_1 >> 5) & 0x01
        constraint_set3_flag = (flags_1 >> 4) & 0x01
        constraint_set4_flag = (flags_1 >> 3) & 0x01
        constraint_set5_flag = (flags_1 >> 2) & 0x01
        AVC_compatible_flags = flags_1 & 0x03
        level_idc = data_buffer[2]
        flags_2 = data_buffer[3]
        AVC_still_present = flags_2 >> 7
        AVC_24_hour_picture_flag = (flags_2 >> 6) & 0x01
        Frame_Packing_SEI_not_present_flag = (flags_2 >> 5) & 0x01
        return Mpeg2AvcVideoDescriptor(profile_idc, constraint_set0_flag, constraint_set1_flag, constraint_set2_flag, constraint_set3_flag, constraint_set4_flag, constraint_set5_flag, AVC_compatible_flags, level_idc, AVC_still_present, AVC_24_hour_picture_flag, Frame_Packing_SEI_not_present_flag)

    @staticmethod
    def __read_mpeg2_aac_audio_descriptor(stream: io.BufferedReader):
        descriptor_header_buffer = stream.read(2)
        if len(descriptor_header_buffer) == 0:
            return
        if len(descriptor_header_buffer) != 2:
            Mpeg2Ps.__logger.warning('Invalid descriptor_header_buffer length')
            return
        descriptor_tag = descriptor_header_buffer[0]
        if descriptor_tag != 0x2b:
            Mpeg2Ps.__logger.warning('Invalid descriptor_tag')
            return
        descriptor_length = descriptor_header_buffer[1]
        if descriptor_length != 3:
            Mpeg2Ps.__logger.warning('Invalid descriptor_length')
            return
        data_buffer = stream.read(descriptor_length)
        if len(data_buffer) != descriptor_length:
            Mpeg2Ps.__logger.warning('Invalid data_buffer length')
            return
        MPEG_2_AAC_profile = data_buffer[0]
        MPEG_2_AAC_channel_configuration = data_buffer[1]
        MPEG_2_AAC_additional_information = data_buffer[2]
        return Mpeg2AacAudioDescriptor(MPEG_2_AAC_profile, MPEG_2_AAC_channel_configuration, MPEG_2_AAC_additional_information)

    @staticmethod
    def __read_hevc_video_descriptor(stream: io.BufferedReader):
        descriptor_header_buffer = stream.read(2)
        if len(descriptor_header_buffer) == 0:
            return
        if len(descriptor_header_buffer) != 2:
            Mpeg2Ps.__logger.warning('Invalid descriptor_header_buffer length')
            return
        descriptor_tag = descriptor_header_buffer[0]
        if descriptor_tag != 0x38 and descriptor_tag != 0x39:
            Mpeg2Ps.__logger.warning('Invalid descriptor_tag')
            return
        descriptor_length = descriptor_header_buffer[1]
        if descriptor_length != 13 and descriptor_length != 15:
            Mpeg2Ps.__logger.warning('Invalid descriptor_length')
            return
        data_buffer = stream.read(13)
        if len(data_buffer) != 13:
            Mpeg2Ps.__logger.warning('Invalid data_buffer length')
            return
        temp = data_buffer[0]
        profile_space = temp >> 6
        tier_flag = (temp >> 5) & 0x01
        profile_idc = temp & 0x1f
        profile_compatibility_indication = int.from_bytes(
            data_buffer[1:5], byteorder='big')
        temp = int.from_bytes(data_buffer[5:11], byteorder='big')
        progressive_source_flag = temp >> 47
        interlaced_source_flag = (temp >> 46) & 0x01
        non_packed_constraint_flag = (temp >> 45) & 0x01
        frame_only_constraint_flag = (temp >> 44) & 0x01
        copied_44bits = temp & 0x0fffffffffff
        level_idc = data_buffer[11]
        temp = data_buffer[12]
        temporal_layer_subset_flag = temp >> 7
        HEVC_still_present_flag = (temp >> 6) & 0x01
        HEVC_24hr_picture_present_flag = (temp >> 5) & 0x01
        sub_pic_hrd_params_not_present_flag = (temp >> 4) & 0x01
        HDR_WCG_idc = temp & 0x03
        temporal_id_min: int | None = None
        temporal_id_max: int | None = None
        if temporal_layer_subset_flag == 0x01:
            extension_buffer = stream.read(2)
            if len(extension_buffer) != 2:
                Mpeg2Ps.__logger.warning('Invalid extension_buffer length')
                return
            temporal_id_min = extension_buffer[0] >> 5
            temporal_id_max = extension_buffer[1] >> 5
        return Mpeg2HevcVideoDescriptor(profile_space, tier_flag, profile_idc, profile_compatibility_indication, progressive_source_flag, interlaced_source_flag, non_packed_constraint_flag, frame_only_constraint_flag, copied_44bits, level_idc, temporal_layer_subset_flag, HEVC_still_present_flag, HEVC_24hr_picture_present_flag, sub_pic_hrd_params_not_present_flag, HDR_WCG_idc, temporal_id_min, temporal_id_max)

    @staticmethod
    def __serialize_descriptor(data: Mpeg2Descriptor):
        if isinstance(data, Mpeg2GenericDescriptor):
            return Mpeg2Ps.__serialize_generic_descriptor(data)
        elif isinstance(data, Mpeg2AvcVideoDescriptor):
            return Mpeg2Ps.__serialize_avc_video_descriptor(data)
        elif isinstance(data, Mpeg2AacAudioDescriptor):
            return Mpeg2Ps.__serialize_aac_audio_descriptor(data)
        elif isinstance(data, Mpeg2HevcVideoDescriptor):
            return Mpeg2Ps.__serialize_hevc_video_descriptor(data)

    @staticmethod
    def __serialize_generic_descriptor(data: Mpeg2GenericDescriptor):
        buffer = data.descriptor_tag.to_bytes(1)
        buffer += len(data.data).to_bytes(1)
        buffer += data.data
        return buffer

    @staticmethod
    def __serialize_avc_video_descriptor(data: Mpeg2AvcVideoDescriptor):
        buffer = b'\x28\x04'
        buffer += data.profile_idc.to_bytes(1)
        flags_1 = (data.constraint_set0_flag & 0x01) << 7
        flags_1 |= (data.constraint_set1_flag & 0x01) << 6
        flags_1 |= (data.constraint_set2_flag & 0x01) << 5
        flags_1 |= (data.constraint_set3_flag & 0x01) << 4
        flags_1 |= (data.constraint_set4_flag & 0x01) << 3
        flags_1 |= (data.constraint_set5_flag & 0x01) << 2
        flags_1 |= data.AVC_compatible_flags & 0x03
        buffer += flags_1.to_bytes(1)
        buffer += data.level_idc.to_bytes(1)
        flags_2 = 0x1f
        flags_2 |= (data.AVC_still_present & 0x01) << 7
        flags_2 |= (data.AVC_24_hour_picture_flag & 0x01) << 6
        flags_2 |= (data.Frame_Packing_SEI_not_present_flag & 0x01) << 5
        buffer += flags_2.to_bytes(1)
        return buffer

    @staticmethod
    def __serialize_aac_audio_descriptor(data: Mpeg2AacAudioDescriptor):
        buffer = b'\x2b\x03'
        buffer += data.MPEG_2_AAC_profile.to_bytes(1)
        buffer += data.MPEG_2_AAC_channel_configuration.to_bytes(1)
        buffer += data.MPEG_2_AAC_additional_information.to_bytes(1)
        return buffer

    @staticmethod
    def __serialize_hevc_video_descriptor(data: Mpeg2HevcVideoDescriptor):
        buffer = b'\x2b'
        if data.temporal_layer_subset_flag & 0x01 == 0x01:
            buffer += b'\x0f'
        else:
            buffer += b'\x0d'
        temp = (data.profile_space & 0x03) << 6
        temp |= (data.tier_flag & 0x01) << 5
        temp |= data.profile_idc & 0x1f
        buffer += temp.to_bytes(1)
        buffer += data.profile_compatibility_indication.to_bytes(
            4, byteorder='big')
        temp = (data.progressive_source_flag & 0x01) << 47
        temp |= (data.interlaced_source_flag & 0x01) << 46
        temp |= (data.non_packed_constraint_flag & 0x01) << 45
        temp |= (data.frame_only_constraint_flag & 0x01) << 44
        temp |= data.copied_44bits & 0x0fffffffffff
        buffer += temp.to_bytes(6, byteorder='big')
        buffer += data.level_idc.to_bytes(1)
        temp = 0x06
        temp |= (data.temporal_layer_subset_flag & 0x01) << 7
        temp |= (data.HEVC_still_present_flag & 0x01) << 6
        temp |= (data.HEVC_24hr_picture_present_flag & 0x01) << 5
        temp |= (data.sub_pic_hrd_params_not_present_flag & 0x01) << 4
        temp |= data.HDR_WCG_idc & 0x03
        buffer += temp.to_bytes(6, byteorder='big')
        if data.temporal_layer_subset_flag & 0x01 == 0x01:
            temp = 0x1f
            temp |= (data.temporal_id_min & 0x03) << 5
            buffer += temp.to_bytes(6, byteorder='big')
            temp = 0x1f
            temp |= (data.temporal_id_max & 0x03) << 5
            buffer += temp.to_bytes(6, byteorder='big')
        return buffer

    @staticmethod
    def read_program_stream_map(stream: io.BufferedReader):
        header_buffer = stream.read(6)
        if len(header_buffer) != 6:
            return
        packet_start_code_prefix = header_buffer[0:3]
        if packet_start_code_prefix != Mpeg2Ps.PACKET_START_CODE:
            Mpeg2Ps.__logger.warning('Invalid packet_start_code_prefix')
            return
        map_stream_id = header_buffer[3]
        if map_stream_id != 0xbc:
            Mpeg2Ps.__logger.warning('Invalid map_stream_id')
            return
        program_stream_map_length = int.from_bytes(
            header_buffer[4:6], byteorder='big')
        program_stream_map_buffer = stream.read(program_stream_map_length)
        if len(program_stream_map_buffer) != program_stream_map_length:
            Mpeg2Ps.__logger.warning(
                'Invalid program_stream_map_buffer length')
            return
        program_stream_map_stream = io.BytesIO(program_stream_map_buffer)

        current_next_indicator = program_stream_map_buffer[0] >> 7
        program_stream_map_version = program_stream_map_buffer[0] & 0x1f

        program_stream_info: list[Mpeg2Descriptor] = []
        program_stream_info_length = int.from_bytes(
            program_stream_map_buffer[2:4], byteorder='big')
        program_stream_map_stream.seek(4)
        program_stream_info_buffer = program_stream_map_stream.read(
            program_stream_info_length)
        if len(program_stream_info_buffer) != program_stream_info_length:
            Mpeg2Ps.__logger.warning(
                'Invalid program_stream_info_buffer length')
            return
        program_stream_info_stream = io.BytesIO(program_stream_info_buffer)
        while True:
            descriptor = Mpeg2Ps.__read_descriptor(program_stream_info_stream)
            if descriptor is None:
                break
            program_stream_info.append(descriptor)

        elementary_stream_map: list[Mpeg2PsElementaryStreamMapEntry] = []
        elementary_stream_map_length_buffer = program_stream_map_stream.read(2)
        if len(elementary_stream_map_length_buffer) != 2:
            Mpeg2Ps.__logger.warning(
                'elementary_stream_map_length_buffer not found')
            return
        elementary_stream_map_length = int.from_bytes(
            elementary_stream_map_length_buffer, byteorder='big')
        elementary_stream_map_buffer = program_stream_map_stream.read(
            elementary_stream_map_length)
        if len(elementary_stream_map_buffer) != elementary_stream_map_length:
            Mpeg2Ps.__logger.warning(
                'Invalid elementary_stream_map_buffer length')
            return
        elementary_stream_map_stream = io.BytesIO(elementary_stream_map_buffer)
        while True:
            elementary_stream_map_entry_buffer = elementary_stream_map_stream.read(
                4)
            if len(elementary_stream_map_entry_buffer) == 0:
                break
            if len(elementary_stream_map_entry_buffer) != 4:
                Mpeg2Ps.__logger.warning(
                    'Invalid elementary_stream_map_entry_buffer length')
                return
            stream_type = elementary_stream_map_entry_buffer[0]
            if stream_type == 0x00:
                Mpeg2Ps.__logger.warning('Reserved stream_id 0x00 detected.')
                break
            elementary_stream_id = elementary_stream_map_entry_buffer[1]

            elementary_stream_info: list[Mpeg2Descriptor] = []
            elementary_stream_info_length = int.from_bytes(
                elementary_stream_map_entry_buffer[2:4], byteorder='big')
            elementary_stream_info_buffer = elementary_stream_map_stream.read(
                elementary_stream_info_length)
            if len(elementary_stream_info_buffer) != elementary_stream_info_length:
                Mpeg2Ps.__logger.warning(
                    'Invalid elementary_stream_info_buffer length')
                return
            elementary_stream_info_stream = io.BytesIO(
                elementary_stream_info_buffer)
            while True:
                descriptor = Mpeg2Ps.__read_descriptor(
                    elementary_stream_info_stream)
                if descriptor is None:
                    break
                elementary_stream_info.append(descriptor)
            elementary_stream_map.append(Mpeg2PsElementaryStreamMapEntry(
                stream_type, elementary_stream_id,  elementary_stream_info))

        crc32_buffer = program_stream_map_stream.read(4)
        if len(crc32_buffer) != 4:
            Mpeg2Ps.__logger.warning('Invalid crc32_buffer length')
            return
        crc32 = int.from_bytes(crc32_buffer, byteorder='big')

        return Mpeg2PsProgramStreamMap(current_next_indicator, program_stream_map_version, program_stream_info, elementary_stream_map)

    @staticmethod
    def serialize_program_stream_map(data: Mpeg2PsProgramStreamMap):
        buffer = Mpeg2Ps.PACKET_START_CODE + b'\xbc'

        temp = 0x60
        temp |= data.current_next_indicator << 7
        temp |= data.program_stream_map_version & 0xf1
        program_stream_map_buffer = temp.to_bytes(1)
        program_stream_map_buffer += b'\xff'

        program_stream_info_buffer = b''
        for descriptor in data.program_stream_info:
            descriptor_buffer = Mpeg2Ps.__serialize_descriptor(descriptor)
            if descriptor_buffer is None:
                continue
            program_stream_info_buffer += descriptor_buffer
        program_stream_map_buffer += len(
            program_stream_info_buffer).to_bytes(2, byteorder='big')
        program_stream_map_buffer += program_stream_info_buffer

        elementary_stream_map_buffer = b''
        for entry in data.elementary_stream_map:
            entry_buffer = entry.stream_type.to_bytes(1)
            entry_buffer += entry.elementary_stream_id.to_bytes(1)

            elementary_stream_info_buffer = b''
            for descriptor in entry.elementary_stream_info:
                descriptor_buffer = Mpeg2Ps.__serialize_descriptor(descriptor)
                if descriptor_buffer is None:
                    continue
                elementary_stream_info_buffer += descriptor_buffer
            entry_buffer += len(elementary_stream_info_buffer).to_bytes(2,
                                                                        byteorder='big')
            entry_buffer += elementary_stream_info_buffer

            elementary_stream_map_buffer += entry_buffer
        program_stream_map_buffer += len(
            elementary_stream_map_buffer).to_bytes(2, byteorder='big')
        program_stream_map_buffer += elementary_stream_map_buffer

        buffer += (len(program_stream_map_buffer) +
                   4).to_bytes(2, byteorder='big')
        buffer += program_stream_map_buffer

        crc32 = Mpeg2Ps.crc32(buffer)
        buffer += crc32.to_bytes(4, byteorder='big')
        # buffer += b'\x46\x17\x52\x32'

        return buffer
