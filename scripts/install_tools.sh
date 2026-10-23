#!/usr/bin/env bash
# AQAR OF AFRICA - install render tools on a GitHub runner, never blocked by a stuck package mirror.
# usage: bash scripts/install_tools.sh [extra apt packages...]   (env PIP_EXTRA: extra pip packages)
set +e
pip install --quiet --retries 3 --timeout 30 pillow==10.4.0 matplotlib==3.9.2 $PIP_EXTRA
timeout 300 bash -c "sudo apt-get -o Acquire::Retries=2 -o Acquire::http::Timeout=20 update -y >/dev/null \
  && sudo apt-get -o Acquire::Retries=2 -o Acquire::http::Timeout=20 install -y ffmpeg fonts-dejavu-core $* >/dev/null" \
  || echo "apt unavailable or too slow: using fallbacks"
if ! command -v ffmpeg >/dev/null || ! command -v ffprobe >/dev/null; then
  echo "static ffmpeg"
  curl -sSL --retry 4 --max-time 300 -o /tmp/ff.tar.xz \
    https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz
  sudo tar -xJf /tmp/ff.tar.xz -C /opt
  sudo ln -sf /opt/ffmpeg-master-latest-linux64-gpl/bin/ffmpeg /usr/local/bin/ffmpeg
  sudo ln -sf /opt/ffmpeg-master-latest-linux64-gpl/bin/ffprobe /usr/local/bin/ffprobe
fi
if [ ! -f /usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf ]; then
  echo "DejaVu fonts from matplotlib"
  src=$(python3 -c "import matplotlib, os; print(os.path.join(os.path.dirname(matplotlib.__file__), 'mpl-data/fonts/ttf'))")
  sudo mkdir -p /usr/share/fonts/truetype/dejavu
  sudo cp "$src"/DejaVuSans*.ttf /usr/share/fonts/truetype/dejavu/
  sudo fc-cache -f >/dev/null 2>&1
fi
ffmpeg -version | head -1 && command -v ffprobe >/dev/null && ls /usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf
