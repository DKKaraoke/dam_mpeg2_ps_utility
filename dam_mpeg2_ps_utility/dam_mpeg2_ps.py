import bitstring
from enum import Flag, auto

from dam_mpeg2_ps_utility.customized_logger import getLogger
from dam_mpeg2_ps_utility.dam_mpeg2_ps_generator_data import GopIndexEntry, GopIndex
from dam_mpeg2_ps_utility.mpeg2_ps import Mpeg2Ps
from dam_mpeg2_ps_utility.mpeg2_ps_data import Mpeg2PesPacketType2, Mpeg2PsPackHeader, Mpeg2PsSystemHeader, Mpeg2PsSystemHeaderPStdInfo, Mpeg2AacAudioDescriptor, Mpeg2AvcVideoDescriptor, Mpeg2HevcVideoDescriptor, Mpeg2Descriptor, Mpeg2PsElementaryStreamMapEntry, Mpeg2PsProgramStreamMap


class DamMpeg2PsCodec(Flag):
    UNDEFINED = auto()
    AVC_VIDEO = auto()
    AAC_AUDIO = auto()
    HEVC_VIDEO = auto()


class DamMpeg2Ps:
    """DAM compatible MPEG2-PS
    """

    __GOP_INDEX_HEADER_SIZE = 6
    __GOP_INDEX_ENTRY_SIZE = 12

    __logger = getLogger('DamMpeg2Ps')

    @staticmethod
    def __size_of_gop_index_pes_packet_bytes(index: GopIndex):
        # NAL unit prefix + NAL unit header + ...
        return 6 + DamMpeg2Ps.__GOP_INDEX_HEADER_SIZE + len(index.gops) * DamMpeg2Ps.__GOP_INDEX_ENTRY_SIZE

    @staticmethod
    def __serialize_gop_index(gop_index: GopIndex):
        stream = bitstring.BitStream()
        stream += bitstring.pack('uint:8, uint:8, uint:8, uint:4, uint:4, uintbe:16',
                                 gop_index.sub_stream_id, gop_index.version, gop_index.stream_id,
                                 gop_index.page_number, gop_index.page_count, len(gop_index.gops) - 1)
        for gop in gop_index.gops:
            stream += bitstring.pack('uintbe:40, uintbe:24, uintbe:32',
                                     gop.ps_pack_header_position, gop.access_unit_size, gop.pts)
        return stream.tobytes()

    @staticmethod
    def __read_gop_index(stream: bitstring.BitStream):
        gops: list[GopIndexEntry] = []

        sub_stream_id: int = stream.read('uint:8')
        version: int = stream.read('uint:8')
        stream_id: int = stream.read('uint:8')
        page_number: int = stream.read('uint:4')
        page_count: int = stream.read('uint:4')
        gop_count: int = stream.read('uintbe:16') + 1
        for _ in range(gop_count):
            ps_pack_header_position: int = stream.read('uintbe:40')
            access_unit_size: int = stream.read('uintbe:24')
            pts: int = stream.read('uintbe:32')
            gops.append(GopIndexEntry(
                ps_pack_header_position, access_unit_size, pts))

        return GopIndex(sub_stream_id, version, stream_id, page_number, page_count, gops)

    @staticmethod
    def load_gop_index(stream: bitstring.BitStream):
        packet_id = Mpeg2Ps.seek_packet(stream, 0xbf)
        if packet_id is None:
            DamMpeg2Ps.__logger.warning('GOP index not found.')
            return
        pes_packet = Mpeg2Ps.read_pes_packet(stream)
        if pes_packet is None:
            DamMpeg2Ps.__logger.warning('Invalid pes_packet.')
            return
        gop_index_stream = bitstring.BitStream(pes_packet.PES_packet_data)
        return DamMpeg2Ps.__read_gop_index(gop_index_stream)

    @staticmethod
    def write_gop_index(input_stream: bitstring.BitStream, output_stream: bitstring.BitStream, gop_index: GopIndex):
        start_position = input_stream.bytepos

        # Seek and read first MPEG2-PS Program Stream Map
        packet_id = Mpeg2Ps.seek_packet(input_stream, 0xbc)
        if packet_id is None:
            DamMpeg2Ps.__logger.warning(
                'First MPEG2-PS Program Stream Map not found.')
            return
        program_stream_map = Mpeg2Ps.read_program_stream_map(input_stream)
        if program_stream_map is None:
            DamMpeg2Ps.__logger.warning('Inavlid program_stream_map.')
            return
        # Copy container header
        copy_size = input_stream.bytepos - start_position
        input_stream.bytepos = start_position
        output_stream.append(input_stream.read(8 * copy_size))

        pes_packet_size = DamMpeg2Ps.__size_of_gop_index_pes_packet_bytes(
            gop_index)
        # Adjust MPEG2-PS Pack Header position
        for i in range(len(gop_index.gops)):
            gop = gop_index.gops[i]
            gop_index.gops[i] = GopIndexEntry(
                start_position + pes_packet_size + gop.ps_pack_header_position, gop.access_unit_size, gop.pts)
        gop_index_buffer = DamMpeg2Ps.__serialize_gop_index(gop_index)
        # Allow 0x000001 (Violation of standards), Do not emulation prevention
        Mpeg2Ps.write_pes_packet(
            output_stream, Mpeg2PesPacketType2(0xbf, gop_index_buffer))

        # Copy stream
        output_stream.append(input_stream.read('bytes'))

    @staticmethod
    def write_container_header(stream: bitstring.BitStream, codec: DamMpeg2PsCodec):
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
