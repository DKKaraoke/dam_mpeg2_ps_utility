#!/usr/bin/env python
# coding: utf-8

import argparse
import bitstring
from enum import Flag, auto
import io

from dam_mpeg2_ps_utility.customized_logger import getLogger
from dam_mpeg2_ps_utility.dam_mpeg2_ps_generator_data import GopIndexEntry, GopIndex
from dam_mpeg2_ps_utility.h264_annex_b import H264AnnexB
from dam_mpeg2_ps_utility.h264_annex_b_data import H264NalUnit
from dam_mpeg2_ps_utility.mpeg2_ps import Mpeg2Ps
from dam_mpeg2_ps_utility.mpeg2_ps_data import Mpeg2PsProgramEnd, Mpeg2PesPacketType1, Mpeg2PesPacketType2, Mpeg2PsPackHeader, Mpeg2PsSystemHeader, Mpeg2PsSystemHeaderPStdInfo, Mpeg2AacAudioDescriptor, Mpeg2AvcVideoDescriptor, Mpeg2HevcVideoDescriptor, Mpeg2Descriptor, Mpeg2PsElementaryStreamMapEntry, Mpeg2PsProgramStreamMap


class DamMpeg2PsCodec(Flag):
    UNDEFINED = auto()
    AVC_VIDEO = auto()
    AAC_AUDIO = auto()
    HEVC_VIDEO = auto()


class DamMpeg2PsUtility:
    """DAM compatible MPEG2-PS Utility
    """

    __GOP_INDEX_HEADER_SIZE = 6
    __GOP_INDEX_ENTRY_SIZE = 12

    __logger = getLogger('DamMpeg2PsUtility')

    nal_units: list[H264NalUnit] = []

    @staticmethod
    def __size_of_gop_index_pes_packet_bytes(index: GopIndex):
        # NAL unit prefix + NAL unit header + ...
        return 6 + DamMpeg2PsUtility.__GOP_INDEX_HEADER_SIZE + len(index.gops) * DamMpeg2PsUtility.__GOP_INDEX_ENTRY_SIZE

    @staticmethod
    def __read_gop_index(stream: bitstring.BitStream):
        gops: list[GopIndexEntry] = []

        sub_stream_id: int = stream.read('uint:8')
        version: int = stream.read('uint:8')
        stream_id: int = stream.read('uint:8')
        page_number: int = stream.read('uint:4')
        page_count: int = stream.read('uint:4')
        gop_count: int = stream.read('uintbe:16')
        for _ in range(gop_count):
            ps_pack_header_position: int = stream.read('uintbe:40')
            access_unit_size: int = stream.read('uintbe:24')
            pts: int = stream.read('uintbe:32')
            gops.append(GopIndexEntry(
                ps_pack_header_position, access_unit_size, pts))

        return GopIndex(sub_stream_id, version, stream_id, page_number, page_count, gops)

    @staticmethod
    def __serialize_gop_index(gop_index: GopIndex):
        stream = bitstring.BitStream()
        stream += bitstring.pack('uint:8, uint:8, uint:8, uint:4, uint:4, uintbe:16',
                                 gop_index.sub_stream_id, gop_index.version, gop_index.stream_id,
                                 gop_index.page_number, gop_index.page_count, len(gop_index.gops))
        for gop in gop_index.gops:
            stream += bitstring.pack('uintbe:40, uintbe:24, uintbe:32',
                                     gop.ps_pack_header_position, gop.access_unit_size, gop.pts)
        return stream.tobytes()

    @staticmethod
    def load_gop_index(stream: bitstring.BitStream):
        packet_id = Mpeg2Ps.seek_packet(stream, 0xbf)
        if packet_id is None:
            DamMpeg2PsUtility.__logger.warning('GOP index not found.')
            return
        pes_packet = Mpeg2Ps.read_pes_packet(stream)
        if pes_packet is None:
            DamMpeg2PsUtility.__logger.warning('Invalid pes_packet.')
            return
        gop_index_stream = bitstring.BitStream(pes_packet.PES_packet_data)
        return DamMpeg2PsUtility.__read_gop_index(gop_index_stream)

    @staticmethod
    def __write_gop_index(input_stream: bitstring.BitStream, output_stream: bitstring.BitStream, gop_index: GopIndex):
        start_position = input_stream.bytepos

        # Seek and read first MPEG2-PS Program Stream Map
        packet_id = Mpeg2Ps.seek_packet(input_stream, 0xbc)
        if packet_id is None:
            DamMpeg2PsUtility.__logger.warning(
                'First MPEG2-PS Program Stream Map not found.')
            return
        program_stream_map = Mpeg2Ps.read_program_stream_map(input_stream)
        if program_stream_map is None:
            DamMpeg2PsUtility.__logger.warning('Inavlid program_stream_map.')
            return
        # Copy container header
        copy_size = input_stream.bytepos - start_position
        input_stream.bytepos = start_position
        output_stream.append(input_stream.read(8 * copy_size))

        pes_packet_size = DamMpeg2PsUtility.__size_of_gop_index_pes_packet_bytes(
            gop_index)
        # Adjust MPEG2-PS Pack Header position
        for i in range(len(gop_index.gops)):
            gop = gop_index.gops[i]
            gop_index.gops[i] = GopIndexEntry(
                start_position + pes_packet_size + gop.ps_pack_header_position, gop.access_unit_size, gop.pts)
        gop_index_buffer = DamMpeg2PsUtility.__serialize_gop_index(gop_index)
        # Allow 0x000001 (Violation of standards), Do not emulation prevention
        Mpeg2Ps.write_pes_packet(
            output_stream, Mpeg2PesPacketType2(0xbf, gop_index_buffer))

        # Copy stream
        output_stream.append(input_stream.read('bytes'))

    @staticmethod
    def __write_container_header(stream: bitstring.BitStream, codec: DamMpeg2PsCodec):
        Mpeg2Ps.write_ps_pack_header(stream, Mpeg2PsPackHeader(0, 0, 20000, 0))
        Mpeg2Ps.write_ps_system_header(stream, Mpeg2PsSystemHeader(
            50000, 0, 0, 0, 0, 1, 1, 1, [Mpeg2PsSystemHeaderPStdInfo(0xe0, 1, 3051)]))

        stream_type = 0x00
        elementary_stream_info: list[Mpeg2Descriptor] = []
        if codec == DamMpeg2PsCodec.AVC_VIDEO:
            stream_type = 0x1b
            elementary_stream_info = [Mpeg2AvcVideoDescriptor(
                77, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 40, 0x00, 0x00, 0x01)]
        elif codec == DamMpeg2PsCodec.AAC_AUDIO:
            stream_type = 0x0f
            elementary_stream_info = [
                Mpeg2AacAudioDescriptor(0x00, 0x00, 0x00)]
        elif codec == DamMpeg2PsCodec.HEVC_VIDEO:
            stream_type = 0x24
            elementary_stream_info = [Mpeg2HevcVideoDescriptor(
                0x00, 0x00, 0x00, 0x00000000, 0x00, 0x00, 0x00, 0x00, 0x000000000000, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00)]
        program_stream_map = Mpeg2PsProgramStreamMap(
            0x01, 0x01, [], [Mpeg2PsElementaryStreamMapEntry(stream_type, 0xe0, elementary_stream_info)])
        Mpeg2Ps.write_program_stream_map(stream, program_stream_map)

    def __init__(self):
        """Constructor
        """

    def load_h264_es(self, stream: io.BufferedReader):
        self.nal_units.clear()

        nal_unit_index = H264AnnexB.index_nal_unit(stream)
        for nal_unit_position, nal_unit_size in nal_unit_index:
            stream.seek(nal_unit_position)
            nal_unit_buffer: bytes = stream.read(nal_unit_size)
            nal_unit = H264AnnexB.parse_nal_unit(nal_unit_buffer)
            if nal_unit is None:
                continue
            self.nal_units.append(nal_unit)

    def write_generic_mpeg_ps(self, stream: bitstring.BitStream, codec: DamMpeg2PsCodec, frame_rate: float):
        temp_stream = bitstring.BitStream()

        DamMpeg2PsUtility.__write_container_header(temp_stream, codec)

        nal_units = self.nal_units.copy()
        sequences: list[list[list[H264NalUnit]]] = []
        current_sequence: list[list[H264NalUnit]] = []
        current_access_unit: list[H264NalUnit] = []
        sps_detected = False
        while True:
            nal_unit: H264NalUnit
            try:
                nal_unit = nal_units.pop(0)
            except IndexError:
                break

            if nal_unit.nal_unit_type == 0x09:
                if sps_detected:
                    if len(current_sequence) != 0:
                        sequences.append(current_sequence)
                        current_sequence = []
                    sps_detected = False
                if len(current_access_unit) != 0:
                    current_sequence.append(current_access_unit)
                    current_access_unit = []

            if nal_unit.nal_unit_type == 0x07:
                sps_detected = True

            current_access_unit.append(nal_unit)

        gops: list[GopIndexEntry] = []

        picture_count = 0
        for sequence in sequences:
            access_unit_position = temp_stream.bytepos

            presentation_time = picture_count / frame_rate
            SCR_base = int(
                (Mpeg2Ps.SYSTEM_CLOCK_FREQUENCY * presentation_time) / 300)
            SCR_ext = int(
                (Mpeg2Ps.SYSTEM_CLOCK_FREQUENCY * presentation_time) % 300)
            ps_pack_header = Mpeg2PsPackHeader(SCR_base, SCR_ext, 20000, 0)
            Mpeg2Ps.write_ps_pack_header(temp_stream, ps_pack_header)

            for access_unit in sequence:
                presentation_time = picture_count / frame_rate
                pts = int((Mpeg2Ps.SYSTEM_CLOCK_FREQUENCY *
                          presentation_time) / 300)
                dts = None

                access_unit_buffer = b''
                for nal_unit in access_unit:
                    if nal_unit.nal_unit_type == 0x01 or nal_unit.nal_unit_type == 0x05:
                        picture_count += 1
                    access_unit_buffer += H264AnnexB.serialize_nal_unit(
                        nal_unit)

                pes_packet_data_buffer_length_limit: int
                if pts is None:
                    PTS_DTS_flags = 0
                    pes_packet_data_buffer_length_limit = 65535 - 3
                else:
                    if dts is None:
                        PTS_DTS_flags = 2
                        pes_packet_data_buffer_length_limit = 65535 - 8
                    else:
                        PTS_DTS_flags = 3
                        pes_packet_data_buffer_length_limit = 65535 - 13
                first_pes_packet_of_nal_unit = True
                while len(access_unit_buffer) != 0:
                    if not first_pes_packet_of_nal_unit:
                        PTS_DTS_flags = 0
                        pes_packet_data_buffer_length_limit = 65535 - 3
                    pes_packet_data_buffer = access_unit_buffer[0:
                                                                pes_packet_data_buffer_length_limit]
                    pes_packet = Mpeg2PesPacketType1(
                        0xe0, 0, 0, 0, 0, 0, PTS_DTS_flags, 0, 0, 0, 0, 0, 0, pts, dts, pes_packet_data_buffer)
                    Mpeg2Ps.write_pes_packet(temp_stream, pes_packet)
                    access_unit_buffer = access_unit_buffer[pes_packet_data_buffer_length_limit:]
                    first_pes_packet_of_nal_unit = False

            access_unit_size = temp_stream.bytepos = access_unit_position

            gops.append(GopIndexEntry(
                access_unit_position, access_unit_size, SCR_base))

        Mpeg2Ps.write_ps_packet(temp_stream, Mpeg2PsProgramEnd())

        DamMpeg2PsUtility.__write_gop_index(
            temp_stream, stream, GopIndex(0xff, 0x01, 0xe0, 0x0, 0x0, gops))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='DAM compatible MPEG2-PS Generator')
    parser.add_argument(
        "input_path", help='Input H.264-ES file path')
    parser.add_argument(
        '--input_codec', choices=['avc', 'hevc'], default='avc')
    parser.add_argument('--frame_rate', type=float,
                        default=29.97)
    parser.add_argument(
        'output_path', help='DAM compatible MPEG2-PS output file path')
    args = parser.parse_args()

    codec = DamMpeg2PsCodec.UNDEFINED
    if args.input_codec == 'avc':
        codec = DamMpeg2PsCodec.AVC_VIDEO
    elif args.input_codec == 'hevc':
        codec = DamMpeg2PsCodec.HEVC_VIDEO

    generator = DamMpeg2PsUtility()

    with open(args.input_path, 'rb') as input_file, open(args.output_path, 'wb') as output_file:
        generator.load_h264_es(input_file)
        bs = bitstring.BitStream()
        generator.write_generic_mpeg_ps(bs, codec, args.frame_rate)
        bs_buffer = bs.tobytes()
        output_file.write(bs_buffer)


if __name__ == "__main__":
    main()
