#!/usr/bin/env python
# coding: utf-8

import argparse
from dam_mpeg2_ps_utility_data import GopIndexEntry, GopIndex
from enum import Enum, Flag, auto
import io
from customized_logger import getLogger
from mpeg2_ps import Mpeg2Ps
from mpeg2_ps_data import Mpeg2PesPacket, Mpeg2PsPackHeader, Mpeg2PsSystemHeader, Mpeg2PsSystemHeaderPStdInfo, Mpeg2AacAudioDescriptor, Mpeg2AvcVideoDescriptor, Mpeg2HevcVideoDescriptor, Mpeg2Descriptor, Mpeg2PsElementaryStreamMapEntry, Mpeg2PsProgramStreamMap
import os
import tempfile


class DamMpeg2PsCompatibility(Flag):
    CONTAINER_PS_PACK_HEADER = auto()
    CONTAINER_PS_SYSTEM_HEADER = auto()
    CONTAINER_PS_PROGRAM_STREAM_MAP = auto()
    CONTAINER_GOP_INDEX = auto()


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

    @staticmethod
    def __size_of_gop_index_pes_packet_bytes(index: GopIndex):
        # NAL unit prefix + NAL unit header + ...
        return 6 + DamMpeg2PsUtility.__GOP_INDEX_HEADER_SIZE + len(index.gops) * DamMpeg2PsUtility.__GOP_INDEX_ENTRY_SIZE

    @staticmethod
    def __read_gop_index(stream: io.BufferedReader):
        gops: list[GopIndexEntry] = []

        header_buffer = stream.read(6)
        if len(header_buffer) != 6:
            DamMpeg2PsUtility.__logger.warning('Invalid header_buffer length')
            return

        sub_stream_id = header_buffer[0]
        version = header_buffer[1]
        stream_id = header_buffer[2]
        page_info = header_buffer[3]
        page_number = page_info >> 4
        page_count = page_info & 0x0f
        gop_count = int.from_bytes(header_buffer[4:6], byteorder='big')
        for _ in range(gop_count):
            entry_buffer = stream.read(12)
            if len(entry_buffer) != 12:
                DamMpeg2PsUtility.__logger.warning(
                    'Invalid entry_buffer length')
                return
            ps_pack_header_position = int.from_bytes(
                entry_buffer[0:5], byteorder='big')
            access_unit_size = int.from_bytes(
                entry_buffer[5:8], byteorder='big')
            pts = int.from_bytes(entry_buffer[8:12], byteorder='big')
            gops.append(GopIndexEntry(
                ps_pack_header_position, access_unit_size, pts))

        return GopIndex(sub_stream_id, version, stream_id, page_number, page_count, gops)

    @staticmethod
    def __serialize_gop_index(gop_index: GopIndex):
        stream = io.BytesIO()
        stream.write(gop_index.sub_stream_id.to_bytes(length=1))
        stream.write(gop_index.version.to_bytes(length=1))
        stream.write(gop_index.stream_id.to_bytes(length=1))
        page_info = (gop_index.page_number &
                     0x04) << 4 | gop_index.page_count & 0x04
        stream.write(page_info.to_bytes(length=1))
        stream.write(len(gop_index.gops).to_bytes(length=2, byteorder='big'))
        for gop in gop_index.gops:
            stream.write(gop.ps_pack_header_position.to_bytes(
                length=5, byteorder='big'))
            stream.write(gop.access_unit_size.to_bytes(
                length=3, byteorder='big'))
            stream.write(gop.pts.to_bytes(length=4, byteorder='big'))
        return stream.getvalue()

    @staticmethod
    def load_gop_index(stream: io.BufferedReader):
        packet_id = Mpeg2Ps.seek_packet(stream, 0xbf)
        if packet_id is None:
            DamMpeg2PsUtility.__logger.warning('GOP index not found')
            return
        pes_packet = Mpeg2Ps.read_pes_packet(stream)
        if pes_packet is None:
            DamMpeg2PsUtility.__logger.warning('Invalid pes_packet')
            return
        gop_index_stream = io.BytesIO(pes_packet.data)
        return DamMpeg2PsUtility.__read_gop_index(gop_index_stream)

    @staticmethod
    def check_compatibility(stream: io.BufferedReader):
        compatibility = DamMpeg2PsCompatibility(0)
        start_position = stream.tell()

        packet_id = Mpeg2Ps.seek_packet(stream, 0xba)
        if packet_id is None:
            DamMpeg2PsUtility.__logger.warning(
                'MPEG2-PS Pack Header not found')
        else:
            ps_pack_header = Mpeg2Ps.read_ps_pack_header(stream)
            if ps_pack_header is None:
                DamMpeg2PsUtility.__logger.warning('Invalid ps_pack_header')
            else:
                compatibility |= DamMpeg2PsCompatibility.CONTAINER_PS_PACK_HEADER
        stream.seek(start_position)

        packet_id = Mpeg2Ps.seek_packet(stream, 0xbb)
        if packet_id is None:
            DamMpeg2PsUtility.__logger.warning(
                'MPEG2-PS System Header not found')
        else:
            ps_system_header = Mpeg2Ps.read_ps_system_header(stream)
            if ps_system_header is None:
                DamMpeg2PsUtility.__logger.warning('Invalid ps_system_header')
            else:
                compatibility |= DamMpeg2PsCompatibility.CONTAINER_PS_SYSTEM_HEADER
        stream.seek(start_position)

        packet_id = Mpeg2Ps.seek_packet(stream, 0xbc)
        if packet_id is None:
            DamMpeg2PsUtility.__logger.warning(
                'MPEG2-PS Program Stream Map not found')
        else:
            program_stream_map = Mpeg2Ps.read_program_stream_map(stream)
            if program_stream_map is None:
                DamMpeg2PsUtility.__logger.warning(
                    'Invalid program_stream_map')
            else:
                compatibility |= DamMpeg2PsCompatibility.CONTAINER_PS_PROGRAM_STREAM_MAP
        stream.seek(start_position)

        packet_id = Mpeg2Ps.seek_packet(stream, 0xbf)
        if packet_id is None:
            DamMpeg2PsUtility.__logger.warning('GOP index not found')
        else:
            gop_index = DamMpeg2PsUtility.__read_gop_index(stream)
            if gop_index is None:
                DamMpeg2PsUtility.__logger.warning('Invalid gop_index')
            else:
                compatibility |= DamMpeg2PsCompatibility.CONTAINER_GOP_INDEX
        stream.seek(start_position)

        return compatibility

    @staticmethod
    def index_gop(stream: io.BufferedReader, stream_id: int):
        gops: list[GopIndexEntry] = []

        first_packet_position = -1
        while True:
            packet_id = Mpeg2Ps.seek_packet(stream)
            if packet_id is None:
                # End of stream
                break

            if first_packet_position == -1:
                first_packet_position = stream.tell()

            # Seek MPEG2-PS Pack Header (Start of sequence)
            if packet_id != 0xba:
                stream.seek(4, os.SEEK_CUR)
                continue
            ps_pack_header_position = stream.tell() - first_packet_position
            ps_pack_header = Mpeg2Ps.read_ps_pack_header(stream)
            if ps_pack_header is None:
                DamMpeg2PsUtility.__logger.warning('Invalid ps_pack_header')
                continue
            packet_id = Mpeg2Ps.read_packet_id(stream)
            if packet_id == 0xbb:
                # Read MPEG2-PS System Header
                ps_system_header = Mpeg2Ps.read_ps_system_header(stream)
                if ps_system_header is None:
                    continue
            # Read Video PES Packet
            packet_id = Mpeg2Ps.read_packet_id(stream)
            pes_packet: Mpeg2PesPacket | None = None
            if packet_id == stream_id:
                pes_packet = Mpeg2Ps.read_pes_packet(stream)
                if pes_packet is None:
                    DamMpeg2PsUtility.__logger.warning('Invalid pes_packet')
                    continue
                if pes_packet.pts is None:
                    continue
            else:
                stream.seek(4, os.SEEK_CUR)
                continue
            while True:
                packet_id = Mpeg2Ps.seek_packet(stream, stream_id)
                if packet_id is None:
                    break
                next_pes_packet_position = stream.tell()
                next_pes_packet = Mpeg2Ps.read_pes_packet(stream)
                # Seek start of Access Unit
                if next_pes_packet is None:
                    DamMpeg2PsUtility.__logger.warning(
                        'Invalid next_pes_packet')
                    break
                if next_pes_packet.pts is not None:
                    stream.seek(next_pes_packet_position)
                    break

            current_position = stream.tell() - first_packet_position
            access_unit_size = current_position - ps_pack_header_position
            gops.append(GopIndexEntry(
                ps_pack_header_position, access_unit_size, pes_packet.pts))

            # Seek End of sequence
            Mpeg2Ps.seek_packet(stream, 0x0a)

        return GopIndex(0xff, 0x01, stream_id, 0x0, 0x0, gops)

    @staticmethod
    def __write_container_ps_pack_header(stream: io.BufferedWriter, header: Mpeg2PsPackHeader):
        # ps_pack_header = Mpeg2PsPackHeader(0, 0, 20000, 0)
        header = Mpeg2PsPackHeader(0, 0, header.program_mux_rate, 0)
        header_buffer = Mpeg2Ps.serialize_ps_pack_header(header)
        stream.write(header_buffer)

    @staticmethod
    def __write_container_ps_system_header(stream: io.BufferedWriter, header: Mpeg2PsSystemHeader, old_stream_id: int, new_stream_id: int):
        if old_stream_id != new_stream_id:
            for i in range(len(header.P_STD_info)):
                P_STD_info_entry = header.P_STD_info[i]
                if P_STD_info_entry.stream_id == old_stream_id:
                    header.P_STD_info[i] = Mpeg2PsSystemHeaderPStdInfo(
                        new_stream_id, P_STD_info_entry.P_STD_buffer_bound_scale, P_STD_info_entry.P_STD_buffer_size_bound)
        header = Mpeg2PsSystemHeader(
            header.rate_bound, header.audio_bound, 0, 0, 0, 1, 1, 1, header.P_STD_info)
        header_buffer = Mpeg2Ps.serialize_ps_system_header(header)
        stream.write(header_buffer)

    @staticmethod
    def __write_program_stream_map(stream: io.BufferedWriter, stream_id: int, codec: DamMpeg2PsCodec):
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
            0x01, 0x01, [], [Mpeg2PsElementaryStreamMapEntry(stream_type, stream_id, elementary_stream_info)])
        program_stream_map_buffer = Mpeg2Ps.serialize_program_stream_map(
            program_stream_map)
        stream.write(program_stream_map_buffer)

    @staticmethod
    def __manipulate_stream(input_stream: io.BufferedReader, output_stream: io.BufferedWriter, old_stream_id: int, new_stream_id: int, codec: DamMpeg2PsCodec):
        # Seek first MPEG2-PS PackHeader
        packet_id = Mpeg2Ps.seek_packet(input_stream, 0xba)
        if packet_id is None:
            DamMpeg2PsUtility.__logger.warning(
                'First MPEG2-PS Pack Header not found.')
            return
        ps_pack_header = Mpeg2Ps.read_ps_pack_header(input_stream)
        if ps_pack_header is None:
            DamMpeg2PsUtility.__logger.warning('Inavlid ps_pack_header.')
            return
        DamMpeg2PsUtility.__write_container_ps_pack_header(
            output_stream, ps_pack_header)

        # Seek first MPEG2-PS System Header
        packet_id = Mpeg2Ps.seek_packet(input_stream, 0xbb)
        if packet_id is None:
            DamMpeg2PsUtility.__logger.warning(
                'First MPEG2-PS System Header not found.')
            return
        ps_system_header = Mpeg2Ps.read_ps_system_header(input_stream)
        if ps_system_header is None:
            DamMpeg2PsUtility.__logger.warning('Inavlid ps_system_header.')
            return
        DamMpeg2PsUtility.__write_container_ps_system_header(
            output_stream, ps_system_header, old_stream_id, new_stream_id)

        DamMpeg2PsUtility.__write_program_stream_map(
            output_stream, new_stream_id, codec)

        # Write first stream header
        ps_pack_header_buffer = Mpeg2Ps.serialize_ps_pack_header(
            ps_pack_header)
        output_stream.write(ps_pack_header_buffer)

        current_position = input_stream.tell()
        while True:
            packet_id = Mpeg2Ps.seek_packet(input_stream)
            if packet_id is None:
                break
            packet_position = input_stream.tell()
            copy_size = packet_position - current_position
            input_stream.seek(current_position)
            output_stream.write(input_stream.read(copy_size))

            if packet_id == 0xbb:
                # Remove MPEG2-PS System Header
                # Read and do nothing
                ps_system_header = Mpeg2Ps.read_ps_system_header(input_stream)
                if ps_system_header is None:
                    DamMpeg2PsUtility.__logger.warning(
                        'Invalid ps_system_header')
                    input_stream.seek(4, os.SEEK_CUR)
                    continue
            elif old_stream_id != new_stream_id and packet_id == old_stream_id:
                # Edit packet stream_id
                output_stream.write(Mpeg2Ps.PACKET_START_CODE)
                output_stream.write(new_stream_id.to_bytes(1))
                input_stream.seek(4, os.SEEK_CUR)

            current_position = input_stream.tell()
            if current_position == packet_position:
                input_stream.seek(4, os.SEEK_CUR)

    @staticmethod
    def __write_gop_index(input_stream: io.BufferedReader, output_stream: io.BufferedWriter, stream_id: int):
        start_position = input_stream.tell()
        gop_index = DamMpeg2PsUtility.index_gop(input_stream, stream_id)
        input_stream.seek(start_position)

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
        copy_size = input_stream.tell() - start_position
        input_stream.seek(start_position)
        output_stream.write(input_stream.read(copy_size))

        pes_packet_size = DamMpeg2PsUtility.__size_of_gop_index_pes_packet_bytes(
            gop_index)
        # Adjust MPEG2-PS Pack Header position
        for i in range(len(gop_index.gops)):
            gop = gop_index.gops[i]
            gop_index.gops[i] = GopIndexEntry(
                start_position + pes_packet_size + gop.ps_pack_header_position, gop.access_unit_size, gop.pts)
        gop_index_buffer = DamMpeg2PsUtility.__serialize_gop_index(gop_index)
        # Allow 0x000001 (Violation of standards), Do not emulation prevention
        pes_packet_buffer = Mpeg2Ps.serialize_pes_packet(
            0xbf, gop_index_buffer)
        output_stream.write(pes_packet_buffer)

        # Copy stream
        output_stream.write(input_stream.read())

    @staticmethod
    def compatibilize(input_stream: io.BufferedReader, output_stream: io.BufferedWriter, stream_id: int, codec: DamMpeg2PsCodec):
        new_stream_id = 0x00
        if codec == DamMpeg2PsCodec.AVC_VIDEO or codec == DamMpeg2PsCodec.HEVC_VIDEO:
            new_stream_id = 0xe0
        elif codec == DamMpeg2PsCodec.AAC_AUDIO:
            new_stream_id = 0xc0

        with tempfile.TemporaryFile() as temp_stream:
            DamMpeg2PsUtility.__manipulate_stream(
                input_stream, temp_stream, stream_id, new_stream_id, codec)
            temp_stream.seek(0)
            DamMpeg2PsUtility.__write_gop_index(
                temp_stream, output_stream, new_stream_id)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='DAM compatible MPEG2-PS Utility.')
    parser.add_argument("input_path",
                        help='Input file path')
    parser.add_argument('--stream_id', type=int, default=0xe0)
    parser.add_argument(
        '--input_codec', choices=['aac', 'avc', 'hevc'], default='avc')
    parser.add_argument('--check', action='store_true',
                        help='Check MPEG-2 PS DAM compatibility')
    parser.add_argument('--dump', action='store_true',
                        help='Print DAM compatible MPEG-2 PS information')
    parser.add_argument('--analyze', action='store_true',
                        help='Analyze and print MPEG2-PS information')
    parser.add_argument(
        '--output_path', help='DAM compatibilized MPEG2-PS output file path')
    args = parser.parse_args()

    with open(args.input_path, 'rb') as input_stream:
        if args.check:
            compatibility = DamMpeg2PsUtility.check_compatibility(input_stream)
            if ~compatibility == DamMpeg2PsCompatibility(0):
                print(
                    f'This MPEG2-PS is DAM compatible. compatibility={compatibility}')
            elif DamMpeg2PsCompatibility.CONTAINER_PS_PACK_HEADER not in compatibility or DamMpeg2PsCompatibility.CONTAINER_PS_SYSTEM_HEADER not in compatibility:
                print(
                    f'This MPEG2-PS is not DAM compatible. (Not convertable) compatibility={compatibility}')
            else:
                print(
                    f'This MPEG2-PS is not DAM compatible. (Convertable) compatibility={compatibility}')
            return

        if args.dump:
            gop_index = DamMpeg2PsUtility.load_gop_index(input_stream)
            print(
                f'gop_index: sub_stream_id={gop_index.sub_stream_id}, version={gop_index.version}, stream_id={gop_index.stream_id}, page_number={gop_index.page_number}, page_count={gop_index.page_count}')
            for index, gop in enumerate(gop_index.gops):
                print(
                    f'gop_index[{index}]: ps_pack_header_position={gop.ps_pack_header_position}, access_unit_size={gop.access_unit_size}, pts={gop.pts}, pts_msec={gop.pts / 90}')
            return

        if args.analyze:
            gop_index = DamMpeg2PsUtility.index_gop(
                input_stream, args.stream_id)
            print(
                f'gop_index: sub_stream_id={gop_index.sub_stream_id}, version={gop_index.version}, stream_id={gop_index.stream_id}, page_number={gop_index.page_number}, page_count={gop_index.page_count}')
            for index, gop in enumerate(gop_index.gops):
                print(
                    f'gop_index[{index}]: ps_pack_header_position={gop.ps_pack_header_position}, access_unit_size={gop.access_unit_size}, pts={gop.pts}, pts_msec={gop.pts / 90}')
            return

        if args.output_path is not None:
            codec = DamMpeg2PsCodec.UNDEFINED
            if args.input_codec == 'avc':
                codec = DamMpeg2PsCodec.AVC_VIDEO
            elif args.input_codec == 'aac':
                codec = DamMpeg2PsCodec.AAC_AUDIO
            elif args.input_codec == 'hevc':
                codec = DamMpeg2PsCodec.HEVC_VIDEO

            with open(args.output_path, 'wb') as output_stream:
                DamMpeg2PsUtility.compatibilize(
                    input_stream, output_stream, args.stream_id, codec)
            return


if __name__ == "__main__":
    main()
