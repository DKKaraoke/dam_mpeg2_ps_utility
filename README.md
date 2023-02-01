# dam_mpeg2_ps_utility

## Summary

DAM Karaoke machines need a GOP index header in MPEG2-PS bitstreams. This software reads and writes DAM Karaoke machine compatible MPEG2-PS.

Also, DAM Karaoke machines need End of sequence (EOS) and End of stream (EOB) NAL units in H.264 bitstreams. Please use it for encoding: https://github.com/DKKaraoke/ffmpeg-x264-add-eos-eob-patched

## Usage

### Dump

```
$ python dump_dam_mpeg2_ps.py --help
usage: dump_dam_mpeg2_ps.py [-h] [--print-packets] input_path

DAM compatible MPEG2-PS Dumper

positional arguments:
  input_path       Input H.264-ES file path

options:
  -h, --help       show this help message and exit
  --print-packets  Print packets
```

## Create

```
$ python create_dam_mpeg2_ps.py --help
usage: create_dam_mpeg2_ps.py [-h] [--input_codec {avc,hevc}] [--frame_rate {24000/1001,24,30000/1001,30,60000/1001,60}] input_path output_path

DAM compatible MPEG2-PS Creator

positional arguments:
  input_path            Input H.264-ES file path
  output_path           DAM compatible MPEG2-PS output file path

options:
  -h, --help            show this help message and exit
  --input_codec {avc,hevc}
  --frame_rate {24000/1001,24,30000/1001,30,60000/1001,60}
```

## List of verified DAM Karaoke machine

- DAM-XG5000[G,R] (LIVE DAM [(GOLD EDITION|RED TUNE)])
- DAM-XG7000[Ⅱ] (LIVE DAM STADIUM [STAGE])
- DAM-XG8000[R] (LIVE DAM Ai[R])

## Authors

- soltia48 (ソルティアよんはち)

## License

[MIT](https://opensource.org/licenses/MIT)

Copyright (c) 2023 soltia48 (ソルティアよんはち)
