"""
Async Order Processor

Processes starter pack orders asynchronously in a queue.
Orders are processed one at a time in the order they were received.
"""

import asyncio
import logging
import os
import uuid
import traceback
from typing import Dict, Optional, List
from datetime import datetime
from collections import deque

from config.settings import settings
from services.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class OrderProcessor:
    """Async order processor with queue"""

    def __init__(self):
        self.queue: deque = deque()
        self.processing = False
        self.current_job: Optional[str] = None
        self._task: Optional[asyncio.Task] = None
        self._ai_generator = None
        self._sculptok_client = None

    def set_services(self, ai_generator, sculptok_client, fal_client=None):
        """Set the AI generator and Sculptok client services"""
        self._ai_generator = ai_generator
        self._sculptok_client = sculptok_client
        self._fal_client = fal_client
        logger.info(f"✅ OrderProcessor services configured (FAL.AI: {'✅' if fal_client else '❌ not set'})")

    async def add_order(self, order_data: Dict) -> str:
        """
        Add an order to the processing queue.
        Returns the job_id immediately.
        """
        job_id = order_data.get("job_id", str(uuid.uuid4())[:8])
        order_data["job_id"] = job_id
        order_data["queued_at"] = datetime.now().isoformat()

        self.queue.append(order_data)
        logger.info(f"📥 Order {job_id} added to queue (position: {len(self.queue)})")

        # Start processing if not already running
        if not self.processing:
            self._task = asyncio.create_task(self._process_queue())

        return job_id

    def get_queue_status(self) -> Dict:
        """Get current queue status"""
        return {
            "queue_length": len(self.queue),
            "processing": self.processing,
            "current_job": self.current_job,
            "queued_jobs": [o.get("job_id") for o in self.queue]
        }

    async def retry_order(self, job_id: str, from_step: int, order_data: Dict = None) -> str:
        """
        Retry an order from a specific step.

        Steps:
        1 - Generate images (GPT-image-1.5)
        2 - Background image generation (optional)
        3 - Background removal (skipped - GPT provides transparent PNGs)
        4 - Depth map generation
        5 - Blender processing
        6 - Sticker generation

        Args:
            job_id: The job ID to retry
            from_step: Step number to resume from (1-7)
            order_data: Optional order data (if not provided, loads from DB)

        Returns:
            job_id
        """
        if order_data is None:
            # Load order data from database
            supabase = get_supabase_client()
            if supabase.is_connected():
                order_record = await supabase.get_order(job_id)
                if not order_record:
                    raise Exception(f"Order {job_id} not found")
                order_data = order_record
            else:
                raise Exception("Database not connected")

        order_data["job_id"] = job_id
        order_data["from_step"] = from_step
        order_data["is_retry"] = True
        order_data["queued_at"] = datetime.now().isoformat()

        # Set job_dir from existing path or construct it
        if not order_data.get("job_dir"):
            order_data["job_dir"] = f"./storage/test_starter_pack/{job_id}"

        self.queue.append(order_data)
        logger.info(f"🔄 Order {job_id} added to queue for retry from step {from_step}")

        # Start processing if not already running
        if not self.processing:
            self._task = asyncio.create_task(self._process_queue())

        return job_id

    async def _process_queue(self):
        """Process orders from the queue one by one"""
        self.processing = True
        logger.info("🔄 Order processor started")

        while self.queue:
            order_data = self.queue.popleft()
            job_id = order_data.get("job_id")
            self.current_job = job_id

            logger.info(f"▶️ Processing order {job_id} ({len(self.queue)} remaining in queue)")

            try:
                # Run in thread pool to avoid blocking the event loop
                await asyncio.to_thread(self._process_order_sync, order_data)
            except Exception as e:
                logger.error(f"❌ Order {job_id} failed with exception: {e}")
                logger.error(traceback.format_exc())
                # Update database with error
                supabase = get_supabase_client()
                if supabase.is_connected():
                    try:
                        await supabase.update_order_status(job_id, "failed", str(e))
                    except:
                        pass

        self.processing = False
        self.current_job = None
        logger.info("✅ Order processor idle - queue empty")

    def _process_order_sync(self, order_data: Dict):
        """Synchronous wrapper to run in thread pool"""
        import asyncio
        # Create new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._process_order(order_data))
        finally:
            loop.close()

    def _save_step_state(self, job_dir: str, step: int, state: Dict):
        """Save intermediate state after a step completes"""
        import json
        state_file = os.path.join(job_dir, "pipeline_state.json")

        # Load existing state or create new
        if os.path.exists(state_file):
            with open(state_file, 'r') as f:
                full_state = json.load(f)
        else:
            full_state = {"steps_completed": [], "data": {}}

        full_state["steps_completed"].append(step)
        full_state["last_step"] = step
        full_state["data"][f"step_{step}"] = state
        full_state["updated_at"] = datetime.now().isoformat()

        with open(state_file, 'w') as f:
            json.dump(full_state, f, indent=2)

        logger.info(f"💾 Saved state for step {step}")

    def _load_step_state(self, job_dir: str) -> Dict:
        """Load saved pipeline state"""
        import json
        state_file = os.path.join(job_dir, "pipeline_state.json")

        if os.path.exists(state_file):
            with open(state_file, 'r') as f:
                return json.load(f)
        return {"steps_completed": [], "data": {}}

    def _find_generated_images(self, job_dir: str) -> tuple:
        """Find existing generated images in job directory.

        Returns images with both original_path (high quality GPT) and nobg_path (for depth maps).
        Blender should use original_path for textures.
        """
        figure_img = None
        accessory_imgs = []

        # Look for ORIGINAL generated images (high quality, transparent background)
        generated_dir = f"./storage/generated/{os.path.basename(job_dir)}"
        if os.path.exists(generated_dir):
            for f in sorted(os.listdir(generated_dir)):
                if f.endswith('.png') and '_texture' not in f:
                    file_path = os.path.join(generated_dir, f)
                    if 'base_character' in f:
                        figure_img = {
                            "file_path": file_path,
                            "original_path": file_path,  # Original GPT image for Blender
                            "type": "base_character"
                        }
                    elif 'accessory' in f:
                        accessory_imgs.append({
                            "file_path": file_path,
                            "original_path": file_path,  # Original GPT image for Blender
                            "type": "accessory"
                        })

        # Check for nobg versions and ADD them as nobg_path (don't replace original!)
        nobg_figure = os.path.join(job_dir, "figure_nobg.png")
        if figure_img and os.path.exists(nobg_figure):
            figure_img["nobg_path"] = nobg_figure

        for i, acc in enumerate(accessory_imgs):
            nobg_path = os.path.join(job_dir, f"accessory_{i+1}_nobg.png")
            if os.path.exists(nobg_path):
                acc["nobg_path"] = nobg_path

        return figure_img, accessory_imgs

    def _find_depth_maps(self, job_dir: str) -> Dict:
        """Find existing depth maps in job directory (accessories only — figure is full 3D via fal.ai)"""
        depth_maps = {}

        for i in range(1, 4):
            acc_depth = os.path.join(job_dir, f"accessory_{i}_depth.png")
            if os.path.exists(acc_depth):
                depth_maps[f"accessory_{i}"] = acc_depth

        return depth_maps

    async def _process_order(self, order_data: Dict):
        """Process a single order through the full pipeline"""
        import aiofiles
        import subprocess
        import threading
        import shutil

        job_id = order_data["job_id"]
        job_dir = order_data["job_dir"]
        supabase = get_supabase_client()

        # Check if this is a retry with a specific starting step
        from_step = order_data.get("from_step", 1)
        is_retry = order_data.get("is_retry", False)

        if is_retry:
            logger.info(f"🔄 [ORDER {job_id}] Retrying pipeline from step {from_step}")
        else:
            logger.info(f"🚀 [ORDER {job_id}] Starting pipeline")

        # Update status to processing
        if supabase.is_connected():
            await supabase.update_order_status(job_id, "processing")

        errors = []
        outputs = {}

        # Initialize variables that might be loaded from previous state
        figure_img = None
        accessory_imgs = []
        background_image_path = None
        depth_maps = {}

        try:
            # Get common data
            user_image_path = order_data.get("user_image_path")
            accessories = order_data.get("accessories", [])
            background_type = order_data.get("background_type", "transparent")
            background_color = order_data.get("background_color", "white")

            # ============================================================
            # STEP 1: Generate images with GPT-image-1.5
            # ============================================================
            if from_step <= 1:
                logger.info(f"[ORDER {job_id}] Step 1: GPT Image Generation")

                generated_images = await self._ai_generator.generate_action_figures(
                    job_id=job_id,
                    user_image_path=user_image_path,
                    accessories=accessories
                )

                if not generated_images:
                    raise Exception("GPT-image-1.5 failed to generate images")

                logger.info(f"[ORDER {job_id}] Generated {len(generated_images)} images")

                # Separate figure and accessories
                for img in generated_images:
                    if "base_character" in img.get("type", ""):
                        figure_img = img
                    else:
                        accessory_imgs.append(img)

                if not figure_img:
                    raise Exception("No base character image generated")

                # Save state after step 1
                self._save_step_state(job_dir, 1, {
                    "figure_img": figure_img,
                    "accessory_imgs": accessory_imgs
                })
            else:
                # Load existing images from previous run
                logger.info(f"[ORDER {job_id}] ⏭️ Skipping Step 1 - Loading existing images")
                figure_img, accessory_imgs = self._find_generated_images(job_dir)
                if not figure_img:
                    raise Exception("No existing figure image found for retry")
                logger.info(f"[ORDER {job_id}] Found figure + {len(accessory_imgs)} accessories")

            # ============================================================
            # STEP 2: Handle background image (if needed)
            # ============================================================
            if from_step <= 2:
                if background_type == "image":
                    logger.info(f"[ORDER {job_id}] Step 2: Background Generation")

                    bg_description = order_data.get("background_description", "")
                    bg_input_path = order_data.get("background_input_path")

                    if bg_input_path and os.path.exists(bg_input_path):
                        # Enhance user's background image
                        from openai import OpenAI
                        client = OpenAI(api_key=settings.OPENAI_API_KEY)

                        enhance_prompt = """Enhance this image to be a high-resolution, detailed background.
Keep the exact same composition and elements, but add more details and improve quality.
Output should be suitable as a background for an action figure card."""

                        with open(bg_input_path, "rb") as f:
                            response = client.images.edit(
                                model="gpt-image-1.5",
                                image=f,
                                prompt=enhance_prompt,
                                size="1024x1024"
                            )

                        if response.data:
                            import base64
                            bg_b64 = response.data[0].b64_json
                            background_image_path = os.path.join(job_dir, "background_enhanced.png")
                            async with aiofiles.open(background_image_path, "wb") as f:
                                await f.write(base64.b64decode(bg_b64))
                            logger.info(f"[ORDER {job_id}] Enhanced background saved")

                    elif bg_description:
                        # Generate new background from description
                        from openai import OpenAI
                        client = OpenAI(api_key=settings.OPENAI_API_KEY)

                        bg_prompt = f"""Create a detailed, high-quality background image: {bg_description}
The image should be suitable as a background for an action figure collector card.
Make it visually interesting but not too busy - it should complement, not overwhelm, the foreground."""

                        response = client.images.generate(
                            model="gpt-image-1.5",
                            prompt=bg_prompt,
                            size="1024x1024",
                            output_format="png",
                            n=1
                        )

                        if response.data:
                            import base64
                            bg_b64 = response.data[0].b64_json
                            background_image_path = os.path.join(job_dir, "background_generated.png")
                            async with aiofiles.open(background_image_path, "wb") as f:
                                await f.write(base64.b64decode(bg_b64))
                            logger.info(f"[ORDER {job_id}] Generated background saved")
            else:
                # Check for existing background images
                for bg_name in ["background_enhanced.png", "background_generated.png"]:
                    bg_path = os.path.join(job_dir, bg_name)
                    if os.path.exists(bg_path):
                        background_image_path = bg_path
                        logger.info(f"[ORDER {job_id}] ⏭️ Skipping Step 2 - Using existing background: {bg_name}")
                        break

            # ============================================================
            # STEP 3: Skip BG Removal (GPT already provides transparent PNGs)
            # ============================================================
            if from_step <= 3:
                logger.info(f"[ORDER {job_id}] Step 3: Skipping BG removal - GPT images already have transparent backgrounds")

                # Use GPT transparent PNGs directly as nobg images
                figure_img["original_path"] = figure_img["file_path"]
                figure_img["nobg_path"] = figure_img["file_path"]

                for acc_img in accessory_imgs:
                    acc_img["original_path"] = acc_img["file_path"]
                    acc_img["nobg_path"] = acc_img["file_path"]

                # Save state after step 3
                self._save_step_state(job_dir, 3, {
                    "figure_img": figure_img,
                    "accessory_imgs": accessory_imgs
                })
            else:
                # Load existing images
                logger.info(f"[ORDER {job_id}] ⏭️ Skipping Step 3 - Loading existing images")
                figure_img, accessory_imgs = self._find_generated_images(job_dir)
                if not figure_img:
                    raise Exception("No existing figure image found for retry")

            # ============================================================
            # STEP 4: Generate depth maps with Sculptok
            # ============================================================
            if from_step <= 4:
                logger.info(f"[ORDER {job_id}] Step 4: 3D Generation + Depth Maps")

                # 4a: Generate figure GLB via fal.ai
                figure_glb_path = os.path.join(job_dir, "base_character_3d.glb")
                if os.path.exists(figure_glb_path):
                    logger.info(f"[ORDER {job_id}] [SKIP] Figure GLB already exists at {figure_glb_path}")
                elif self._fal_client:
                    figure_img_path = figure_img.get("original_path") or figure_img.get("file_path")
                    logger.info(f"[ORDER {job_id}] Generating figure 3D via fal.ai from {figure_img_path}")
                    fal_result = await self._fal_client.generate_3d_from_local_image(
                        image_path=figure_img_path,
                        output_path=figure_glb_path,
                    )
                    if fal_result.get("success"):
                        logger.info(f"[ORDER {job_id}] Figure GLB generated: {figure_glb_path}")
                    else:
                        raise Exception(f"fal.ai figure 3D generation failed: {fal_result.get('error')}")
                else:
                    raise Exception("No fal.ai client configured and no existing figure GLB found")

                # 4b: Accessory depth maps via Sculptok
                logger.info(f"[ORDER {job_id}] Generating accessory depth maps via Sculptok")

                # Accessory depth maps (skip_bg_removal=True since we already did it)
                for i, acc_img in enumerate(accessory_imgs):
                    acc_name = f"accessory_{i+1}"
                    # Use nobg images for depth maps
                    acc_depth_img = acc_img.get("nobg_path") or acc_img.get("file_path")

                    acc_depth_result = await self._sculptok_client.process_image_to_depth_map(
                        image_path=acc_depth_img,
                        output_dir=job_dir,
                        image_name=acc_name,
                        skip_bg_removal=True,  # Already removed background
                        style="pro",
                        version="1.5",
                        draw_hd="4k",
                        ext_info="16bit"
                    )

                    if acc_depth_result.get("success"):
                        depth_maps[acc_name] = acc_depth_result.get("outputs", {}).get("depth_image")
                        logger.info(f"[ORDER {job_id}] {acc_name} depth map generated")
                    else:
                        errors.append(f"{acc_name} depth map failed")

                # Save state after step 4
                self._save_step_state(job_dir, 4, {"depth_maps": depth_maps, "figure_glb": figure_glb_path})
            else:
                # Load existing assets
                logger.info(f"[ORDER {job_id}] ⏭️ Skipping Step 4 - Loading existing assets")
                figure_glb_path = os.path.join(job_dir, "base_character_3d.glb")
                if not os.path.exists(figure_glb_path):
                    logger.warning(f"[ORDER {job_id}] ⚠️ Figure GLB not found at {figure_glb_path}")
                depth_maps = self._find_depth_maps(job_dir)
                logger.info(f"[ORDER {job_id}] Found {len(depth_maps)} accessory depth maps")

            # ============================================================
            # STEP 5: Blender 2.5D card (depth map displacement)
            # ============================================================
            output_dir = os.path.join(job_dir, "final_output")
            os.makedirs(output_dir, exist_ok=True)

            if from_step <= 5:
                logger.info(f"[ORDER {job_id}] Step 5: Blender 2.5D Processing")

                blender_script = os.path.join(os.path.dirname(__file__), "blender_starter_pack.py")

                # Build Blender command
                blender_cmd = [
                    "blender", "--background", "--python", blender_script, "--"
                ]

                # Figure is handled as full 3D by PrintMaker (via fal.ai GLB), not as 2.5D depth relief.
                # Do NOT pass --figure_img or --figure_depth to Blender — the figure slot stays flat.

                # Add accessories
                for i, acc_img in enumerate(accessory_imgs):
                    acc_num = i + 1
                    acc_name = f"accessory_{acc_num}"
                    if acc_name in depth_maps and acc_num <= 3:
                        acc_texture_img = acc_img.get("original_path") or acc_img.get("file_path")
                        blender_cmd.extend([
                            f"--acc{acc_num}_img", acc_texture_img,
                            f"--acc{acc_num}_depth", depth_maps[acc_name]
                        ])

                blender_cmd.extend([
                    "--title", order_data.get("title", ""),
                    "--subtitle", order_data.get("subtitle", ""),
                    "--text_color", order_data.get("text_color", "red"),
                    "--background_type", background_type,
                    "--background_color", background_color,
                ])

                if background_image_path:
                    blender_cmd.extend(["--background_image", background_image_path])

                blender_cmd.extend([
                    "--output_dir", output_dir,
                    "--job_id", job_id
                ])

                logger.info(f"[ORDER {job_id}] Running Blender 2.5D...")
                blender_proc = subprocess.Popen(
                    blender_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )

                def _stream_blender_stderr(proc, jid):
                    for line in proc.stderr:
                        logger.warning(f"[ORDER {jid}] [Blender:err] {line.rstrip()}")

                blender_stderr_thread = threading.Thread(target=_stream_blender_stderr, args=(blender_proc, job_id), daemon=True)
                blender_stderr_thread.start()

                for line in blender_proc.stdout:
                    logger.info(f"[ORDER {job_id}] [Blender] {line.rstrip()}")

                blender_proc.wait(timeout=600)
                blender_stderr_thread.join(timeout=5)

                if blender_proc.returncode == 0:
                    stl_25d = os.path.join(output_dir, f"{job_id}.stl")
                    texture_25d = os.path.join(output_dir, f"{job_id}_texture.png")
                    blend_25d = os.path.join(output_dir, f"{job_id}.blend")

                    if os.path.exists(stl_25d):
                        outputs["stl_25d"] = stl_25d
                        outputs["stl_25d_url"] = f"/storage/test_starter_pack/{job_id}/final_output/{job_id}.stl"
                    if os.path.exists(texture_25d):
                        outputs["texture"] = texture_25d
                        outputs["texture_url"] = f"/storage/test_starter_pack/{job_id}/final_output/{job_id}_texture.png"
                    if os.path.exists(blend_25d):
                        outputs["blend_25d"] = blend_25d
                        outputs["blend_25d_url"] = f"/storage/test_starter_pack/{job_id}/final_output/{job_id}.blend"

                    logger.info(f"[ORDER {job_id}] Blender 2.5D completed successfully")
                    self._save_step_state(job_dir, 5, {"stl_25d": str(stl_25d), "texture": str(texture_25d)})
                else:
                    raise Exception(f"Blender 2.5D failed with return code {blender_proc.returncode}")
            else:
                logger.info(f"[ORDER {job_id}] ⏭️ Skipping Step 5 - Loading existing Blender outputs")
                stl_25d = os.path.join(output_dir, f"{job_id}.stl")
                texture_25d = os.path.join(output_dir, f"{job_id}_texture.png")

                if os.path.exists(stl_25d):
                    outputs["stl_25d"] = stl_25d
                    outputs["stl_25d_url"] = f"/storage/test_starter_pack/{job_id}/final_output/{job_id}.stl"
                if os.path.exists(texture_25d):
                    outputs["texture"] = texture_25d
                    outputs["texture_url"] = f"/storage/test_starter_pack/{job_id}/final_output/{job_id}_texture.png"

            # ============================================================
            # STEP 6: PrintMaker (figure STL, jigs, printing assets)
            # ============================================================
            if from_step <= 6:
                logger.info(f"[ORDER {job_id}] Step 6: PrintMaker Processing")

                # Set up PrintMaker job directories
                pm_workdir = settings.PRINTMAKER_WORKDIR
                pm_job_dir = os.path.join(pm_workdir, "jobs", job_id)
                pm_in_dir = os.path.join(pm_job_dir, "in")
                pm_out_dir = os.path.join(pm_job_dir, "out")
                os.makedirs(pm_in_dir, exist_ok=True)
                os.makedirs(pm_out_dir, exist_ok=True)

                # Copy figure GLB to PrintMaker input
                figure_glb_path = os.path.join(job_dir, "base_character_3d.glb")
                if not os.path.exists(figure_glb_path):
                    raise Exception(f"Figure GLB not found at {figure_glb_path}")
                pm_figure_path = os.path.join(pm_in_dir, "base_character_3d.glb")
                shutil.copy2(figure_glb_path, pm_figure_path)
                logger.info(f"[ORDER {job_id}] Copied figure GLB to {pm_figure_path}")

                # Run PrintMaker executable directly
                pm_cmd = [
                    settings.PRINTMAKER_EXECUTABLE,
                    "--job", job_id,
                    "--workdir", pm_workdir,
                    "--dpi", str(settings.PRINTMAKER_DPI),
                    "--title", order_data.get("title", "Starter Pack"),
                    "--subtitle", order_data.get("subtitle", ""),
                ]

                logger.info(f"[ORDER {job_id}] Running PrintMaker: {' '.join(pm_cmd)}")

                # Stream stdout/stderr live
                pm_proc = subprocess.Popen(
                    pm_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=pm_workdir,
                )

                def _stream_pm_stderr(proc, jid):
                    for line in proc.stderr:
                        logger.warning(f"[ORDER {jid}] [PrintMaker:err] {line.rstrip()}")

                pm_stderr_thread = threading.Thread(target=_stream_pm_stderr, args=(pm_proc, job_id), daemon=True)
                pm_stderr_thread.start()

                for line in pm_proc.stdout:
                    logger.info(f"[ORDER {job_id}] [PrintMaker] {line.rstrip()}")

                pm_proc.wait(timeout=settings.PRINTMAKER_TIMEOUT)
                pm_stderr_thread.join(timeout=5)

                if pm_proc.returncode == 0:
                    logger.info(f"[ORDER {job_id}] PrintMaker completed successfully")

                    # Copy PrintMaker outputs to final_output (skip directories)
                    for f in os.listdir(pm_out_dir):
                        src = os.path.join(pm_out_dir, f)
                        if not os.path.isfile(src):
                            continue
                        dst = os.path.join(output_dir, f)
                        shutil.copy2(src, dst)

                    # Map key outputs
                    card_stl = os.path.join(output_dir, "card_model.stl")
                    card_blend = os.path.join(output_dir, "card_model.blend")
                    figure_stl = os.path.join(output_dir, "card_figure.stl")
                    card_main = os.path.join(output_dir, "card_main.png")
                    card_ref = os.path.join(output_dir, "card_reference.png")

                    if os.path.exists(card_stl):
                        outputs["stl"] = card_stl
                        outputs["stl_url"] = f"/storage/test_starter_pack/{job_id}/final_output/card_model.stl"
                    if os.path.exists(figure_stl):
                        outputs["figure_stl"] = figure_stl
                        outputs["figure_stl_url"] = f"/storage/test_starter_pack/{job_id}/final_output/card_figure.stl"
                    if os.path.exists(card_blend):
                        outputs["blend"] = card_blend
                        outputs["blend_url"] = f"/storage/test_starter_pack/{job_id}/final_output/card_model.blend"
                    if os.path.exists(card_main):
                        outputs["texture"] = card_main
                        outputs["texture_url"] = f"/storage/test_starter_pack/{job_id}/final_output/card_main.png"
                    if os.path.exists(card_ref):
                        outputs["reference"] = card_ref
                        outputs["reference_url"] = f"/storage/test_starter_pack/{job_id}/final_output/card_reference.png"

                    # Collect jig outputs
                    for jig_file in os.listdir(output_dir):
                        if jig_file.startswith("card_jig_") and jig_file.endswith(".stl"):
                            side = jig_file.replace("card_jig_", "").replace(".stl", "")
                            outputs[f"jig_{side}_stl"] = os.path.join(output_dir, jig_file)
                            outputs[f"jig_{side}_stl_url"] = f"/storage/test_starter_pack/{job_id}/final_output/{jig_file}"
                else:
                    logger.error(f"[ORDER {job_id}] PrintMaker failed with return code {pm_proc.returncode}")
                    raise Exception(f"PrintMaker failed with return code {pm_proc.returncode}")
            else:
                logger.info(f"[ORDER {job_id}] ⏭️ Skipping Step 6 - Loading existing PrintMaker outputs")
                card_stl = os.path.join(output_dir, "card_model.stl")
                card_main = os.path.join(output_dir, "card_main.png")

                if os.path.exists(card_stl):
                    outputs["stl"] = card_stl
                    outputs["stl_url"] = f"/storage/test_starter_pack/{job_id}/final_output/card_model.stl"
                if os.path.exists(card_main):
                    outputs["texture"] = card_main
                    outputs["texture_url"] = f"/storage/test_starter_pack/{job_id}/final_output/card_main.png"

            # ============================================================
            # STEP 7: Generate stickers (front and back)
            # ============================================================
            if outputs.get("texture"):
                logger.info(f"[ORDER {job_id}] Step 7: Sticker Generation")

                from services.sticker_generator import generate_stickers

                try:
                    stickers = generate_stickers(
                        texture_path=outputs["texture"],
                        output_dir=output_dir,
                        job_id=job_id,
                        title=order_data.get("title", ""),
                        subtitle=order_data.get("subtitle", "")
                    )

                    if stickers.get("front"):
                        outputs["sticker_front"] = stickers["front"]
                        outputs["sticker_front_url"] = f"/storage/test_starter_pack/{job_id}/final_output/{job_id}_sticker_front.png"
                    if stickers.get("back"):
                        outputs["sticker_back"] = stickers["back"]
                        outputs["sticker_back_url"] = f"/storage/test_starter_pack/{job_id}/final_output/{job_id}_sticker_back.png"

                    logger.info(f"[ORDER {job_id}] Stickers generated successfully")
                except Exception as sticker_error:
                    logger.warning(f"[ORDER {job_id}] Sticker generation failed: {sticker_error}")
                    errors.append(f"Sticker generation failed: {sticker_error}")

            # ============================================================
            # FINAL: Update database with results
            # ============================================================
            success = outputs.get("stl") is not None and outputs.get("texture") is not None

            if supabase.is_connected():
                if success:
                    await supabase.update_order_outputs(job_id, {
                        "stl_path": outputs.get("stl"),
                        "texture_path": outputs.get("texture"),
                        "blend_path": outputs.get("blend"),
                        "stl_url": outputs.get("stl_url"),
                        "texture_url": outputs.get("texture_url"),
                        "blend_url": outputs.get("blend_url"),
                        "sticker_front_path": outputs.get("sticker_front"),
                        "sticker_back_path": outputs.get("sticker_back"),
                        "sticker_front_url": outputs.get("sticker_front_url"),
                        "sticker_back_url": outputs.get("sticker_back_url")
                    })
                    logger.info(f"✅ [ORDER {job_id}] Completed successfully")
                else:
                    error_msg = "; ".join(errors) if errors else "Unknown error"
                    await supabase.update_order_status(job_id, "failed", error_msg)
                    logger.error(f"❌ [ORDER {job_id}] Failed: {error_msg}")

        except Exception as e:
            logger.error(f"❌ [ORDER {job_id}] Exception: {e}")
            if supabase.is_connected():
                await supabase.update_order_status(job_id, "failed", str(e))
            raise


# Singleton instance
_order_processor: Optional[OrderProcessor] = None


def get_order_processor() -> OrderProcessor:
    """Get or create order processor singleton"""
    global _order_processor
    if _order_processor is None:
        _order_processor = OrderProcessor()
    return _order_processor
