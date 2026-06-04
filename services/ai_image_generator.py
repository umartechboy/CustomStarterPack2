import base64
import os
import aiofiles
import requests as http_requests
from openai import OpenAI
from typing import List, Dict, Optional
from datetime import datetime
from config.settings import settings

class AIImageGenerator:
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.OPENAI_MODEL
        self.size = settings.IMAGE_SIZE
        self.quality = settings.IMAGE_QUALITY
        self.transparent_background = settings.TRANSPARENT_BACKGROUND

    async def generate_action_figures(self, job_id: str, user_image_path: str, accessories: List[str]) -> List[Dict]:

        """Generate 4 action figure images: 1 base (from user image) + 3 accessories (standalone)"""
        results = []

        # Create output directory for this job
        output_dir = os.path.join(settings.GENERATED_PATH, job_id)
        os.makedirs(output_dir, exist_ok=True)

        print(f"🎨 Generating action figures")

        # 1. Generate base action figure from user image using IMAGE EDIT API
        base_prompt = self._build_character_prompt()
        base_result = await self._generate_from_user_image(
            job_id=job_id,
            user_image_path=user_image_path,
            prompt=base_prompt,
            image_type="base_character",
            output_dir=output_dir
        )
        if base_result:
            results.append(base_result)

        # 2. Generate standalone accessory images using IMAGE GENERATION API
        # FIX 2026-05-23: empty/placeholder accessories SKIPPEN — bei leer wird sonst random Objekt generiert
        EMPTY_VALUES = {"", "-", "—", "–", "none", "keine", "kein"}
        for i, accessory in enumerate(accessories, 1):
            if not accessory or accessory.strip().lower() in EMPTY_VALUES:
                print(f"[ai_image_gen] skipping accessory_{i} (empty/placeholder: '{accessory_en}')")
                continue
            accessory_prompt = self._build_accessory_prompt(accessory)
            accessory_result = await self._generate_accessory_image(
                job_id=job_id,
                prompt=accessory_prompt,
                image_type=f"accessory_{i}",
                output_dir=output_dir,
                accessory_name=accessory
            )
            if accessory_result:
                results.append(accessory_result)

        return results

    async def ensure_transparent_background(self, image_path: str) -> Dict:
        """Ensure image has transparent background using ComfyUI background removal"""
        try:
            print(f"🖼️ Processing background removal for: {image_path}")

            # Check if file exists
            if not os.path.exists(image_path):
                return {"success": False, "error": "Image file not found"}

            # ALWAYS use ComfyUI for better background removal
            # Even if DALL-E claims transparent background, ComfyUI does it better for 3D
            from services.background_remover import ComfyUIBackgroundRemover

            bg_remover = ComfyUIBackgroundRemover()

            # Create processed file path
            base_name = os.path.splitext(image_path)[0]
            processed_path = f"{base_name}_transparent.png"

            # Process with ComfyUI
            success = await bg_remover.remove_background_single(image_path, processed_path)

            if success:
                print(f"✅ ComfyUI background removed and saved to: {processed_path}")
                return {
                    "success": True,
                    "file_path": processed_path,
                    "original_path": image_path,
                    "method": "comfyui_rmbg",
                    "processed_at": datetime.now().isoformat()
                }
            else:
                # Fallback to original if ComfyUI fails
                print(f"⚠️ ComfyUI failed, keeping original: {image_path}")
                return {
                    "success": True,
                    "file_path": image_path,
                    "method": "original_fallback",
                    "processed_at": datetime.now().isoformat()
                }

        except Exception as e:
            print(f"❌ Background removal failed for {image_path}: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "original_path": image_path,
                "processed_at": datetime.now().isoformat()
            }

    def _build_character_prompt(self) -> str:
        """Build character prompt for hyperrealistic UV-print quality figure.

        Optimized for:
        - Exact facial likeness preservation
        - Hyperrealistic skin textures and details
        - Vibrant, accurate colors for UV printing
        - Clean edges for 2.5D lithophane conversion
        """
        return """Create a HYPERREALISTIC full-body portrait of this exact person for UV printing:

CAMERA ANGLE (CRITICAL - FLAT LAY VIEW):
- TOP-DOWN / FLAT LAY perspective - as if the figure is lying flat and photographed from directly above
- NO perspective distortion - orthographic style view
- Figure should appear flat like a paper doll or action figure in packaging
- This prevents weird 3D angles and ensures clean 2.5D conversion

FACE & SKIN (CRITICAL - HIGHEST PRIORITY):
- EXACT facial likeness - preserve every facial feature precisely as in the input photo
- Hyperrealistic skin texture with visible pores, subtle wrinkles, natural skin imperfections
- Accurate skin tone matching the original photo exactly
- Natural skin subsurface scattering and realistic flesh tones
- Detailed eyes with realistic iris patterns, reflections, and natural eye moisture
- Natural hair texture with individual strand details, accurate hair color
- Realistic lips with natural color and subtle texture
- Face forward, neutral expression

POSE - EXTREMELY IMPORTANT - MUST FOLLOW EXACTLY:
- A-POSE ONLY: Arms STRAIGHT down, touching the sides of the thighs
- Arms must be FULLY EXTENDED downward, NOT bent at elbows
- Hands open with fingers pointing DOWN toward the ground, palms facing inward toward thighs
- NO fists, NO gloves visible on hands, NO bent arms
- Arms should form a straight vertical line from shoulder to fingertips
- Standing like a wooden mannequin or store display dummy
- Legs straight, feet together or slightly apart
- This is a NEUTRAL REFERENCE POSE for 3D scanning - absolutely NO action poses

FULL BODY REQUIREMENTS:
- Complete full-body view from head to feet - nothing cropped
- Natural human proportions (not stylized or cartoonish)
- Feet flat on ground, legs straight

CLOTHING & FABRIC:
- Hyperrealistic fabric textures - visible weave, stitching, material properties
- Accurate colors matching any visible clothing from original photo
- Natural fabric folds and draping
- Realistic material properties (cotton, denim, leather, etc.)
- Clean, unbranded clothing - no text or logos

LIGHTING & COLOR (CRITICAL FOR UV PRINTING):
- Bright, even front lighting - no harsh shadows
- Vibrant, saturated colors optimized for print reproduction
- High color accuracy - colors must print true to screen
- Soft diffused lighting that reveals all details
- No dark shadows that would print as black areas
- Clean highlight areas without blown-out whites

COMPOSITION:
- Centered in frame with small margin on all sides
- Full body visible with no cropping
- Pure transparent background (PNG with alpha)
- Sharp, clean edges around the figure
- High resolution details throughout

OUTPUT QUALITY:
- Photorealistic quality - should look like a professional photograph
- Maximum detail and sharpness
- Print-ready color profile
- Clean silhouette for easy background separation

CRITICAL: This is for UV PRINTING - colors must be vibrant and accurate. Face must be IDENTICAL to input photo. Hyperrealistic quality, not stylized or cartoon."""

    # DE→EN translations to prevent GPT from interpreting German words as labels/prints on objects.
    # Covers most common gift/object words customers type. Missing → falls through unchanged.
    _DE_TO_EN = {
        'hund': 'dog', 'katze': 'cat', 'pferd': 'horse', 'vogel': 'bird',
        'fisch': 'fish', 'hase': 'rabbit', 'kaninchen': 'rabbit', 'maus': 'mouse',
        'fussball': 'soccer ball', 'fußball': 'soccer ball', 'ball': 'ball',
        'basketball': 'basketball', 'tennisball': 'tennis ball',
        'gitarre': 'electric guitar', 'klavier': 'piano', 'trompete': 'trumpet',
        'kopfhörer': 'headphones', 'kopfhoerer': 'headphones',
        'kamera': 'professional camera', 'fotoapparat': 'professional camera',
        'auto': 'car', 'motorrad': 'motorcycle', 'fahrrad': 'bicycle', 'flugzeug': 'airplane',
        'buch': 'book', 'rucksack': 'backpack', 'tasche': 'handbag', 'koffer': 'suitcase',
        'krone': 'royal crown', 'ring': 'diamond ring', 'kette': 'gold necklace',
        'uhr': 'wristwatch', 'sonnenbrille': 'sunglasses', 'brille': 'eyeglasses',
        'schuhe': 'sneakers', 'schuh': 'sneaker', 'mütze': 'baseball cap', 'muetze': 'baseball cap',
        'hut': 'fedora hat', 'helm': 'racing helmet',
        'blume': 'rose flower', 'rose': 'rose flower', 'baum': 'tree',
        'apfel': 'apple', 'banane': 'banana', 'pizza': 'pizza slice',
        'kaffee': 'coffee cup', 'tee': 'tea cup', 'bier': 'beer mug', 'wein': 'wine glass',
        'krügerl': 'beer mug', 'kruegerl': 'beer mug', 'cocktail': 'cocktail glass',
        'schnitzel': 'wiener schnitzel', 'burger': 'hamburger',
        'geld': 'stack of dollar bills', 'goldbarren': 'gold bar',
        'laptop': 'silver laptop', 'handy': 'smartphone', 'smartphone': 'smartphone',
        'controller': 'gaming controller', 'konsole': 'gaming console',
        'mikrofon': 'studio microphone', 'lautsprecher': 'speaker',
        'pokal': 'gold trophy', 'medaille': 'gold medal',
        'herz': 'red heart', 'stern': 'gold star',
        'gewicht': 'dumbbell', 'hantel': 'dumbbell', 'kettlebell': 'kettlebell',
        'yoga': 'yoga mat', 'matte': 'yoga mat',
        'pfote': 'paw print', 'knochen': 'dog bone',
        'reisepass': 'passport', 'führerschein': 'driver license',
    }

    def _translate_accessory(self, accessory: str) -> str:
        """Map German object word to English noun phrase for accurate GPT-Image generation."""
        key = (accessory or '').strip().lower()
        return self._DE_TO_EN.get(key, accessory)

    def _build_accessory_prompt(self, accessory: str) -> str:
        """Build hyperrealistic accessory prompt optimized for UV printing and 3D conversion.

        Optimized for:
        - Photorealistic materials and textures
        - Vibrant, accurate colors for UV printing
        - Clean edges for 2.5D lithophane conversion
        - Proper lighting for depth map generation
        """
        accessory_en = self._translate_accessory(accessory)
        return f"""Create a HYPERREALISTIC {accessory_en} for UV printing:

INTERPRETATION NOTE:
- '{accessory_en}' refers to the literal physical object/animal/item itself
- Do NOT add text, labels, prints, brand logos, or written words on or near the object
- The object is the subject — render it as a photograph of the real thing, not a labeled product

ACCESSORY REQUIREMENTS:
- ONLY ONE single {accessory_en} in the image - no duplicates, no multiple items
- PHOTOREALISTIC quality - should look like a professional product photograph
- Hyperrealistic materials with visible surface details, textures, and imperfections
- Real-world accurate proportions and scale
- Premium quality finish with realistic material properties

MATERIAL & TEXTURE (CRITICAL FOR UV PRINTING):
- Hyperrealistic surface textures - visible grain, scratches, wear patterns where appropriate
- Accurate material properties (metal reflections, fabric weave, leather grain, etc.)
- Natural material imperfections that add realism
- True-to-life colors that will print accurately
- Realistic subsurface scattering for translucent materials
- Visible fine details like stitching, seams, engraving, embossing

CAMERA ANGLE (CRITICAL FOR 3D CONVERSION - MUST FOLLOW EXACTLY):
- FLAT LAY / TOP-DOWN view - camera looking STRAIGHT DOWN at the object from directly above
- Object lying completely FLAT on surface, photographed from 90 degrees above
- NO perspective, NO 3D angles, NO tilting - pure orthographic top-down view
- Like photographing an object placed flat on a table, camera pointing straight down
- Shows the full shape and outline of the object clearly as a 2D silhouette
- Front face of the object should be visible and facing up toward camera
- This prevents weird 3D angles and ensures clean 2.5D lithophane conversion

LIGHTING (CRITICAL FOR UV PRINTING):
- Bright, even front lighting - no harsh shadows
- Soft, diffused light from all directions
- NO cast shadows on or around the object
- NO dark ambient occlusion shadows
- Colors must be vibrant and saturated for print reproduction
- No blown-out highlights or crushed blacks
- Pure transparent background (PNG with alpha)

COMPOSITION (CRITICAL):
- ONE accessory only - single item, not a set or collection
- Centered in the middle of the image
- Complete item visible with no cropping at all
- Isolated item on pure transparent background
- No other objects, props, or accessories in the scene
- Sharp, clean edges around the object
- Object should fill about 70% of the frame
- High resolution details throughout

OUTPUT QUALITY:
- Photorealistic quality - should look like a real photograph
- Maximum detail and sharpness
- Print-ready vibrant colors
- Clean silhouette for easy background separation

CRITICAL: Generate exactly ONE hyperrealistic {accessory_en} - single item only, flat lay angle from above, NO SHADOWS, centered, complete, photorealistic quality for UV printing. The object itself is what's rendered, NOT a label or print of the word."""

    async def _generate_from_user_image(self, job_id: str, user_image_path: str, prompt: str, image_type: str,
                                       output_dir: str) -> Dict:
        """Generate action figure from user image using OpenAI Image Edit API with gpt-image-1.5"""
        try:
            import time
            print(f"🎭 Generating {image_type} from user image for job {job_id}")
            print(f"📐 Using gpt-image-1.5 with 1024x1536 dimensions")

            # Retry up to 3 times for transient 500 errors
            max_retries = 3
            resp = None
            for attempt in range(1, max_retries + 1):
                # Use raw multipart form request — the Python SDK sends JSON which
                # the /v1/images/edits endpoint rejects for gpt-image-1.5
                with open(user_image_path, 'rb') as image_file:
                    resp = http_requests.post(
                        'https://api.openai.com/v1/images/edits',
                        headers={'Authorization': f'Bearer {settings.OPENAI_API_KEY}'},
                        files={'image': (os.path.basename(user_image_path), image_file, 'image/png')},
                        data={
                            'model': 'gpt-image-1.5',
                            'prompt': prompt,
                            'size': '1024x1536',
                            'quality': 'high',
                            'input_fidelity': 'high',
                            'output_format': 'png',
                            'background': 'transparent' if self.transparent_background else 'auto',
                            'moderation': 'low',
                            'n': '1',
                        },
                        timeout=300
                    )

                if resp.status_code == 200:
                    break
                elif resp.status_code >= 500 and attempt < max_retries:
                    wait = attempt * 10
                    print(f"⚠️ OpenAI 500 error (attempt {attempt}/{max_retries}), retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    raise Exception(f"Error code: {resp.status_code} - {resp.json()}")

            response_data = resp.json()
            image_base64 = response_data['data'][0]['b64_json']
            image_bytes = base64.b64decode(image_base64)

            # Save the image
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{image_type}_{timestamp}.png"
            file_path = os.path.join(output_dir, filename)

            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(image_bytes)

            print(f"✅ Saved {image_type} to {file_path}")

            return {
                "type": image_type,
                "method": "image_edit",
                "model_used": "gpt-image-1.5",
                "prompt": prompt,
                "size": "1024x1536",
                "quality": "high",
                "input_fidelity": "high",
                "transparent_background": self.transparent_background,
                "file_path": file_path,
                "filename": filename,
                "url": f"/storage/generated/{job_id}/{filename}",
                "generated_at": datetime.now().isoformat(),
                "tokens_used": response_data.get('usage', {}).get('total_tokens')
            }

        except Exception as e:
            print(f"⚠️ OpenAI direct failed for {image_type}: {str(e)}")
            print(f"🔄 Falling back to fal.ai gpt-image-1.5/edit...")

            try:
                return await self._generate_from_user_image_fal(
                    job_id=job_id,
                    user_image_path=user_image_path,
                    prompt=prompt,
                    image_type=image_type,
                    output_dir=output_dir
                )
            except Exception as fal_e:
                print(f"❌ fal.ai fallback also failed for {image_type}: {str(fal_e)}")
                return None

    async def _generate_from_user_image_fal(self, job_id: str, user_image_path: str, prompt: str,
                                            image_type: str, output_dir: str) -> Dict:
        """Fallback: generate action figure via fal.ai gpt-image-1.5/edit endpoint"""
        import fal_client
        os.environ['FAL_KEY'] = settings.FAL_API_KEY

        # Upload image to fal.ai first
        with open(user_image_path, 'rb') as f:
            image_url = fal_client.upload(f.read(), content_type='image/png')
        print(f"📤 Uploaded image to fal.ai: {image_url}")

        result = fal_client.subscribe(
            "fal-ai/gpt-image-1.5/edit",
            arguments={
                "prompt": prompt,
                "image_urls": [image_url],
                "image_size": "1024x1536",
                "quality": "high",
                "input_fidelity": "high",
                "output_format": "png",
                "background": "transparent" if self.transparent_background else "auto",
                "num_images": 1,
            },
        )

        if not result or not result.get('images'):
            raise Exception("fal.ai returned no images")

        # Download the generated image
        img_url = result['images'][0]['url']
        print(f"📥 Downloading fal.ai result: {img_url}")
        img_resp = http_requests.get(img_url, timeout=60)
        if img_resp.status_code != 200:
            raise Exception(f"Failed to download fal.ai image: HTTP {img_resp.status_code}")

        image_bytes = img_resp.content

        # Save the image
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{image_type}_{timestamp}.png"
        file_path = os.path.join(output_dir, filename)

        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(image_bytes)

        print(f"✅ Saved {image_type} via fal.ai to {file_path}")

        return {
            "type": image_type,
            "method": "fal_image_edit",
            "model_used": "gpt-image-1.5-fal",
            "prompt": prompt,
            "size": "1024x1536",
            "quality": "high",
            "input_fidelity": "high",
            "transparent_background": self.transparent_background,
            "file_path": file_path,
            "filename": filename,
            "url": f"/storage/generated/{job_id}/{filename}",
            "generated_at": datetime.now().isoformat(),
            "tokens_used": None
        }


    async def _generate_accessory_image(self, job_id: str, prompt: str, image_type: str, output_dir: str, accessory_name: str) -> Dict:
        """Generate standalone accessory image using OpenAI Image Generation API with gpt-image-1"""
        try:
            print(f"🎭 Generating {image_type} accessory for job {job_id}")
            print(f"📐 Using gpt-image-1.5 with 1024x1536 dimensions")

            response = self.client.images.generate(
                model="gpt-image-1.5",
                prompt=prompt,
                size="1024x1536",
                background="transparent" if self.transparent_background else "auto",
                quality="high",
                output_format="png",
                n=1
            )

            # Handle base64 response (gpt-image-1 always returns b64_json)
            image_data = response.data[0]
            image_bytes = base64.b64decode(image_data.b64_json)

            # Save the image
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{image_type}_{timestamp}.png"
            file_path = os.path.join(output_dir, filename)

            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(image_bytes)

            print(f"✅ Saved {image_type} to {file_path}")

            return {
                "type": image_type,
                "method": "image_generation",
                "model_used": "gpt-image-1.5",
                "prompt": prompt,
                "size": "1024x1536",
                "quality": "high",
                "transparent_background": self.transparent_background,
                "accessory": accessory_name,
                "file_path": file_path,
                "filename": filename,
                "url": f"/storage/generated/{job_id}/{filename}",
                "generated_at": datetime.now().isoformat(),
                "tokens_used": response.usage.total_tokens if hasattr(response, 'usage') else None
            }

        except Exception as e:
            print(f"⚠️ OpenAI direct failed for {image_type}: {str(e)}")
            print(f"🔄 Falling back to fal.ai for accessory {image_type}...")
            try:
                import fal_client
                os.environ['FAL_KEY'] = settings.FAL_API_KEY
                result = fal_client.subscribe(
                    "fal-ai/gpt-image-1.5",
                    arguments={
                        "prompt": prompt,
                        "image_size": "1024x1536",
                        "quality": "high",
                        "output_format": "png",
                        "background": "transparent" if self.transparent_background else "auto",
                        "num_images": 1,
                    },
                )
                if not result or not result.get('images'):
                    raise Exception("fal.ai returned no images")
                img_url = result['images'][0]['url']
                print(f"📥 Downloading fal.ai accessory result: {img_url}")
                img_resp = http_requests.get(img_url, timeout=60)
                if img_resp.status_code != 200:
                    raise Exception(f"Failed to download fal.ai image: HTTP {img_resp.status_code}")
                image_bytes = img_resp.content
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"{image_type}_{timestamp}.png"
                file_path = os.path.join(output_dir, filename)
                async with aiofiles.open(file_path, 'wb') as f:
                    await f.write(image_bytes)
                print(f"✅ Saved {image_type} via fal.ai to {file_path}")
                return {
                    "type": image_type,
                    "method": "fal_image_generation",
                    "model_used": "gpt-image-1.5-fal",
                    "prompt": prompt,
                    "size": "1024x1536",
                    "quality": "high",
                    "transparent_background": self.transparent_background,
                    "accessory": accessory_name,
                    "file_path": file_path,
                    "filename": filename,
                    "url": f"/storage/generated/{job_id}/{filename}",
                    "generated_at": datetime.now().isoformat(),
                    "tokens_used": None
                }
            except Exception as fal_e:
                print(f"❌ fal.ai fallback also failed for {image_type}: {str(fal_e)}")
                return None
