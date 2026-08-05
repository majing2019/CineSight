#!/usr/bin/env bash
# 一键部署 Mage-VL 本地视觉 skill（macOS / Apple Silicon）。
# 幂等：venv 已就绪且有标记文件时会跳过重复安装。
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$SKILL_DIR/venv"
MODEL_ID="microsoft/Mage-VL"
MARKER="$VENV_DIR/.mage_ready"

echo "==> Mage-VL 部署 (skill: $SKILL_DIR)"

# 优先用 uv（可自动安装独立的 Python 3.12，不依赖 Homebrew/系统 Python 版本）
if command -v uv >/dev/null 2>&1; then
  UV="$(command -v uv)"
elif [ -x "$HOME/.local/bin/uv" ]; then
  UV="$HOME/.local/bin/uv"
else
  UV=""
fi
if [ -n "$UV" ]; then
  echo "==> 使用 uv 管理 Python 环境: $UV"
else
  echo "  [!] 未找到 uv。系统 Python 需 >=3.10（torch/transformers 要求），"
  echo "     请先安装 uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
  command -v python3 >/dev/null || { echo "错误：未找到 python3"; exit 1; }
fi

if ! command -v ffmpeg >/dev/null; then
  echo "  [i] 未检测到系统 ffmpeg。视频抽帧走 opencv 内置 FFmpeg，可正常工作；"
  echo "     如需官方 codec 视频后端（仅 Linux），再装 ffmpeg。"
fi

# 1) Python 虚拟环境 + 依赖
if [ -d "$VENV_DIR" ] && [ -f "$MARKER" ]; then
  echo "==> venv 已部署（如需重装，删除 $MARKER 后重跑）"
else
  echo "==> 创建 venv: $VENV_DIR"
  if [ -n "$UV" ]; then
    "$UV" venv --python 3.12 "$VENV_DIR"
  else
    "$(command -v python3)" -m venv "$VENV_DIR"
  fi
  echo "==> 安装 torch/torchvision（Apple Silicon 版本）..."
  if [ -n "$UV" ]; then
    "$UV" pip install --python "$VENV_DIR/bin/python" torch torchvision
  else
    "$VENV_DIR/bin/pip" install --upgrade pip setuptools wheel
    "$VENV_DIR/bin/pip" install torch torchvision
  fi
  echo "==> 安装其余依赖（不含 CUDA-only 的 flash-attn / mamba-ssm）..."
  if [ -n "$UV" ]; then
    "$UV" pip install --python "$VENV_DIR/bin/python" -r "$SKILL_DIR/scripts/requirements-mac.txt"
  else
    "$VENV_DIR/bin/pip" install -r "$SKILL_DIR/scripts/requirements-mac.txt"
  fi
  touch "$MARKER"
fi

# 2) 预下载模型权重（~10.8GB，ModelScope 优先，HF 兜底）
MODEL_ID="microsoft/Mage-VL"
MODEL_DIR="$HOME/.cache/mage-vl/microsoft/Mage-VL"
if [ -d "$MODEL_DIR" ] && [ -f "$MODEL_DIR/model-00001-of-00002.safetensors" ]; then
  echo "==> 模型权重已存在: $MODEL_DIR"
else
  echo "==> 下载模型权重 $MODEL_ID -> $MODEL_DIR（约 10.8GB）..."
  if [ "${USE_HF:-0}" = "1" ]; then
    echo "  (USE_HF=1：从 HuggingFace 下载，可能需能访问 huggingface.co 的网络)"
    "$VENV_DIR/bin/python" -c "
from huggingface_hub import snapshot_download
snapshot_download('$MODEL_ID', local_dir='$MODEL_DIR')
" && echo "==> HF 下载完成"
  else
    echo "  (默认从 ModelScope 下载，国内网络可达；如需 HF 请设 USE_HF=1)"
    "$VENV_DIR/bin/modelscope" download --model "$MODEL_ID" --local_dir "$MODEL_DIR" \
      || { echo "ModelScope 下载失败，尝试 HF 通道..."; "$VENV_DIR/bin/python" -c "
from huggingface_hub import snapshot_download
snapshot_download('$MODEL_ID', local_dir='$MODEL_DIR')
"; }
  fi
fi

# 3) 冒烟测试：确认依赖可导入、模型目录完整
echo "==> 冒烟测试..."
"$VENV_DIR/bin/python" -c "
from pathlib import Path
from transformers import AutoModelForCausalLM, AutoProcessor
print('OK: transformers 可加载 Mage-VL 自定义代码')
d = Path('$MODEL_DIR')
if d.is_dir() and (d / 'model-00001-of-00002.safetensors').exists():
    print(f'OK: 模型权重就绪 ({d})')
else:
    print('WARN: 未在本地找到完整权重，analyze.py 将回退到 HF id microsoft/Mage-VL')
" || { echo "导入失败，请把报错反馈给维护者。"; exit 1; }

echo
echo "==> 部署完成。用法示例："
echo "  $VENV_DIR/bin/python $SKILL_DIR/scripts/analyze.py --input /path/to/image.jpg"
echo "  $VENV_DIR/bin/python $SKILL_DIR/scripts/analyze.py --input /path/to/video.mp4 --task video"
echo
