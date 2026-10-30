#!/usr/bin/env python3
"""
预下载 faster-whisper 模型到 models/ 目录（走 ModelScope，国内友好，断点续传）

用法:
  python download_model.py                      # 默认 large-v3-turbo
  python download_model.py small                # 下载指定大小模型

候选模型 id：mobiuslabsgmbh/faster-whisper-<size>（官方镜像，只有部分尺寸）
→ pengzhendong/faster-whisper-<size>（全尺寸），自动回退。
产物目录 models/faster-whisper-<size>/，正是 step2 resolve_model_id 识别的布局。
"""

import sys

from common import ensure_model

MODEL_SIZE = sys.argv[1] if len(sys.argv) > 1 else "large-v3-turbo"

local_dir = ensure_model(MODEL_SIZE)
print(f"[就绪] 模型 {MODEL_SIZE}: {local_dir}")
