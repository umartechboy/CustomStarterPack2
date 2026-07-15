#!/bin/bash
# Pipeline auto-start: SSH key + tool symlinks + cron + FastAPI
LOG=/workspace/SimpleMe/start_pipeline.log
exec >> "$LOG" 2>&1

# 1. SSH key
mkdir -p /root/.ssh
chmod 700 /root/.ssh
KEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIP0mEi5hkvkO++/HcGrO5LTg2l19UNIwIuSAab5ez+bp claude-fix"
if ! grep -qF "$KEY" /root/.ssh/authorized_keys 2>/dev/null; then
    echo "[$(date)] Adding SSH key..."
    echo "$KEY" >> /root/.ssh/authorized_keys
    chmod 600 /root/.ssh/authorized_keys
fi

# 2. Install Blender/Node into persistent /workspace/tools if missing
#    (only happens on a genuinely fresh /workspace volume; normally these
#    are already cached from a previous run and this is a no-op)
BLENDER_VERSION=5.1.1
if [ ! -x /workspace/tools/blender5/blender ]; then
    echo "[$(date)] Installing Blender $BLENDER_VERSION..."
    mkdir -p /workspace/tools/blender5
    TMP_TGZ=$(mktemp --suffix=.tar.xz)
    if curl -fsSL -o "$TMP_TGZ" "https://download.blender.org/release/Blender${BLENDER_VERSION%.*}/blender-${BLENDER_VERSION}-linux-x64.tar.xz"; then
        tar -xJf "$TMP_TGZ" -C /workspace/tools/blender5 --strip-components=1
    else
        echo "[$(date)] Blender download failed"
    fi
    rm -f "$TMP_TGZ"
fi

NODE_VERSION=20.18.0
if [ ! -x /workspace/tools/node/bin/node ]; then
    echo "[$(date)] Installing Node v$NODE_VERSION..."
    mkdir -p /workspace/tools/node
    TMP_TGZ=$(mktemp --suffix=.tar.xz)
    if curl -fsSL -o "$TMP_TGZ" "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz"; then
        tar -xJf "$TMP_TGZ" -C /workspace/tools/node --strip-components=1
    else
        echo "[$(date)] Node download failed"
    fi
    rm -f "$TMP_TGZ"
fi

# 3. Symlink persistent tools
[ -L /usr/local/bin/blender ] || ln -sf /workspace/tools/blender5/blender /usr/local/bin/blender
[ -L /usr/local/bin/blender-5 ] || ln -sf /workspace/tools/blender5/blender /usr/local/bin/blender-5
[ -L /usr/local/bin/dotnet ] || ln -sf /workspace/tools/dotnet-sdk/dotnet /usr/local/bin/dotnet
[ -L /usr/local/bin/node ] || ln -sf /workspace/tools/node/bin/node /usr/local/bin/node
[ -L /usr/local/bin/npm ] || ln -sf /workspace/tools/node/bin/npm /usr/local/bin/npm
[ -L /usr/local/bin/npx ] || ln -sf /workspace/tools/node/bin/npx /usr/local/bin/npx
# Standard .NET install location (PrintMaker apphost looks here):
[ -L /usr/share/dotnet ] || ln -sf /workspace/tools/dotnet-sdk /usr/share/dotnet
# Ensure .NET 8 runtime is available alongside .NET 9 (PrintMaker targets net8.0)
NET8_SRC=/workspace/tools/dotnet/shared/Microsoft.NETCore.App/8.0.26
NET8_DST=/workspace/tools/dotnet-sdk/shared/Microsoft.NETCore.App/8.0.26
[ -d "$NET8_DST" ] || cp -r "$NET8_SRC" "$NET8_DST"

# 4. Install runtime libs if missing
if ! ldconfig -p | grep -q libXrender; then
    apt-get install -y libxrender1 libsm6 libxi6 libxxf86vm1 libxfixes3 libxrandr2 libxkbcommon0 libwayland-client0 libwayland-egl1 libdbus-1-3 libgl1 libegl1 libxext6 libx11-xcb1 cron 2>&1 | tail -3
fi

# 4b. Ensure Pillow is installed in Blender's Python
BLENDER_PY=/workspace/tools/blender5/5.1/python/bin/python3.13
if ! $BLENDER_PY -c "import PIL" 2>/dev/null; then
    echo "[$(date)] Installing Pillow into Blender Python..."
    $BLENDER_PY -m pip install Pillow --quiet
fi

# 4c. Ensure standalone Python 3.13 + bpy venv exists (needed for PrintMaker jig generation)
if [ ! -x /root/bpy_env_313/bin/python ]; then
    echo "[$(date)] Setting up bpy_env_313..."
    if ! command -v python3.13 > /dev/null; then
        echo "[$(date)] Installing Python 3.13..."
        apt-get install -y python3.13 python3.13-venv 2>&1 | tail -3
    fi
    if command -v python3.13 > /dev/null; then
        python3.13 -m venv /root/bpy_env_313
        /root/bpy_env_313/bin/python -m pip install --upgrade pip --quiet
        /root/bpy_env_313/bin/python -m pip install bpy --quiet
    else
        echo "[$(date)] python3.13 unavailable, skipping bpy_env_313 setup"
    fi
fi

# 5. Cron
if ! pgrep cron > /dev/null; then
    [ -x /etc/init.d/cron ] && /etc/init.d/cron start 2>/dev/null || /usr/sbin/cron 2>/dev/null || true
fi

# 6. FastAPI
if ! pgrep -f "uvicorn api.main" > /dev/null; then
    echo "[$(date)] Starting FastAPI..."
    cd /workspace/SimpleMe
    DOTNET_ROOT=/workspace/tools/dotnet-sdk nohup ./venv/bin/python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --log-level info >> /workspace/SimpleMe/server.log 2>&1 &
    disown
fi

# 7. Vite admin
if ! pgrep -f "vite" > /dev/null; then
    cd /workspace/SimpleMe/admin
    if [ ! -d node_modules ]; then
        echo "[$(date)] Installing admin frontend deps..."
        npm install
    fi
    nohup npm run dev -- --host 0.0.0.0 --port 5173 >> /workspace/SimpleMe/admin/vite.log 2>&1 &
    disown
fi
