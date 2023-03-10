#!/usr/bin/env python
# coding: utf-8

import argparse
import bitstring
from decimal import Decimal
import io

from dam_mpeg2_ps_utility.customized_logger import getLogger
from dam_mpeg2_ps_utility.dam_mpeg2_ps import DamMpeg2Ps, DamMpeg2PsCodec
from dam_mpeg2_ps_utility.dam_mpeg2_ps_generator_data import GopIndexEntry, GopIndex
from dam_mpeg2_ps_utility.h264_annex_b import H264AnnexB
from dam_mpeg2_ps_utility.h264_annex_b_data import H264NalUnit
from dam_mpeg2_ps_utility.mpeg2_ps import Mpeg2Ps
from dam_mpeg2_ps_utility.mpeg2_ps_data import (
    Mpeg2PsProgramEnd,
    Mpeg2PesPacketType1,
    Mpeg2PsPackHeader,
)


class DamMpeg2PsGenerator:
    """DAM compatible MPEG2-PS Generator"""

    nal_units: list[H264NalUnit] = []

    __logger = getLogger("DamMpeg2PsGenerator")

    def __init__(self):
        """Constructor"""

    def load_h264_es(self, stream: io.BufferedReader):
        """Load H.264-ES

        Args:
            stream (io.BufferedReader): Readable stream of H.264-ES
        """

        self.nal_units.clear()

        nal_unit_index = H264AnnexB.index_nal_unit(stream)
        for nal_unit_position, nal_unit_size in nal_unit_index:
            stream.seek(nal_unit_position)
            nal_unit_buffer: bytes = stream.read(nal_unit_size)
            nal_unit = H264AnnexB.parse_nal_unit(nal_unit_buffer)
            if nal_unit is None:
                continue
            self.nal_units.append(nal_unit)

    def write_mpeg2_ps(
        self, stream: bitstring.BitStream, codec: DamMpeg2PsCodec, frame_rate: Decimal
    ):
        """Write MPEG2-PS

        Args:
            stream (bitstring.BitStream): Writable stream of MPEG2-PS
            codec (DamMpeg2PsCodec): Codec
            frame_rate (Decimal): Frame rate
        """

        temp_stream = bitstring.BitStream()

        # Write Container Header
        DamMpeg2Ps.write_container_header(temp_stream, codec)

        # List Sequence and Access Unit
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

            # Access Unit Delimiter
            if nal_unit.nal_unit_type == 0x09:
                if sps_detected:
                    if len(current_sequence) != 0:
                        sequences.append(current_sequence)
                        current_sequence = []
                    sps_detected = False
                if len(current_access_unit) != 0:
                    current_sequence.append(current_access_unit)
                    current_access_unit = []

            # Sequence Parameter Set
            if nal_unit.nal_unit_type == 0x07:
                sps_detected = True

            current_access_unit.append(nal_unit)

        gops: list[GopIndexEntry] = []

        picture_count = Decimal(0)
        for sequence in sequences:
            access_unit_position = len(temp_stream) / 8

            # Write PS Pack header
            presentation_time = picture_count / frame_rate
            SCR_base = int((Mpeg2Ps.SYSTEM_CLOCK_FREQUENCY * presentation_time) / 300)
            SCR_ext = int((Mpeg2Ps.SYSTEM_CLOCK_FREQUENCY * presentation_time) % 300)
            ps_pack_header = Mpeg2PsPackHeader(SCR_base, SCR_ext, 20000, 0)
            Mpeg2Ps.write_ps_pack_header(temp_stream, ps_pack_header)

            for access_unit in sequence:
                presentation_time = picture_count / frame_rate
                pts = int((Mpeg2Ps.SYSTEM_CLOCK_FREQUENCY * presentation_time) / 300)
                dts = None

                access_unit_buffer = b""
                for nal_unit in access_unit:
                    # Picture's NAL unit
                    if nal_unit.nal_unit_type == 0x01 or nal_unit.nal_unit_type == 0x05:
                        picture_count += 1
                    access_unit_buffer += H264AnnexB.serialize_nal_unit(nal_unit)

                # Fill and separate PES Packet
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
                    pes_packet_data_buffer = access_unit_buffer[
                        0:pes_packet_data_buffer_length_limit
                    ]
                    pes_packet = Mpeg2PesPacketType1(
                        0xE0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        PTS_DTS_flags,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        pts,
                        dts,
                        pes_packet_data_buffer,
                    )
                    Mpeg2Ps.write_pes_packet(temp_stream, pes_packet)
                    access_unit_buffer = access_unit_buffer[
                        pes_packet_data_buffer_length_limit:
                    ]
                    first_pes_packet_of_nal_unit = False

            # Add a GOP index entry
            access_unit_size = len(temp_stream) / 8 - access_unit_position
            gops.append(GopIndexEntry(access_unit_position, access_unit_size, SCR_base))
            DamMpeg2PsGenerator.__logger.debug(
                f"GOP index entry added. access_unit_position={access_unit_position}, access_unit_size={access_unit_size}, pts={SCR_base}, pts_msec={SCR_base / 90}"
            )

        # Write Program End
        Mpeg2Ps.write_ps_packet(temp_stream, Mpeg2PsProgramEnd())
        # Add GOP index entry of Program end
        access_unit_position = len(temp_stream) / 8
        presentation_time = picture_count / frame_rate
        SCR_base = int((Mpeg2Ps.SYSTEM_CLOCK_FREQUENCY * presentation_time) / 300)
        gops.append(GopIndexEntry(access_unit_position, 0, SCR_base))
        DamMpeg2PsGenerator.__logger.debug(
            f"GOP index entry (Program end) added. access_unit_position={access_unit_position}, access_unit_size=0, pts={SCR_base}, pts_msec={SCR_base / 90}"
        )

        # Write GOP index
        DamMpeg2Ps.write_gop_index(
            temp_stream, stream, GopIndex(0xFF, 0x01, 0xE0, 0x0, 0x0, gops)
        )


def main(argv=None):
    parser = argparse.ArgumentParser(description="DAM compatible MPEG2-PS Creator")
    parser.add_argument("input_path", help="Input H.264-ES file path")
    parser.add_argument("--input_codec", choices=["avc", "hevc"], default="avc")
    parser.add_argument(
        "--frame_rate",
        choices=["24000/1001", "24", "30000/1001", "30", "60000/1001", "60"],
        default="30000/1001",
    )
    parser.add_argument("output_path", help="DAM compatible MPEG2-PS output file path")
    args = parser.parse_args()

    codec = DamMpeg2PsCodec.UNDEFINED
    if args.input_codec == "avc":
        codec = DamMpeg2PsCodec.AVC_VIDEO
    elif args.input_codec == "hevc":
        codec = DamMpeg2PsCodec.HEVC_VIDEO

    frame_rate = Decimal(30000) / 1001
    if args.frame_rate == "24000/1001":
        frame_rate = Decimal(24000) / 1001
    elif args.frame_rate == "24":
        frame_rate = Decimal(30)
    elif args.frame_rate == "30000/1001":
        frame_rate = Decimal(30000) / 1001
    elif args.frame_rate == "30":
        frame_rate = Decimal(30)
    elif args.frame_rate == "60000/1001":
        frame_rate = Decimal(60000) / 1001
    elif args.frame_rate == "60":
        frame_rate = Decimal(60)

    generator = DamMpeg2PsGenerator()

    with open(args.input_path, "rb") as input_file, open(
        args.output_path, "wb"
    ) as output_file:
        generator.load_h264_es(input_file)
        temp_stream = bitstring.BitStream()
        generator.write_mpeg2_ps(temp_stream, codec, frame_rate)
        bs_buffer = temp_stream.tobytes()
        output_file.write(bs_buffer)


if __name__ == "__main__":
    main()
