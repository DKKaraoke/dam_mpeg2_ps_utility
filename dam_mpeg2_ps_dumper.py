#!/usr/bin/env python
# coding: utf-8

import argparse
import bitstring
import io

from dam_mpeg2_ps_utility.customized_logger import getLogger
from dam_mpeg2_ps_utility.dam_mpeg2_ps import DamMpeg2Ps, DamMpeg2PsCodec
from dam_mpeg2_ps_utility.dam_mpeg2_ps_generator_data import GopIndexEntry, GopIndex
from dam_mpeg2_ps_utility.h264_annex_b import H264AnnexB
from dam_mpeg2_ps_utility.h264_annex_b_data import H264NalUnit
from dam_mpeg2_ps_utility.mpeg2_ps import Mpeg2Ps
from dam_mpeg2_ps_utility.mpeg2_ps_data import Mpeg2PsProgramEnd, Mpeg2PesPacketType1, Mpeg2PsPackHeader


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='DAM compatible MPEG2-PS Dumper')
    parser.add_argument(
        "input_path", help='Input H.264-ES file path')
    args = parser.parse_args()

    with open(args.input_path, 'rb') as input_file:
        input_stream = bitstring.BitStream(input_file.read())
        gop_index = DamMpeg2Ps.load_gop_index(input_stream)
        if gop_index is None:
            print('Failed to load GOP index.')
            return
        print(
            f'gop_index: sub_stream_id={gop_index.sub_stream_id}, version={gop_index.version}, stream_id={gop_index.stream_id}, page_number={gop_index.page_number}, page_count={gop_index.page_count}')
        if len(gop_index.gops) == 0:
            return
        pts_offset = gop_index.gops[0].pts
        for index, gop in enumerate(gop_index.gops):
            print(
                f'gop_index[{index}]: ps_pack_header_position={gop.ps_pack_header_position}, access_unit_size={gop.access_unit_size}, pts={gop.pts}, pts_msec={gop.pts / 90}, related_pts_msec={(gop.pts - pts_offset) / 90}')


if __name__ == "__main__":
    main()
