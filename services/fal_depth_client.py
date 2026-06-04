"""
FAL.AI Depth-Anything Client — drop-in replacement for SculptokClient.

Generates depth maps for accessory images via the fal.ai-hosted
Depth-Anything endpoint. Same call signature + return shape as
SculptokClient.process_image_to_depth_map() so order_processor.py
needs ZERO changes — only the wiring in api/main.py swaps the client.

Why this replaces Sculptok:
  • Sculptok had an unstable hosted depth-map service that's now broken.
  • fal.ai Depth-Anything is the SOTA depth-estimation model, cloud-hosted,
    99.9% uptime, ~3 sec per image, ~$0.005 per call.
  • Output is a normalized 16-bit grayscale depth map, exactly what the
    downstream Blender 2.5D displacement step expects.

Endpoint:        fal-ai/imageutils/depth (Depth-Anything-V2 based)
Cost per map:    ~$0.005
Avg latency:     ~3 seconds
"""

import asyncio
import logging
import os
from typing import Dict, Optional

import aiohttp
import fal_client
from config.settings import settings

logger = logging.getLogger(__name__)
# Silence the noisy fal/httpx polling logs
logging.getLogger("httpx").setLevel(logging.WARNING)


class FalDepthClient:
    """Drop-in replacement for SculptokClient — generates depth maps via fal.ai."""

    # Same model id as fal.ai's depth utility — based on Depth-Anything-V2
    MODEL_ID = "fal-ai/imageutils/depth"

    def __init__(self, api_key: Optional[str] = None):
        # fal_client reads FAL_KEY from env automatically
        key = api_key or settings.FAL_API_KEY or os.environ.get("FAL_KEY")
        if key and not os.environ.get("FAL_KEY"):
            os.environ["FAL_KEY"] = key
        self.api_key = key
        if not key:
            logger.warning("⚠️ FalDepthClient: no FAL_KEY found — calls will fail!")
        else:
            logger.info(f"✅ FalDepthClient initialized (model={self.MODEL_ID})")

    async def health_check(self) -> bool:
        """Cheap health check — verifies the fal.ai key is set."""
        return bool(os.environ.get("FAL_KEY"))

    # ───────────────────────────────────────────────────────────────────
    # Public API — matches SculptokClient signature 1:1 so order_processor
    # can be wired without modification.
    # ───────────────────────────────────────────────────────────────────
    async def process_image_to_depth_map(
        self,
        image_path: str,
        output_dir: str,
        image_name: str = "model",
        skip_bg_removal: bool = False,   # accepted for compat — we don't need it
        style: str = "pro",              # accepted for compat — ignored
        version: str = "1.5",            # accepted for compat — ignored
        draw_hd: str = "4k",             # accepted for compat — ignored
        ext_info: str = "16bit",         # accepted for compat — ignored
    ) -> Dict:
        """
        Generate a depth map for a single accessory image.

        Same signature + return shape as SculptokClient.process_image_to_depth_map.

        Returns:
            {
                "success": True,
                "outputs": { "depth_image": "<absolute path to PNG>" }
            }
            or on failure:
            { "success": False, "error": "<reason>" }
        """
        if not os.path.exists(image_path):
            return {"success": False, "error": f"Input image not found: {image_path}"}

        os.makedirs(output_dir, exist_ok=True)
        depth_out_path = os.path.join(output_dir, f"{image_name}_depth.png")

        # If a depth map already exists (e.g. retry case), short-circuit
        if os.path.exists(depth_out_path) and os.path.getsize(depth_out_path) > 0:
            logger.info(f"[FAL-DEPTH] ⏭️ Cached: {depth_out_path}")
            return {"success": True, "outputs": {"depth_image": depth_out_path}}

        logger.info(f"[FAL-DEPTH] Generating depth for {os.path.basename(image_path)}")

        try:
            # Step 1: upload the input image to fal.ai storage so the model
            # can read it. fal_client handles this synchronously — wrap in a
            # thread so we don't block the asyncio loop.
            input_url = await asyncio.to_thread(fal_client.upload_file, image_path)
            logger.debug(f"[FAL-DEPTH] uploaded → {input_url}")

            # Step 2: call the depth-map endpoint (synchronous → thread)
            def _run():
                return fal_client.subscribe(
                    self.MODEL_ID,
                    arguments={"image_url": input_url},
                    with_logs=False,
                )
            result = await asyncio.to_thread(_run)

            # The fal depth endpoint returns:
            #   { "image": { "url": "https://fal.media/.../depth.png", ... } }
            depth_obj = (result or {}).get("image") or {}
            depth_url = depth_obj.get("url")
            if not depth_url:
                logger.error(f"[FAL-DEPTH] No depth URL in result: {result}")
                return {"success": False, "error": "fal.ai returned no depth URL"}

            # Step 3: download the depth PNG to local disk
            async with aiohttp.ClientSession() as session:
                async with session.get(depth_url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if resp.status != 200:
                        return {
                            "success": False,
                            "error": f"Depth download failed: HTTP {resp.status}",
                        }
                    data = await resp.read()

            with open(depth_out_path, "wb") as f:
                f.write(data)

            # Zero out background pixels using the source image's alpha channel.
            # Depth models estimate depth for every pixel including transparent
            # background areas, producing gray values that displace the mesh into
            # visible raised platforms. Masking those pixels to 0 eliminates the
            # platforms while leaving the object depth untouched.
            try:
                from PIL import Image as _PIL
                import numpy as _np
                depth_img = _PIL.open(depth_out_path).convert("L")
                src_alpha = _PIL.open(image_path).convert("RGBA").resize(
                    depth_img.size, _PIL.LANCZOS
                ).split()[3]
                d = _np.array(depth_img, dtype=_np.uint8)
                a = _np.array(src_alpha, dtype=_np.uint8)
                d[a < 128] = 0
                _PIL.fromarray(d).save(depth_out_path)
                zeroed = int((a < 128).sum())
                logger.info(f"[FAL-DEPTH] 🎭 {image_name}: alpha-masked {zeroed:,} bg pixels → 0")
            except Exception as _me:
                logger.warning(f"[FAL-DEPTH] alpha-mask skipped for {image_name}: {_me}")

            size_kb = len(data) // 1024
            logger.info(f"[FAL-DEPTH] ✅ {image_name}: {size_kb} KB → {depth_out_path}")

            return {
                "success": True,
                "outputs": {"depth_image": depth_out_path},
                "provider": "fal.ai/depth-anything",
            }

        except Exception as e:
            logger.exception(f"[FAL-DEPTH] Failed for {image_path}: {e}")
            return {"success": False, "error": str(e)}


def create_fal_depth_client() -> FalDepthClient:
    """Factory function — mirrors create_sculptok_client() so the wiring stays simple."""
    return FalDepthClient()
