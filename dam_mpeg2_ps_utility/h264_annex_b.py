from collections import namedtuple
from dam_mpeg2_ps_utility.h264_annex_b_data import H264NalUnit
import io
from logging import getLogger, Formatter, StreamHandler, DEBUG
import os


class H264AnnexB:
    """H.264 Annex B
    """

    __NAL_UNIT_START_CODE = b'\x00\x00\x01'
    __NAL_UNIT_START_CODE_LONG = b'\x00\x00\x00\x01'
    __EBSP_ESCAPE_START_CODE = b'\x00\x00\x03'

    __logger = getLogger('H264AnnexB')

    @staticmethod
    def seek_nal_unit(stream: io.BufferedReader, nal_unit_type: int | None = None):
        zero_count = 0
        while True:
            buffer = stream.read(1)
            # End of stream
            if len(buffer) == 0:
                break
            current_byte = int.from_bytes(buffer, byteorder='big')
            if 2 <= zero_count and current_byte == 0x01:
                buffer = stream.read(1)
                # End of stream
                if len(buffer) == 0:
                    break
                current_byte = int.from_bytes(buffer, byteorder='big')
                current_nal_unit_type = current_byte & 0x1f
                zero_count = min(zero_count, 3)
                if nal_unit_type is None:
                    stream.seek(-(zero_count + 2), os.SEEK_CUR)
                    return current_nal_unit_type
                else:
                    if current_nal_unit_type == nal_unit_type:
                        stream.seek(-(zero_count + 2), os.SEEK_CUR)
                        return current_nal_unit_type
            # Count zero
            if current_byte == 0x00:
                zero_count += 1
            else:
                zero_count = 0

    @staticmethod
    def __find_ebsp_escaped(buffer: bytes, start=0):
        position = buffer.find(
            H264AnnexB.__EBSP_ESCAPE_START_CODE, start)
        if position == -1 or len(buffer) - 1 < position + 3:
            return -1
        if 0x03 < buffer[position + 3]:
            return H264AnnexB.__find_ebsp_escaped(buffer, position + 4)
        return position

    @staticmethod
    def __list_ebsp_escaped_position(buffer: bytes):
        position_list: list[int] = []
        position = 0
        while True:
            position = H264AnnexB.__find_ebsp_escaped(buffer, position)
            if position == -1:
                break
            position_list.append(position)
            position += 4
        return position_list

    @staticmethod
    def __ebsp_unescape(buffer: bytes):
        return b'\x00\x00' + buffer[3:4]

    @staticmethod
    def __ebsp_to_rbsp(ebsp: bytes):
        rbsp = b''
        escaped_positions = H264AnnexB.__list_ebsp_escaped_position(ebsp)
        current_position = 0
        for escaped_position in escaped_positions:
            rbsp += ebsp[current_position:escaped_position]
            rbsp += H264AnnexB.__ebsp_unescape(
                ebsp[escaped_position:escaped_position+4])
            current_position = escaped_position + 4
        rbsp += ebsp[current_position:]
        return rbsp

    @staticmethod
    def __find_ebsp_escape_needed(buffer: bytes, start=0):
        position = buffer.find(b'\x00\x00', start)
        buffer_length = len(buffer)
        if position == -1 or buffer_length - 1 < position + 2:
            return -1
        tail_value = buffer[position + 2]
        if 0x03 < tail_value:
            return H264AnnexB.__find_ebsp_escape_needed(buffer, position + 3)
        # Do not escape tail 0x000003
        if buffer_length - 1 == position + 2 and tail_value == 0x03:
            return -1
        return position

    @staticmethod
    def __list_ebsp_escape_needed_position(buffer: bytes):
        position_list: list[int] = []
        position = 0
        while True:
            position = H264AnnexB.__find_ebsp_escape_needed(buffer, position)
            if position == -1:
                break
            position_list.append(position)
            position += 3
        return position_list

    @staticmethod
    def __ebsp_escape(buffer: bytes):
        return b'\x00\x00\x03' + buffer[2:3]

    @staticmethod
    def __rbsp_to_ebsp(rbsp: bytes):
        ebsp = b''
        escape_needed_positions = H264AnnexB.__list_ebsp_escape_needed_position(
            rbsp)
        current_position = 0
        for escape_needed_position in escape_needed_positions:
            ebsp += rbsp[current_position:escape_needed_position]
            ebsp += H264AnnexB.__ebsp_escape(
                rbsp[escape_needed_position:escape_needed_position+3])
            current_position = escape_needed_position + 3
        ebsp += rbsp[current_position:]
        return ebsp

    @staticmethod
    def index_nal_unit(stream: io.BufferedReader):
        index: list[tuple[int, int]] = []

        last_position = -1
        while True:
            nal_unit_type = H264AnnexB.seek_nal_unit(stream)
            if nal_unit_type is None:
                break
            position = stream.tell()
            if last_position != -1:
                index.append((last_position, position - last_position))
            last_position = position
            stream.seek(4, os.SEEK_CUR)

        if last_position != -1:
            position = stream.tell()
            index.append((last_position, position - last_position))

        return index

    @staticmethod
    def parse_nal_unit(buffer: bytes):
        if len(buffer) < 4:
            H264AnnexB.__logger.warning('Invalid buffer length.')
            return

        stream = io.BytesIO(buffer)

        # Prefix
        prefix_zero_count = 0
        for _ in range(4):
            if int.from_bytes(stream.read(1), byteorder='big') == 0x01:
                break
            prefix_zero_count += 1
        is_start_code_long = False if prefix_zero_count <= 2 else True
        # Read header
        header_buffer = stream.read(1)
        if len(header_buffer) != 1:
            H264AnnexB.__logger.warning('Invalid header_buffer length.')
            return
        header = int.from_bytes(header_buffer, byteorder='big')
        forbidden_zero_bit = header >> 7
        if forbidden_zero_bit != 0x00:
            H264AnnexB.__logger.warning('Invalid forbidden_zero_bit.')
            return
        nal_ref_idc = (header >> 5) & 0x03
        nal_unit_type = header & 0x1f
        # Read EBSP
        ebsp = stream.read()
        rbsp = H264AnnexB.__ebsp_to_rbsp(ebsp)

        return H264NalUnit(is_start_code_long, nal_ref_idc, nal_unit_type, rbsp)

    @staticmethod
    def serialize_nal_unit(nal_unit: H264NalUnit):
        prefix = H264AnnexB.__NAL_UNIT_START_CODE_LONG if nal_unit.is_start_code_long else H264AnnexB.__NAL_UNIT_START_CODE

        header = (nal_unit.nal_ref_idc & 0x03) << 5
        header |= nal_unit.nal_unit_type & 0x1f

        ebsp = H264AnnexB.__rbsp_to_ebsp(nal_unit.rbsp)

        return prefix + header.to_bytes(length=1, byteorder='big') + ebsp
